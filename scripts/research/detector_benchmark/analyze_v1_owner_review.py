"""Replay the private bird-v1 presence and primary-box review without a database.

The input directory contains private image IDs and paths. Only aggregate counts and
input hashes are printed; keep the CSVs and the box manifest out of version control.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

PRESENCE_LABELS = {"bird", "no_bird", "unsure"}
BOX_LABELS = {"usable", "poor_crop", "wrong_target", "unsure"}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _indexed(rows: list[dict[str, str]], path: Path) -> dict[int, dict[str, str]]:
    result = {}
    for row in rows:
        image_id = int(row["image_id"])
        if image_id in result:
            raise ValueError(f"duplicate image_id in {path.name}: {image_id}")
        result[image_id] = row
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(root: Path) -> dict:
    cohort_path = root / "cohort.csv"
    presence_path = root / "labels.csv"
    sampling_path = root / "sampling.json"
    box_path = root / "box_page" / "box_labels.csv"
    manifest_path = root / "box_page" / "manifest.json"

    cohort = _indexed(_rows(cohort_path), cohort_path)
    presence = _indexed(_rows(presence_path), presence_path)
    boxes = _indexed(_rows(box_path), box_path)
    sampling = json.loads(sampling_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_rows = _indexed(manifest["rows"], manifest_path)

    if not cohort or set(presence) != set(cohort):
        raise ValueError("presence labels must cover the cohort exactly")
    if any(row["label"] not in PRESENCE_LABELS for row in presence.values()):
        raise ValueError("invalid presence label")
    strata = Counter(row["stratum"] for row in cohort.values())
    if dict(strata) != sampling["sample"]:
        raise ValueError("cohort strata do not match the frozen sampling manifest")
    populations = {item["stratum"]: int(item["images"]) for item in sampling["population"]}
    detected_strata = {stratum for stratum in strata if stratum.startswith("det_")}
    if set(populations) != detected_strata or "no_detection" not in strata:
        raise ValueError("sampling manifest must cover detected strata and no detections")

    expected_boxes = {
        image_id for image_id, row in cohort.items()
        if row["stratum"].startswith("det_") and presence[image_id]["label"] == "bird"
    }
    if set(boxes) != expected_boxes or set(manifest_rows) != expected_boxes:
        raise ValueError("box labels and manifest must cover every detected bird frame exactly")
    for image_id, row in boxes.items():
        if row["box_label"] not in BOX_LABELS:
            raise ValueError(f"invalid box label for image {image_id}")
        frozen = manifest_rows[image_id]
        if (int(row["run_id"]) != int(frozen["run_id"])
                or int(row["region_id"]) != int(frozen["region_id"])):
            raise ValueError(f"box label references a changed run or region: {image_id}")

    presence_by_stratum = defaultdict(Counter)
    outcomes_by_stratum = defaultdict(Counter)
    for image_id, row in cohort.items():
        stratum = row["stratum"]
        label = presence[image_id]["label"]
        presence_by_stratum[stratum][label] += 1
        if stratum.startswith("det_"):
            outcome = boxes[image_id]["box_label"] if label == "bird" else f"presence_{label}"
            outcomes_by_stratum[stratum][outcome] += 1

    detected_outcomes = Counter()
    for counts in outcomes_by_stratum.values():
        detected_outcomes.update(counts)

    return {
        "input_sha256": {
            str(path.relative_to(root)).replace("\\", "/"): _sha256(path)
            for path in (cohort_path, presence_path, sampling_path, box_path, manifest_path)
        },
        "reviewed_images": len(cohort),
        "presence_labels": dict(Counter(row["label"] for row in presence.values())),
        "detected_reviewed": sum(n for stratum, n in strata.items() if stratum.startswith("det_")),
        "detected_primary_outcomes": dict(sorted(detected_outcomes.items())),
        "no_detection_reviewed": strata["no_detection"],
        "no_detection_presence": dict(sorted(presence_by_stratum["no_detection"].items())),
        "detected_strata": {
            stratum: {
                "population": populations[stratum],
                "sample": strata[stratum],
                "presence": dict(sorted(presence_by_stratum[stratum].items())),
                "primary_outcomes": dict(sorted(outcomes_by_stratum[stratum].items())),
            }
            for stratum in sorted(outcomes_by_stratum)
        },
        "note": "Folder-balanced, stratified development sample; counts are not library-wide rates.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("root", type=Path, help="private review directory")
    parser.add_argument("--out", type=Path, help="write aggregate JSON to this path")
    args = parser.parse_args()
    result = analyze(args.root)
    payload = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
