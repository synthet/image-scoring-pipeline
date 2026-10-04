"""CLI-agent rater stream for the blind model-selection study (#517): Codex, Antigravity, Claude.

Agents grade the same blind burst/stack units the owner grades on the review page (Reject / Keep /
Pick per frame, best frame starred, ties allowed). Scope: group units in train + validation only;
the test split is never touched. Agent labels are a **separate rater stream**: they never enter
``reviews.jsonl`` and never count toward the 150-group gate or the final model decision.

Run on the Windows host from the repository root (the CLIs and rawpy are installed there):

    python scripts/research/model_selection/study_agent_judges.py prepare
    python scripts/research/model_selection/study_agent_judges.py run --judge codex
    python scripts/research/model_selection/study_agent_judges.py analyze

Previews, raw replies and the analysis land in ``.agent/scratch/study_agents/``.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from modules.score_analytics import study  # noqa: E402
from scripts.research.scene_route.cli_judges import command  # noqa: E402

STUDY = Path("reports/model-selection-2026-10-01")
ROOT = Path(".agent/scratch/study_agents")
JUDGES = ("codex", "agy", "claude")
GRADES = {"reject": 0, "keep": 1, "pick": 2}
MODELS = ("general", "liqe", "spaq", "topiq", "arniqa", "ava", "clip_quality_v0")
SPLITS = ("train", "validation")
MAX_FRAMES = 12
SEED = "study-agents-1"


def group_units(sample: dict) -> list[dict]:
    """Train + validation burst/stack units, excluding test-retest repeats."""
    units = [u for u in sample["units"]
             if u["kind"] != "single" and u["split"] in SPLITS and not u.get("repeat_of")]
    assert all(u["split"] != "test" for u in units)
    return units


def frame_name(unit_id: str, n: int) -> str:
    return f"{unit_id}_{n}.jpg"


def prepare(study_dir: Path, root: Path, long_edge: int) -> Counter:
    from modules.score_analytics.study_data import read_json
    from modules.score_analytics.study_review import local_preview

    sample = read_json(study_dir / "sample.json")
    paths = {r["id"]: r["path"] for r in read_json(study_dir / "snapshot.json.gz")["images"]}
    (root / "img").mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    for u in group_units(sample):
        for n, iid in enumerate(u["image_ids"], 1):
            target = root / "img" / frame_name(u["id"], n)
            if target.exists():
                counts["exists"] += 1
                continue
            try:
                target.write_bytes(local_preview(paths[iid], long_edge))
                counts["written"] += 1
            except Exception as exc:  # noqa: BLE001 — a missing file only removes that unit
                counts[f"failed:{type(exc).__name__}"] += 1
    return counts


def batches(units: list[dict], max_frames: int = MAX_FRAMES) -> list[list[dict]]:
    """Seeded shuffle, then pack whole units into calls of at most ``max_frames`` frames."""
    order = sorted(units, key=lambda u: u["id"])
    random.Random(SEED).shuffle(order)
    out, cur, size = [], [], 0
    for u in order:
        n = len(u["image_ids"])
        if cur and size + n > max_frames:
            out.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += n
    if cur:
        out.append(cur)
    return out


def prompt_for(batch: list[dict], root: Path, judge: str) -> str:
    how = {"codex": "The photos are attached as images, in the order listed below.",
           "agy": "Read each local JPEG at the paths below for visual analysis. Do not modify files or run programs.",
           "claude": "Read each JPEG at the paths below with the Read tool. Do not modify files."}[judge]
    lines = []
    for u in batch:
        lines.append(f"Unit {u['id']} ({len(u['image_ids'])} frames):")
        lines += [f"- frame {n}: {(root / 'img' / frame_name(u['id'], n)).resolve()}"
                  for n in range(1, len(u["image_ids"]) + 1)]
    files = "\n".join(lines)
    return (
        f"Independent photo culling for a blind study. {how}\n{files}\n\n"
        "Each unit is a burst or stack of near-duplicate photos of the same scene by a nature photographer. "
        "Judge each unit on its own, comparing its frames like a photographer culling a burst: subject "
        "sharpness (above all the eyes), motion blur, pose and gesture, timing, composition, exposure.\n"
        "For every frame of every unit give:\n"
        "- grade: 'reject' (not worth keeping), 'keep' (acceptable, not among the best) or 'pick' "
        "(among the best frames of the unit);\n"
        "- best: true for the single best frame. It must be a pick. If several frames are equally good "
        "and you see no certain difference, mark all of them best. If no frame is usable, reject every "
        "frame and mark none best.\n\n"
        'Return only JSON: {"units":[{"unit":"<unit id>","frames":[{"frame":1,"grade":"pick","best":true}]}]} '
        "covering every unit and every frame listed above.")


def parse_reply(text: str) -> dict[str, list[dict]]:
    """Last JSON object with a ``units`` list in a CLI reply -> {unit_id: raw frame rows}."""
    decoder = json.JSONDecoder()
    for start in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            data, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("units"), list):
            return {str(row.get("unit")): row.get("frames") for row in data["units"]
                    if isinstance(row, dict) and isinstance(row.get("frames"), list)}
    return {}


def to_record(unit: dict, frames: list) -> dict | None:
    """A judge's frame rows -> review-shaped record, or None when anything is invalid (never coerced)."""
    by_n = {}
    for f in frames:
        if not isinstance(f, dict) or f.get("grade") not in GRADES or type(f.get("best")) is not bool:
            return None
        n = f.get("frame")
        if type(n) is not int or n in by_n:
            return None
        by_n[n] = f
    if set(by_n) != set(range(1, len(unit["image_ids"]) + 1)):
        return None
    record = {"unit_id": unit["id"], "status": "done",
              "frames": [{"image_id": iid, "grade": GRADES[by_n[n]["grade"]], "best": by_n[n]["best"]}
                         for n, iid in enumerate(unit["image_ids"], 1)]}
    try:  # same structural rules as owner reviews; the source field only satisfies the validator
        study.validate_review(unit, {**record, "reviewer": "agent", "source": "human_blind"})
    except ValueError:
        return None
    return record


