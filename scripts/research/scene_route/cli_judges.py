"""AI CLI judges for the scene-route sample (#412): Codex, Antigravity and Claude label each photo.

The judges see only the blind page JPEGs, never a model prediction, stratum or owner label. Their
majority vote is a second-opinion label set: it is used to compare the classifier arms while owner
labels are pending, and to queue disagreements for the owner. It is **not** ground truth.

Run on the Windows host from the repository root (the CLIs are installed there):

    python scripts/research/scene_route/cli_judges.py run --judge codex
    python scripts/research/scene_route/cli_judges.py run --judge agy
    python scripts/research/scene_route/cli_judges.py run --judge claude
    python scripts/research/scene_route/cli_judges.py consensus

Raw replies land in ``.agent/scratch/scene_route/sample/judges/<judge>/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
from collections import Counter
from itertools import combinations
from pathlib import Path

SAMPLE = Path(".agent/scratch/scene_route/sample")
JUDGES = ("codex", "agy", "claude")
SCENES = {
    "wildlife_bird": "a bird is the main subject",
    "other_animal": "a non-bird, non-insect animal is the main subject (mammal, reptile, amphibian, fish, pet)",
    "wildlife_insect": "an insect or spider is the main subject",
    "people": "one or more people are the main subject",
    "urban_architecture": "buildings, streets, city scenes or interiors",
    "landscape": "natural scenery without a clear animal or person subject (water, sky, mountains, forest)",
    "vehicles": "a car, aircraft, train, bus or boat is the main subject",
    "plants_flowers": "a flower, plant or leaves is the main subject",
    "other": "anything else (objects, food, abstract, night shots without a clear subject)",
    "cant_tell": "the photo is too unclear to decide",
}


def prompt_for(paths: list[Path], judge: str) -> str:
    defs = "\n".join(f"- {k}: {v}" for k, v in SCENES.items())
    how = {"codex": "The photos are attached as images, in the order of the IDs below.",
           "agy": "Read each local JPEG at the paths below for visual analysis. Do not modify files or run programs.",
           "claude": "Read each JPEG at the paths below with the Read tool. Do not modify files."}[judge]
    files = "\n".join(f"- image_id {p.stem}: {p.resolve()}" for p in paths)
    return (f"Independent photo labelling. {how}\n{files}\n\n"
            f"For each photo give:\n1. scene: exactly one label for the MAIN subject or scene:\n{defs}\n"
            "When an animal or person is clearly the subject, choose that over the setting.\n"
            "2. bird_visible: yes if ANY bird is visible anywhere, however small or partly hidden; otherwise no.\n\n"
            'Return only JSON: {"images":[{"image_id":123,"scene":"landscape","bird_visible":"no"}]} '
            "with every image_id listed above.")


def command(judge: str, prompt: str, paths: list[Path], out: Path) -> list[str]:
    if judge == "codex":
        cli = Path(os.environ["APPDATA"]) / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        args = ["node", str(cli), "exec", "--sandbox", "read-only", "--cd", str(Path.cwd()), "--ephemeral",
                "--output-last-message", str(out)]
        for p in paths:
            args += ["--image", str(p.resolve())]
        return [*args, "--", prompt]
    if judge == "agy":
        return [str(Path(os.environ["LOCALAPPDATA"]) / "agy" / "bin" / "agy.exe"), "-p", prompt,
                "--mode", "plan", "--sandbox", "--output-format", "text"]
    return [str(Path(os.environ["USERPROFILE"]) / ".local" / "bin" / "claude.exe"), "-p", prompt,
            "--restricted", "--tools", "Read", "--output-format", "text"]


def parse_reply(text: str) -> dict[int, dict]:
    """Last JSON object with an ``images`` list in a CLI reply -> {image_id: {scene, bird_visible}}."""
    decoder = json.JSONDecoder()
    for start in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            data, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("images"), list):
            out = {}
            for row in data["images"]:
                scene, bird = row.get("scene"), str(row.get("bird_visible", "")).lower()
                if scene in SCENES and bird in ("yes", "no"):
                    out[int(row["image_id"])] = {"scene": scene, "bird_visible": bird}
            return out
    return {}


def _cohort_ids(root: Path) -> list[int]:
    with (root / "cohort.csv").open(newline="", encoding="utf-8") as fh:
        return sorted(int(r["image_id"]) for r in csv.DictReader(fh))


def load_judge(root: Path, judge: str) -> dict[int, dict]:
    labels: dict[int, dict] = {}
    for f in sorted((root / "judges" / judge).glob("*.json")):
        labels.update(parse_reply(f.read_text(encoding="utf-8", errors="replace")))
    return labels


def run(root: Path, judge: str, batch_size: int, timeout: int) -> Counter:
    done = load_judge(root, judge)
    todo = [i for i in _cohort_ids(root) if i not in done]
    out_dir = root / "judges" / judge
    out_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    for start in range(0, len(todo), batch_size):
        ids = todo[start:start + batch_size]
        paths = [root / "page" / "img" / f"{i}.jpg" for i in ids]
        out = out_dir / f"{ids[0]}_{ids[-1]}.json"
        prompt = prompt_for(paths, judge)
        try:
            proc = subprocess.run(command(judge, prompt, paths, out), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
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


def consensus(root: Path) -> dict:
    """Majority of the judges that answered. Scene ties become ``cant_tell``; bird ties count as visible."""
    ids = _cohort_ids(root)
    votes = {j: load_judge(root, j) for j in JUDGES}
    rows, disputed = [], []
    for i in ids:
        answers = [votes[j][i] for j in JUDGES if i in votes[j]]
        scene_votes = Counter(a["scene"] for a in answers).most_common()
        bird_votes = Counter(a["bird_visible"] for a in answers)
        scene = scene_votes[0][0] if scene_votes and scene_votes[0][1] >= 2 else "cant_tell"
        bird = "yes" if bird_votes["yes"] >= bird_votes["no"] and bird_votes["yes"] else "no"
        rows.append({"image_id": i, "scene": scene, "bird_visible": bird})
        if len(answers) < len(JUDGES) or len(scene_votes) > 1 or len(bird_votes) > 1:
            disputed.append({"image_id": i, **{j: json.dumps(votes[j].get(i)) for j in JUDGES}})
    with (root / "judge_labels.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=("image_id", "scene", "bird_visible"))
        w.writeheader()
        w.writerows(rows)
    with (root / "judge_disputed.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=("image_id", *JUDGES))
        w.writeheader()
        w.writerows(disputed)
    pairwise = {}
    for a, b in combinations(JUDGES, 2):
        both = [i for i in ids if i in votes[a] and i in votes[b]]
        pairwise[f"{a}~{b}"] = {
            "n": len(both),
            "scene_agree": sum(votes[a][i]["scene"] == votes[b][i]["scene"] for i in both),
            "bird_agree": sum(votes[a][i]["bird_visible"] == votes[b][i]["bird_visible"] for i in both)}
    summary = {"images": len(ids), "coverage": {j: len(set(votes[j]) & set(ids)) for j in JUDGES},
               "unanimous": len(ids) - len(disputed), "disputed": len(disputed),
               "scene_counts": dict(Counter(r["scene"] for r in rows)), "pairwise": pairwise}
    (root / "judge_summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("run", "consensus"))
    parser.add_argument("--judge", choices=JUDGES)
    parser.add_argument("--root", type=Path, default=SAMPLE)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.action == "run":
        if not args.judge:
            parser.error("run needs --judge")
        print(json.dumps(run(args.root, args.judge, args.batch_size, args.timeout)))
    else:
        print(json.dumps(consensus(args.root), indent=1))


if __name__ == "__main__":
    main()
