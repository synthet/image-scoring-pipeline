#!/usr/bin/env python3
"""Benchmark Jev-ready evidence against historical picks on real data.

This experiment is deliberately read-only. It measures how much signal is
available before Jev is called:

* existing technical/aesthetic scores;
* exact caption diversity inside mixed pick/reject stacks;
* per-image novelty in the registered embedding spaces.

The output contains aggregate metrics only. It never writes to PostgreSQL and
never includes file paths, thumbnails, image bytes, or per-image rows.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import dotenv_values
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from modules import config, db


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "reports" / "typesafe-culling-real-data" / "summary.json"

SPACE_TABLES = {
    "mobilenet_v2_imagenet_gap": "image_embeddings",
    "clip_vit_b32_image": "image_embeddings_512",
    "bioclip_2_image": "image_embeddings_768",
    "openclip_l14_laion2b_image": "image_embeddings_768",
}

SCORE_FEATURES = ["score_general", "score_technical", "score_aesthetic"]
CAPTION_FEATURES = ["caption_uniqueness", "caption_missing"]
MODEL_SCORE_NAMES = [
    "spaq",
    "ava",
    "liqe",
    "topiq",
    "arniqa",
    "clip_quality_v0",
    "koniq",
    "paq2piq",
]


def _selected_stacks_sql(max_stack_size: int, limit_stacks: int) -> str:
    limit = f"LIMIT {int(limit_stacks)}" if limit_stacks > 0 else ""
    return f"""
        SELECT i.stack_id
        FROM images i
        WHERE i.stack_id IS NOT NULL
        GROUP BY i.stack_id
        HAVING COUNT(*) BETWEEN 2 AND {int(max_stack_size)}
           AND COUNT(*) FILTER (WHERE i.pick_status = 1) > 0
           AND COUNT(*) FILTER (WHERE i.pick_status = -1) > 0
        ORDER BY i.stack_id
        {limit}
    """


def _load_base_rows(max_stack_size: int, limit_stacks: int) -> list[dict[str, Any]]:
    stacks_sql = _selected_stacks_sql(max_stack_size, limit_stacks)
    sql = f"""
        WITH selected_stacks AS ({stacks_sql}),
        candidates AS (
            SELECT
                i.id AS image_id,
                i.stack_id,
                i.folder_id,
                i.pick_status,
                i.score_general,
                i.score_technical,
                i.score_aesthetic,
                LOWER(BTRIM(COALESCE(i.description, ''))) AS caption,
                LOWER(COALESCE(i.keywords, '')) AS keywords
            FROM images i
            JOIN selected_stacks s ON s.stack_id = i.stack_id
        ),
        caption_counts AS (
            SELECT stack_id, caption, COUNT(*) AS caption_count
            FROM candidates
            GROUP BY stack_id, caption
        ),
        stack_stats AS (
            SELECT
                stack_id,
                COUNT(*) AS labeled_in_stack,
                COUNT(DISTINCT NULLIF(caption, '')) AS distinct_captions
            FROM candidates
            GROUP BY stack_id
        )
        SELECT
            l.*,
            cc.caption_count,
            ss.labeled_in_stack,
            ss.distinct_captions,
            BOOL_OR(
                l.keywords ~ '(species:|bird|wildlife|deer|fawn|squirrel|fox|bear|elk|moose|rabbit|animal)'
            ) OVER (PARTITION BY l.stack_id) AS wildlife_hint
        FROM candidates l
        JOIN caption_counts cc
          ON cc.stack_id = l.stack_id AND cc.caption = l.caption
        JOIN stack_stats ss ON ss.stack_id = l.stack_id
        ORDER BY l.stack_id, l.image_id
    """
    return [dict(row) for row in (db.get_connector().query(sql) or [])]


def _load_embedding_novelty(
    code: str,
    table: str,
    *,
    max_stack_size: int,
    limit_stacks: int,
) -> dict[int, float]:
    if table not in {"image_embeddings", "image_embeddings_512", "image_embeddings_768"}:
        raise ValueError(f"Unsupported embedding table: {table}")
    stacks_sql = _selected_stacks_sql(max_stack_size, limit_stacks)
    sql = f"""
        WITH selected_stacks AS ({stacks_sql}),
        vectors AS (
            SELECT e.image_id, i.stack_id, i.pick_status, e.embedding
            FROM {table} e
            JOIN embedding_spaces es ON es.id = e.embedding_space_id
            JOIN images i ON i.id = e.image_id
            JOIN selected_stacks s ON s.stack_id = i.stack_id
            WHERE es.code = ?
              AND e.embedding IS NOT NULL
        )
        SELECT a.image_id, MIN(a.embedding <=> b.embedding) AS nearest_distance
        FROM vectors a
        JOIN vectors b
          ON b.stack_id = a.stack_id AND b.image_id <> a.image_id
        WHERE a.pick_status IN (-1, 1)
        GROUP BY a.image_id
    """
    rows = db.get_connector().query(sql, (code,)) or []
    return {
        int(row["image_id"]): float(row["nearest_distance"])
        for row in rows
        if row.get("nearest_distance") is not None
    }


def _load_model_scores(
    *, max_stack_size: int, limit_stacks: int
) -> dict[int, dict[str, float]]:
    stacks_sql = _selected_stacks_sql(max_stack_size, limit_stacks)
    placeholders = ", ".join("?" for _ in MODEL_SCORE_NAMES)
    sql = f"""
        WITH selected_stacks AS ({stacks_sql})
        SELECT ims.image_id, ims.model_name, ims.normalized
        FROM image_model_scores ims
        JOIN images i ON i.id = ims.image_id
        JOIN selected_stacks s ON s.stack_id = i.stack_id
        WHERE ims.model_name IN ({placeholders})
          AND ims.status = 'success'
          AND ims.normalized IS NOT NULL
    """
    out: dict[int, dict[str, float]] = {}
    for row in db.get_connector().query(sql, tuple(MODEL_SCORE_NAMES)) or []:
        out.setdefault(int(row["image_id"]), {})[str(row["model_name"])] = float(
            row["normalized"]
        )
    return out


def _safe_metric(fn, y_true: np.ndarray, y_score: np.ndarray) -> float | None:
    try:
        value = float(fn(y_true, y_score))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _evaluate_variant(
    matrix: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    columns: list[str],
) -> tuple[np.ndarray, dict[str, Any]]:
    transformer = ColumnTransformer(
        [("numeric", Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]), list(range(matrix.shape[1])))],
        remainder="drop",
    )
    model = Pipeline([
        ("features", transformer),
        ("model", LogisticRegression(max_iter=2_000, class_weight="balanced")),
    ])
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    probabilities = cross_val_predict(
        model,
        matrix,
        y,
        groups=groups,
        cv=splitter,
        method="predict_proba",
        n_jobs=1,
    )[:, 1]
    return probabilities, {
        "features": columns,
        "roc_auc": _safe_metric(roc_auc_score, y, probabilities),
        "average_precision": _safe_metric(average_precision_score, y, probabilities),
    }


def _caption_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_stack: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_stack.setdefault(int(row["stack_id"]), []).append(row)

    collapsed = 0
    unique_ratios: list[float] = []
    picked_total = 0
    picked_duplicated_by_reject = 0
    for members in by_stack.values():
        captions = [str(row.get("caption") or "") for row in members]
        nonempty = {caption for caption in captions if caption}
        if len(nonempty) <= 1:
            collapsed += 1
        unique_ratios.append(len(nonempty) / max(1, len(members)))
        rejected_captions = {
            str(row.get("caption") or "")
            for row in members
            if int(row.get("pick_status") or 0) == -1 and row.get("caption")
        }
        for row in members:
            if int(row.get("pick_status") or 0) != 1:
                continue
            picked_total += 1
            if row.get("caption") and row["caption"] in rejected_captions:
                picked_duplicated_by_reject += 1

    missing = sum(1 for row in rows if not row.get("caption"))
    return {
        "stack_count": len(by_stack),
        "exactly_collapsed_stack_count": collapsed,
        "exactly_collapsed_stack_rate": collapsed / max(1, len(by_stack)),
        "mean_distinct_caption_ratio": float(np.mean(unique_ratios)),
        "missing_caption_count": missing,
        "missing_caption_rate": missing / max(1, len(rows)),
        "picked_count": picked_total,
        "picked_caption_duplicated_by_reject_count": picked_duplicated_by_reject,
        "picked_caption_duplicated_by_reject_rate": (
            picked_duplicated_by_reject / max(1, picked_total)
        ),
    }


def _top_k_score_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank by score_general and keep the historical number of picks per stack."""
    by_stack: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_stack.setdefault(int(row["stack_id"]), []).append(row)

    hits = 0
    picks = 0
    random_expected_hits = 0.0
    captioned_hits = 0
    captioned_picks = 0
    captioned_random = 0.0
    captioned_stacks = 0
    for members in by_stack.values():
        true_picks = {
            int(row["image_id"])
            for row in members
            if int(row.get("pick_status") or 0) == 1
        }
        k = len(true_picks)
        ranked = sorted(
            members,
            key=lambda row: (
                float(row["score_general"])
                if row.get("score_general") is not None
                else float("-inf")
            ),
            reverse=True,
        )
        predicted = {int(row["image_id"]) for row in ranked[:k]}
        stack_hits = len(true_picks & predicted)
        hits += stack_hits
        picks += k
        random_expected_hits += k * k / len(members)

        if all(bool(row.get("caption")) for row in members):
            captioned_stacks += 1
            captioned_hits += stack_hits
            captioned_picks += k
            captioned_random += k * k / len(members)

    return {
        "all_mixed": {
            "stacks": len(by_stack),
            "picks": picks,
            "pick_recall": hits / max(1, picks),
            "random_expected_recall": random_expected_hits / max(1, picks),
        },
        "fully_captioned": {
            "stacks": captioned_stacks,
            "picks": captioned_picks,
            "pick_recall": captioned_hits / max(1, captioned_picks),
            "random_expected_recall": captioned_random / max(1, captioned_picks),
        },
    }


