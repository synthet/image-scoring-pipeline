"""Replay the private bird-v1 failure review without a database."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iou(a: list[float], b: list[float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, ix2-ix1) * max(0.0, iy2-iy1)
    area_a = (a[2]-a[0]) * (a[3]-a[1])
    area_b = (b[2]-b[0]) * (b[3]-b[1])
    denominator = area_a + area_b - intersection
    return intersection / denominator if denominator > 0 else 0.0


def analyze(manifest_path: Path, csv_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = {str(item["image_id"]): item for item in manifest["items"]}
    if len(items) != manifest["case_count"]:
        raise ValueError("manifest has duplicate or missing cases")
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["image_id"]].append(row)
    if set(groups) != set(items):
        raise ValueError("CSV case IDs differ from frozen manifest")

    for image_id, case_rows in groups.items():
        item = items[image_id]
        candidates = {c["id"]: c for c in item["candidates"] if not c["primary"]}
        if {row["reviewed"] for row in case_rows} != {"1"}:
            raise ValueError(f"image {image_id} is not fully reviewed")
        if len({row["cause"] for row in case_rows}) != 1:
            raise ValueError(f"image {image_id} has conflicting causes")
        ids = [row["candidate_id"] for row in case_rows if row["candidate_id"]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"image {image_id} has duplicate candidate grades")
        for row in case_rows:
            if row["kind"] != item["kind"] or row["original_primary_grade"] != item["primary_grade"]:
                raise ValueError(f"image {image_id} metadata differs from manifest")
            candidate_id = row["candidate_id"]
            if candidate_id:
                if candidate_id not in candidates or row["provider"] != candidates[candidate_id]["provider"]:
                    raise ValueError(f"image {image_id} candidate differs from manifest")
                if row["candidate_grade"] not in {"usable", "poor_crop", "wrong_target", "unsure"}:
                    raise ValueError(f"image {image_id} has invalid candidate grade")
            elif row["provider"] or row["candidate_grade"]:
                raise ValueError(f"image {image_id} has incomplete candidate fields")
        if item["kind"] == "false_detection":
            if case_rows[0]["cause"] not in {"animal", "scene_texture", "other_object", "label_correction", "unsure"}:
                raise ValueError(f"image {image_id} has invalid false-detection cause")
            if ids:
                raise ValueError(f"image {image_id} has box grades on a false detection")
        elif item["kind"] == "bad_primary":
            if case_rows[0]["cause"] or set(ids) != set(candidates):
                raise ValueError(f"image {image_id} is missing an alternative grade")
        else:
            raise ValueError(f"image {image_id} has unknown kind")

    false_ids = [image_id for image_id, item in items.items() if item["kind"] == "false_detection"]
    bad_ids = [image_id for image_id, item in items.items() if item["kind"] == "bad_primary"]
    cause_counts = Counter(groups[image_id][0]["cause"] for image_id in false_ids)
    usable_by_provider = {}
    providers = sorted({row["provider"] for image_id in bad_ids for row in groups[image_id] if row["provider"]})
    for provider in providers:
        usable_by_provider[provider] = sum(any(row["provider"] == provider and row["candidate_grade"] == "usable"
                                               for row in groups[image_id]) for image_id in bad_ids)
    bad_with_usable = sum(any(row["candidate_grade"] == "usable" for row in groups[image_id]) for image_id in bad_ids)
    bad_with_no_alternatives = sum(len(items[image_id]["candidates"]) == 1 for image_id in bad_ids)
    by_original_grade = {}
    for grade in ("poor_crop", "wrong_target"):
        subset = [image_id for image_id in bad_ids if items[image_id]["primary_grade"] == grade]
        by_original_grade[grade] = {
            "cases": len(subset),
            "with_usable_alternative": sum(any(row["candidate_grade"] == "usable" for row in groups[image_id])
                                           for image_id in subset),
        }

    rtmdet_checks = {}
    for conf in (0.25, 0.40):
        for iou in (None, 0.50):
            key = f"conf_ge_{conf:.2f}" + ("_anywhere" if iou is None else f"_iou_ge_{iou:.2f}")
            count = 0
            for image_id in false_ids:
                item = items[image_id]
                primary = next(c["box"] for c in item["candidates"] if c["primary"])
                if any(c["provider"] == "RTMDet animal" and c["confidence"] >= conf
                       and (iou is None or _iou(primary, c["box"]) >= iou)
                       for c in item["candidates"]):
                    count += 1
            rtmdet_checks[key] = count

    grade_counts = Counter((row["provider"], row["candidate_grade"])
                           for image_id in bad_ids for row in groups[image_id] if row["candidate_id"])
    return {
        "manifest_sha256": _sha(manifest_path),
        "review_csv_sha256": _sha(csv_path),
        "case_count": len(items),
        "csv_rows": len(rows),
        "false_detection_count": len(false_ids),
        "false_detection_causes": dict(cause_counts),
        "bad_primary_count": len(bad_ids),
        "bad_primary_with_usable_alternative": bad_with_usable,
        "bad_primary_with_no_alternatives": bad_with_no_alternatives,
        "bad_primary_by_original_grade": by_original_grade,
        "bad_primary_usable_by_provider": usable_by_provider,
        "candidate_grade_rows": {f"{provider} | {grade}": count for (provider, grade), count in grade_counts.items()},
        "false_detection_rtmdet_frame_and_spatial_checks": rtmdet_checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.manifest, args.csv), indent=2))


if __name__ == "__main__":
    main()
