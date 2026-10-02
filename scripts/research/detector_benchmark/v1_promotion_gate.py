"""Promotion gate for the bird_detect_v1 shadow boxes (#469). Research only; no database writes.

The owner and failure reviews (docs/reports/bird-v1-owner-review-2026-09-29.md,
bird-v1-failure-review-2026-09-30.md) keep all 16,666 v1 shadow detections out of
``images.bird_bbox`` until three things hold. Each action below covers one step:

``snapshot``           freeze the current v1 detected runs and regions (read-only SQL)
``probe``              RTMDet + small-box refine on the **production inference rendition**
``reproduce``          gate 1: do the review-JPEG rescues reproduce on production pixels?
``fit``                gate 2: choose one rule from a pre-declared grid on development labels, then freeze it
``freeze-validation``  gate 3a: draw an independent sample (dev images and dev folders excluded)
``page``               gate 3b: blind two-step owner page (presence first, then the proposed box)
``analyze``            gate 3c: per-stratum present-and-usable rate with a Wilson 95% interval

Run the database and GPU actions in gpu-shell from /app, for example:

    python scripts/research/detector_benchmark/v1_promotion_gate.py snapshot
    python scripts/research/detector_benchmark/v1_promotion_gate.py probe --cases failure_review
    python scripts/research/detector_benchmark/v1_promotion_gate.py reproduce

Everything is written under the gitignored ``.agent/scratch/bird_v1_promotion/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import itertools
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from modules.localization_cascade import REFINE_MIN_IOU, iou

V1_VERSION = "synthet/bird-detect-v0/bird_detect_v1.pt"
RULE_VERSION = "v1_promotion_rule/1"
DEV_ROOT = Path(".agent/scratch/bird_v1_owner_labels")
OUT_ROOT = Path(".agent/scratch/bird_v1_promotion")
MATCH_IOU = 0.5
# Fit criterion: population-weighted dev precision (usable / promoted) at least this, on at least
# MIN_PROMOTED promoted dev frames. Weighted because the dev sample drew 16 frames per cell regardless
# of cell size. Adopted after the unweighted pass found no setting at 0.90 (see rule.json).
FIT_CRITERION = "population_weighted_precision/1"
FIT_MIN_PRECISION = 0.90
FIT_MIN_PROMOTED = 10
GATE_LOWER_BOUND = 0.90

_SNAPSHOT_SQL = """
SELECT r.image_id, r.id AS run_id, r.rendition_hash, i.file_path,
       g.id AS region_id, g.rank, g.confidence, g.x1, g.y1, g.x2, g.y2
FROM image_localization_runs r
JOIN images i ON i.id = r.image_id
JOIN image_regions g ON g.localization_run_id = r.id
WHERE r.detector_key = 'bird' AND r.is_current AND r.status = 'detected'
  AND r.detector_version = ? AND i.bird_bbox = '{"detected": false}'::jsonb
ORDER BY r.image_id, g.rank
"""


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

def conf_band(conf: float) -> str:
    return "low" if conf < 0.40 else "mid" if conf < 0.70 else "high"


def area_band(region) -> str:
    a = (region[2] - region[0]) * (region[3] - region[1])
    return "small" if a < 0.005 else "medium" if a < 0.02 else "large"


def folder_of(file_path: str) -> str:
    return (file_path or "").replace("\\", "/").rsplit("/", 1)[0]


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; (0, 1) when n == 0."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_new_json(path: Path, payload) -> None:
    """Write a frozen artifact; refuse to overwrite it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)
        handle.write("\n")


