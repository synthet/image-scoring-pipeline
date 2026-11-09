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


def _render_pair(render, item, overview, crop):
    """Run a renderer into temporary files, then keep EXIF-free copies only."""
    raw = [overview.with_name(f"raw-{overview.name}"), crop.with_name(f"raw-{crop.name}")]
    render(item, raw[0], raw[1])
    for src, target in zip(raw, (overview, crop)):
        _copy_without_exif(src, target)
        src.unlink()


def write_round_sheet(items, round_number, source, out_dir, render=None):
    """Owner-facing sheet: opaque tokens and EXIF-free images only. Returns the private token map.

    Images are copied from ``source`` (``full/`` and ``crop/``), or drawn by ``render(item, overview, crop)``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    private, public = [], []
    for n, item in enumerate(items, 1):
        token = f"r{round_number}-{n:02}"
        overview, crop = out_dir / f"{token}_overview.jpg", out_dir / f"{token}_crop.jpg"
        if render is not None:
            _render_pair(render, item, overview, crop)
        else:
            _copy_without_exif(Path(source) / "full" / f"{item['image_id']}.jpg", overview)
            _copy_without_exif(Path(source) / "crop" / f"{item['image_id']}.jpg", crop)
        files = [overview.name, crop.name]
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


def _write_lock(root, confirmed, seed, make_images, rubric, records, names, repo):
    """Write the d01–d20 draw, answer key, manifest and lock receipt. Create-only."""
    root, repo = Path(root), Path(repo)
    for name in names.values():
        if (root / name).exists():
            raise FileExistsError(name)
    chosen = [(s, i) for s in COMPOSITION for i in confirmed[s]]
    chosen.sort(key=lambda row: rank(seed, f"order:{row[1]}"))
    blind = root / names["blind"]
    blind.mkdir()
    items, answers, hashes = [], {}, {}
    for number, (stratum, image_id) in enumerate(chosen, 1):
        token = f"d{number:02}"
        overview, crop = blind / f"{token}_overview.jpg", blind / f"{token}_crop.jpg"
        make_images({"image_id": image_id, "stratum": stratum}, overview, crop)
        for target in (overview, crop):
            hashes[target.name] = sha256(target)
        items.append({"id": token, "files": [p.relative_to(repo).as_posix() for p in (overview, crop)]})
        answers[token] = {"image_id": image_id, "grade": stratum, "usable": stratum == "usable"}
    outputs = {"manifest": root / names["manifest"], "answer_key": root / names["key"], "lock": root / names["lock"]}
    with outputs["answer_key"].open("x", encoding="utf-8") as handle:
        json.dump(answers, handle, indent=2)
        handle.write("\n")
    with outputs["manifest"].open("x", encoding="utf-8") as handle:
        json.dump({"items": items, "sha256": hashes, "rubric_sha256": sha256(rubric)}, handle, indent=2)
        handle.write("\n")
    entries = (("manifest", outputs["manifest"]), ("answer_key", outputs["answer_key"]), *records, ("rubric", rubric))
    files = {name: {"path": Path(path).resolve().relative_to(root.resolve()).as_posix(), "sha256": sha256(path)}
             for name, path in entries}
    with outputs["lock"].open("x", encoding="utf-8") as handle:
        json.dump({"locked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files},
                  handle, indent=2)
        handle.write("\n")
    return outputs


def lock(root, candidates, stored, validation, source, rubric, repo):
    """Revision 2: write the 8 / 6 / 6 draw from confirmed items, copying the reviewed images."""
    state = replay(candidates, json.loads(Path(validation).read_text(encoding="utf-8"))["reviews"], stored)
    if not state["complete"]:
        raise ValueError(f"the review is not complete: {state['stopped'] or 'rounds remain'}")

    def copy_images(item, overview, crop):
        _copy_without_exif(Path(source) / "full" / f"{item['image_id']}.jpg", overview)
        _copy_without_exif(Path(source) / "crop" / f"{item['image_id']}.jpg", crop)

    names = {"blind": BLIND, "manifest": MANIFEST, "key": KEY, "lock": LOCK}
    return _write_lock(root, state["confirmed"], candidates["seed"], copy_images, rubric,
                       (("validation", validation),), names, repo)


# --- Revision 3 (2026-11-09) ---------------------------------------------------------------------

FREEZE4 = "freeze-receipt-rubric-rev3-20261109.json"
VALIDATION4 = "controls4-validation-20261109.json"
BLIND4 = "calibration-r4-blind-20261109"
MANIFEST4 = "calibration-r4-manifest-20261109.json"
KEY4 = "calibration-r4-answer-key-20261109.json"
LOCK4 = "lock-receipt-controls4-20261109.json"
ROUND1_STOP = "a wrong_target control was rejected"


def replay_rev3(candidates, batch, round1, later, stored):
    """Revision 3: round 1 as recorded under revision 2, then round 2 (spare batch plus the poor_crop
    replacement) and any single-item poor_crop rounds after it. Raises ValueError on a broken record."""
    first = replay(candidates, round1, stored)
    if first["stopped"] != ROUND1_STOP:
        raise ValueError("round 1 did not stop on a rejected wrong_target control")
    rejected = {s: [r["image_id"] for r in round1 if r["stratum"] == s and r["decision"] == "rejected"]
                for s in COMPOSITION}
    if rejected["usable"] or len(rejected["poor_crop"]) != 1:
        raise ValueError("round 1 outcome is outside revision 3")
    strata, order_seed = candidates["strata"], batch["review_order_seed"]
    confirmed = {s: list(first["confirmed"][s]) for s in COMPOSITION}
    need = COMPOSITION["wrong_target"] - len(confirmed["wrong_target"])
    frozen = batch["poor_crop_replacement"]
    pointer = COMPOSITION["poor_crop"]
    if frozen["position"] != pointer or frozen["image_id"] != strata["poor_crop"][pointer]:
        raise ValueError("frozen replacement differs from the candidate list")
    pointer += 1
    batch_ids = set(batch["batch_low"]) | set(batch["batch_rest"])
    meta = {i: {"image_id": i, "stratum": None, "position": None, "replaces": None, "kind": "batch"} for i in batch_ids}
    meta[frozen["image_id"]] = {"image_id": frozen["image_id"], "stratum": "poor_crop", "position": frozen["position"],
                                "replaces": rejected["poor_crop"][0], "kind": "replacement"}
    if sorted(batch["round2_review_order"]) != sorted(meta):
        raise ValueError("frozen round 2 order differs from the batch")
    expected = [meta[i] for i in batch["round2_review_order"]]
    rounds = sorted({r["round"] for r in later})
    if rounds != list(range(2, 2 + len(rounds))):
        raise ValueError("later rounds must run 2, 3, 4 without gaps")
    fields = ("image_id", "stratum", "position", "replaces", "kind")
    labels, new_wrong, stopped = {}, [], None
    for number in rounds:
        if stopped:
            raise ValueError("a review round follows a stop")
        got = [r for r in later if r["round"] == number]
        if [{k: r.get(k) for k in fields} for r in got] != [{k: e[k] for k in fields} for e in expected]:
            raise ValueError(f"round {number} does not follow the frozen order")
        following = []
        for row in got:
            if row["blind"] not in LABEL_CHOICES:
                raise ValueError("invalid blind label")
            if row["kind"] == "batch":
                if row["stored"] is not None or row["decision"] != "labelled":
                    raise ValueError("a batch row carries a stored label or a decision")
                labels[row["image_id"]] = row["blind"]
                continue
            if row["stored"] != stored[str(row["image_id"])]:
                raise ValueError("stored label differs from the source labels")
            if row["decision"] != decide(row["blind"], row["stored"]):
                raise ValueError("decision does not follow from the labels")
            if row["decision"] == "confirmed":
                confirmed["poor_crop"].append(row["image_id"])
            elif pointer >= len(strata["poor_crop"]):
                stopped = "poor_crop candidates exhausted"
            else:
                following.append({"image_id": strata["poor_crop"][pointer], "stratum": "poor_crop",
                                  "position": pointer, "replaces": row["image_id"], "kind": "replacement"})
                pointer += 1
        if number == 2:
            spares = [i for i in sorted(batch_ids, key=lambda i: rank(batch["spare_seed"], i))
                      if labels.get(i) == "wrong_target"]
            if len(spares) < need:
                stopped = f"fewer than {need} wrong_target labels in the batch"
            new_wrong = spares[:need]
            confirmed["wrong_target"].extend(new_wrong)
        expected = [] if stopped else _ordered(following, order_seed)
    complete = bool(rounds) and not stopped and {s: len(v) for s, v in confirmed.items()} == COMPOSITION
    return {"confirmed": confirmed, "next_round": [] if (stopped or complete) else expected,
            "stopped": stopped, "complete": complete, "new_wrong_target": new_wrong}


def record_round_rev3(path, candidates, batch, stored, round1, sheet, blind, notes):
    """Store a revision-3 round. Batch items keep the owner's label only; replacements are decided as before."""
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
        label = blind[item["token"]]
        known = None if item["kind"] == "batch" else stored[str(item["image_id"])]
        rows.append({"round": round_number, "token": item["token"], "image_id": item["image_id"],
                     "stratum": item["stratum"], "position": item["position"], "replaces": item["replaces"],
                     "kind": item["kind"], "blind": label, "stored": known,
                     "decision": "labelled" if known is None else decide(label, known),
                     "note": notes.get(item["token"], ""), "recorded_at": now})
    data["reviews"].extend(rows)
    replay_rev3(candidates, batch, round1, data["reviews"], stored)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return rows


