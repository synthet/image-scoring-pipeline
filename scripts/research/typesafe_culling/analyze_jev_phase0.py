#!/usr/bin/env python3
"""Aggregate the local Jev Phase-0 action arm without exposing image records."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = (
    ROOT
    / ".agent"
    / "scratch"
    / "typesafe-culling"
    / "phase0-action-full-scores-jev-1.13.0.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / "reports"
    / "typesafe-culling-real-data"
    / "phase0-jev-full-score-summary.json"
)
LABELS = ("pick", "keep", "reject")


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def analyze(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    successful = [row for row in rows if row.get("status") == "success"]
    target_counts: Counter[str] = Counter()
    prediction_counts: Counter[str] = Counter()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    confidences: list[float] = []
    completeness: list[float] = []
    probability_sum_errors = 0
    log_losses: list[float] = []
    brier_scores: list[float] = []

    for row in successful:
        target = str(row.get("historical_label") or "unknown")
        judgment = row.get("judgments", {}).get("culling.action", {})
        prediction = str(judgment.get("value") or "unknown")
        probabilities = judgment.get("probabilities") or {}
        target_counts[target] += 1
        prediction_counts[prediction] += 1
        confusion[target][prediction] += 1
        if judgment.get("confidence") is not None:
            confidences.append(float(judgment["confidence"]))
        if judgment.get("evidence_completeness") is not None:
            completeness.append(float(judgment["evidence_completeness"]))
        probability_sum = sum(float(probabilities.get(label, 0.0)) for label in LABELS)
        if abs(probability_sum - 1.0) > 0.011:
            probability_sum_errors += 1
        if target in LABELS:
            target_probability = max(float(probabilities.get(target, 0.0)), 1e-12)
            log_losses.append(-math.log(target_probability))
            brier_scores.append(
                sum(
                    (float(probabilities.get(label, 0.0)) - float(label == target)) ** 2
                    for label in LABELS
                )
            )

    historical_picks = target_counts["pick"]
    historical_rejects = target_counts["reject"]
    predicted_rejects = prediction_counts["reject"]
    direct_matches = sum(confusion[label][label] for label in ("pick", "reject"))
    return {
        "schema_version": "jev-culling-phase0-results/1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "jev-1.13.0",
        "probability_status": "uncalibrated",
        "comparison_scope": "deterministic_prefix_exploration",
        "records": len(rows),
        "successful": len(successful),
        "failed": len(rows) - len(successful),
        "historical_label_counts": dict(target_counts),
        "predicted_label_counts": dict(prediction_counts),
        "confusion": {target: dict(counts) for target, counts in confusion.items()},
        "direct_historical_label_agreement": _safe_rate(
            direct_matches, historical_picks + historical_rejects
        ),
        "pick_preservation_rate": _safe_rate(
            historical_picks - confusion["pick"]["reject"], historical_picks
        ),
        "reject_recall": _safe_rate(confusion["reject"]["reject"], historical_rejects),
        "reject_precision": _safe_rate(confusion["reject"]["reject"], predicted_rejects),
        "multiclass_log_loss": mean(log_losses) if log_losses else None,
        "multiclass_brier_score": mean(brier_scores) if brier_scores else None,
        "mean_confidence": mean(confidences) if confidences else None,
        "mean_evidence_completeness": mean(completeness) if completeness else None,
        "probability_sum_error_count": probability_sum_errors,
        "limitations": [
            "Historical pick/reject labels are behavior targets, not proof of safe deletion.",
            "No historical keep labels exist in this cohort.",
            "The deterministic prefix is exploratory, not a locked session-level test split.",
            "Pairwise visual differences were not supplied.",
            "Probabilities are uncalibrated.",
        ],
    }


def _render_markdown(result: dict[str, Any]) -> str:
    def fmt(value: Any) -> str:
        return "n/a" if value is None else f"{float(value):.3f}"

    return f"""# Jev Phase-0 action Choice: real-data exploratory arm

Generated: `{result['generated_at']}`  
Model: `{result['model']}` (pinned)  
Probability status: **{result['probability_status']}**

This is a read-only shadow experiment. Jev received structured scores, captions,
concepts, and retained-set similarity evidence. It did not receive image bytes,
file paths, or historical labels.

## Results

- Calls: {result['records']} ({result['successful']} successful, {result['failed']} failed)
- Historical labels: `{json.dumps(result['historical_label_counts'], sort_keys=True)}`
- Jev actions: `{json.dumps(result['predicted_label_counts'], sort_keys=True)}`
- Direct historical-label agreement: {fmt(result['direct_historical_label_agreement'])}
- Pick preservation (pick or keep rather than reject): {fmt(result['pick_preservation_rate'])}
- Reject recall: {fmt(result['reject_recall'])}
- Reject precision: {fmt(result['reject_precision'])}
- Multiclass log loss: {fmt(result['multiclass_log_loss'])}
- Multiclass Brier score: {fmt(result['multiclass_brier_score'])}
- Mean Jev confidence: {fmt(result['mean_confidence'])}
- Mean evidence sufficiency: {fmt(result['mean_evidence_completeness'])}
- Invalid probability sums: {result['probability_sum_error_count']}

## Limits

""" + "\n".join(f"- {item}" for item in result["limitations"]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = analyze(args.input.resolve())
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(_render_markdown(result), encoding="utf-8")
    print(json.dumps({"ok": True, "records": result["records"], "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
