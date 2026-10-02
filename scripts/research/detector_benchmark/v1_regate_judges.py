"""AI CLI judges for the #472 agent pre-screen: Codex, Antigravity and Claude grade each proposed box.

Each item has two blind JPEGs from ``v1_regate.py agent-sample``: the full photo with the proposed box
in red, and a zoomed crop of the box. Judges never see the stratum, rule, scores or owner labels.
Their labels are a pre-screen to decide whether owner labelling is worth it, **not** the owner gate.

Run on the Windows host from the repository root (the CLIs are installed there):

    python scripts/research/detector_benchmark/v1_regate_judges.py run --judge claude
    python scripts/research/detector_benchmark/v1_regate_judges.py table

Raw replies land in ``.agent/scratch/bird_v1_regate/agent_sample/judges/<judge>/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.research.scene_route.cli_judges import command  # noqa: E402

SAMPLE = Path(".agent/scratch/bird_v1_regate/agent_sample")
JUDGES = ("codex", "agy", "claude")
PRESENCE = ("bird", "no_bird", "unsure")
GRADES = ("usable", "poor_crop", "wrong_target", "unsure")
SEED = "bird-v1-regate-agents-1"


def prompt_for(ids: list[int], root: Path, judge: str) -> str:
    how = {"codex": "The photos are attached as images, two per ID in the order listed below.",
           "agy": "Read each local JPEG at the paths below for visual analysis. Do not modify files or run programs.",
           "claude": "Read each JPEG at the paths below with the Read tool. Do not modify files."}[judge]
    files = "\n".join(f"- image_id {i}: full photo {(root / 'img' / f'{i}.jpg').resolve()} ; "
                      f"zoomed crop {(root / 'img' / f'{i}_crop.jpg').resolve()}" for i in ids)
    return (
        f"Independent photo labelling for a bird-detection audit. {how}\n{files}\n\n"
        "Each image_id has a full photo and a zoomed crop. A red rectangle marks a proposed bird box.\n"
        "For each image_id give:\n"
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
        'Return only JSON: {"images":[{"image_id":123,"presence":"bird","grade":"usable","reason":"..."}]} '
        "with every image_id listed above.")


def parse_reply(text: str) -> dict[int, dict]:
    decoder = json.JSONDecoder()
    for start in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            data, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("images"), list):
            out = {}
            for row in data["images"]:
                presence, grade = str(row.get("presence", "")), str(row.get("grade", ""))
                if presence in PRESENCE and grade in GRADES:
                    out[int(row["image_id"])] = {"presence": presence,
                                                 "grade": grade if presence == "bird" else "unsure",
                                                 "reason": str(row.get("reason", ""))[:200]}
            return out
    return {}


def blind_ids(root: Path) -> list[int]:
    with (root / "cohort.csv").open(newline="", encoding="utf-8") as fh:
        ids = sorted(int(r["image_id"]) for r in csv.DictReader(fh))
    random.Random(SEED).shuffle(ids)
    return ids


def load_judge(root: Path, judge: str) -> dict[int, dict]:
    labels: dict[int, dict] = {}
    for f in sorted((root / "judges" / judge).glob("*.json")):
        labels.update(parse_reply(f.read_text(encoding="utf-8", errors="replace")))
    return labels


def run(root: Path, judge: str, batch_size: int, timeout: int) -> Counter:
    done = load_judge(root, judge)
    todo = [i for i in blind_ids(root) if i not in done]
    out_dir = root / "judges" / judge
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    for start in range(0, len(todo), batch_size):
        ids = todo[start:start + batch_size]
        paths = [root / "img" / f"{i}{suffix}.jpg" for i in ids for suffix in ("", "_crop")]
        out = out_dir / f"{start:04d}_{ids[0]}.json"
        try:
            proc = subprocess.run(command(judge, prompt_for(ids, root, judge), paths, out), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                  stdin=subprocess.DEVNULL)
            if judge != "codex":
                out.write_text(proc.stdout, encoding="utf-8")
            (out_dir / f"{out.stem}.stderr.log").write_text(proc.stderr[-4000:], encoding="utf-8")
        except subprocess.TimeoutExpired:
            counts["timeout"] += len(ids)
            continue
        got = parse_reply(out.read_text(encoding="utf-8", errors="replace")) if out.exists() else {}
        counts["labelled"] += len(set(got) & set(ids))
        counts["missing"] += len(set(ids) - set(got))
        print(f"{judge}: {start + len(ids)}/{len(todo)} {dict(counts)}", flush=True)
    return counts


def table(root: Path) -> list[dict]:
    """One row per item: every judge's answer, plus stratum and owner outcome (for analysis only)."""
    with (root / "cohort.csv").open(newline="", encoding="utf-8") as fh:
        cohort = {int(r["image_id"]): r for r in csv.DictReader(fh)}
    votes = {j: load_judge(root, j) for j in JUDGES}
    rows = []
    for iid, meta in sorted(cohort.items()):
        row = {"image_id": iid, "stratum": meta["stratum"], "owner_outcome": meta["owner_outcome"]}
        for j in JUDGES:
            v = votes[j].get(iid)
            row[j] = None if v is None else {"presence": v["presence"], "grade": v["grade"], "reason": v["reason"]}
        rows.append(row)
    (root / "judge_table.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("run", "table"))
    parser.add_argument("--judge", choices=JUDGES)
    parser.add_argument("--root", type=Path, default=SAMPLE)
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.action == "run":
        if not args.judge:
            parser.error("run needs --judge")
        print(json.dumps(run(args.root, args.judge, args.batch_size, args.timeout)))
    else:
        rows = table(args.root)
        print(json.dumps({j: sum(r[j] is not None for r in rows) for j in JUDGES} | {"items": len(rows)}))


if __name__ == "__main__":
    main()
