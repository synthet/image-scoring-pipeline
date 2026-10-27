"""Blind multi-CLI bird-box panel: rule/4 small-stratum gate (#593) and cascade AC-17 (#408).

Each frame is two blind JPEGs: the full photo with the box in red, and a zoomed crop (rendered by
``v1_regate._render``). Two rubrics:

* ``usable``: the #472 owner-gate rubric (presence + usable / poor_crop / wrong_target / unsure);
* ``tight``: the 2026-09-24 box-panel grades (TIGHT / LOOSE / PARTIAL / MULTI / WRONG).

Labels are **agent-panel labels**, not owner labels. CLI plumbing is shared with
``species_panel.py``.

    # container
    python scripts/research/judges/box_panel.py build-rule4 --root <root>
    # host
    python scripts/research/judges/box_panel.py run --judge claude --root <root>
    python scripts/research/judges/box_panel.py consensus --root <root> --judges claude,codex,agy
    python scripts/research/judges/box_panel.py gate-rule4 --root <root>
"""

from __future__ import annotations

import argparse
import json
import random
import re
import secrets
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.research.judges.species_panel import _call, command, stage_batch, wilson  # noqa: E402

RUBRICS = {
    "usable": ("usable", "poor_crop", "wrong_target", "unsure"),
    "tight": ("TIGHT", "LOOSE", "PARTIAL", "MULTI", "WRONG"),
}
PRESENCE = ("bird", "no_bird", "unsure")
RULE4_VERSION = "v1_regate_rule/4"
RULE4_SEED = "bird-v1-regate-validation-d1"
RULE4_P_BIRD = 0.95
RULE4_SAMPLE = 130
CALIB_SEED = "bird-v1-regate-calib-d1"


def prompt_for(frames: list[dict], judge: str, blind: Path, rubric: str) -> str:
    how = {"codex": "The photos are attached as images, two per id in the order listed below."}.get(
        judge, "Open each local JPEG at the paths below to look at it. Do not modify files or run programs.")
    items = "\n".join(f"- id {f['token']}: full photo {(blind / (f['token'] + '.jpg')).resolve()} ; "
                      f"zoomed crop {(blind / (f['token'] + '_crop.jpg')).resolve()}" for f in frames)
    head = (f"Independent photo labelling for a bird-detection audit. {how}\n{items}\n\n"
            "Each id has a full photo and a zoomed crop. A red rectangle marks a proposed bird box.\n")
    if rubric == "usable":
        return head + (
            "For each id give:\n"
            "1. presence: 'bird' if a real bird is visible anywhere in the photo, 'no_bird' if none, "
            "'unsure' if you cannot tell.\n"
            "2. grade of the red box (only when presence is 'bird'; otherwise 'unsure'):\n"
            "- usable: the box frames a real bird that is the photo's subject, with most of the bird inside "
            "and not much empty space; good enough to crop for a quality check of that bird.\n"
            "- poor_crop: it is on the bird but badly framed (cuts off a large part, or is far too large).\n"
            "- wrong_target: it frames something else (branch, leaf, another animal) or a minor bird "
            "instead of the main one.\n"
            "- unsure: you cannot tell.\n"
            "3. reason: at most 15 words on what is inside the box.\n\n"
            'Return only JSON: {"images":[{"id":"<id>","presence":"bird","grade":"usable","reason":"..."}]} '
            "with every id listed above.")
    return head + (
        "For each id grade the red box:\n"
        "- TIGHT: one whole bird, snugly boxed.\n"
        "- LOOSE: one whole bird, but the box is more than about twice the bird's size.\n"
        "- PARTIAL: a significant part of the bird is cut off by the box.\n"
        "- MULTI: several birds boxed as one.\n"
        "- WRONG: no bird inside the box.\n"
        "Also give reason: at most 15 words on what is inside the box.\n\n"
        'Return only JSON: {"images":[{"id":"<id>","grade":"TIGHT","reason":"..."}]} with every id listed above.')