def load_judge(root: Path, judge: str, units: dict[str, dict]) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for f in sorted((root / "judges" / judge).glob("*.json")):
        for uid, frames in parse_reply(f.read_text(encoding="utf-8", errors="replace")).items():
            if uid in units:
                rec = to_record(units[uid], frames)
                if rec is not None:
                    records[uid] = rec
    return records


def run(study_dir: Path, root: Path, judge: str, timeout: int, max_batches: int | None = None) -> Counter:
    from modules.score_analytics.study_data import read_json

    units = {u["id"]: u for u in group_units(read_json(study_dir / "sample.json"))}
    done = load_judge(root, judge, units)
    todo = batches([u for uid, u in units.items() if uid not in done])[:max_batches]
    out_dir = root / "judges" / judge
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    for k, batch in enumerate(todo):
        paths = [root / "img" / frame_name(u["id"], n) for u in batch for n in range(1, len(u["image_ids"]) + 1)]
        if not all(p.exists() for p in paths):
            counts["no_preview"] += len(batch)
            continue
        out = out_dir / f"{len(list(out_dir.glob('*.json'))):04d}_{batch[0]['id']}.json"
        try:
            proc = subprocess.run(command(judge, prompt_for(batch, root, judge), paths, out), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                  stdin=subprocess.DEVNULL)
            if judge != "codex":
                out.write_text(proc.stdout, encoding="utf-8")
            (out_dir / f"{out.stem}.stderr.log").write_text(proc.stderr[-4000:], encoding="utf-8")
        except subprocess.TimeoutExpired:
            counts["timeout"] += len(batch)
            continue
        reply = parse_reply(out.read_text(encoding="utf-8", errors="replace")) if out.exists() else {}
        for u in batch:
            counts["labelled" if u["id"] in reply and to_record(u, reply[u["id"]]) else "invalid_or_missing"] += 1
        print(f"{judge}: batch {k + 1}/{len(todo)} {dict(counts)}", flush=True)
    return counts


