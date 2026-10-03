#!/usr/bin/env python3
"""Create/review/evaluate a frozen model-selection study. See --help."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create", "explore", "serve", "progress", "select", "test", "benchmark",
                                                "tie-tolerance"])
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--singles", type=int, default=600)
    parser.add_argument("--groups", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--reviewer", default="owner")
    parser.add_argument("--models", default="arniqa,ava,clip_quality_v0,liqe,spaq,topiq")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7862)
    parser.add_argument("--backend", default="http://127.0.0.1:7860")
    parser.add_argument("--benchmark-images", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from modules.score_analytics.study_data import freeze_database, make_sample, read_json, write_json

    root = args.study.resolve()
    if args.command == "create":
        if root.exists():
            parser.error("Study directory already exists; use a new path to preserve its snapshot and labels")
        if args.singles < 1 or args.groups < 1:
            parser.error("Sample counts must be positive")
        logging.info("Reading a consistent database snapshot")
        snapshot = freeze_database()
        sample = make_sample(snapshot, singles=args.singles, groups=args.groups, seed=args.seed)
        root.mkdir(parents=True)
        write_json(root / "snapshot.json.gz", snapshot)
        fingerprint = hashlib.sha256((root / "snapshot.json.gz").read_bytes()).hexdigest()
        sample["snapshot_sha256"] = fingerprint
        sample["study_id"] = fingerprint[:16]
        write_json(root / "sample.json", sample)
        sha = "unavailable-in-container"
        if shutil.which("git"):
            sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        write_json(root / "manifest.json", {"git_sha": sha, "snapshot_sha256": fingerprint,
                                           "sample_sha256": hashlib.sha256((root / "sample.json").read_bytes()).hexdigest(),
                                           "created_at": snapshot["created_at"],
                                           "code_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                           for p in (ROOT / "modules/score_analytics").glob("study*.py")}})
        (root / "reviews.jsonl").touch()
        logging.info("Frozen %d images and %d review units at %s", len(snapshot["images"]), len(sample["units"]), root)
        return 0
    sample = read_json(root / "sample.json")
    manifest = read_json(root / "manifest.json")
    if hashlib.sha256((root / "sample.json").read_bytes()).hexdigest() != manifest["sample_sha256"]:
        raise ValueError("Sample changed after freezing")
    if args.command == "serve":
        from modules.score_analytics.study_review import serve

        serve(root, host=args.host, port=args.port, backend=args.backend)
        return 0
    from modules.score_analytics import study_report

    records = [json.loads(line) for line in (root / "reviews.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    reviews = study_report.load_reviews(sample, records, args.reviewer)
    if args.command == "progress":
        print(json.dumps(study_report.review_progress(sample, reviews), indent=2))
        return 0
    if hashlib.sha256((root / "snapshot.json.gz").read_bytes()).hexdigest() != sample["snapshot_sha256"]:
        raise ValueError("Snapshot changed after freezing")
    snapshot = read_json(root / "snapshot.json.gz")
    if args.command == "explore":
        study_report.exploratory(snapshot, sample, root)
    elif args.command == "select":
        if (root / "test_results.json").exists():
            raise ValueError("Test already accessed. Collect a fresh holdout for a new selection")
        selection = study_report.select_candidates(snapshot, sample, reviews, models=args.models.split(","))
        selection.update({"snapshot_sha256": sample["snapshot_sha256"], "reviewer": args.reviewer})
        write_json(root / "selection.json", selection)
    elif args.command == "test":
        target = root / "test_results.json"
        if target.exists():
            raise ValueError("Test results already exist; don't repeatedly inspect the holdout")
        selection = read_json(root / "selection.json")
        if selection["snapshot_sha256"] != sample["snapshot_sha256"] or selection["reviewer"] != args.reviewer:
            raise ValueError("Selection belongs to a different study or reviewer")
        report = study_report.evaluate_test(snapshot, sample, reviews, selection, resamples=args.bootstrap)
        write_json(target, report)
    elif args.command == "benchmark":
        from modules.score_analytics.study_benchmark import benchmark

        benchmark(snapshot, sample, root, args.models.split(","), args.benchmark_images, args.repeats)
    elif args.command == "tie-tolerance":
        from modules.score_analytics.study import tie_tolerance_curve

        # Calibration may only see train + validation; the test split stays unread (#508).
        rows = [r for split in ("train", "validation")
                for r in study_report._rows(snapshot, sample, reviews, "culling", split, ("general",))[0]]
        assert all(r["split"] != "test" for r in rows)
        result = tie_tolerance_curve(
            [{"id": r["id"], "scores": r["x"][:, 0], "grades": r["grades"]} for r in rows],
            resamples=args.bootstrap,
        )
        write_json(root / "tie_tolerance.json", result)
        for c in result["curve"]:
            ci = "n/a" if c["ci95"] is None else f"[{c['ci95'][0]:.2f}, {c['ci95'][1]:.2f}]"
            agree = "n/a" if c["agreement"] is None else f"{c['agreement']:.2f}"
            print(f"eps={c['epsilon']:<7} pairs={c['pairs']:<5} groups={c['groups']:<4} "
                  f"agreement={agree:<5} ci95={ci:<13} qualifies={c['qualifies']}")
        print(f"recommended_epsilon={result['recommended_epsilon']} "
              f"(groups={result['groups']}, equal-grade pairs={result['equal_grade_pairs']})")
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