def parse_reply(text: str, rubric: str) -> dict[str, dict]:
    decoder = json.JSONDecoder()
    grades = RUBRICS[rubric]
    for start in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            data, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("images"), list):
            out = {}
            for row in data["images"]:
                grade = str(row.get("grade", "")).strip()
                grade = grade.upper() if rubric == "tight" else grade.lower()
                if not row.get("id") or grade not in grades:
                    continue
                ans = {"grade": grade, "reason": str(row.get("reason", ""))[:200]}
                if rubric == "usable":
                    presence = str(row.get("presence", "")).strip().lower()
                    if presence not in PRESENCE:
                        continue
                    ans = {"presence": presence, "grade": grade if presence == "bird" else "unsure",
                           "reason": ans["reason"]}
                out[str(row["id"])] = ans
            return out
    return {}


def load_manifest(root: Path) -> dict:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def load_judge(root: Path, judge: str, rubric: str) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for f in sorted((root / "judges" / judge).glob("*.txt")):
        labels.update(parse_reply(f.read_text(encoding="utf-8", errors="replace"), rubric))
    return labels


def run(root: Path, judge: str, batch_size: int, timeout: int, limit: int | None, shard: str = "0/1") -> Counter:
    man = load_manifest(root)
    rubric, blind = man["rubric"], root / "blind"
    done = load_judge(root, judge, rubric)
    k, n = (int(x) for x in shard.split("/"))
    todo = [f for i, f in enumerate(man["frames"]) if i % n == k and f["token"] not in done][:limit]
    out_dir = root / "judges" / judge
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    fails = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        out = out_dir / f"{batch[0]['token']}.txt"
        names = [f"{f['token']}{s}.jpg" for f in batch for s in ("", "_crop")]
        where = stage_batch(blind, names, root / "staged" / batch[0]["token"]) if judge == "cursor" else blind
        paths = [where / n for n in names]
        argv, stdin, cwd = command(judge, prompt_for(batch, judge, where, rubric), paths, out, where)
        try:
            stdout, stderr = _call(argv, stdin, cwd, timeout)
            if judge != "codex" or not out.exists():
                out.write_text(stdout, encoding="utf-8")
            (out_dir / f"{out.stem}.stderr.log").write_text(stderr[-4000:], encoding="utf-8")
        except subprocess.TimeoutExpired:
            counts["timeout"] += len(batch)
            fails += 1
        else:
            got = parse_reply(out.read_text(encoding="utf-8", errors="replace"), rubric)
            ok = len(set(got) & {f["token"] for f in batch})
            counts["labelled"] += ok
            counts["missing"] += len(batch) - ok
            fails = 0 if ok else fails + 1
        print(f"{judge}: {start + len(batch)}/{len(todo)} {dict(counts)}", flush=True)
        if fails >= 3:
            counts["stopped_after_3_failures"] = 1
            break
    return counts


def verdict(answer: dict | None, rubric: str) -> str | None:
    """A judge's binary-ish verdict: ``usable``/``not_usable`` or the tight grade; ``None`` when unsure."""
    if not answer:
        return None
    if rubric == "tight":
        return answer["grade"]
    if answer["presence"] == "no_bird":
        return "not_usable"
    if answer["presence"] != "bird" or answer["grade"] == "unsure":
        return None
    return "usable" if answer["grade"] == "usable" else "not_usable"