def _jev_availability() -> dict[str, Any]:
    secret = config.get_secret("typesafe")
    dotenv_token = dotenv_values(ROOT / ".env").get("JEV_TOKEN")
    has_key = bool(
        os.environ.get("TYPESAFE_API_KEY")
        or os.environ.get("JEV_TOKEN")
        or dotenv_token
        or (secret.get("api_key") if isinstance(secret, dict) else secret)
    )
    has_sdk = importlib.util.find_spec("typesafe_sdk") is not None
    return {
        "status": "available" if has_key and has_sdk else "unavailable",
        "api_key_configured": has_key,
        "sdk_installed": has_sdk,
        "network_calls_made": 0,
        "note": (
            "No Jev calls were made. Configure a fresh server-side key and install the SDK "
            "before adding the Jev arm; never reuse a credential exposed in a transcript."
            if not (has_key and has_sdk)
            else "Capability is available, but this baseline intentionally makes no paid calls."
        ),
    }


def run(max_stack_size: int, limit_stacks: int) -> dict[str, Any]:
    candidates = _load_base_rows(max_stack_size, limit_stacks)
    if not candidates:
        raise RuntimeError("No mixed pick/reject stacks matched the experiment criteria")
    rows = [row for row in candidates if int(row.get("pick_status") or 0) in (-1, 1)]

    novelty: dict[str, dict[int, float]] = {}
    for code, table in SPACE_TABLES.items():
        novelty[code] = _load_embedding_novelty(
            code,
            table,
            max_stack_size=max_stack_size,
            limit_stacks=limit_stacks,
        )
    model_scores = _load_model_scores(
        max_stack_size=max_stack_size, limit_stacks=limit_stacks
    )

    feature_names = [*SCORE_FEATURES, *CAPTION_FEATURES]
    for code in SPACE_TABLES:
        feature_names.append(f"novelty:{code}")
    model_feature_names = [f"model:{name}" for name in MODEL_SCORE_NAMES]
    feature_names.extend(model_feature_names)

    records: list[list[float]] = []
    y_values: list[int] = []
    groups: list[int] = []
    wildlife: list[bool] = []
    for row in rows:
        image_id = int(row["image_id"])
        caption_count = max(1, int(row.get("caption_count") or 1))
        record = [
            float(row[name]) if row.get(name) is not None else np.nan
            for name in SCORE_FEATURES
        ]
        record.extend([
            1.0 / caption_count,
            0.0 if row.get("caption") else 1.0,
        ])
        record.extend(novelty[code].get(image_id, np.nan) for code in SPACE_TABLES)
        per_model = model_scores.get(image_id, {})
        record.extend(per_model.get(name, np.nan) for name in MODEL_SCORE_NAMES)
        records.append(record)
        y_values.append(1 if int(row["pick_status"]) == 1 else 0)
        folder_id = row.get("folder_id")
        groups.append(int(folder_id) if folder_id is not None else -int(row["stack_id"]))
        wildlife.append(bool(row.get("wildlife_hint")))

    matrix = np.asarray(records, dtype=float)
    y = np.asarray(y_values, dtype=int)
    group_values = np.asarray(groups, dtype=int)
    wildlife_mask = np.asarray(wildlife, dtype=bool)

    variants = {
        "scores": SCORE_FEATURES,
        "scores_plus_caption": [*SCORE_FEATURES, *CAPTION_FEATURES],
    }
    for code in SPACE_TABLES:
        variants[f"scores_plus_{code}"] = [*SCORE_FEATURES, f"novelty:{code}"]
    variants["all_model_scores"] = model_feature_names
    variants["composites_plus_all_model_scores"] = [
        *SCORE_FEATURES,
        *model_feature_names,
    ]
    variants["all_evidence"] = feature_names

    evaluations: dict[str, Any] = {}
    for name, columns in variants.items():
        indices = [feature_names.index(column) for column in columns]
        probabilities, metrics = _evaluate_variant(
            matrix[:, indices], y, group_values, columns
        )
        metrics["wildlife_hint"] = {
            "rows": int(wildlife_mask.sum()),
            "roc_auc": _safe_metric(
                roc_auc_score, y[wildlife_mask], probabilities[wildlife_mask]
            ),
            "average_precision": _safe_metric(
                average_precision_score, y[wildlife_mask], probabilities[wildlife_mask]
            ),
        }
        evaluations[name] = metrics

    coverage = {
        code: {
            "rows": len(values),
            "rate": len(values) / len(rows),
        }
        for code, values in novelty.items()
    }
    return {
        "schema_version": "typesafe-culling-real-data/1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "issue": 359,
        "read_only": True,
        "selection": {
            "criteria": "mixed historical pick/reject stacks, 2..max_stack_size images",
            "max_stack_size": max_stack_size,
            "limit_stacks": limit_stacks,
            "candidate_rows": len(candidates),
            "labeled_rows": len(rows),
            "stacks": len({int(row["stack_id"]) for row in candidates}),
            "folders": len(set(groups)),
            "picked": int(y.sum()),
            "rejected": int((1 - y).sum()),
            "wildlife_hint_rows": int(wildlife_mask.sum()),
        },
        "caption_evidence": _caption_metrics(candidates),
        "deterministic_score_baseline": _top_k_score_baseline(candidates),
        "embedding_novelty_coverage": coverage,
        "model_score_coverage": {
            name: {
                "rows": sum(name in values for values in model_scores.values()),
                "rate": sum(name in values for values in model_scores.values()) / len(rows),
            }
            for name in MODEL_SCORE_NAMES
        },
        "evaluation": {
            "method": "5-fold StratifiedGroupKFold; groups are folder_id",
            "target": "historical pick_status (proxy label, not ground truth)",
            "variants": evaluations,
        },
        "jev_arm": _jev_availability(),
        "limitations": [
            "Historical pick_status reflects prior workflow and user preference, not objective truth.",
            "The wildlife subset is a metadata hint and can contain false-positive tags.",
            "Embedding novelty measures geometric difference, not photographic significance.",
            "Exact caption diversity misses paraphrases and cannot recover omitted visual facts.",
        ],
    }


