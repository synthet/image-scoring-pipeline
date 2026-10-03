"""Re-gate the v1 shadow boxes with the scene route as a false-positive filter (#472).

Step 2 of #472: fit the pre-declared ``v1_regate_rule/1`` family on development data only
(the #387 dev sample and the #469 validation sample, which has now been seen). The family,
estimator and selection rule were posted to #472 before this ran; see
``.agent/scratch/bird_v1_regate/PREDECLARATION.md``. Reads the database (scene labels) and the
frozen #469 artifacts; writes only ``fit.json`` / ``rule.json`` under ``--out``.

    python scripts/research/detector_benchmark/v1_regate.py fit
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.research.detector_benchmark.v1_promotion_gate import (  # noqa: E402
    DEV_ROOT,
    OUT_ROOT,
    Decision,
    RuleParams,
    _read_csv,
    _write_csv,
    _write_new_json,
    area_band,
    decide,
    folder_of,
    load_dev_labels,
    load_probe,
    load_rule,
    load_snapshot,
    outcome_for,
    sample_strata,
    sha256_file,
    v1_regions_of,
)

RULE_VERSION = "v1_regate_rule/1"
SCENE_VERSION = "scene_v2/siglip2_base/f497b4a991ec716d"
SCENE_LABEL = "wildlife_bird"
REGATE_ROOT = Path(".agent/scratch/bird_v1_regate")
THRESHOLDS = tuple(round(0.03 + 0.01 * i, 2) for i in range(13))
CORROBORATION = ("none", "rtmdet")
MIN_AREAS = (0.0, 0.005, 0.01)
MIN_COMBINED_PRECISION = 0.90
MIN_DESIGN_PRECISION = 0.85
MIN_PROMOTED_PER_DESIGN = 10
COHORT = 16666


@dataclass(frozen=True)
class RegateParams:
    threshold: float
    corroboration: str
    min_area: float

    def rule_hash(self) -> str:
        blob = json.dumps({"version": RULE_VERSION, "scene_version": SCENE_VERSION, **asdict(self)}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def decide(self, snap_item: dict, probe: dict | None, p_bird: float | None, frozen) -> Decision:
        return regate(snap_item, probe, p_bird, self, frozen)


def grid() -> list[RegateParams]:
    return [RegateParams(t, c, a) for t, c, a in itertools.product(THRESHOLDS, CORROBORATION, MIN_AREAS)]


def box_area(region) -> float:
    return max(0.0, region[2] - region[0]) * max(0.0, region[3] - region[1])


def regate(snap_item: dict, probe: dict | None, p_bird: float | None, params: RegateParams, frozen) -> Decision:
    """Deterministic re-gate decision for one v1-detected image."""
    if p_bird is None:
        return Decision("keep_shadow", "no_scene_label")
    if p_bird < params.threshold:
        return Decision("keep_shadow", "scene_not_bird")
    if params.corroboration == "rtmdet":
        if probe is None or probe.get("error"):
            return Decision("keep_shadow", "unprobed")
        d = decide(v1_regions_of(snap_item), probe.get("coco", []), probe.get("refine", []), frozen)
        if d.action != "promote":
            return Decision("keep_shadow", "no_rtmdet_corroboration")
        geometry, source = d.primary, d.source
    else:
        v1 = sorted(v1_regions_of(snap_item), key=lambda r: r["rank"])
        if not v1:
            return Decision("keep_shadow", "no_v1_box")
        geometry, source = tuple(v1[0]["region"]), "v1:bird"
    if box_area(geometry) < params.min_area:
        return Decision("keep_shadow", "box_too_small")
    return Decision("promote", "scene_route", geometry, source)


def load_validation_labels(promotion_root: Path) -> tuple[dict[int, dict], dict[str, float], int]:
    """#469 validation sample as dev labels: presence + the grade of its proposed box."""
    v = promotion_root / "validation"
    sampling = json.loads((v / "sampling.json").read_text(encoding="utf-8"))
    proposals = json.loads((v / "proposals.json").read_text(encoding="utf-8"))
    cohort = {int(r["image_id"]): r for r in _read_csv(v / "cohort.csv")}
    labels: dict[int, dict] = {}
    for r in _read_csv(v / "labels.csv"):
        iid = int(r["image_id"])
        graded = []
        if r["presence"] == "bird" and r["box_label"]:
            graded.append((tuple(proposals[str(iid)]["box"]), r["box_label"], proposals[str(iid)]["source"]))
        labels[iid] = {"stratum": cohort[iid]["stratum"], "folder": folder_of(cohort[iid]["file_path"]),
                       "presence": r["presence"], "graded": graded}
    weights = {s: sampling["population"][s] / sampling["sample"][s] for s in sampling["population"]}
    return labels, weights, sum(sampling["population"].values())