def lock_rev3(root, candidates, batch, stored, round1_path, round2_path, rubric, render, repo):
    """Revision 3: render all 20 confirmed controls with one renderer, then lock both validation records."""
    round1 = json.loads(Path(round1_path).read_text(encoding="utf-8"))["reviews"]
    later = json.loads(Path(round2_path).read_text(encoding="utf-8"))["reviews"]
    state = replay_rev3(candidates, batch, round1, later, stored)
    if not state["complete"]:
        raise ValueError(f"the review is not complete: {state['stopped'] or 'rounds remain'}")
    names = {"blind": BLIND4, "manifest": MANIFEST4, "key": KEY4, "lock": LOCK4}
    return _write_lock(root, state["confirmed"], candidates["seed"],
                       lambda item, overview, crop: _render_pair(render, item, overview, crop), rubric,
                       (("round1", round1_path), ("round2", round2_path)), names, repo)


def load_frozen_rev3(root):
    """Revision 3's frozen inputs, each checked against its freeze receipt and the revision-2 chain."""
    receipt = json.loads((root / FREEZE4).read_text(encoding="utf-8"))
    for name, field in (("amendment", "amendment_sha256"), ("rubric", "rubric_sha256"), ("batch", "batch_sha256"),
                        ("pbird_snapshot", "pbird_snapshot_sha256")):
        if sha256(root / receipt[name]) != receipt[field]:
            raise ValueError(f"frozen {name} changed")
    if sha256(root / FREEZE) != receipt["revision2_freeze_sha256"]:
        raise ValueError("revision 2 freeze changed")
    if sha256(root / VALIDATION) != receipt["round1_validation_sha256"]:
        raise ValueError("round 1 record changed")
    _, candidates, stored, source = load_frozen(root)
    batch = json.loads((root / receipt["batch"]).read_text(encoding="utf-8"))
    round1 = json.loads((root / VALIDATION).read_text(encoding="utf-8"))["reviews"]
    return receipt, candidates, batch, stored, round1, source


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