def consensus(root: Path, judges: list[str]) -> dict:
    man = load_manifest(root)
    rubric = man["rubric"]
    votes = {j: load_judge(root, j, rubric) for j in judges}
    need = 2 if len(judges) == 3 else 3
    labels, splits = {}, []
    for f in man["frames"]:
        vs = Counter(v for v in (verdict(votes[j].get(f["token"]), rubric) for j in judges) if v)
        top = vs.most_common(1)[0] if vs else (None, 0)
        labels[f["token"]] = top[0] if top[1] >= need else None
        if labels[f["token"]] is None:
            splits.append({"token": f["token"], "votes": {j: votes[j].get(f["token"]) for j in judges}})
    summary = {"rubric": rubric, "judges": judges, "need": need, "frames": len(man["frames"]),
               "coverage": {j: len(votes[j]) for j in judges},
               "labelled": sum(1 for v in labels.values() if v), "splits": len(splits)}
    (root / "consensus.json").write_text(json.dumps({"summary": summary, "labels": labels}, indent=1),
                                         encoding="utf-8")
    (root / "splits.json").write_text(json.dumps(splits, indent=1), encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# rule/4 (#593)
# ---------------------------------------------------------------------------

def rule4_promotes(rule3_decision, coco: list[dict], p_bird: float | None) -> bool:
    """``v1_regate_rule/4``: ``/3`` promotions; small boxes also need p(bird) >= 0.95 and one RTMDet bird."""
    from scripts.research.detector_benchmark.v1_promotion_gate import area_band
    from scripts.research.detector_benchmark.v1_regate import B_BIRD_COUNT_CONF

    if rule3_decision.action != "promote":
        return False
    if area_band(rule3_decision.primary) != "small":
        return True
    n_birds = sum(1 for b in coco if b["cls"] == "bird" and b["conf"] >= B_BIRD_COUNT_CONF)
    return p_bird is not None and p_bird >= RULE4_P_BIRD and n_birds == 1


def _rule4_inputs():
    from scripts.research.detector_benchmark import v1_regate as rg
    from scripts.research.detector_benchmark.v1_promotion_gate import OUT_ROOT, load_probe, load_snapshot

    rule = json.loads((rg.REGATE_ROOT / "rule_c.json").read_text(encoding="utf-8"))
    params = rg.SubsetParamsV3(**rule["params"])
    if params.rule_hash() != rule["rule_hash"]:
        raise ValueError("rule_c.json hash does not match its parameters")
    snap = load_snapshot(OUT_ROOT)
    prod = load_probe(OUT_ROOT / "probe_production.jsonl")
    scene = rg.load_scene_probs(snap, rg.SCENE_VERSION_V3)
    return rg, rule, params, snap, prod, scene


def rule4_hash(rule3_hash: str) -> str:
    import hashlib

    blob = json.dumps({"version": RULE4_VERSION, "base": rule3_hash, "small_p_bird": RULE4_P_BIRD,
                       "small_rt_birds": 1}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_rule4(root: Path) -> dict:
    """Fresh small-stratum sample under rule/4 plus owner-labelled calibration items, rendered blind."""
    import csv

    from scripts.research.detector_benchmark.v1_promotion_gate import _order_key, area_band, folder_of

    rg, rule, params, snap, prod, scene = _rule4_inputs()
    vdir = rg.REGATE_ROOT / "owner_c" / "validation"
    owner = {int(r["image_id"]): r for r in csv.DictReader((vdir / "labels_owner.csv").open(encoding="utf-8"))}
    excluded = set(owner) | {int(r["image_id"]) for r in csv.DictReader(
        (rg.REGATE_ROOT / "agent_sample" / "cohort.csv").open(encoding="utf-8"))}
    population: dict[str, list[dict]] = defaultdict(list)
    boxes: dict[int, list[float]] = {}
    for iid, item in sorted(snap.items()):
        d = params.decide(item, prod.get(iid), scene.get(iid))
        if d.action == "promote":
            boxes[iid] = list(d.primary)
        if area_band(d.primary or (0, 0, 1, 1)) != "small" or not rule4_promotes(
                d, (prod.get(iid) or {}).get("coco", []), scene.get(iid)):
            continue
        if iid not in excluded:
            population["rule4_small"].append({"image_id": iid, "folder": folder_of(item["file_path"]),
                                              "file_path": item["file_path"], "box": list(d.primary)})
    # Seeded draw of RULE4_SAMPLE without the one-per-folder cap of ``sample_strata``: the eligible small
    # boxes span too few folders for that design to reach the pre-registered size.
    fresh = sorted(population["rule4_small"], key=lambda m: _order_key(RULE4_SEED, m["image_id"]))[:RULE4_SAMPLE]
    # Calibration: every owner not-usable item (any band) + usable ones, so judge error can be measured.
    not_ok = [i for i, r in owner.items() if not (r["presence"] == "bird" and r["box_label"] == "usable")]
    ok = [i for i, r in owner.items() if i not in not_ok]
    rng = random.Random(CALIB_SEED)
    calib = sorted(not_ok) + rng.sample(sorted(ok), 20 - len(not_ok))

    blind = root / "blind"
    blind.mkdir(parents=True, exist_ok=False)
    frames = []
    items = [(m["image_id"], m["file_path"], m["box"], "fresh", None) for m in fresh]
    items += [(i, snap[i]["file_path"], boxes[i], "calibration",
               "usable" if i in ok else "not_usable") for i in calib]
    for n, (iid, path, box, kind, owner_outcome) in enumerate(items, 1):
        token = secrets.token_hex(6)
        rg._render(path, box, blind / f"{token}.jpg", blind / f"{token}_crop.jpg")
        frames.append({"token": token, "image_id": iid, "kind": kind, "owner": owner_outcome, "box": box,
                       "folder": folder_of(path)})
        if n % 25 == 0:
            print(f"build-rule4: {n}/{len(items)}", flush=True)
    random.Random(RULE4_SEED).shuffle(frames)
    manifest = {"rubric": "usable", "rule_version": RULE4_VERSION, "rule_hash": rule4_hash(rule["rule_hash"]),
                "base_rule_hash": rule["rule_hash"], "seed": RULE4_SEED,
                "population_small": len(population["rule4_small"]) + sum(
                    1 for i in excluded if i in boxes and area_band(boxes[i]) == "small"
                    and rule4_promotes(params.decide(snap[i], prod.get(i), scene.get(i)),
                                       (prod.get(i) or {}).get("coco", []), scene.get(i))),
                "eligible": len(population["rule4_small"]), "frames": frames}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {k: v for k, v in manifest.items() if k != "frames"} | {
        "fresh": len(fresh), "calibration": len(calib), "calibration_not_usable": len(not_ok)}


def gate_rule4(root: Path, adjudicated: Path | None) -> dict:
    man = load_manifest(root)
    labels = json.loads((root / "consensus.json").read_text(encoding="utf-8"))["labels"]
    if adjudicated and adjudicated.exists():
        labels.update({k: v for k, v in json.loads(adjudicated.read_text(encoding="utf-8")).items() if v})
    fresh = [f for f in man["frames"] if f["kind"] == "fresh"]
    calib = [f for f in man["frames"] if f["kind"] == "calibration"]
    resolved = [f for f in fresh if labels.get(f["token"])]
    ok = sum(1 for f in resolved if labels[f["token"]] == "usable")
    lo, hi = wilson(ok, len(resolved))
    sens = [labels.get(f["token"]) == "usable" for f in calib if f["owner"] == "usable"]
    spec = [labels.get(f["token"]) == "not_usable" for f in calib if f["owner"] == "not_usable"]
    # Sensitivity (not gating): one frame per folder, first by the sampling order.
    from scripts.research.detector_benchmark.v1_promotion_gate import _order_key

    per_folder: dict[str, dict] = {}
    for f in sorted(resolved, key=lambda f: _order_key(man["seed"], f["image_id"])):
        per_folder.setdefault(f.get("folder", f["token"]), f)
    pf_ok = sum(1 for f in per_folder.values() if labels[f["token"]] == "usable")
    result = {"rule_hash": man["rule_hash"], "fresh": len(fresh), "resolved": len(resolved),
              "unresolved": len(fresh) - len(resolved), "usable": ok,
              "rate": round(ok / len(resolved), 4) if resolved else None,
              "wilson95": [round(lo, 4), round(hi, 4)], "pass": lo >= 0.90,
              "calibration": {"sensitivity": [sum(sens), len(sens)], "specificity": [sum(spec), len(spec)]},
              "one_per_folder": {"usable": pf_ok, "n": len(per_folder),
                                 "wilson95": [round(v, 4) for v in wilson(pf_ok, len(per_folder))]}}
    (root / "gate.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def rule4_manifest(root: Path, out: Path) -> dict:
    """Frozen input for ``promote_localization_selections.py``: rule/4 small promotions only.

    Large/medium ``/3`` boxes are already selected (#472); this adds the small stratum that passed.
    """
    import hashlib

    from scripts.research.detector_benchmark.v1_promotion_gate import area_band

    gate = json.loads((root / "gate.json").read_text(encoding="utf-8"))
    if not gate["pass"]:
        raise ValueError("rule/4 gate did not pass")
    rg, rule, params, snap, prod, scene = _rule4_inputs()
    h = rule4_hash(rule["rule_hash"])
    if gate["rule_hash"] != h:
        raise ValueError("gate.json and the rule/4 hash disagree")
    rows = []
    for iid, item in sorted(snap.items()):
        d = params.decide(item, prod.get(iid), scene.get(iid))
        if d.action != "promote" or area_band(d.primary) != "small":
            continue
        if not rule4_promotes(d, prod[iid]["coco"], scene.get(iid)):
            continue
        conf = max(b["conf"] for b in prod[iid]["coco"] if b["cls"] == "bird")
        rows.append({"image_id": iid, "v1_run_id": int(item["run_id"]), "rendition_hash": item["rendition_hash"],
                     "region": [round(v, 6) for v in d.primary], "conf": round(conf, 4), "source": d.source,
                     "stratum": "promote_small"})
    gate_path = root / "gate.json"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps({
        "schema_version": 1, "selected_by": f"{RULE4_VERSION}:{h}", "detector_version": RULE4_VERSION,
        "detector_config_hash": h,
        "evidence": {"issue": 593, "rule_hash": h, "base_rule_hash": rule["rule_hash"],
                     "scene_version": rg.SCENE_VERSION_V3, "gate": "agent-panel",
                     "gate_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
                     "passing_strata": ["promote_small"]},
        "rows": rows}, indent=1), encoding="utf-8")
    return {"rows": len(rows), "path": str(out), "selected_by": f"{RULE4_VERSION}:{h}"}


# ---------------------------------------------------------------------------
# cascade AC-17 / AC-18 (#408)
# ---------------------------------------------------------------------------

AC17_SEED = "cascade-ac17-1"
AC17_FALLBACK = 0.60


def cascade_box(rec: dict, threshold: float = AC17_FALLBACK, refine_area_frac: float = 0.02) -> tuple[str, list] | None:
    """(step, rank-0 region) the production cascade adopts for one benchmark record, or ``None``."""
    from modules.localization_cascade import ChildOutcome, combine

    yolo = ChildOutcome("detected" if rec["yolo"] else "no_detection", "y", rec["yolo"])
    coco_boxes = [b for b in rec["coco"] if b["conf"] >= threshold]
    coco = ChildOutcome("detected" if coco_boxes else "no_detection", "c", coco_boxes)
    refined = {tuple(f["coco_region"]): f["yolo"] for f in rec.get("refine", [])}
    res = combine(yolo, coco, refine=lambda region: refined.get(tuple(region), []), refine_area_frac=refine_area_frac)
    if res.status != "detected" or not res.regions:
        return None
    top = res.regions[0]
    return top["provider_class_id"].split(":")[0], list(top["region"])


def build_ac17(root: Path, bench: Path, raw: Path) -> dict:
    """Render YOLO and fallback boxes on owner-labelled bird frames of the #377 cohort (container)."""
    import csv

    from scripts.research.detector_benchmark import v1_regate as rg

    cohort = {int(r["image_id"]): r for r in csv.DictReader((bench / "cohort.csv").open(encoding="utf-8"))}
    labels = {int(r["image_id"]): r["label"] for r in csv.DictReader((bench / "labels.csv").open(encoding="utf-8"))}
    recs = [json.loads(line) for line in raw.open(encoding="utf-8")]
    items = []
    for rec in recs:
        iid = int(rec["image_id"])
        if "error" in rec or labels.get(iid) != "bird":
            continue
        if rec["yolo"]:
            items.append((iid, "yolo", "yolo", list(rec["yolo"][0]["region"])))
        else:
            adopted = cascade_box(rec)
            if adopted:
                items.append((iid, "fallback", adopted[0], adopted[1]))
    blind = root / "blind"
    blind.mkdir(parents=True, exist_ok=False)
    frames = []
    for n, (iid, kind, step, box) in enumerate(items, 1):
        token = secrets.token_hex(6)
        rg._render(cohort[iid]["file_path"], box, blind / f"{token}.jpg", blind / f"{token}_crop.jpg")
        frames.append({"token": token, "image_id": iid, "kind": kind, "step": step, "box": box})
        if n % 25 == 0:
            print(f"build-ac17: {n}/{len(items)}", flush=True)
    random.Random(AC17_SEED).shuffle(frames)
    (root / "manifest.json").write_text(json.dumps({"rubric": "tight", "seed": AC17_SEED, "fallback": AC17_FALLBACK,
                                                    "frames": frames}, indent=1), encoding="utf-8")
    return {"frames": len(frames), "by_kind": dict(Counter(f["kind"] for f in frames)),
            "by_step": dict(Counter(f["step"] for f in frames))}


def gate_ac17(root: Path, bench: Path, raw: Path, adjudicated: Path | None) -> dict:
    """AC-17 TIGHT rates (YOLO vs cascade) and AC-18 presence on the independent strata."""
    import csv

    man = load_manifest(root)
    labels = json.loads((root / "consensus.json").read_text(encoding="utf-8"))["labels"]
    if adjudicated and adjudicated.exists():
        labels.update({k: v for k, v in json.loads(adjudicated.read_text(encoding="utf-8")).items() if v})
    by_kind: dict[str, Counter] = defaultdict(Counter)
    for f in man["frames"]:
        lab = labels.get(f["token"])
        by_kind[f["kind"]]["unresolved" if lab is None else lab] += 1
    def rate(kinds):
        n = sum(sum(v for k, v in by_kind[x].items() if k != "unresolved") for x in kinds)
        t = sum(by_kind[x]["TIGHT"] for x in kinds)
        return t, n
    yt, yn = rate(["yolo"])
    ct, cn = rate(["yolo", "fallback"])
    ft, fn = rate(["fallback"])
    fl = by_kind["fallback"]["TIGHT"] + by_kind["fallback"]["LOOSE"]
    # AC-18 on the independent strata (owner presence labels), cascade at the fallback threshold.
    bench_labels = {int(r["image_id"]): r["label"] for r in csv.DictReader((bench / "labels.csv").open(encoding="utf-8"))}
    recs = [json.loads(line) for line in raw.open(encoding="utf-8")]
    ind = [r for r in recs if "error" not in r and r["stratum"] in ("miss_birdkw", "miss_nokw")]
    birds = [r for r in ind if bench_labels.get(int(r["image_id"])) == "bird"]
    nob = [r for r in ind if bench_labels.get(int(r["image_id"])) == "no_bird"]
    hit = lambda r: cascade_box(r) is not None  # noqa: E731
    ac18 = {"yolo_recall": [sum(bool(r["yolo"]) for r in birds), len(birds)],
            "cascade_recall": [sum(hit(r) for r in birds), len(birds)],
            "cascade_fp": [sum(hit(r) for r in nob), len(nob)],
            "yolo_fp": [sum(bool(r["yolo"]) for r in nob), len(nob)]}
    ac18["pass"] = (ac18["cascade_fp"][0] <= 0.10 * max(1, len(nob))
                    and ac18["cascade_recall"][0] >= ac18["yolo_recall"][0])
    result = {"by_kind": {k: dict(v) for k, v in by_kind.items()},
              "yolo_tight": [yt, yn, round(yt / yn, 4) if yn else None],
              "cascade_tight": [ct, cn, round(ct / cn, 4) if cn else None],
              "fallback_tight": [ft, fn], "fallback_usable_tight_or_loose": [fl, fn],
              "AC17_pass": bool(yn and cn) and ct / cn >= yt / yn - 0.05, "AC18": ac18}
    result["pass"] = result["AC17_pass"] and ac18["pass"]
    (root / "gate.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("action", choices=("build-rule4", "run", "consensus", "gate-rule4", "manifest-rule4",
                                      "build-ac17", "gate-ac17"))
    p.add_argument("--bench", type=Path, help="#377 benchmark dir with cohort.csv and labels.csv")
    p.add_argument("--raw", type=Path, help="cascade_benchmark raw.jsonl")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--judge", choices=("claude", "codex", "agy", "cursor"))
    p.add_argument("--judges", default="claude,codex,agy")
    p.add_argument("--batch-size", type=int, default=5)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--limit", type=int)
    p.add_argument("--shard", default="0/1", help="k/n: this process judges frames i with i %% n == k")
    p.add_argument("--adjudicated", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.action == "build-rule4":
        res = build_rule4(a.root)
    elif a.action == "run":
        if not a.judge:
            p.error("run needs --judge")
        res = run(a.root, a.judge, a.batch_size, a.timeout, a.limit, a.shard)
    elif a.action == "consensus":
        res = consensus(a.root, a.judges.split(","))
    elif a.action == "gate-rule4":
        res = gate_rule4(a.root, a.adjudicated)
    elif a.action == "build-ac17":
        res = build_ac17(a.root, a.bench, a.raw)
    elif a.action == "gate-ac17":
        res = gate_ac17(a.root, a.bench, a.raw, a.adjudicated)
    else:
        res = rule4_manifest(a.root, a.out)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
