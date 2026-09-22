#!/usr/bin/env python3
"""Export a local, read-only Phase-0 Jev culling evidence cohort.

The JSONL contains real captions and image identifiers, so it is written under
``.agent/scratch`` (gitignored). The committed manifest contains aggregates
only. No image bytes or file paths are exported, and PostgreSQL is never
modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules import db


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = (
    ROOT / ".agent" / "scratch" / "typesafe-culling" / "phase0-evidence-v3.jsonl"
)
DEFAULT_MANIFEST = (
    ROOT / "reports" / "typesafe-culling-real-data" / "phase0-manifest.json"
)
EMBEDDING_CODE = "openclip_l14_laion2b_image"
SCHEMA_VERSION = "jev-culling-evidence/3"
MODEL_REGISTRY = {
    "spaq": ("global_perceptual_iqa", "perceptual quality"),
    "ava": ("global_aesthetics", "aesthetic quality"),
    "liqe": ("global_perceptual_iqa", "perceptual quality"),
    "topiq": ("global_perceptual_iqa", "no-reference technical quality"),
    "arniqa": ("global_perceptual_iqa", "no-reference technical quality"),
    "clip_quality_v0": ("auxiliary_prompt_quality", "auxiliary pick/reject signal"),
    "koniq": ("global_perceptual_iqa", "perceptual quality"),
    "paq2piq": ("global_perceptual_iqa", "perceptual quality"),
}


def _selected_stacks_sql(limit_stacks: int) -> str:
    limit = f"LIMIT {int(limit_stacks)}" if limit_stacks > 0 else ""
    return f"""
        SELECT i.stack_id
        FROM images i
        WHERE i.stack_id IS NOT NULL
        GROUP BY i.stack_id
        HAVING COUNT(*) BETWEEN 2 AND 10
           AND COUNT(*) FILTER (WHERE i.pick_status = 1) > 0
           AND COUNT(*) FILTER (WHERE i.pick_status = -1) > 0
           AND COUNT(*) FILTER (WHERE COALESCE(BTRIM(i.description), '') = '') = 0
        ORDER BY i.stack_id
        {limit}
    """


def _load_images(limit_stacks: int) -> list[dict[str, Any]]:
    sql = f"""
        WITH selected_stacks AS ({_selected_stacks_sql(limit_stacks)})
        SELECT
            i.id AS image_id,
            i.stack_id,
            i.pick_status,
            i.description AS caption,
            i.score_general,
            i.score_technical,
            i.score_aesthetic
        FROM images i
        JOIN selected_stacks s ON s.stack_id = i.stack_id
        ORDER BY i.stack_id, i.id
    """
    return [dict(row) for row in (db.get_connector().query(sql) or [])]


def _load_concepts(limit_stacks: int) -> dict[int, list[dict[str, Any]]]:
    sql = f"""
        WITH selected_stacks AS ({_selected_stacks_sql(limit_stacks)})
        SELECT
            ik.image_id,
            kd.keyword_display AS label,
            ik.source,
            ik.confidence,
            ik.relevance_weight
        FROM image_keywords ik
        JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
        JOIN images i ON i.id = ik.image_id
        JOIN selected_stacks s ON s.stack_id = i.stack_id
        ORDER BY ik.image_id, ik.confidence DESC NULLS LAST, kd.keyword_display
    """
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in db.get_connector().query(sql) or []:
        out[int(row["image_id"])].append(
            {
                "label": str(row["label"]),
                "source": str(row.get("source") or "unknown"),
                "confidence": (
                    float(row["confidence"])
                    if row.get("confidence") is not None
                    else None
                ),
                "relevance_weight": (
                    float(row["relevance_weight"])
                    if row.get("relevance_weight") is not None
                    else None
                ),
            }
        )
    return dict(out)


def _load_model_scores(limit_stacks: int) -> dict[int, list[dict[str, Any]]]:
    sql = f"""
        WITH selected_stacks AS ({_selected_stacks_sql(limit_stacks)})
        SELECT
            ims.image_id,
            ims.model_name,
            ims.raw_score,
            ims.normalized,
            ims.status,
            ims.is_shadow,
            ims.model_version
        FROM image_model_scores ims
        JOIN images i ON i.id = ims.image_id
        JOIN selected_stacks s ON s.stack_id = i.stack_id
        WHERE ims.model_name IN ({', '.join('?' for _ in MODEL_REGISTRY)})
        ORDER BY ims.image_id, ims.model_name
    """
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in db.get_connector().query(sql, tuple(MODEL_REGISTRY)) or []:
        model_name = str(row["model_name"])
        correlation_group, task = MODEL_REGISTRY[model_name]
        out[int(row["image_id"])].append(
            {
                "metric_id": model_name,
                "task": task,
                "correlation_group": correlation_group,
                "status": "ok" if row.get("status") == "success" else row.get("status"),
                "raw_score": (
                    float(row["raw_score"])
                    if row.get("raw_score") is not None
                    else None
                ),
                "normalized": (
                    float(row["normalized"])
                    if row.get("normalized") is not None
                    else None
                ),
                "normalized_direction": "higher_is_better",
                "model_version": row.get("model_version"),
                "is_shadow": bool(row.get("is_shadow")),
            }
        )
    return dict(out)


def _load_candidate_to_pick_neighbours(
    limit_stacks: int,
    neighbours: int,
) -> dict[int, list[dict[str, Any]]]:
    sql = f"""
        WITH selected_stacks AS ({_selected_stacks_sql(limit_stacks)}),
        vectors AS (
            SELECT e.image_id, i.stack_id, i.pick_status, e.embedding
            FROM image_embeddings_768 e
            JOIN embedding_spaces es ON es.id = e.embedding_space_id
            JOIN images i ON i.id = e.image_id
            JOIN selected_stacks s ON s.stack_id = i.stack_id
            WHERE es.code = ? AND e.embedding IS NOT NULL
        ),
        ranked AS (
            SELECT
                candidate.image_id AS candidate_image_id,
                picked.image_id AS picked_image_id,
                1.0 - (candidate.embedding <=> picked.embedding) AS cosine_similarity,
                ROW_NUMBER() OVER (
                    PARTITION BY candidate.image_id
                    ORDER BY candidate.embedding <=> picked.embedding, picked.image_id
                ) AS rank
            FROM vectors candidate
            JOIN vectors picked
              ON picked.stack_id = candidate.stack_id
             AND picked.pick_status = 1
             AND picked.image_id <> candidate.image_id
            WHERE candidate.pick_status IN (-1, 1)
        )
        SELECT candidate_image_id, picked_image_id, cosine_similarity, rank
        FROM ranked
        WHERE rank <= ?
        ORDER BY candidate_image_id, rank
    """
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    params = (EMBEDDING_CODE, int(neighbours))
    for row in db.get_connector().query(sql, params) or []:
        out[int(row["candidate_image_id"])].append(
            {
                "picked_image_id": int(row["picked_image_id"]),
                "cosine_similarity": float(row["cosine_similarity"]),
                "rank": int(row["rank"]),
                "embedding_space": EMBEDDING_CODE,
            }
        )
    return dict(out)


def _image_evidence(
    row: dict[str, Any],
    concepts: dict[int, list[dict[str, Any]]],
    model_scores: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    image_id = int(row["image_id"])
    return {
        "image_id": image_id,
        "caption": str(row.get("caption") or "").strip(),
        "technical": {
            "score_general": row.get("score_general"),
            "score_technical": row.get("score_technical"),
            "score_aesthetic": row.get("score_aesthetic"),
        },
        "model_observations": model_scores.get(image_id, []),
        "concepts": concepts.get(image_id, [])[:12],
    }


def _score_comparisons(
    candidate: dict[str, Any], retained: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    retained_by_metric: dict[str, list[float]] = defaultdict(list)
    for image in retained:
        for observation in image["model_observations"]:
            if observation.get("status") == "ok" and observation.get("normalized") is not None:
                retained_by_metric[str(observation["metric_id"])].append(
                    float(observation["normalized"])
                )
    comparisons: list[dict[str, Any]] = []
    for observation in candidate["model_observations"]:
        value = observation.get("normalized")
        peers = retained_by_metric.get(str(observation["metric_id"]), [])
        if observation.get("status") != "ok" or value is None or not peers:
            continue
        numeric = float(value)
        comparisons.append(
            {
                "metric_id": observation["metric_id"],
                "candidate_normalized": numeric,
                "best_retained_normalized": max(peers),
                "candidate_minus_best_retained": numeric - max(peers),
                "candidate_rank_higher_is_better": 1 + sum(peer > numeric for peer in peers),
                "comparison_count": len(peers),
            }
        )
    return comparisons


def _evidence_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export(limit_stacks: int, neighbours: int, output: Path) -> dict[str, Any]:
    images = _load_images(limit_stacks)
    concepts = _load_concepts(limit_stacks)
    model_scores = _load_model_scores(limit_stacks)
    neighbour_map = _load_candidate_to_pick_neighbours(limit_stacks, neighbours)
    by_stack: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in images:
        by_stack[int(row["stack_id"])].append(row)

    output.parent.mkdir(parents=True, exist_ok=True)
    record_count = 0
    target_counts = {"pick": 0, "reject": 0}
    missing_concepts = 0
    missing_neighbours = 0
    default_weight_concepts = 0
    concept_count = 0
    with output.open("w", encoding="utf-8") as handle:
        for stack_id, members in sorted(by_stack.items()):
            retained = [row for row in members if int(row.get("pick_status") or 0) == 1]
            labeled = [
                row for row in members if int(row.get("pick_status") or 0) in (-1, 1)
            ]
            for row in labeled:
                image_id = int(row["image_id"])
                target_label = (
                    "pick" if int(row.get("pick_status") or 0) == 1 else "reject"
                )
                comparison_rows = [
                    retained_row
                    for retained_row in retained
                    if int(retained_row["image_id"]) != image_id
                ]
                retained_evidence = [
                    _image_evidence(retained_row, concepts, model_scores)
                    for retained_row in comparison_rows
                ]
                retained_ids = {
                    int(retained_row["image_id"])
                    for retained_row in comparison_rows
                }
                candidate = _image_evidence(row, concepts, model_scores)
                neighbour_rows = [
                    item
                    for item in neighbour_map.get(image_id, [])
                    if item["picked_image_id"] in retained_ids
                ]
                if not candidate["concepts"]:
                    missing_concepts += 1
                if not neighbour_rows:
                    missing_neighbours += 1
                for concept in candidate["concepts"]:
                    concept_count += 1
                    if concept.get("relevance_weight") == 1.0:
                        default_weight_concepts += 1
                record = {
                    "schema_version": SCHEMA_VERSION,
                    # Evaluation-only target. The runner removes this field
                    # before sending state, preventing historical-label leakage.
                    "historical_label": target_label,
                    "stack_id": stack_id,
                    "selection_context": {
                        "purpose": "choose photographs for editing or presentation",
                        "comparison_scope": "candidate_vs_historically_retained_set",
                        "execution_mode": "offline_shadow",
                    },
                    "candidate": candidate,
                    "retained": retained_evidence,
                    "nearest_retained": neighbour_rows,
                    "precomputed_score_comparisons": _score_comparisons(
                        candidate, retained_evidence
                    ),
                    "evidence_status": {
                        "caption": "observed" if candidate["caption"] else "not_evaluated",
                        "concepts": "observed" if candidate["concepts"] else "not_evaluated",
                        "neighbours": "observed" if neighbour_rows else "not_evaluated",
                        "pairwise_visual_differences": "not_evaluated",
                    },
                    "provenance": {
                        "source": "production_postgres_read_only",
                        "embedding_space": EMBEDDING_CODE,
                        "caption_field": "images.description",
                        "concept_source": "image_keywords+keywords_dim",
                        "score_semantics": "raw_existing_scores_higher_is_better",
                    },
                }
                record["evidence_hash"] = _evidence_hash(record)
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                record_count += 1
                target_counts[target_label] += 1

    return {
        "schema_version": "jev-culling-phase0-manifest/3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "output": str(output),
        "output_gitignored": ".agent/scratch" in output.as_posix(),
        "stack_count": len(by_stack),
        "candidate_image_count": len(images),
        "labeled_candidate_records": record_count,
        "historical_label_counts": target_counts,
        "missing_concepts": missing_concepts,
        "missing_neighbours": missing_neighbours,
        "concept_count": concept_count,
        "default_one_relevance_weight_count": default_weight_concepts,
        "default_one_relevance_weight_rate": (
            default_weight_concepts / max(1, concept_count)
        ),
        "embedding_space": EMBEDDING_CODE,
        "model_score_metrics": list(MODEL_REGISTRY),
        "pairwise_visual_differences": "not_evaluated",
        "jev_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit-stacks", type=int, default=0)
    parser.add_argument("--neighbours", type=int, default=3)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    if args.limit_stacks < 0:
        parser.error("--limit-stacks cannot be negative")
    if not 1 <= args.neighbours <= 10:
        parser.error("--neighbours must be between 1 and 10")

    manifest = export(args.limit_stacks, args.neighbours, args.output.resolve())
    path = args.manifest.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "manifest": str(path),
        "records": manifest["labeled_candidate_records"],
        "stacks": manifest["stack_count"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