def real_renderer(root, source):
    """Draw every revision-3 frame the same way: the owner-labelled box for labelled images, the cohort
    box for batch images, on the localization rendition. Runs in gpu-shell (RAW decode, database)."""
    from scripts.research.detector_benchmark.v1_regate import _render

    labelled = {int(r["image_id"]): r["box"]
                for r in json.loads((Path(source) / "manifest.json").read_text(encoding="utf-8"))["rows"]}
    cohort = {int(r["image_id"]): r for r in
              json.loads((root / "cohort-frozen-20261026.json").read_text(encoding="utf-8"))["images"]}

    def file_path(image_id):
        if image_id in cohort:
            return cohort[image_id]["file_path"]
        from modules.db_connector import get_connector

        row = get_connector().query_one("SELECT file_path FROM images WHERE id = ?", (image_id,))
        if not row or not row.get("file_path"):
            raise ValueError(f"no file path for image {image_id}")
        return row["file_path"]

    def render(item, overview, crop):
        image_id = int(item["image_id"])
        if image_id in labelled:
            box = labelled[image_id]
        else:
            row = cohort[image_id]
            box = [row["x1"], row["y1"], row["x2"], row["y2"]]
        _render(file_path(image_id), box, overview, crop)

    return render


def main_rev3(args, root):
    receipt, candidates, batch, stored, round1, source = load_frozen_rev3(root)
    record = root / VALIDATION4
    later = json.loads(record.read_text(encoding="utf-8"))["reviews"] if record.exists() else []
    state = replay_rev3(candidates, batch, round1, later, stored)
    private_path = root / f"controls4-round{getattr(args, 'round', 0)}-private.json"
    if args.command == "round":
        if args.round != len({r["round"] for r in later}) + 2 or not state["next_round"]:
            raise SystemExit(f"no round {args.round} to write: {state['stopped'] or 'review complete'}")
        sheet = write_round_sheet(state["next_round"], args.round, None, root / f"controls4-round{args.round}",
                                  render=real_renderer(root, source))
        with private_path.open("x", encoding="utf-8") as handle:
            json.dump(sheet, handle, indent=2)
        print(json.dumps({"round": args.round, "items": len(sheet)}))
    elif args.command == "record":
        owner = json.loads(args.labels.read_text(encoding="utf-8"))
        sheet = json.loads(private_path.read_text(encoding="utf-8"))
        rows = record_round_rev3(record, candidates, batch, stored, round1, sheet, owner["labels"],
                                 owner.get("notes", {}))
        after = replay_rev3(candidates, batch, round1, json.loads(record.read_text(encoding="utf-8"))["reviews"],
                            stored)
        print(json.dumps({"round": args.round, "recorded": len(rows),
                          "rejected": sum(r["decision"] == "rejected" for r in rows),
                          "new_wrong_target": len(after["new_wrong_target"]),
                          "next_round_items": len(after["next_round"]), "stopped": after["stopped"],
                          "complete": after["complete"]}))
    else:
        outputs = lock_rev3(root, candidates, batch, stored, root / VALIDATION, record, root / receipt["rubric"],
                            real_renderer(root, source), repo=Path(__file__).resolve().parents[3])
        print(json.dumps({name: str(path.name) for name, path in outputs.items()}))


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
    if (root / FREEZE4).exists():
        main_rev3(args, root)
        return
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