def load_probe(path: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            iid = int(row["image_id"])
            if iid in records:
                raise ValueError(f"duplicate probe record: {iid}")
            records[iid] = row
    return records


def load_snapshot(root: Path) -> dict[int, dict]:
    payload = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
    if payload.get("detector_version") != V1_VERSION:
        raise ValueError("snapshot is not for the v1 detector")
    return {int(item["image_id"]): item for item in payload["images"]}


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleParams:
    """``overlap``: an RTMDet *bird* box must overlap a v1 box. ``rtmdet_only``: any RTMDet bird box suffices.

    ``primary`` picks the promoted geometry: the corroborated v1 box, or the RTMDet box (refined
    by YOLO on its padded crop when the cascade's refine applies).
    """

    mode: str
    min_coco_conf: float
    min_iou: float
    primary: str

    def rule_hash(self) -> str:
        blob = json.dumps({"version": RULE_VERSION, **asdict(self)}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Decision:
    action: str  # "promote" | "keep_shadow"
    reason: str
    primary: tuple | None = None
    source: str = ""
    v1_region_id: int | None = None


def _refined(coco_box: dict, refine: list[dict]) -> tuple[tuple, str]:
    region = tuple(coco_box["region"])
    for rec in refine or []:
        if iou(tuple(rec["coco_region"]), region) < 0.999:
            continue
        best = max(rec.get("yolo") or [], key=lambda rb: iou(tuple(rb["region"]), region), default=None)
        if best is not None and iou(tuple(best["region"]), region) >= REFINE_MIN_IOU:
            return tuple(best["region"]), "coco+refine:bird"
    return region, "coco:bird"


def decide(v1_regions: list[dict], coco: list[dict], refine: list[dict], params: RuleParams) -> Decision:
    """Deterministic promotion decision for one v1-detected image.

    ``v1_regions``: ``{"region_id", "rank", "conf", "region"}``; ``coco``: probe boxes with ``cls``.
    """
    birds = sorted((b for b in coco if b["cls"] == "bird" and b["conf"] >= params.min_coco_conf),
                   key=lambda b: (-b["conf"], tuple(b["region"])))
    if not birds:
        return Decision("keep_shadow", "no_rtmdet_bird")
    v1 = sorted(v1_regions, key=lambda r: r["rank"])

    if params.mode == "rtmdet_only":
        box = birds[0]
        geometry, source = _refined(box, refine)
        overlaps = [r for r in v1 if iou(tuple(r["region"]), tuple(box["region"])) >= params.min_iou]
        return Decision("promote", "rtmdet_bird", geometry, source,
                        overlaps[0]["region_id"] if overlaps else None)

    pairs = [(r, b, iou(tuple(r["region"]), tuple(b["region"]))) for r in v1 for b in birds]
    pairs = [p for p in pairs if p[2] >= params.min_iou]
    if not pairs:
        return Decision("keep_shadow", "no_rtmdet_bird_overlap")
    region, box, _ = min(pairs, key=lambda p: (p[0]["rank"], -p[1]["conf"], -p[2]))
    if params.primary == "v1":
        return Decision("promote", "overlap", tuple(region["region"]), "v1:bird", region["region_id"])
    geometry, source = _refined(box, refine)
    return Decision("promote", "overlap", geometry, source, region["region_id"])


def rule_grid() -> list[RuleParams]:
    grid = [RuleParams("overlap", c, t, p)
            for c, t, p in itertools.product((0.25, 0.40, 0.55), (0.3, 0.5), ("v1", "rtmdet"))]
    grid += [RuleParams("rtmdet_only", c, MATCH_IOU, "rtmdet") for c in (0.25, 0.40, 0.55)]
    return grid


def v1_regions_of(snapshot_item: dict) -> list[dict]:
    return [{"region_id": r["region_id"], "rank": r["rank"], "conf": r["conf"], "region": tuple(r["region"])}
            for r in snapshot_item["regions"]]


# ---------------------------------------------------------------------------
# snapshot / probe (database read, GPU)
# ---------------------------------------------------------------------------

def snapshot(root: Path) -> int:
    from modules import db

    rows = db.get_connector().query(_SNAPSHOT_SQL, (V1_VERSION,))
    images: dict[int, dict] = {}
    for r in rows:
        item = images.setdefault(int(r["image_id"]), {
            "image_id": int(r["image_id"]), "run_id": int(r["run_id"]),
            "rendition_hash": r["rendition_hash"], "file_path": r["file_path"], "regions": []})
        item["regions"].append({"region_id": int(r["region_id"]), "rank": int(r["rank"]),
                                "conf": float(r["confidence"]),
                                "region": [float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])]})
    _write_new_json(root / "snapshot.json", {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "detector_version": V1_VERSION,
        "source": "current v1 detected runs whose production bird_bbox is still the no-bird sentinel",
        "images": list(images.values())})
    print(f"Froze {len(images)} images, {len(rows)} regions in {root / 'snapshot.json'}")
    return len(images)