def load_scene_probs(image_ids, scene_version: str = SCENE_VERSION) -> dict[int, float]:
    from modules import db

    ids = sorted({int(i) for i in image_ids})
    out: dict[int, float] = {}
    for start in range(0, len(ids), 1000):
        chunk = ids[start:start + 1000]
        rows = db.get_connector().query(
            f"SELECT image_id, probs FROM image_scene_labels WHERE scene_version = ? "
            f"AND image_id IN ({','.join('?' * len(chunk))})",
            (scene_version, *chunk),
        )
        for r in rows or []:
            probs = r["probs"] if isinstance(r["probs"], dict) else json.loads(r["probs"])
            out[int(r["image_id"])] = float(probs[SCENE_LABEL])
    return out


def evaluate_design(params, labels, weights, snap, prod, scene, frozen) -> dict:
    outcomes: Counter = Counter()
    by_stratum: dict[str, Counter] = defaultdict(Counter)
    for iid, label in labels.items():
        if iid not in snap:
            outcomes["not_in_snapshot"] += 1
            continue
        d = params.decide(snap[iid], prod.get(iid), scene.get(iid), frozen)
        if d.action != "promote":
            outcomes[f"kept:{d.reason}"] += 1
            continue
        o = outcome_for(label, d)
        outcomes[o] += 1
        by_stratum[label["stratum"]][o] += 1
    promoted = sum(sum(c.values()) for c in by_stratum.values())
    w_promoted = sum(weights[s] * sum(c.values()) for s, c in by_stratum.items())
    w_usable = sum(weights[s] * c["usable"] for s, c in by_stratum.items())
    return {"promoted": promoted, "usable": sum(c["usable"] for c in by_stratum.values()),
            "weighted_precision": round(w_usable / w_promoted, 4) if w_promoted else None,
            "est_promoted": w_promoted, "est_usable": w_usable,
            "outcomes": dict(sorted(outcomes.items())),
            "by_stratum": {k: dict(sorted(v.items())) for k, v in sorted(by_stratum.items())}}


def combine(params, dev: dict, val: dict, val_population: int,
            floors: tuple[float, float, int] = (MIN_COMBINED_PRECISION, MIN_DESIGN_PRECISION,
                                                MIN_PROMOTED_PER_DESIGN)) -> dict:
    min_combined, min_design, min_promoted = floors
    scale = COHORT / val_population
    precisions = [dev["weighted_precision"], val["weighted_precision"]]
    combined = round(sum(precisions) / 2, 4) if None not in precisions else None
    est_usable = (dev["est_usable"] + val["est_usable"] * scale) / 2
    est_promoted = (dev["est_promoted"] + val["est_promoted"] * scale) / 2
    eligible = (combined is not None and combined >= min_combined
                and min(precisions) >= min_design
                and min(dev["promoted"], val["promoted"]) >= min_promoted)
    return {"params": asdict(params), "rule_hash": params.rule_hash(), "eligible": eligible,
            "combined_weighted_precision": combined, "est_usable": round(est_usable),
            "est_promoted": round(est_promoted), "dev": dev, "validation": val}


def select(results: list[dict]) -> dict | None:
    ok = [r for r in results if r["eligible"]]
    if not ok:
        return None
    return min(ok, key=lambda r: (-r["est_usable"], r["est_promoted"] - r["est_usable"],
                                  -r["params"]["threshold"], r["params"]["corroboration"] != "rtmdet",
                                  -r["params"]["min_area"], r["rule_hash"]))


