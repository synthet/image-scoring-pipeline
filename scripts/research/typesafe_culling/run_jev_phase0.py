#!/usr/bin/env python3
"""Run a bounded, resumable Jev arm over the frozen Phase-0 evidence JSONL.

This runner never reads image files and never writes PostgreSQL. It sends only
the structured evidence already exported by ``export_phase0_evidence.py``.
Results stay under the gitignored ``.agent/scratch`` tree.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from modules.typesafe.client import TypeSafeClient


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = (
    ROOT / ".agent" / "scratch" / "typesafe-culling" / "phase0-evidence-v3.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / ".agent"
    / "scratch"
    / "typesafe-culling"
    / "phase0-action-full-scores-jev-1.13.0.jsonl"
)
DEFAULT_MODEL = "jev-1.13.0"
RUBRICS = ["culling.action"]


def _load_repo_jev_token() -> None:
    """Load only JEV_TOKEN from the repo .env, without exposing its value."""
    if os.environ.get("JEV_TOKEN") or os.environ.get("TYPESAFE_API_KEY"):
        return
    value = dotenv_values(ROOT / ".env").get("JEV_TOKEN")
    if value:
        os.environ["JEV_TOKEN"] = value


def _read_completed(path: Path) -> set[str]:
    completed: set[str] = set()
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == "success" and row.get("evidence_hash"):
                completed.add(str(row["evidence_hash"]))
    return completed


def _judgment_payload(judgment: Any) -> dict[str, Any]:
    return {
        "value": judgment.value,
        "confidence": judgment.confidence,
        "probabilities": judgment.probabilities,
        "evidence_completeness": judgment.evidence_completeness,
        "model": judgment.model,
        "rubric_version": judgment.rubric_version,
        "question_type": judgment.question_type,
    }


def _model_state(evidence: dict[str, Any]) -> dict[str, Any]:
    """Strip evaluation-only fields before state leaves the machine."""
    return {
        key: value
        for key, value in evidence.items()
        if key not in {"historical_label", "evidence_hash"}
    }


def run(
    input_path: Path,
    output_path: Path,
    *,
    limit: int,
    model: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Phase-0 evidence file not found: {input_path}")
    if model in {"jev-latest", "jev-preview"}:
        raise ValueError("Experiments require a pinned Jev version, not a moving alias")

    _load_repo_jev_token()
    client = TypeSafeClient(
        enabled=True,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    if not client.available:
        raise RuntimeError(f"TypeSafe unavailable: {client.unavailable_reason}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = _read_completed(output_path)
    attempted = 0
    succeeded = 0
    failed = 0
    skipped = 0
    with input_path.open("r", encoding="utf-8") as source, output_path.open(
        "a", encoding="utf-8"
    ) as sink:
        for line in source:
            if attempted >= limit:
                break
            evidence = json.loads(line)
            evidence_hash = str(evidence["evidence_hash"])
            if evidence_hash in completed:
                skipped += 1
                continue

            attempted += 1
            judgments = client.judge(
                _model_state(evidence), RUBRICS, check_evidence=True
            )
            status = "success" if len(judgments) == len(RUBRICS) else "failed"
            if status == "success":
                succeeded += 1
            else:
                failed += 1
            row = {
                "schema_version": "jev-culling-judgment/1",
                "evidence_hash": evidence_hash,
                "stack_id": evidence["stack_id"],
                "candidate_image_id": evidence["candidate"]["image_id"],
                "historical_label": evidence.get("historical_label"),
                "status": status,
                "judgments": {
                    key: _judgment_payload(value)
                    for key, value in judgments.items()
                },
            }
            sink.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            sink.flush()

    return {
        "model": model,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "previously_completed_skipped": skipped,
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    summary = run(
        args.input.resolve(),
        args.output.resolve(),
        limit=args.limit,
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