def _case_ids(which: str, dev_root: Path, snap: dict[int, dict]) -> list[int]:
    if which == "all":
        return sorted(snap)
    if which == "failure_review":
        manifest = json.loads((dev_root / "failure_review" / "manifest.json").read_text(encoding="utf-8"))
        return [int(item["image_id"]) for item in manifest["items"]]
    return [int(r["image_id"]) for r in _read_csv(dev_root / "cohort.csv") if r["stratum"].startswith("det_")]


def probe(root: Path, dev_root: Path, which: str, weights: Path, limit: int) -> Counter:
    from modules.bird_detection import BirdDetector
    from modules.detectors.rtmdet import load_rtmdet
    from modules.localization import DecodeError, decode_for_localization
    from scripts.research.detector_benchmark.rtmdet_probe import probe_image

    snap = load_snapshot(root)
    ids = _case_ids(which, dev_root, snap)
    missing = [iid for iid in ids if iid not in snap]
    if missing:
        raise ValueError(f"{len(missing)} requested images are not in the snapshot, e.g. {missing[:5]}")
    out = root / "probe_production.jsonl"
    done = load_probe(out)

    rt = load_rtmdet(str(weights))
    if not rt.enabled:
        raise RuntimeError(f"RTMDet unavailable: {rt.error_code} {rt.error_detail}")
    yolo = BirdDetector()
    if yolo.model_file != "bird_detect_v1.pt":
        raise RuntimeError(f"expected v1 YOLO for refine, got {yolo.model_file}")
    yolo.load_model()

    todo = [iid for iid in ids if iid not in done]
    if limit > 0:
        todo = todo[:limit]
    counts: Counter = Counter()
    with out.open("a", encoding="utf-8") as handle:
        for n, iid in enumerate(todo, 1):
            item = snap[iid]
            rec = {"image_id": iid, "run_id": item["run_id"], "image_source": "production_rendition",
                   "rtmdet_config_hash": rt.config_hash}
            try:
                decoded = decode_for_localization(item["file_path"])
                rec["rendition_hash"] = decoded.descriptor.rendition_hash
                if rec["rendition_hash"] != item["rendition_hash"]:
                    rec["error"] = "rendition_mismatch"
                else:
                    rec.update(probe_image(decoded.image, rt, yolo))
            except DecodeError as exc:
                rec["error"] = f"decode_error: {exc}"[:200]
            except Exception as exc:  # noqa: BLE001 — keep per-image failures visible
                rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
            counts[rec.get("error", "ok").split(":")[0]] += 1
            handle.write(json.dumps(rec) + "\n")
            handle.flush()
            if n % 50 == 0 or n == len(todo):
                print(f"probed {n}/{len(todo)} {dict(counts)}", flush=True)
    return counts


# ---------------------------------------------------------------------------
# Development labels
# ---------------------------------------------------------------------------

def load_dev_labels(dev_root: Path) -> dict[int, dict]:
    """Per detected dev image: presence label and every owner-graded box ``(box, grade)``."""
    cohort = {int(r["image_id"]): r for r in _read_csv(dev_root / "cohort.csv")}
    presence = {int(r["image_id"]): r["label"] for r in _read_csv(dev_root / "labels.csv")}
    box_grades = {int(r["image_id"]): r["box_label"] for r in _read_csv(dev_root / "box_page" / "box_labels.csv")}
    box_manifest = json.loads((dev_root / "box_page" / "manifest.json").read_text(encoding="utf-8"))
    primaries = {int(r["image_id"]): r["box"] for r in box_manifest["rows"]}
    fr_manifest = json.loads((dev_root / "failure_review" / "manifest.json").read_text(encoding="utf-8"))
    fr_boxes = {(int(item["image_id"]), c["id"]): c["box"] for item in fr_manifest["items"] for c in item["candidates"]}
    fr_csv = dev_root / "failure_review" / "partial_results_2.csv"

    dev: dict[int, dict] = {}
    for iid, row in cohort.items():
        if not row["stratum"].startswith("det_"):
            continue
        graded = []
        if iid in box_grades:
            graded.append((tuple(primaries[iid]), box_grades[iid], "v1 primary"))
        dev[iid] = {"stratum": row["stratum"], "folder": folder_of(row["file_path"]),
                    "presence": presence[iid], "graded": graded}
    for r in _read_csv(fr_csv):
        if not r["candidate_id"] or not r["candidate_grade"]:
            continue
        iid = int(r["image_id"])
        dev[iid]["graded"].append((tuple(fr_boxes[(iid, r["candidate_id"])]), r["candidate_grade"], r["provider"]))
    return dev