def _format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def render_markdown(result: dict[str, Any]) -> str:
    selection = result["selection"]
    captions = result["caption_evidence"]
    baseline = result["deterministic_score_baseline"]
    lines = [
        "# Jev-ready culling evidence: real-data baseline",
        "",
        f"Generated: `{result['generated_at']}`  ",
        "Tracking: [#359](https://github.com/synthet/image-scoring-backend/issues/359)",
        "",
        "This is a read-only baseline over historical image records. It evaluates whether the",
        "evidence available to a future Jev experiment carries useful pick/reject signal.",
        "No database row, rating, pick, cull decision, or image file was changed.",
        "",
        "## Dataset",
        "",
        f"- {selection['candidate_rows']:,} candidates across {selection['stacks']:,} mixed stacks",
        f"- {selection['labeled_rows']:,} candidates have pick/reject labels",
        f"- {selection['picked']:,} picks and {selection['rejected']:,} rejects",
        f"- {selection['folders']:,} folder groups used for leakage-resistant validation",
        f"- {selection['wildlife_hint_rows']:,} rows in metadata-hinted wildlife stacks",
        "",
        "## Caption evidence",
        "",
        f"- Fully collapsed stacks: {captions['exactly_collapsed_stack_count']:,} "
        f"({_format_pct(captions['exactly_collapsed_stack_rate'])})",
        f"- Mean distinct-caption ratio: {_format_pct(captions['mean_distinct_caption_ratio'])}",
        f"- Picks whose caption also appears on a reject in the same stack: "
        f"{captions['picked_caption_duplicated_by_reject_count']:,} "
        f"({_format_pct(captions['picked_caption_duplicated_by_reject_rate'])})",
        f"- Missing captions: {captions['missing_caption_count']:,} "
        f"({_format_pct(captions['missing_caption_rate'])})",
        "",
        "## Deterministic score baseline",
        "",
        "| Cohort | Stacks | Picks | Score-only pick recall | Random expectation |",
        "|---|---:|---:|---:|---:|",
        f"| All mixed | {baseline['all_mixed']['stacks']:,} | "
        f"{baseline['all_mixed']['picks']:,} | "
        f"{baseline['all_mixed']['pick_recall']:.4f} | "
        f"{baseline['all_mixed']['random_expected_recall']:.4f} |",
        f"| Fully captioned | {baseline['fully_captioned']['stacks']:,} | "
        f"{baseline['fully_captioned']['picks']:,} | "
        f"{baseline['fully_captioned']['pick_recall']:.4f} | "
        f"{baseline['fully_captioned']['random_expected_recall']:.4f} |",
        "",
        "## Folder-grouped historical-pick prediction",
        "",
        "| Variant | ROC-AUC | Average precision | Wildlife ROC-AUC | Wildlife AP |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, metrics in result["evaluation"]["variants"].items():
        wildlife = metrics["wildlife_hint"]
        lines.append(
            f"| `{name}` | {metrics['roc_auc']:.3f} | {metrics['average_precision']:.3f} | "
            f"{wildlife['roc_auc']:.3f} | {wildlife['average_precision']:.3f} |"
        )
    lines.extend([
        "",
        "These scores measure agreement with historical picks. They do not establish that",
        "historical rejects were safe to remove or that an embedding recognized the reason a",
        "frame was distinctive.",
        "",
        "## Jev arm",
        "",
        f"Status: **{result['jev_arm']['status']}**. " + result["jev_arm"]["note"],
        "",
        "## Interpretation rule",
        "",
        "Promote a Jev experiment only after structured or paired visual evidence improves over",
        "the score-only baseline on held-out folders. Then evaluate rules and Jev on the exact",
        "same evidence so improved perception is not incorrectly credited to the decision model.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-stack-size", type=int, default=10)
    parser.add_argument("--limit-stacks", type=int, default=0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.max_stack_size < 2:
        parser.error("--max-stack-size must be at least 2")
    if args.limit_stacks < 0:
        parser.error("--limit-stacks cannot be negative")

    result = run(args.max_stack_size, args.limit_stacks)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output": str(output),
        "rows": result["selection"]["labeled_rows"],
        "stacks": result["selection"]["stacks"],
        "jev": result["jev_arm"]["status"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
