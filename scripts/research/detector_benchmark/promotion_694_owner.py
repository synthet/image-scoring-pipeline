"""#694 owner-labelled validation (2026-11-09): the owner labels the frozen 390-frame sample directly.

No provider calls or database writes. Every output is a local artifact; recorded batches are final.

    python -m scripts.research.detector_benchmark.promotion_694_owner render      (gpu-shell: RAW decode)
    python -m scripts.research.detector_benchmark.promotion_694_owner record --batch 1 --labels <owner.json>
    python -m scripts.research.detector_benchmark.promotion_694_owner status

``render`` draws every frame the same way as the controls, EXIF-free, under the opaque token of its
place in the frozen mixed order, and writes a public sheet with tokens and files only. ``record``
appends one batch of the owner's labels. Nothing here prints a band, an image id or a label count;
the gate's ``analyze-owner`` reads the full record once all 13 batches are in.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(".agent/scratch/promotion-694")
FREEZE = "freeze-receipt-owner-labels-20261109.json"
FREEZE_SHA256 = "84494706fb7f0b1fdfab399c7b2c46cded7be95c1b64fb14b4a5d62b325da304"
ORDER = "owner-order-20261109.json"
BLIND = "owner-sample-20261109"
MANIFEST = "owner-sample-manifest-20261109.json"
RECORD = "owner-labels-record-20261109.json"
SEED = "bird-694-owner-sample-1"
BATCH_SIZE = 30
BATCHES = 13
LABEL_CHOICES = ("usable", "poor_crop", "wrong_target", "no_bird", "unsure")
# Note wording that points at an outcome, taken from the owner's own reasons in control rounds 1 to 3.
NOTE_HINTS = {
    "no_bird": r"\bnot a bird\b|\bno bird\b",
    "poor_crop": r"clipped|\bcut\b|outside|too (tight|loose)",
    "wrong_target": r"wrong (bird|target)|other bird|two birds|several birds|not the \w+ bird",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mixed_order(image_ids, seed=SEED, batch_size=BATCH_SIZE):
    """The frozen order: ``sha256(seed + ":" + image_id)`` ascending; token = place, batches of 30."""
    order = sorted((int(i) for i in image_ids), key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())
    return [{"token": f"v{n:03}", "image_id": image_id, "batch": (n - 1) // batch_size + 1}
            for n, image_id in enumerate(order, 1)]


def load_frozen(root, sample):
    """Check the pinned freeze receipt, the pre-registration and the order; return the order's items."""
    root = Path(root)
    if sha256(root / FREEZE) != FREEZE_SHA256:
        raise ValueError("owner-labels freeze receipt changed")
    receipt = json.loads((root / FREEZE).read_text(encoding="utf-8"))
    for key in ("preregistration", "order"):
        if sha256(root / receipt[key]) != receipt[f"{key}_sha256"]:
            raise ValueError(f"frozen {key} changed")
    frozen = json.loads((root / receipt["order"]).read_text(encoding="utf-8"))
    if frozen["seed"] != SEED or frozen["batch_size"] != BATCH_SIZE:
        raise ValueError("frozen order rule changed")
    if frozen["items"] != mixed_order([r["image_id"] for r in sample]):
        raise ValueError("frozen order does not match the frozen sample")
    return frozen["items"]


def note_conflicts(labels, notes):
    """Tokens whose note names an outcome other than their label: shown back to the owner once."""
    flagged = []
    for token, label in labels.items():
        note = (notes.get(token) or "").lower()
        if any(other != label and re.search(pattern, note) for other, pattern in NOTE_HINTS.items()):
            flagged.append(token)
    return flagged