def fit(promotion_root: Path, dev_root: Path, out: Path) -> dict | None:
    snap = load_snapshot(promotion_root)
    prod = load_probe(promotion_root / "probe_production.jsonl")
    frozen = load_rule(promotion_root)
    dev = load_dev_labels(dev_root)
    dev_sampling = json.loads((dev_root / "sampling.json").read_text(encoding="utf-8"))
    dev_weights = {p["stratum"]: p["images"] / dev_sampling["sample"][p["stratum"]] for p in dev_sampling["population"]}
    val, val_weights, val_population = load_validation_labels(promotion_root)
    scene = load_scene_probs(list(dev) + list(val))
    coverage = {"dev": f"{sum(i in scene for i in dev)}/{len(dev)}",
                "validation": f"{sum(i in scene for i in val)}/{len(val)}"}
    results = []
    for params in grid():
        d = evaluate_design(params, dev, dev_weights, snap, prod, scene, frozen)
        v = evaluate_design(params, val, val_weights, snap, prod, scene, frozen)
        results.append(combine(params, d, v, val_population))
    chosen = select(results)
    report = {"rule_version": RULE_VERSION, "scene_version": SCENE_VERSION, "scene_coverage": coverage,
              "criterion": {"min_combined_weighted_precision": MIN_COMBINED_PRECISION,
                            "min_design_weighted_precision": MIN_DESIGN_PRECISION,
                            "min_promoted_per_design": MIN_PROMOTED_PER_DESIGN},
              "settings": len(results), "eligible": sum(r["eligible"] for r in results),
              "chosen": chosen["rule_hash"] if chosen else None, "results": results}
    out.mkdir(parents=True, exist_ok=True)
    (out / "fit.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    if chosen is not None:
        _write_new_json(out / "rule.json", {
            "rule_version": RULE_VERSION, "scene_version": SCENE_VERSION, "rule_hash": chosen["rule_hash"],
            "params": chosen["params"], "frozen_utc": datetime.now(timezone.utc).isoformat(),
            "inputs_sha256": {name: sha256_file(promotion_root / name)
                              for name in ("snapshot.json", "probe_production.jsonl", "rule.json")},
        })
    return chosen


# ---------------------------------------------------------------------------
# option (b): v1_regate_rule/2 — narrower sub-population (pre-declared on #472)
# ---------------------------------------------------------------------------

RULE_VERSION_B = "v1_regate_rule/2"
RULE_VERSION_C = "v1_regate_rule/3"
SCENE_VERSION_V3 = "scene_v3/siglip2_base/91179fd7133da642"
B_CONF = (0.55, 0.60, 0.65, 0.70, 0.75)
B_MAX_BIRDS = (1, 2, 3, None)
B_THRESHOLDS = (0.05, 0.50, 0.90)
B_BIRD_COUNT_CONF = 0.25
B_FLOORS = (0.95, 0.90, 10)


@dataclass(frozen=True)
class SubsetParams:
    min_rt_conf: float
    max_rt_birds: int | None
    threshold: float

    RULE_VERSION = RULE_VERSION_B
    SCENE_VERSION = SCENE_VERSION

    def rule_hash(self) -> str:
        blob = json.dumps({"version": self.RULE_VERSION, "scene_version": self.SCENE_VERSION, **asdict(self)},
                          sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def decide(self, snap_item: dict, probe: dict | None, p_bird: float | None, frozen=None) -> Decision:
        if p_bird is None:
            return Decision("keep_shadow", "no_scene_label")
        if p_bird < self.threshold:
            return Decision("keep_shadow", "scene_not_bird")
        if probe is None or probe.get("error"):
            return Decision("keep_shadow", "unprobed")
        coco = probe.get("coco", [])
        n_birds = sum(1 for b in coco if b["cls"] == "bird" and b["conf"] >= B_BIRD_COUNT_CONF)
        if self.max_rt_birds is not None and n_birds > self.max_rt_birds:
            return Decision("keep_shadow", "too_many_birds")
        d = decide(v1_regions_of(snap_item), coco, probe.get("refine", []),
                   RuleParams("rtmdet_only", self.min_rt_conf, 0.5, "rtmdet"))
        if d.action != "promote":
            return Decision("keep_shadow", "rtmdet_below_conf")
        return Decision("promote", "subset", d.primary, d.source)


class SubsetParamsV3(SubsetParams):
    """``v1_regate_rule/3``: the ``/2`` family with ``p(wildlife_bird)`` from ``scene_v3`` (orca fix)."""

    RULE_VERSION = RULE_VERSION_C
    SCENE_VERSION = SCENE_VERSION_V3


def grid_b(cls: type[SubsetParams] = SubsetParams) -> list[SubsetParams]:
    return [cls(c, k, t) for c, k, t in itertools.product(B_CONF, B_MAX_BIRDS, B_THRESHOLDS)]


def select_b(results: list[dict]) -> dict | None:
    ok = [r for r in results if r["eligible"]]
    if not ok:
        return None
    big = 10**6
    return min(ok, key=lambda r: (-r["est_usable"], r["est_promoted"] - r["est_usable"],
                                  -r["params"]["min_rt_conf"],
                                  r["params"]["max_rt_birds"] if r["params"]["max_rt_birds"] is not None else big,
                                  -r["params"]["threshold"], r["rule_hash"]))


def fit_b(promotion_root: Path, dev_root: Path, out: Path, cls: type[SubsetParams] = SubsetParams,
          name: str = "b") -> dict | None:
    snap = load_snapshot(promotion_root)
    prod = load_probe(promotion_root / "probe_production.jsonl")
    dev = load_dev_labels(dev_root)
    dev_sampling = json.loads((dev_root / "sampling.json").read_text(encoding="utf-8"))
    dev_weights = {p["stratum"]: p["images"] / dev_sampling["sample"][p["stratum"]] for p in dev_sampling["population"]}
    val, val_weights, val_population = load_validation_labels(promotion_root)
    scene = load_scene_probs(list(dev) + list(val), cls.SCENE_VERSION)
    missing = [i for i in list(dev) + list(val) if i not in scene]
    if missing:
        raise ValueError(f"{len(missing)} labelled images have no {cls.SCENE_VERSION} scene label")
    results = []
    for params in grid_b(cls):
        d = evaluate_design(params, dev, dev_weights, snap, prod, scene, None)
        v = evaluate_design(params, val, val_weights, snap, prod, scene, None)
        results.append(combine(params, d, v, val_population, B_FLOORS))
    chosen = select_b(results)
    report = {"rule_version": cls.RULE_VERSION, "scene_version": cls.SCENE_VERSION,
              "criterion": dict(zip(("min_combined_weighted_precision", "min_design_weighted_precision",
                                     "min_promoted_per_design"), B_FLOORS)),
              "settings": len(results), "eligible": sum(r["eligible"] for r in results),
              "chosen": chosen["rule_hash"] if chosen else None, "results": results}
    out.mkdir(parents=True, exist_ok=True)
    (out / f"fit_{name}.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    if chosen is not None:
        _write_new_json(out / f"rule_{name}.json", {
            "rule_version": cls.RULE_VERSION, "scene_version": cls.SCENE_VERSION, "rule_hash": chosen["rule_hash"],
            "params": chosen["params"], "frozen_utc": datetime.now(timezone.utc).isoformat(),
            "inputs_sha256": {name: sha256_file(promotion_root / name)
                              for name in ("snapshot.json", "probe_production.jsonl")},
        })
    return chosen


# ---------------------------------------------------------------------------
# agent-sample: AI pre-screen of the frozen rule (not a gate; owner labels stay the gate)
# ---------------------------------------------------------------------------

def load_regate_rule(out: Path) -> RegateParams:
    payload = json.loads((out / "rule.json").read_text(encoding="utf-8"))
    params = RegateParams(**payload["params"])
    if params.rule_hash() != payload["rule_hash"]:
        raise ValueError("rule.json hash does not match its parameters")
    return params


def _render(file_path: str, box, target: Path, crop_target: Path, long_edge: int = 1280) -> None:
    from PIL import ImageDraw

    from modules.localization import decode_for_localization

    img = decode_for_localization(file_path).image.convert("RGB")
    w, h = img.size
    x1, y1, x2, y2 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    bw, bh = x2 - x1, y2 - y1
    pad = max(bw, bh, 0.08 * max(w, h))
    crop = img.crop((max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)))
    cdraw = ImageDraw.Draw(crop)
    ox, oy = max(0, x1 - pad), max(0, y1 - pad)
    cdraw.rectangle((x1 - ox, y1 - oy, x2 - ox, y2 - oy), outline=(255, 0, 0), width=max(2, crop.width // 200))
    crop.thumbnail((768, 768))
    if max(crop.size) < 512:
        scale = 512 / max(crop.size)
        crop = crop.resize((round(crop.width * scale), round(crop.height * scale)))
    crop.save(crop_target, "JPEG", quality=90)
    draw = ImageDraw.Draw(img)
    draw.rectangle((x1, y1, x2, y2), outline=(255, 0, 0), width=max(3, w // 300))
    img.thumbnail((long_edge, long_edge))
    img.save(target, "JPEG", quality=90)


def agent_sample(promotion_root: Path, dev_root: Path, out: Path, seed: str, per_band: int, calib: int,
                 allow_seen_folders: bool = False) -> dict:
    """Unlabelled promotions + owner-labelled calibration items, rendered blind.

    Owner-labelled images are always excluded. Their folders are too, unless ``allow_seen_folders``
    (fine for an AI pre-screen, which is not the owner gate).
    """
    snap = load_snapshot(promotion_root)
    prod = load_probe(promotion_root / "probe_production.jsonl")
    frozen = load_rule(promotion_root)
    params = load_regate_rule(out)
    scene = load_scene_probs(snap)
    dev_rows = _read_csv(dev_root / "cohort.csv")
    val_labels, _, _ = load_validation_labels(promotion_root)
    fr_ids = {int(i["image_id"]) for i in json.loads(
        (dev_root / "failure_review" / "manifest.json").read_text(encoding="utf-8"))["items"]}
    seen_ids = {int(r["image_id"]) for r in dev_rows} | set(load_dev_labels(dev_root)) | set(val_labels) | fr_ids
    seen_folders = ({folder_of(r["file_path"]) for r in dev_rows} | {v["folder"] for v in val_labels.values()}
                    | {folder_of(snap[i]["file_path"]) for i in fr_ids if i in snap})

    population: dict[str, list[dict]] = defaultdict(list)
    for iid, item in sorted(snap.items()):
        folder = folder_of(item["file_path"])
        if iid in seen_ids or (folder in seen_folders and not allow_seen_folders):
            continue
        d = regate(item, prod.get(iid), scene.get(iid), params, frozen)
        if d.action == "promote":
            population[f"promote_{area_band(d.primary)}"].append(
                {"image_id": iid, "folder": folder, "file_path": item["file_path"], "box": list(d.primary)})
    fresh = sample_strata(population, seed, {s: per_band for s in population})

    calib_pool: dict[str, list[dict]] = defaultdict(list)
    for iid, label in val_labels.items():
        d = regate(snap[iid], prod.get(iid), scene.get(iid), params, frozen)
        if d.action != "promote":
            continue
        owner = outcome_for(label, d)
        group = "calib_usable" if owner == "usable" else "calib_not_usable"
        calib_pool[group].append({"image_id": iid, "folder": label["folder"], "file_path": snap[iid]["file_path"],
                                  "box": list(d.primary), "owner_outcome": owner})
    calibration = sample_strata(calib_pool, seed, {"calib_usable": calib // 2, "calib_not_usable": calib - calib // 2})

    img_dir = out / "agent_sample" / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for group in (fresh, calibration):
        for stratum, members in group.items():
            for m in members:
                target, crop = img_dir / f"{m['image_id']}.jpg", img_dir / f"{m['image_id']}_crop.jpg"
                if not target.exists():
                    _render(m["file_path"], m["box"], target, crop)
                rows.append({"image_id": m["image_id"], "stratum": stratum, "folder": m["folder"],
                             "box": json.dumps([round(v, 4) for v in m["box"]]),
                             "owner_outcome": m.get("owner_outcome", "")})
    _write_csv(out / "agent_sample" / "cohort.csv", ("image_id", "stratum", "folder", "box", "owner_outcome"), rows)
    summary = {"rule_hash": params.rule_hash(), "seed": seed, "allow_seen_folders": allow_seen_folders,
               "fresh_population": {s: len(v) for s, v in sorted(population.items())},
               "sample": {s: len(v) for s, v in sorted({**fresh, **calibration}.items())}}
    (out / "agent_sample" / "sampling.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# owner validation of /3 (registered on #472 before drawing)
# ---------------------------------------------------------------------------

VALIDATION_C_SEED = "bird-v1-regate-validation-c1"
VALIDATION_C_BUDGET = 300


def freeze_validation_c(promotion_root: Path, dev_root: Path, out: Path, seed: str = VALIDATION_C_SEED,
                        budget: int = VALIDATION_C_BUDGET) -> dict:
    """Draw the registered /3 owner sample into ``out/owner_c/validation`` (same layout as #469)."""
    snap = load_snapshot(promotion_root)
    prod = load_probe(promotion_root / "probe_production.jsonl")
    rule = json.loads((out / "rule_c.json").read_text(encoding="utf-8"))
    params = SubsetParamsV3(**rule["params"])
    if params.rule_hash() != rule["rule_hash"]:
        raise ValueError("rule_c.json hash does not match its parameters")
    scene = load_scene_probs(snap, SCENE_VERSION_V3)

    excluded = {int(r["image_id"]) for r in _read_csv(dev_root / "cohort.csv")}
    excluded |= {int(i["image_id"]) for i in json.loads(
        (dev_root / "failure_review" / "manifest.json").read_text(encoding="utf-8"))["items"]}
    excluded |= set(load_validation_labels(promotion_root)[0])
    excluded |= {int(r["image_id"]) for r in _read_csv(Path(".agent/scratch/scene_route/sample/cohort.csv"))}
    excluded |= {int(r["image_id"]) for r in _read_csv(out / "agent_sample" / "cohort.csv")}

    population: dict[str, list[dict]] = defaultdict(list)
    unlabelled_scene = 0
    for iid, item in sorted(snap.items()):
        if scene.get(iid) is None:
            unlabelled_scene += 1
        d = params.decide(item, prod.get(iid), scene.get(iid))
        if d.action != "promote":
            continue
        population[f"promote_{area_band(d.primary)}"].append(
            {"image_id": iid, "folder": folder_of(item["file_path"]), "file_path": item["file_path"],
             "box": list(d.primary), "source": d.source, "eligible": iid not in excluded})
    eligible = {s: [m for m in v if m["eligible"]] for s, v in population.items()}
    small_cap = len({m["folder"] for m in eligible.get("promote_small", [])})
    rest = budget - small_cap
    sizes = {"promote_small": small_cap, "promote_large": rest - rest // 2, "promote_medium": rest // 2}
    picked = sample_strata(eligible, seed, sizes)

    vdir = out / "owner_c" / "validation"
    if (vdir / "cohort.csv").exists():
        raise FileExistsError(f"{vdir / 'cohort.csv'} already exists; the sample is frozen")
    vdir.mkdir(parents=True, exist_ok=True)
    rows = [{"image_id": m["image_id"], "stratum": s, "file_path": m["file_path"]}
            for s, ms in sorted(picked.items()) for m in ms]
    _write_csv(vdir / "cohort.csv", ("image_id", "stratum", "file_path"), rows)
    _write_new_json(vdir / "proposals.json", {str(m["image_id"]): {"box": m["box"], "source": m["source"]}
                                              for ms in picked.values() for m in ms})
    sampling = {"seed": seed, "rule_hash": rule["rule_hash"], "rule_version": RULE_VERSION_C,
                "scene_version": SCENE_VERSION_V3, "frozen_utc": datetime.now(timezone.utc).isoformat(),
                "excluded_images": len(excluded), "snapshot_images_without_v3_label": unlabelled_scene,
                "population": {s: len(v) for s, v in sorted(population.items())},
                "eligible": {s: len(v) for s, v in sorted(eligible.items())},
                "sample": {s: len(v) for s, v in sorted(picked.items())},
                "requested": sizes}
    _write_new_json(vdir / "sampling.json", sampling)
    return sampling


def promotion_manifest(promotion_root: Path, out: Path) -> dict:
    """Frozen input for ``scripts/maintenance/promote_localization_selections.py`` (#472 step 6, #484).

    Only strata that passed owner validation (``owner_c/validation/analysis.json``) are included.
    """
    analysis_path = out / "owner_c" / "validation" / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    rule = json.loads((out / "rule_c.json").read_text(encoding="utf-8"))
    params = SubsetParamsV3(**rule["params"])
    if params.rule_hash() != rule["rule_hash"] or analysis["rule_hash"] != rule["rule_hash"]:
        raise ValueError("rule_c.json and analysis.json disagree on the rule hash")
    passing = set(analysis["passing_strata"])
    snap = load_snapshot(promotion_root)
    prod = load_probe(promotion_root / "probe_production.jsonl")
    scene = load_scene_probs(snap, SCENE_VERSION_V3)
    rows, counts = [], Counter()
    for iid, item in sorted(snap.items()):
        d = params.decide(item, prod.get(iid), scene.get(iid))
        if d.action != "promote":
            continue
        stratum = f"promote_{area_band(d.primary)}"
        counts[stratum] += 1
        if stratum not in passing:
            continue
        conf = max(b["conf"] for b in prod[iid]["coco"] if b["cls"] == "bird")
        rows.append({"image_id": iid, "v1_run_id": int(item["run_id"]), "rendition_hash": item["rendition_hash"],
                     "region": [round(v, 6) for v in d.primary], "conf": round(conf, 4), "source": d.source,
                     "stratum": stratum})
    target = out / "promotion_manifest.json"
    _write_new_json(target, {
        "schema_version": 1, "selected_by": f"{RULE_VERSION_C}:{rule['rule_hash']}",
        "detector_version": RULE_VERSION_C, "detector_config_hash": rule["rule_hash"],
        "evidence": {"issue": 472, "rule_hash": rule["rule_hash"], "scene_version": SCENE_VERSION_V3,
                     "validation_analysis_sha256": sha256_file(analysis_path),
                     "passing_strata": sorted(passing)},
        "rows": rows,
    })
    return {"rows": len(rows), "promoted_by_stratum": dict(counts), "passing": sorted(passing), "path": str(target)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("fit", "fit-b", "fit-c", "agent-sample", "freeze-validation-c", "page-c",
                                           "promotion-manifest"))
    parser.add_argument("--promotion-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--dev-root", type=Path, default=DEV_ROOT)
    parser.add_argument("--out", type=Path, default=REGATE_ROOT)
    parser.add_argument("--seed", default="bird-v1-regate-agents-1")
    parser.add_argument("--per-band", type=int, default=30)
    parser.add_argument("--calib", type=int, default=30)
    parser.add_argument("--allow-seen-folders", action="store_true")
    args = parser.parse_args()
    if args.action == "promotion-manifest":
        print(json.dumps(promotion_manifest(args.promotion_root, args.out), indent=1))
        return
    if args.action == "freeze-validation-c":
        print(json.dumps(freeze_validation_c(args.promotion_root, args.dev_root, args.out), indent=1))
        return
    if args.action == "page-c":
        from scripts.research.detector_benchmark.v1_promotion_gate import build_page

        n = build_page(args.out / "owner_c", VALIDATION_C_SEED)
        print(f"Built {n} items at {args.out / 'owner_c' / 'validation' / 'page' / 'index.html'}")
        return
    if args.action == "fit-c":
        chosen = fit_b(args.promotion_root, args.dev_root, args.out, SubsetParamsV3, "c")
        print(json.dumps(chosen, indent=1) if chosen else "No /3 setting meets the pre-declared criterion.")
        return
    if args.action == "fit-b":
        chosen = fit_b(args.promotion_root, args.dev_root, args.out)
        print(json.dumps(chosen, indent=1) if chosen else "No /2 setting meets the pre-declared criterion; option (b) fails.")
        return
    if args.action == "agent-sample":
        print(json.dumps(agent_sample(args.promotion_root, args.dev_root, args.out, args.seed,
                                      args.per_band, args.calib, args.allow_seen_folders), indent=1))
        return
    chosen = fit(args.promotion_root, args.dev_root, args.out)
    print(json.dumps(chosen, indent=1) if chosen else "No setting meets the pre-declared criterion; step 2 fails.")


if __name__ == "__main__":
    main()
