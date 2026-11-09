"""#694 rubric amendment (2026-11-08, revision 2): control candidates, blind owner review and the lock.

No provider calls or database writes. Every output is a local, create-only artifact.

    python -m scripts.research.detector_benchmark.promotion_694_controls round --round 1
    python -m scripts.research.detector_benchmark.promotion_694_controls record --round 1 --labels <owner.json>
    python -m scripts.research.detector_benchmark.promotion_694_controls lock

``round`` writes a sheet the owner labels: opaque tokens and EXIF-free images, with no stratum,
candidate position or label. ``record`` stores the owner's blind labels with the stored labels and
decisions, before the stored labels are shown. ``lock`` writes the 8 / 6 / 6 draw from confirmed
items only, and a lock receipt with the hash of every artifact.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

COMPOSITION = {"wrong_target": 8, "poor_crop": 6, "usable": 6}
LABEL_CHOICES = ("usable", "poor_crop", "wrong_target", "unsure")
ROOT = Path(".agent/scratch/promotion-694")
FREEZE = "freeze-receipt-rubric-20261108.json"
VALIDATION = "controls3-validation-20261108.json"
BLIND = "calibration-r3-blind-20261108"
MANIFEST = "calibration-r3-manifest-20261108.json"
KEY = "calibration-r3-answer-key-20261108.json"
LOCK = "lock-receipt-controls3-20261108.json"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rank(seed, image_id):
    return hashlib.sha256(f"{seed}:{image_id}".encode()).hexdigest()


def decide(blind, stored):
    return "confirmed" if blind == stored else "rejected"


def candidate_lists(labels, answer_keys, sample_ids, seed):
    """Per-stratum candidates: earlier non-wrong_target frames out, the same 8 wrong_target reused."""
    wrong = [{str(v["image_id"]) for v in key.values() if v["grade"] == "wrong_target"} for key in answer_keys]
    if any(w != wrong[0] for w in wrong) or len(wrong[0]) != COMPOSITION["wrong_target"]:
        raise ValueError("the wrong_target frames differ between earlier draws")
    earlier = {str(v["image_id"]) for key in answer_keys for v in key.values() if v["grade"] != "wrong_target"}
    sample = {str(i) for i in sample_ids}
    strata = {"wrong_target": sorted(wrong[0], key=lambda i: rank(seed, i))}
    for grade in ("poor_crop", "usable"):
        pool = {str(r["image_id"]) for r in labels if r["box_label"] == grade} - earlier - sample
        strata[grade] = sorted(pool, key=lambda i: rank(seed, i))
    return {grade: [int(i) for i in ids] for grade, ids in strata.items()}


def _ordered(items, order_seed):
    return sorted(items, key=lambda r: rank(order_seed, r["image_id"]))


def replay(candidates, reviews, stored):
    """Re-derive every review round from the frozen lists, and check the record follows them.

    Returns the confirmed items per stratum, the next round (empty when complete or stopped), and
    a stop reason. Raises ValueError when the record breaks a rule.
    """
    strata, order_seed = candidates["strata"], candidates["review_order_seed"]
    expected = _ordered([{"image_id": i, "stratum": s, "position": p, "replaces": None}
                         for s, n in COMPOSITION.items() for p, i in enumerate(strata[s][:n])], order_seed)
    pointer = {s: COMPOSITION[s] for s in COMPOSITION}
    confirmed = {s: [] for s in COMPOSITION}
    rounds = sorted({r["round"] for r in reviews})
    if rounds != list(range(1, len(rounds) + 1)):
        raise ValueError("review rounds must run 1, 2, 3 without gaps")
    stopped = None
    for number in rounds:
        if stopped:
            raise ValueError("a review round follows a stop")
        got = [r for r in reviews if r["round"] == number]
        fields = ("image_id", "stratum", "position", "replaces")
        if [{k: r.get(k) for k in fields} for r in got] != [{k: e[k] for k in fields} for e in expected]:
            raise ValueError(f"round {number} does not follow the frozen review order")
        for row in got:
            if row["blind"] not in LABEL_CHOICES:
                raise ValueError("invalid blind label")
            if row["stored"] != stored[str(row["image_id"])]:
                raise ValueError("stored label differs from the source labels")
            if row["decision"] != decide(row["blind"], row["stored"]):
                raise ValueError("decision does not follow from the labels")
        rejected = [r for r in got if r["decision"] == "rejected"]
        for row in got:
            if row["decision"] == "confirmed":
                confirmed[row["stratum"]].append(row["image_id"])
        expected = []
        if any(r["stratum"] == "wrong_target" for r in rejected):
            stopped = "a wrong_target control was rejected"
            continue
        for row in rejected:
            stratum = row["stratum"]
            if pointer[stratum] >= len(strata[stratum]):
                stopped = f"{stratum} candidates exhausted"
                expected = []
                break
            expected.append({"image_id": strata[stratum][pointer[stratum]], "stratum": stratum,
                             "position": pointer[stratum], "replaces": row["image_id"]})
            pointer[stratum] += 1
        expected = _ordered(expected, order_seed)
    complete = not stopped and {s: len(v) for s, v in confirmed.items()} == COMPOSITION
    return {"confirmed": confirmed, "next_round": [] if (stopped or complete) else expected,
            "stopped": stopped, "complete": complete}


def _copy_without_exif(src, target):
    with Image.open(src) as image:
        image.convert("RGB").save(target, quality=95, exif=b"")
    with Image.open(target) as check:
        if check.getexif():
            raise ValueError(f"EXIF survived in {target.name}")


def write_round_sheet(items, round_number, source, out_dir):
    """Owner-facing sheet: opaque tokens and EXIF-free images only. Returns the private token map."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    private, public = [], []
    for n, item in enumerate(items, 1):
        token = f"r{round_number}-{n:02}"
        files = []
        for kind, suffix in (("full", "overview"), ("crop", "crop")):
            target = out_dir / f"{token}_{suffix}.jpg"
            _copy_without_exif(Path(source) / kind / f"{item['image_id']}.jpg", target)
            files.append(target.name)
        public.append({"token": token, "files": files})
        private.append({**item, "token": token})
    (out_dir / "sheet.json").write_text(json.dumps({"round": round_number, "items": public}, indent=2) + "\n",
                                        encoding="utf-8")
    return private