def record_batch(path, items, batch, labels, notes, original_sha256=None):
    """Append one batch of the owner's labels. Batches go in order and are final once recorded."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"batches": []}
    done = [b["batch"] for b in data["batches"]]
    if batch in done:
        raise ValueError(f"batch {batch} is already recorded")
    if batch != len(done) + 1:
        raise ValueError(f"batches are recorded in order; next is {len(done) + 1}")
    tokens = [r["token"] for r in items if r["batch"] == batch]
    if set(labels) != set(tokens):
        raise ValueError("the owner must label every frame of the batch, and only those")
    if any(label not in LABEL_CHOICES for label in labels.values()):
        raise ValueError("unknown label")
    if not set(notes) <= set(tokens):
        raise ValueError("note for a frame outside the batch")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [{"token": t, "label": labels[t], "note": notes.get(t, ""), "batch": batch, "recorded_at": now}
            for t in tokens]
    data["batches"].append({"batch": batch, "recorded_at": now, "original_sha256": original_sha256, "rows": rows})
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"batch": batch, "recorded": len(rows), "batches_done": len(done) + 1,
            "batches_left": BATCHES - len(done) - 1}


def sample_renderer(sample):
    """Draw a frame from its frozen sample box on the localization rendition, as for the controls."""
    from scripts.research.detector_benchmark.v1_regate import _render

    by_id = {int(r["image_id"]): r for r in sample}

    def render(item, overview, crop):
        row = by_id[int(item["image_id"])]
        _render(row["file_path"], [row["x1"], row["y1"], row["x2"], row["y2"]], overview, crop)

    return render


def render_sample(root, repo, items, sample, render):
    """Render missing pairs (a stopped run resumes), then write the manifest and public sheet once."""
    from scripts.research.detector_benchmark.promotion_694_controls import _render_pair

    root, repo = Path(root), Path(repo)
    out = root / BLIND
    out.mkdir(exist_ok=True)
    by_id = {int(r["image_id"]): r for r in sample}
    rendered = 0
    for item in items:
        overview, crop = out / f"{item['token']}_overview.jpg", out / f"{item['token']}_crop.jpg"
        if not (overview.exists() and crop.exists()):
            _render_pair(render, item, overview, crop)
            rendered += 1
    rows, hashes = [], {}
    for item in items:
        files = [str((out / f"{item['token']}_{kind}.jpg").relative_to(repo)).replace("\\", "/")
                 for kind in ("overview", "crop")]
        hashes.update({name: sha256(repo / name) for name in files})
        source = by_id[item["image_id"]]
        rows.append({"id": item["token"], **{k: source[k] for k in ("image_id", "band", "folder_id", "run_id",
                                                                    "region_id", "rendition_hash")},
                     "batch": item["batch"], "files": files})
    with (root / MANIFEST).open("x", encoding="utf-8") as handle:
        json.dump({"freeze_sha256": FREEZE_SHA256, "items": rows, "sha256": hashes}, handle, indent=2)
        handle.write("\n")
    sheet = {"batches": {str(b): [{"token": r["id"], "files": [Path(f).name for f in r["files"]]}
                                  for r in rows if r["batch"] == b] for b in range(1, BATCHES + 1)}}
    with (out / "sheet.json").open("x", encoding="utf-8") as handle:
        json.dump(sheet, handle, indent=2)
        handle.write("\n")
    return rendered


def main():
    from scripts.research.detector_benchmark.promotion_694_gate import verify_frozen

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("render")
    record = sub.add_parser("record")
    record.add_argument("--batch", type=int, required=True)
    record.add_argument("--labels", type=Path, required=True,
                        help='JSON {"labels": {token: label}, "notes": {token: text}}')
    record.add_argument("--original", type=Path, help="the owner's paste as sent, kept when notes were resolved")
    sub.add_parser("status")
    args = parser.parse_args()
    root, repo = args.root.resolve(), Path(__file__).resolve().parents[3]
    _, sample = verify_frozen(root)
    items = load_frozen(root, sample)
    if args.command == "render":
        print(json.dumps({"rendered": render_sample(root, repo, items, sample, sample_renderer(sample)),
                          "frames": len(items)}))
    elif args.command == "record":
        owner = json.loads(args.labels.read_text(encoding="utf-8"))
        original = sha256(args.original) if args.original else sha256(args.labels)
        print(json.dumps(record_batch(root / RECORD, items, args.batch, owner["labels"], owner.get("notes", {}),
                                      original_sha256=original)))
    else:
        path = root / RECORD
        done = len(json.loads(path.read_text(encoding="utf-8"))["batches"]) if path.exists() else 0
        print(json.dumps({"batches_done": done, "batches_left": BATCHES - done}))


if __name__ == "__main__":
    main()
