#!/usr/bin/env python3
"""Join UGC JSONL with DB scores; emit Spearman correlation CSV + one-page markdown.

Run after ``export_cohort.py`` and ``fetch_ugc.py`` (gpu-shell for DB)::

    scripts/batch/docker_gpu_run.bat scripts/research/everypixel_correlation/join_and_analyze.py
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from scripts.research.everypixel_correlation.statistical_modeling import (
    run_modeling_suite,
    write_joined_csv,
    write_modeling_artifacts,
)
from scripts.research.everypixel_correlation.common import (
    COMPOSITE_COLUMNS,
    CORE_MODEL_NAMES,
    DEFAULT_MANIFEST,
    DEFAULT_UGC_JSONL,
    REPORTS_DIR,
)

logger = logging.getLogger(__name__)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _load_model_scores(image_ids: list[int]) -> dict[int, dict[str, float]]:
    from modules import db

    if not image_ids:
        return {}
    db.init_db()
    placeholders = ", ".join("?" for _ in image_ids)
    model_ph = ", ".join("?" for _ in CORE_MODEL_NAMES)
    sql = f"""
        SELECT ims.image_id, ims.model_name, ims.normalized
        FROM image_model_scores ims
        WHERE ims.image_id IN ({placeholders})
          AND ims.model_name IN ({model_ph})
          AND ims.status = 'success'
          AND COALESCE(ims.is_shadow, FALSE) = FALSE
    """
    params = tuple(image_ids) + CORE_MODEL_NAMES
    out: dict[int, dict[str, float]] = {}
    for row in db.get_connector().query(sql, params) or []:
        iid = int(row["image_id"])
        name = str(row["model_name"])
        norm = row.get("normalized")
        if norm is None:
            continue
        out.setdefault(iid, {})[name] = float(norm)
    return out


def _paired_vectors(
    joined: list[dict[str, Any]],
    target: str,
    feature: str,
) -> tuple[np.ndarray, np.ndarray]:
    xs: list[float] = []
    ys: list[float] = []
    for row in joined:
        t = row.get(target)
        f = row.get(feature)
        if t is None or f is None:
            continue
        try:
            xs.append(float(t))
            ys.append(float(f))
        except (TypeError, ValueError):
            continue
    if len(xs) < 3:
        return np.array([]), np.array([])
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def build_joined_rows(
    manifest: dict[str, Any],
    ugc_rows: list[dict[str, Any]],
    model_scores: dict[int, dict[str, float]],
) -> list[dict[str, Any]]:
    manifest_by_id = {int(r["image_id"]): r for r in manifest.get("images") or []}
    joined: list[dict[str, Any]] = []
    for u in ugc_rows:
        if u.get("status") != "ok":
            continue
        iid = int(u["image_id"])
        base = dict(manifest_by_id.get(iid, {}))
        row: dict[str, Any] = {
            "image_id": iid,
            "ugc_score": u.get("ugc_score"),
            "ugc_class": u.get("ugc_class"),
        }
        for col in COMPOSITE_COLUMNS:
            row[col] = base.get(col)
        row["rating"] = base.get("rating")
        for name in CORE_MODEL_NAMES:
            row[name] = model_scores.get(iid, {}).get(name)
        joined.append(row)
    return joined


def correlation_table(joined: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = list(COMPOSITE_COLUMNS) + list(CORE_MODEL_NAMES) + ["rating"]
    targets = ("ugc_class", "ugc_score")
    rows: list[dict[str, Any]] = []
    for target in targets:
        for feature in features:
            x, y = _paired_vectors(joined, target, feature)
            n = len(x)
            if n < 3:
                rows.append(
                    {
                        "target": target,
                        "feature": feature,
                        "n": n,
                        "spearman_r": "",
                        "p_value": "",
                    }
                )
                continue
            r, p = spearmanr(x, y)
            rows.append(
                {
                    "target": target,
                    "feature": feature,
                    "n": n,
                    "spearman_r": round(float(r), 4),
                    "p_value": round(float(p), 6) if p == p else "",
                }
            )
    return rows


def write_correlation_csv(path: Path, table: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["target", "feature", "n", "spearman_r", "p_value"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(table)


def write_summary_md(
    path: Path,
    *,
    manifest: dict[str, Any],
    joined: list[dict[str, Any]],
    table: list[dict[str, Any]],
) -> None:
    def _top(target: str, k: int = 8) -> list[dict[str, Any]]:
        subset = [r for r in table if r["target"] == target and r.get("spearman_r") != ""]
        subset.sort(key=lambda r: abs(float(r["spearman_r"])), reverse=True)
        return subset[:k]

    lines = [
        "# Everypixel UGC correlation summary",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Manifest: `{manifest.get('manifest_id', '?')}` — **{manifest.get('sample_count', '?')}** sampled "
        f"({manifest.get('per_quintile', '?')} per `score_general` quintile, seed {manifest.get('seed', '?')})",
        f"- Joined rows (UGC ok): **{len(joined)}**",
        "",
        "## Primary target: `ugc_class` (Spearman vs local scores)",
        "",
        "| feature | n | ρ | p |",
        "|---------|---:|---:|---:|",
    ]
    for r in _top("ugc_class"):
        lines.append(
            f"| {r['feature']} | {r['n']} | {r['spearman_r']} | {r['p_value']} |"
        )
    lines.extend(
        [
            "",
            "## Secondary: `ugc_score`",
            "",
            "| feature | n | ρ | p |",
            "|---------|---:|---:|---:|",
        ]
    )
    for r in _top("ugc_score"):
        lines.append(
            f"| {r['feature']} | {r['n']} | {r['spearman_r']} | {r['p_value']} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Read-only study; does not write to `image_model_scores`.",
            "- Everypixel UGC calls use JPEG renditions (RAW decoded server-side).",
            "- Full matrix: `correlation_matrix.csv` in this directory.",
            "- Multivariate pass: `modeling_summary.md`, `descriptive_stats.csv`, `vif_predictors.csv`, `regression_models.json`.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def analyze(
    *,
    manifest_path: Path,
    jsonl_path: Path,
    out_dir: Path,
) -> tuple[Path, Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ugc_rows = _load_jsonl(jsonl_path)
    ok_ids = [int(r["image_id"]) for r in ugc_rows if r.get("status") == "ok"]
    model_scores = _load_model_scores(ok_ids)
    joined = build_joined_rows(manifest, ugc_rows, model_scores)
    table = correlation_table(joined)

    csv_path = out_dir / "correlation_matrix.csv"
    md_path = out_dir / "correlation_summary.md"
    write_correlation_csv(csv_path, table)
    write_summary_md(md_path, manifest=manifest, joined=joined, table=table)

    write_joined_csv(out_dir / "joined_scores.csv", joined)
    suite = run_modeling_suite(joined)
    modeling_md = write_modeling_artifacts(out_dir, suite)

    logger.info(
        "Wrote %s, %s, %s (%d joined rows)",
        csv_path,
        md_path,
        modeling_md,
        len(joined),
    )
    return csv_path, md_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Join UGC results and compute correlations")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_UGC_JSONL)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args()

    if not args.manifest.is_file():
        raise SystemExit(f"Missing manifest: {args.manifest}")
    if not args.jsonl.is_file():
        raise SystemExit(f"Missing JSONL: {args.jsonl} (run fetch_ugc.py first)")

    analyze(manifest_path=args.manifest, jsonl_path=args.jsonl, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