def consensus(records: list[dict]) -> dict | None:
    """Per-frame lower-median grade over >= 2 judges; best = picks with the most stars (ties kept)."""
    if len(records) < 2:
        return None
    ids = [f["image_id"] for f in records[0]["frames"]]
    grades, stars = {}, {}
    for iid in ids:
        rows = [next(f for f in r["frames"] if f["image_id"] == iid) for r in records]
        g = sorted(f["grade"] for f in rows)
        grades[iid] = g[(len(g) - 1) // 2]
        stars[iid] = sum(f["best"] for f in rows)
    picks = [i for i in ids if grades[i] == 2]
    if any(grades.values()) and not picks:
        return None  # keeps without any pick: no valid best frame
    top = max((stars[i] for i in picks), default=0)
    return {"frames": [{"image_id": i, "grade": grades[i], "best": i in picks and stars[i] == top} for i in ids]}


def _labels(record: dict) -> tuple[np.ndarray, np.ndarray]:
    return (np.array([f["grade"] for f in record["frames"]]), np.array([f["best"] for f in record["frames"]]))


def agreement(a: dict, b: dict) -> dict:
    """Frame-grade exact agreement and best-frame overlap between two records of one unit."""
    order = [f["image_id"] for f in a["frames"]]
    b_by_id = {f["image_id"]: f for f in b["frames"]}
    ga, ba = _labels(a)
    gb, bb = _labels({"frames": [b_by_id[i] for i in order]})
    out = {"frames": len(ga), "same_grade": int((ga == gb).sum())}
    if ba.any() and bb.any():
        out["best_overlap"] = bool((ba & bb).any())
    elif not ba.any() and not bb.any():
        out["best_overlap"] = True  # both rejected every frame
    else:
        out["best_overlap"] = False
    return out


def _summarize(pairs: list[dict]) -> dict:
    if not pairs:
        return {"units": 0}
    return {"units": len(pairs),
            "frame_grade_agreement": round(sum(p["same_grade"] for p in pairs) / sum(p["frames"] for p in pairs), 3),
            "best_overlap": round(float(np.mean([p["best_overlap"] for p in pairs])), 3)}


def model_top1(records: dict[str, dict], images: dict[int, dict]) -> dict:
    """Mean best-frame top1 per model (``study.group_metrics``) plus the random-pick chance level."""
    out = {}
    for model in MODELS:
        vals, chance = [], []
        for rec in records.values():
            grades, best = _labels(rec)
            scores = [images[f["image_id"]]["scores"].get(model) for f in rec["frames"]]
            if any(s is None for s in scores):
                continue
            m = study.group_metrics(scores, grades, best)
            if m and m["top1"] is not None:
                vals.append(m["top1"])
                chance.append(best.mean())
        out[model] = {"units": len(vals), "top1": round(float(np.mean(vals)), 3) if vals else None,
                      "chance": round(float(np.mean(chance)), 3) if chance else None}
    return out


def analyze(study_dir: Path, root: Path) -> dict:
    from modules.score_analytics import study_report
    from modules.score_analytics.study_data import read_json

    sample = read_json(study_dir / "sample.json")
    units = {u["id"]: u for u in group_units(sample)}
    images = {r["id"]: r for r in read_json(study_dir / "snapshot.json.gz")["images"]}
    lines = (study_dir / "reviews.jsonl").read_text(encoding="utf-8").splitlines()
    owner = {uid: r for uid, r in study_report.load_reviews(sample, [json.loads(x) for x in lines if x.strip()],
                                                             "owner").items()
             if uid in units and r["status"] == "done"}
    judges = {j: load_judge(root, j, units) for j in JUDGES}
    cons = {uid: c for uid in units
            if (c := consensus([judges[j][uid] for j in JUDGES if uid in judges[j]])) is not None}
    result = {
        "scope": {"group_units": len(units), "owner_labelled": len(owner)},
        "coverage": {j: len(judges[j]) for j in JUDGES} | {"consensus": len(cons)},
        # Reliability first: how well each agent stream matches the owner on shared units.
        "vs_owner": {name: _summarize([agreement(recs[u], owner[u]) for u in owner if u in recs])
                     for name, recs in [*judges.items(), ("consensus", cons)]},
        "inter_judge": {f"{a}~{b}": _summarize([agreement(judges[a][u], judges[b][u])
                                                for u in judges[a] if u in judges[b]])
                        for a, b in combinations(JUDGES, 2)},
        "model_top1": {"owner": model_top1(owner, images), "consensus": model_top1(cons, images)}
                      | {j: model_top1(judges[j], images) for j in JUDGES},
    }
    (root / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("prepare", "run", "analyze"))
    parser.add_argument("--judge", choices=JUDGES)
    parser.add_argument("--study", type=Path, default=STUDY)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--long-edge", type=int, default=1600)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--max-batches", type=int, default=None, help="run: stop after N calls (smoke test)")
    args = parser.parse_args()
    if args.action == "prepare":
        print(json.dumps(prepare(args.study, args.root, args.long_edge)))
    elif args.action == "run":
        if not args.judge:
            parser.error("run needs --judge")
        print(json.dumps(run(args.study, args.root, args.judge, args.timeout, args.max_batches)))
    else:
        print(json.dumps(analyze(args.study, args.root), indent=1))


if __name__ == "__main__":
    main()