def record_round(path, candidates, stored, sheet, blind, notes):
    """Store one round's blind labels, the stored labels and the decisions. Rounds are append-only."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"reviews": []}
    round_number = int(sheet[0]["token"].split("-")[0][1:])
    if any(r["round"] == round_number for r in data["reviews"]):
        raise ValueError(f"round {round_number} is already recorded")
    if set(blind) != {i["token"] for i in sheet}:
        raise ValueError("the owner must label every item in the round")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for item in sheet:
        label = stored[str(item["image_id"])]
        rows.append({"round": round_number, "token": item["token"], "image_id": item["image_id"],
                     "stratum": item["stratum"], "position": item["position"], "replaces": item["replaces"],
                     "blind": blind[item["token"]], "stored": label,
                     "decision": decide(blind[item["token"]], label), "note": notes.get(item["token"], ""),
                     "recorded_at": now})
    data["reviews"].extend(rows)
    replay(candidates, data["reviews"], stored)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return rows


def lock(root, candidates, stored, validation, source, rubric, repo):
    """Write the 8 / 6 / 6 draw from confirmed items, then the lock receipt. Create-only."""
    root, repo = Path(root), Path(repo)
    state = replay(candidates, json.loads(Path(validation).read_text(encoding="utf-8"))["reviews"], stored)
    if not state["complete"]:
        raise ValueError(f"the review is not complete: {state['stopped'] or 'rounds remain'}")
    for name in (BLIND, MANIFEST, KEY, LOCK):
        if (root / name).exists():
            raise FileExistsError(name)
    seed = candidates["seed"]
    chosen = [(s, i) for s in COMPOSITION for i in state["confirmed"][s]]
    chosen.sort(key=lambda row: rank(seed, f"order:{row[1]}"))
    blind = root / BLIND
    blind.mkdir()
    items, answers, hashes = [], {}, {}
    for number, (stratum, image_id) in enumerate(chosen, 1):
        token = f"d{number:02}"
        files = []
        for kind, suffix in (("full", "overview"), ("crop", "crop")):
            target = blind / f"{token}_{suffix}.jpg"
            _copy_without_exif(Path(source) / kind / f"{image_id}.jpg", target)
            files.append(target.relative_to(repo).as_posix())
            hashes[target.name] = sha256(target)
        items.append({"id": token, "files": files})
        answers[token] = {"image_id": image_id, "grade": stratum, "usable": stratum == "usable"}
    outputs = {"manifest": root / MANIFEST, "answer_key": root / KEY, "lock": root / LOCK}
    with outputs["answer_key"].open("x", encoding="utf-8") as handle:
        json.dump(answers, handle, indent=2)
        handle.write("\n")
    with outputs["manifest"].open("x", encoding="utf-8") as handle:
        json.dump({"items": items, "sha256": hashes, "rubric_sha256": sha256(rubric)}, handle, indent=2)
        handle.write("\n")
    files = {name: {"path": Path(path).resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256(path)}
             for name, path in (("manifest", outputs["manifest"]), ("answer_key", outputs["answer_key"]),
                                ("validation", validation), ("rubric", rubric))}
    with outputs["lock"].open("x", encoding="utf-8") as handle:
        json.dump({"locked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files},
                  handle, indent=2)
        handle.write("\n")
    return outputs


def load_frozen(root):
    """The frozen candidates, rubric and source labels, each checked against the freeze receipt."""
    receipt = json.loads((root / FREEZE).read_text(encoding="utf-8"))
    for name, field in (("candidates", "candidates_sha256"), ("rubric", "rubric_sha256")):
        if sha256(root / receipt[name]) != receipt[field]:
            raise ValueError(f"frozen {name} changed")
    source = root.parent / "bird_v1_owner_labels" / "box_page"
    if sha256(source / "box_labels.csv") != receipt["source_labels_sha256"]:
        raise ValueError("source labels changed since the freeze")
    with (source / "box_labels.csv").open(encoding="utf-8-sig") as handle:
        stored = {r["image_id"]: r["box_label"] for r in csv.DictReader(handle)}
    candidates = json.loads((root / receipt["candidates"]).read_text(encoding="utf-8"))
    return receipt, candidates, stored, source


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("round", "record"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--round", type=int, required=True)
        if name == "record":
            cmd.add_argument("--labels", type=Path, required=True,
                             help='JSON {"labels": {token: label}, "notes": {token: text}}')
    sub.add_parser("lock")
    args = parser.parse_args()
    root = args.root.resolve()
    receipt, candidates, stored, source = load_frozen(root)
    validation = root / VALIDATION
    reviews = json.loads(validation.read_text(encoding="utf-8"))["reviews"] if validation.exists() else []
    state = replay(candidates, reviews, stored)
    private_path = root / f"controls3-round{getattr(args, 'round', 0)}-private.json"
    if args.command == "round":
        if args.round != len({r["round"] for r in reviews}) + 1 or not state["next_round"]:
            raise SystemExit(f"no round {args.round} to write: {state['stopped'] or 'review complete'}")
        sheet = write_round_sheet(state["next_round"], args.round, source, root / f"controls3-round{args.round}")
        with private_path.open("x", encoding="utf-8") as handle:
            json.dump(sheet, handle, indent=2)
        print(json.dumps({"round": args.round, "items": len(sheet)}))
    elif args.command == "record":
        owner = json.loads(args.labels.read_text(encoding="utf-8"))
        sheet = json.loads(private_path.read_text(encoding="utf-8"))
        rows = record_round(validation, candidates, stored, sheet, owner["labels"], owner.get("notes", {}))
        after = replay(candidates, json.loads(validation.read_text(encoding="utf-8"))["reviews"], stored)
        print(json.dumps({"round": args.round, "recorded": len(rows),
                          "rejected": sum(r["decision"] == "rejected" for r in rows),
                          "next_round_items": len(after["next_round"]), "stopped": after["stopped"],
                          "complete": after["complete"]}))
    else:
        outputs = lock(root, candidates, stored, validation, source, root / receipt["rubric"],
                       repo=Path(__file__).resolve().parents[3])
        print(json.dumps({name: str(path.name) for name, path in outputs.items()}))


if __name__ == "__main__":
    main()
