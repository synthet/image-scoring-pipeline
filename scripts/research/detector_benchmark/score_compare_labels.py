"""Score blind v0 vs v1 box preferences from compare_labels.csv + mapping.json.

    python scripts/research/detector_benchmark/score_compare_labels.py \\
        --labels .agent/scratch/bird_detect_compare/compare_labels.csv \\
        --mapping .agent/scratch/bird_detect_compare/page/mapping.json \\
        --out .agent/scratch/bird_detect_compare/compare_scores.json

``pick`` is screen-side (a/b from the labeller). ``mapping.json`` records which
weight was Option A vs B per image_id.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

V0_NAME = "bird_detect_v0.pt"
V1_NAME = "bird_detect_v1.pt"


def _winner_model(pick: str, row: dict) -> str | None:
    pick = pick.strip().lower()
    if pick == "a":
        return row["option_a_model"]
    if pick == "b":
        return row["option_b_model"]
    return None


def _model_bucket(filename: str) -> str:
    name = (filename or "").strip()
    if name == V1_NAME or name.endswith("/bird_detect_v1.pt"):
        return "v1"
    if name == V0_NAME or name.endswith("/bird_detect_v0.pt"):
        return "v0"
    return "other"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.mapping, encoding="utf-8") as fh:
        manifest = json.load(fh)
    mapping_rows = manifest.get("rows", [])
    by_id = {int(r["image_id"]): r for r in mapping_rows}
    if len(by_id) != len(mapping_rows):
        raise ValueError("mapping contains duplicate image IDs")
    for image_id, row in by_id.items():
        options = {_model_bucket(row.get("option_a_model", "")),
                   _model_bucket(row.get("option_b_model", ""))}
        if options != {"v0", "v1"}:
            raise ValueError(f"mapping has invalid model pair for image {image_id}")
        v0_side = row.get("v0_on_screen")
        if v0_side not in ("a", "b") or _model_bucket(row[f"option_{v0_side}_model"]) != "v0":
            raise ValueError(f"mapping has inconsistent v0 side for image {image_id}")

    labels: list[dict] = []
    with open(args.labels, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            pick = row["pick"].strip().lower()
            if pick not in ("a", "b", "tie", "neither", "unsure"):
                raise ValueError(f"invalid pick {pick!r} for image {row['image_id']}")
            labels.append({"image_id": int(row["image_id"]), "pick": pick})

    label_ids = [x["image_id"] for x in labels]
    if len(label_ids) != len(set(label_ids)):
        raise ValueError("labels contain duplicate image IDs")
    if set(label_ids) != set(by_id):
        raise ValueError("labels must cover the mapping exactly")

    pick_counts = Counter(x["pick"] for x in labels)
    decisive = [x for x in labels if x["pick"] in ("a", "b")]
    v0_wins = v1_wins = 0
    per_stratum_v0: Counter = Counter()
    per_stratum_v1: Counter = Counter()
    per_stratum_n: Counter = Counter()
    rows_out = []

    for item in labels:
        m = by_id[item["image_id"]]
        pick = item["pick"]
        winner_file = _winner_model(pick, m)
        winner = _model_bucket(winner_file) if winner_file else None
        stratum = m.get("stratum") or ""
        if winner == "v0":
            v0_wins += 1
            per_stratum_v0[stratum] += 1
        elif winner == "v1":
            v1_wins += 1
            per_stratum_v1[stratum] += 1
        if pick in ("a", "b"):
            per_stratum_n[stratum] += 1
        rows_out.append({
            "image_id": item["image_id"],
            "stratum": stratum,
            "pick": pick,
            "winner": winner,
            "option_a_model": m["option_a_model"],
            "option_b_model": m["option_b_model"],
        })

    n_decisive = len(decisive)
    if v0_wins + v1_wins != n_decisive:
        raise RuntimeError("decisive picks did not map to exactly one model")
    payload = {
        "labels_sha256": hashlib.sha256(Path(args.labels).read_bytes()).hexdigest(),
        "mapping_sha256": hashlib.sha256(Path(args.mapping).read_bytes()).hexdigest(),
        "labels_path": str(Path(args.labels).resolve()),
        "mapping_path": str(Path(args.mapping).resolve()),
        "models": manifest.get("models", {"v0": V0_NAME, "v1": V1_NAME}),
        "n_labelled": len(labels),
        "n_pairs_in_mapping": len(by_id),
        "pick_counts": dict(sorted(pick_counts.items())),
        "decisive": {
            "n": n_decisive,
            "v0_wins": v0_wins,
            "v1_wins": v1_wins,
            "v0_share": round(v0_wins / n_decisive, 4) if n_decisive else None,
            "v1_share": round(v1_wins / n_decisive, 4) if n_decisive else None,
        },
        "by_stratum": {
            s: {
                "decisive": per_stratum_n[s],
                "v0_wins": per_stratum_v0[s],
                "v1_wins": per_stratum_v1[s],
            }
            for s in sorted(set(per_stratum_n) | set(per_stratum_v0) | set(per_stratum_v1))
        },
        "rows": rows_out,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Labelled: {len(labels)} / {len(by_id)} pairs in mapping")
    print("Picks:", dict(pick_counts))
    if n_decisive:
        print(f"Decisive (a or b): v0 {v0_wins} ({100*v0_wins/n_decisive:.1f}%)  "
              f"v1 {v1_wins} ({100*v1_wins/n_decisive:.1f}%)")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