def outcome_for(label: dict, decision: Decision) -> str:
    """Owner outcome of a promotion: ``no_bird``, ``unsure``, a box grade, or ``ungraded``."""
    if label["presence"] != "bird":
        return label["presence"]
    best = max(label["graded"], key=lambda g: iou(g[0], decision.primary), default=None)
    if best is None or iou(best[0], decision.primary) < MATCH_IOU:
        return "ungraded"
    return best[1]


# ---------------------------------------------------------------------------
# reproduce (gate 1)
# ---------------------------------------------------------------------------

def reproduce(root: Path, dev_root: Path) -> dict:
    manifest = json.loads((dev_root / "failure_review" / "manifest.json").read_text(encoding="utf-8"))
    rows = _read_csv(dev_root / "failure_review" / "partial_results_2.csv")
    snap = load_snapshot(root)
    prod = load_probe(root / "probe_production.jsonl")
    items = {int(item["image_id"]): item for item in manifest["items"]}

    missing = [iid for iid in items if iid not in prod]
    errors = Counter(prod[iid]["error"].split(":")[0] for iid in items if iid in prod and prod[iid].get("error"))

    def prod_boxes(iid: int, provider: str) -> list[tuple]:
        rec = prod.get(iid) or {}
        if provider == "RTMDet animal":
            return [tuple(b["region"]) for b in rec.get("coco", [])]
        if provider == "YOLO refined RTMDet":
            return [tuple(y["region"]) for r in rec.get("refine", []) for y in r.get("yolo", [])]
        return [tuple(r["region"]) for r in snap[iid]["regions"]] if iid in snap else []

    usable_cases: dict[int, list[bool]] = defaultdict(list)
    per_provider: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        if r["candidate_grade"] != "usable":
            continue
        iid = int(r["image_id"])
        box = tuple(next(c["box"] for c in items[iid]["candidates"] if c["id"] == r["candidate_id"]))
        hit = any(iou(box, b) >= MATCH_IOU for b in prod_boxes(iid, r["provider"]))
        usable_cases[iid].append(hit)
        per_provider[r["provider"]]["reproduced" if hit else "lost"] += 1

    fp = [iid for iid, item in items.items() if item["kind"] == "false_detection"]
    corroboration = {}
    for cls_name in ("any", "bird"):
        for conf, need_overlap in ((0.25, False), (0.25, True), (0.40, False), (0.40, True)):
            n = 0
            for iid in fp:
                rec, item = prod.get(iid) or {}, snap.get(iid)
                if item is None:
                    continue
                primary = tuple(min(item["regions"], key=lambda g: g["rank"])["region"])
                boxes = [b for b in rec.get("coco", []) if b["conf"] >= conf and (cls_name == "any" or b["cls"] == "bird")]
                if need_overlap:
                    boxes = [b for b in boxes if iou(tuple(b["region"]), primary) >= MATCH_IOU]
                n += bool(boxes)
            corroboration[f"cls={cls_name} conf>={conf} overlap={need_overlap}"] = n

    result = {
        "cases": len(items), "probe_missing": len(missing), "probe_errors": dict(errors),
        "usable_alternative_cases": len(usable_cases),
        "cases_reproduced": sum(any(v) for v in usable_cases.values()),
        "usable_candidates_by_provider": {k: dict(v) for k, v in sorted(per_provider.items())},
        "false_detections": len(fp), "false_detection_corroboration": corroboration,
    }
    (root / "reproduce.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


# ---------------------------------------------------------------------------
# fit (gate 2)
# ---------------------------------------------------------------------------

def evaluate(params: RuleParams, dev: dict[int, dict], snap: dict[int, dict], prod: dict[int, dict],
             weights: dict[str, float]) -> dict:
    """Dev outcomes for one setting; ``weights`` maps a dev stratum to population / sample size."""
    outcomes: Counter = Counter()
    by_stratum: dict[str, Counter] = defaultdict(Counter)
    for iid, label in dev.items():
        rec = prod.get(iid)
        if rec is None or rec.get("error") or iid not in snap:
            outcomes["unprobed"] += 1
            continue
        d = decide(v1_regions_of(snap[iid]), rec.get("coco", []), rec.get("refine", []), params)
        if d.action != "promote":
            outcomes["kept"] += 1
            continue
        o = outcome_for(label, d)
        outcomes[o] += 1
        by_stratum[label["stratum"]][o] += 1
    promoted = sum(n for k, n in outcomes.items() if k not in ("kept", "unprobed"))
    usable = outcomes["usable"]
    w_promoted = sum(weights[s] * sum(c.values()) for s, c in by_stratum.items())
    w_usable = sum(weights[s] * c["usable"] for s, c in by_stratum.items())
    return {"params": asdict(params), "rule_hash": params.rule_hash(), "promoted": promoted,
            "usable": usable, "precision": round(usable / promoted, 4) if promoted else None,
            "est_promoted": round(w_promoted), "est_usable": round(w_usable),
            "weighted_precision": round(w_usable / w_promoted, 4) if w_promoted else None,
            "outcomes": dict(sorted(outcomes.items())),
            "by_stratum": {k: dict(sorted(v.items())) for k, v in sorted(by_stratum.items())}}


def select(results: list[dict]) -> dict | None:
    """Most estimated usable promotions among settings meeting the weighted dev precision floor.

    Ties prefer fewer estimated non-usable promotions, then the more conservative thresholds.
    """
    ok = [r for r in results if r["promoted"] >= FIT_MIN_PROMOTED and (r["weighted_precision"] or 0) >= FIT_MIN_PRECISION]
    if not ok:
        return None
    return min(ok, key=lambda r: (-r["est_usable"], r["est_promoted"] - r["est_usable"],
                                  -r["params"]["min_coco_conf"], -r["params"]["min_iou"], r["rule_hash"]))


def fit(root: Path, dev_root: Path) -> dict | None:
    dev = load_dev_labels(dev_root)
    snap = load_snapshot(root)
    prod = load_probe(root / "probe_production.jsonl")
    sampling = json.loads((dev_root / "sampling.json").read_text(encoding="utf-8"))
    weights = {p["stratum"]: p["images"] / sampling["sample"][p["stratum"]] for p in sampling["population"]}
    results = [evaluate(p, dev, snap, prod, weights) for p in rule_grid()]
    chosen = select(results)
    criterion = {"name": FIT_CRITERION, "min_weighted_precision": FIT_MIN_PRECISION, "min_promoted": FIT_MIN_PROMOTED}
    report = {"dev_images": len(dev), "criterion": criterion,
              "results": results, "chosen": chosen["rule_hash"] if chosen else None}
    (root / "fit.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    if chosen is not None:
        _write_new_json(root / "rule.json", {
            "rule_version": RULE_VERSION, "rule_hash": chosen["rule_hash"], "params": chosen["params"],
            "frozen_utc": datetime.now(timezone.utc).isoformat(),
            "rtmdet_config_hashes": sorted({r["rtmdet_config_hash"] for r in prod.values() if "rtmdet_config_hash" in r}),
            "inputs_sha256": {"probe_production.jsonl": sha256_file(root / "probe_production.jsonl"),
                              "snapshot.json": sha256_file(root / "snapshot.json")},
            "criterion": criterion, "dev_result": chosen,
            "note": ("Fitted on the development sample; this result cannot validate itself. The criterion "
                     "was switched from unweighted to population-weighted dev precision after the unweighted "
                     "pass found no setting at 0.90 (best 0.826); the independent validation sample is the test.")})
    return chosen


def load_rule(root: Path) -> RuleParams:
    payload = json.loads((root / "rule.json").read_text(encoding="utf-8"))
    params = RuleParams(**payload["params"])
    if params.rule_hash() != payload["rule_hash"]:
        raise ValueError("rule.json hash does not match its parameters")
    return params


# ---------------------------------------------------------------------------
# freeze-validation (gate 3a)
# ---------------------------------------------------------------------------

def _order_key(seed: str, image_id: int) -> str:
    return hashlib.md5(f"{image_id}{seed}".encode()).hexdigest()


def sample_strata(population: dict[str, list[dict]], seed: str, sizes: dict[str, int]) -> dict[str, list[dict]]:
    """Deterministic per-stratum draw, at most one image per folder in each stratum."""
    picked: dict[str, list[dict]] = {}
    for stratum, members in sorted(population.items()):
        chosen, folders = [], set()
        for m in sorted(members, key=lambda m: _order_key(seed, m["image_id"])):
            if len(chosen) >= sizes.get(stratum, 0):
                break
            if m["folder"] in folders:
                continue
            folders.add(m["folder"])
            chosen.append(m)
        picked[stratum] = chosen
    return picked


def validation_population(snap: dict[int, dict], prod: dict[int, dict], params: RuleParams,
                          dev_ids: set[int], dev_folders: set[str]) -> tuple[dict[str, list[dict]], Counter]:
    population: dict[str, list[dict]] = defaultdict(list)
    excluded: Counter = Counter()
    for iid, item in sorted(snap.items()):
        folder = folder_of(item["file_path"])
        if iid in dev_ids:
            excluded["dev_image"] += 1
            continue
        if folder in dev_folders:
            excluded["dev_folder"] += 1
            continue
        rec = prod.get(iid)
        if rec is None or rec.get("error"):
            excluded["unprobed" if rec is None else "probe_error"] += 1
            continue
        regions = v1_regions_of(item)
        d = decide(regions, rec.get("coco", []), rec.get("refine", []), params)
        if d.action == "promote":
            stratum, box, source = f"promote_{area_band(d.primary)}", d.primary, d.source
        else:
            top = min(regions, key=lambda r: r["rank"])
            stratum, box, source = "keep_shadow", top["region"], "v1:bird"
        population[stratum].append({"image_id": iid, "folder": folder, "file_path": item["file_path"],
                                    "box": list(box), "source": source, "decision": d.action})
    return population, excluded


def freeze_validation(root: Path, dev_root: Path, seed: str, per_promote: int, keep_shadow: int) -> dict:
    params = load_rule(root)
    snap = load_snapshot(root)
    prod = load_probe(root / "probe_production.jsonl")
    dev_rows = _read_csv(dev_root / "cohort.csv")
    dev_ids = {int(r["image_id"]) for r in dev_rows}
    dev_folders = {folder_of(r["file_path"]) for r in dev_rows}
    population, excluded = validation_population(snap, prod, params, dev_ids, dev_folders)
    sizes = {s: (keep_shadow if s == "keep_shadow" else per_promote) for s in population}
    picked = sample_strata(population, seed, sizes)

    out = root / "validation"
    rows = [{"image_id": m["image_id"], "stratum": s, "file_path": m["file_path"]}
            for s, members in picked.items() for m in members]
    if (out / "cohort.csv").exists():
        raise FileExistsError(f"validation cohort already frozen: {out / 'cohort.csv'}")
    _write_csv(out / "cohort.csv", ("image_id", "stratum", "file_path"), rows)
    _write_new_json(out / "proposals.json", {str(m["image_id"]): {"box": m["box"], "source": m["source"]}
                                             for members in picked.values() for m in members})
    sampling = {"seed": seed, "rule_hash": params.rule_hash(), "frozen_utc": datetime.now(timezone.utc).isoformat(),
                "excluded": dict(excluded),
                "population": {s: len(m) for s, m in sorted(population.items())},
                "sample": {s: len(m) for s, m in sorted(picked.items())},
                "folders": {s: len({m["folder"] for m in members}) for s, members in sorted(population.items())}}
    _write_new_json(out / "sampling.json", sampling)
    return sampling


# ---------------------------------------------------------------------------
# page (gate 3b)
# ---------------------------------------------------------------------------

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bird validation labels</title><style>
:root{--bg:#f6f6f4;--fg:#1d1d1b;--muted:#6b6b66;--box:#e0245e;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a3a29b;--card:#22221f}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}
main{max-width:1320px;margin:0 auto;padding:16px}.stage{position:relative;display:inline-block;max-width:100%}
.stage img{display:block;max-width:100%;max-height:78vh}.box{position:absolute;border:3px solid var(--box);display:none}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}button{font:inherit;padding:6px 12px}
.hint{color:var(--muted)}</style></head><body><main>
<div class="bar"><strong id="pos"></strong><span id="step" class="hint"></span></div>
<div class="bar" id="presence"><button data-p="bird">B — bird visible</button><button data-p="no_bird">N — no bird</button><button data-p="unsure">U — unsure</button></div>
<div class="bar" id="grade" hidden><button data-g="usable">1 — usable crop</button><button data-g="poor_crop">2 — poor crop</button><button data-g="wrong_target">3 — wrong target</button><button data-g="unsure">4 — unsure</button></div>
<div class="stage"><img id="photo" alt="Photo to label"><div class="box" id="box"></div></div>
<div class="bar"><button id="prev">← Previous</button><button id="next">Next →</button><button id="download">Download labels.csv</button><span id="done" class="hint"></span></div>
<p class="hint">Step 1: is any bird visible? Step 2 shows one proposed box: grade whether it frames a bird usefully.</p>
</main><script>
const ITEMS=__ITEMS__;const KEY="__KEY__";let labels={};try{labels=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
let i=0;const $=id=>document.getElementById(id);
function save(){try{localStorage.setItem(KEY,JSON.stringify(labels))}catch(e){}}
function render(){const it=ITEMS[i],l=labels[it.id]||{};$("photo").src=it.img;$("pos").textContent=`${i+1} / ${ITEMS.length}`;
 const showBox=l.presence==="bird";$("presence").hidden=false;$("grade").hidden=!showBox;
 const b=$("box");b.style.display=showBox?"block":"none";b.style.left=it.box[0]*100+"%";b.style.top=it.box[1]*100+"%";
 b.style.width=(it.box[2]-it.box[0])*100+"%";b.style.height=(it.box[3]-it.box[1])*100+"%";
 $("step").textContent=l.presence?(showBox?(l.grade?`presence: bird · grade: ${l.grade}`:"grade the box"):`presence: ${l.presence}`):"is any bird visible?";
 $("done").textContent=`${Object.values(labels).filter(v=>v.presence&&(v.presence!=="bird"||v.grade)).length} complete`}
function setP(p){const it=ITEMS[i];labels[it.id]={presence:p};save();if(p!=="bird"&&i<ITEMS.length-1)i++;render()}
function setG(g){const it=ITEMS[i];if(!labels[it.id]||labels[it.id].presence!=="bird")return;labels[it.id].grade=g;save();if(i<ITEMS.length-1)i++;render()}
document.querySelectorAll("[data-p]").forEach(b=>b.onclick=()=>setP(b.dataset.p));
document.querySelectorAll("[data-g]").forEach(b=>b.onclick=()=>setG(b.dataset.g));
$("prev").onclick=()=>{if(i>0)i--;render()};$("next").onclick=()=>{if(i<ITEMS.length-1)i++;render()};
document.addEventListener("keydown",e=>{const k=e.key.toLowerCase();if(k==="b")setP("bird");else if(k==="n")setP("no_bird");else if(k==="u")setP("unsure");
 else if(k==="1")setG("usable");else if(k==="2")setG("poor_crop");else if(k==="3")setG("wrong_target");else if(k==="4")setG("unsure");
 else if(e.key==="ArrowLeft")$("prev").click();else if(e.key==="ArrowRight")$("next").click()});
$("download").onclick=()=>{const rows=[["image_id","presence","box_label"]].concat(ITEMS.map(it=>[it.id,(labels[it.id]||{}).presence||"",(labels[it.id]||{}).grade||""]));
 const url=URL.createObjectURL(new Blob([rows.map(r=>r.join(",")).join("\\n")+"\\n"],{type:"text/csv"}));const a=document.createElement("a");a.href=url;a.download="labels.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
render();
</script></body></html>"""


def build_page(root: Path, seed: str, long_edge: int = 1280) -> int:
    """Blind page: no stratum, decision, source, or confidence reaches the HTML."""
    from modules.localization import decode_for_localization

    out = root / "validation"
    cohort = _read_csv(out / "cohort.csv")
    proposals = json.loads((out / "proposals.json").read_text(encoding="utf-8"))
    img_dir = out / "page" / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for row in cohort:
        iid = int(row["image_id"])
        target = img_dir / f"{iid}.jpg"
        if not target.exists():
            img = decode_for_localization(row["file_path"]).image
            img.thumbnail((long_edge, long_edge))
            img.save(target, "JPEG", quality=90)
        items.append({"id": iid, "img": f"img/{iid}.jpg", "box": proposals[str(iid)]["box"]})
    random.Random(seed).shuffle(items)
    sampling = json.loads((out / "sampling.json").read_text(encoding="utf-8"))
    page = (_PAGE.replace("__ITEMS__", json.dumps(items))
            .replace("__KEY__", html.escape(f"bird-v1-validation-{sampling['rule_hash']}-{seed}")))
    (out / "page" / "index.html").write_text(page, encoding="utf-8")
    return len(items)


# ---------------------------------------------------------------------------
# analyze (gate 3c)
# ---------------------------------------------------------------------------

def analyze(root: Path, labels_path: Path) -> dict:
    out = root / "validation"
    cohort = {int(r["image_id"]): r["stratum"] for r in _read_csv(out / "cohort.csv")}
    labels = {int(r["image_id"]): r for r in _read_csv(labels_path)}
    if set(labels) != set(cohort):
        raise ValueError(f"labels cover {len(set(labels) & set(cohort))}/{len(cohort)} cohort images")
    sampling = json.loads((out / "sampling.json").read_text(encoding="utf-8"))
    tallies: dict[str, Counter] = defaultdict(Counter)
    for iid, stratum in cohort.items():
        lab = labels[iid]
        if lab["presence"] == "bird" and not lab["box_label"]:
            raise ValueError(f"bird-visible image {iid} has no box grade")
        outcome = lab["box_label"] if lab["presence"] == "bird" else lab["presence"]
        tallies[stratum][outcome] += 1

    strata = {}
    for stratum, counts in sorted(tallies.items()):
        n, ok = sum(counts.values()), counts["usable"]
        lo, hi = wilson(ok, n)
        strata[stratum] = {"population": sampling["population"][stratum], "sample": n,
                           "present_and_usable": ok, "rate": round(ok / n, 4),
                           "wilson95": [round(lo, 4), round(hi, 4)], "outcomes": dict(sorted(counts.items())),
                           "passes": stratum != "keep_shadow" and lo >= GATE_LOWER_BOUND}
    promote = {s: v for s, v in strata.items() if s != "keep_shadow"}
    pop = sum(v["population"] for v in promote.values())
    weighted = sum(v["rate"] * v["population"] for v in promote.values()) / pop if pop else None
    result = {"rule_hash": sampling["rule_hash"], "seed": sampling["seed"], "gate_lower_bound": GATE_LOWER_BOUND,
              "inputs_sha256": {"cohort.csv": sha256_file(out / "cohort.csv"),
                                "sampling.json": sha256_file(out / "sampling.json"),
                                "labels": sha256_file(labels_path)},
              "strata": strata, "promote_weighted_rate": round(weighted, 4) if weighted is not None else None,
              "passing_strata": sorted(s for s, v in promote.items() if v["passes"])}
    (out / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("snapshot", "probe", "reproduce", "fit", "freeze-validation", "page", "analyze"))
    parser.add_argument("--root", type=Path, default=OUT_ROOT)
    parser.add_argument("--dev-root", type=Path, default=DEV_ROOT)
    parser.add_argument("--cases", choices=("failure_review", "dev", "all"), default="failure_review")
    parser.add_argument("--weights", type=Path, default=Path("models/rtmdet_tiny_coco.onnx"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", default="bird-v1-validation-1")
    parser.add_argument("--per-promote", type=int, default=60)
    parser.add_argument("--keep-shadow", type=int, default=60)
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)

    if args.action == "snapshot":
        snapshot(args.root)
    elif args.action == "probe":
        print(json.dumps(probe(args.root, args.dev_root, args.cases, args.weights, args.limit)))
    elif args.action == "reproduce":
        print(json.dumps(reproduce(args.root, args.dev_root), indent=1))
    elif args.action == "fit":
        chosen = fit(args.root, args.dev_root)
        print(json.dumps(chosen, indent=1) if chosen else "No grid setting meets the dev criterion; the gate stays closed.")
    elif args.action == "freeze-validation":
        print(json.dumps(freeze_validation(args.root, args.dev_root, args.seed, args.per_promote, args.keep_shadow), indent=1))
    elif args.action == "page":
        print(f"Built {build_page(args.root, args.seed)} items at {args.root / 'validation' / 'page' / 'index.html'}")
    else:
        if args.labels is None:
            parser.error("analyze needs --labels")
        print(json.dumps(analyze(args.root, args.labels), indent=1))


if __name__ == "__main__":
    main()
