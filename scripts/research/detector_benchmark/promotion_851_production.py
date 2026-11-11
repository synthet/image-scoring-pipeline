"""#851: the owner labels current production selections under the #694 standard (pre-registered 2026-11-11).

Observational only: no provider calls, no database writes, no selection changes. Every output is a
local, create-only artifact; recorded batches are final.

    python -m scripts.research.detector_benchmark.promotion_851_production freeze-sample  (gpu-shell: DB read)
    python -m scripts.research.detector_benchmark.promotion_851_production render         (gpu-shell: RAW decode)
    python -m scripts.research.detector_benchmark.promotion_851_production record --batch 1 --labels <owner.json>
    python -m scripts.research.detector_benchmark.promotion_851_production status
    python -m scripts.research.detector_benchmark.promotion_851_production analyze --output <new.json>

The frozen pre-registration (``PREREGISTRATION_851_20261111.md``) fixes the population, bands, sample
size, exclusions, seeds, the 30 hidden #694 repeats and the interpretation rule. Two mechanics it leaves
open are fixed here, before any frame is drawn or labelled:

- the 95% interval for a difference of two proportions is Newcombe's hybrid Wilson-score interval
  (Newcombe 1998, method 10), built from the same Wilson bounds as the bar;
- the interpretation rule's "the usable-share difference from #694 excluding 0" is read per band, and
  must hold in both large and medium; the small band is reported but does not enter the verdict, as in
  the frozen rule's "in large or medium".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scripts.research.detector_benchmark import promotion_694_owner as owner694
from scripts.research.detector_benchmark.promotion_694_owner import mixed_order, note_conflicts, record_batch
from scripts.research.detector_benchmark.v1_promotion_gate import area_band, wilson

ROOT = Path(".agent/scratch/production-relabel-851")
P694 = Path(".agent/scratch/promotion-694")
PREREG = "PREREGISTRATION_851_20261111.md"
FREEZE = "freeze-receipt-851-20261111.json"
FREEZE_SHA256 = "c22b8a0becc6cc532dfc8299decc2af5aa8a3923ff18fba6023c42484ff3667a"
SAMPLE = "sample-frozen-851.json"
SAMPLE_RECEIPT = "sample-receipt-851.json"
MANIFEST = "owner-sample-manifest-851.json"
BLIND = "owner-sample-851"
RECORD = "owner-labels-record-851.json"
SEED_SAMPLE = "bird-851-production-sample-1"
SEED_REPEATS = "bird-851-repeats-1"
SEED_ORDER = "bird-851-order-1"
PER_BAND = 130
REPEATS_PER_BAND = 10
BATCH_SIZE = 30
BATCHES = 14
BANDS = ("large", "medium", "small")
RULE_BANDS = {"v1_regate_rule/3": {"large", "medium"}, "v1_regate_rule/4": {"small"}}
BAR = 0.90
IDENTITY = ("image_id", "band", "folder_id", "run_id", "region_id", "rendition_hash")

SQL = """
SELECT s.image_id, s.selected_by, s.localization_run_id AS run_id, s.region_id,
       r.rendition_hash, r.coord_space, g.x1, g.y1, g.x2, g.y2, i.file_path, i.folder_id
FROM image_localization_selections s
JOIN image_localization_runs r ON r.id = s.localization_run_id
JOIN image_regions g ON g.id = s.region_id
JOIN images i ON i.id = s.image_id
WHERE s.detector_key = 'bird' AND s.revoked_at IS NULL
  AND (s.selected_by LIKE 'v1_regate_rule/3:%' OR s.selected_by LIKE 'v1_regate_rule/4:%')
ORDER BY s.image_id
"""


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seeded(ids, seed):
    return sorted(ids, key=lambda i: hashlib.sha256(f"{seed}:{int(i)}".encode()).hexdigest())


def write_new(path, payload):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, allow_nan=False)
        handle.write("\n")


def load_freeze(root):
    """Check the pinned freeze receipt and the pre-registration it names; return the receipt."""
    root = Path(root)
    if sha256(root / FREEZE) != FREEZE_SHA256:
        raise ValueError("#851 freeze receipt changed")
    receipt = json.loads((root / FREEZE).read_text(encoding="utf-8"))
    if sha256(root / receipt["preregistration"]) != receipt["preregistration_sha256"]:
        raise ValueError("frozen #851 pre-registration changed")
    if receipt["seeds"] != {"production": SEED_SAMPLE, "repeats": SEED_REPEATS, "order": SEED_ORDER}:
        raise ValueError("frozen seeds do not match this module")
    return receipt


def _ids_in(value, found):
    if isinstance(value, dict):
        if "image_id" in value:
            found.add(int(value["image_id"]))
        for item in value.values():
            _ids_in(item, found)
    elif isinstance(value, list):
        for item in value:
            _ids_in(item, found)
    return found


def exclusions(p694, receipt):
    """The frozen exclusion ids, the 390 #694 sample frames and every #694 control frame."""
    p694 = Path(p694)
    path = p694 / "exclusions-frozen-20261026.json"
    if sha256(path) != receipt["exclusions_sha256"]:
        raise ValueError("frozen exclusions changed")
    excluded = {int(i) for i in json.loads(path.read_text(encoding="utf-8"))["ids"]}
    evidence = [{"path": path.name, "sha256": sha256(path), "ids": len(excluded)}]
    sample694 = json.loads((p694 / "sample-frozen-20261026.json").read_text(encoding="utf-8"))["frames"]
    excluded |= {int(r["image_id"]) for r in sample694}
    evidence.append({"path": "sample-frozen-20261026.json", "sha256": sha256(p694 / "sample-frozen-20261026.json"),
                     "ids": len(sample694)})
    for control in sorted(p694.glob("controls*.json")) + sorted(p694.glob("calibration*manifest*.json")):
        found = _ids_in(json.loads(control.read_text(encoding="utf-8")), set())
        excluded |= found
        evidence.append({"path": control.name, "sha256": sha256(control), "ids": len(found)})
    return excluded, evidence, sample694


def classify(rows, file_exists):
    """Band each active selection and collect hard stops; drop rows whose file is gone."""
    pools, stops, missing = {b: [] for b in BANDS}, [], 0
    if len(rows) != len({int(r["image_id"]) for r in rows}):
        stops.append("duplicate active selections for one image")
    for row in rows:
        rule = row["selected_by"].split(":", 1)[0]
        box = [float(row[k]) for k in ("x1", "y1", "x2", "y2")]
        if not (all(math.isfinite(v) and 0 <= v <= 1 for v in box) and box[0] < box[2] and box[1] < box[3]):
            stops.append("invalid box")
            continue
        if row["coord_space"] != "display_normalized":
            stops.append("coordinate space is not display_normalized")
            continue
        band = area_band(box)
        if band not in RULE_BANDS.get(rule, set()):
            stops.append(f"{rule} box in the {band} band")
            continue
        if not file_exists(row["file_path"]):
            missing += 1
            continue
        pools[band].append({**row, "image_id": int(row["image_id"]), "band": band, "rule": rule,
                            "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3]})
    return pools, sorted(Counter(stops).items()), missing


def draw(pools, excluded, sample694, file_exists):
    """The seeded production sample and the 30 repeats; raise on any pre-registered hard stop."""
    eligible = {b: [r for r in pools[b] if r["image_id"] not in excluded] for b in BANDS}
    short = {b: len(v) for b, v in eligible.items() if len(v) < PER_BAND}
    if short:
        raise ValueError(f"hard stop: fewer than {PER_BAND} eligible frames: {short}")
    production = []
    for band in BANDS:
        by_id = {r["image_id"]: r for r in eligible[band]}
        production += [{**by_id[i], "kind": "production"} for i in seeded(by_id, SEED_SAMPLE)[:PER_BAND]]
    repeats = []
    for band in BANDS:
        by_id = {int(r["image_id"]): r for r in sample694 if r["band"] == band and file_exists(r["file_path"])}
        picked = seeded(by_id, SEED_REPEATS)[:REPEATS_PER_BAND]
        if len(picked) < REPEATS_PER_BAND:
            raise ValueError(f"hard stop: fewer than {REPEATS_PER_BAND} #694 repeats on disk in {band}")
        repeats += [{**by_id[i], "image_id": i, "kind": "repeat"} for i in picked]
    frames = production + repeats
    if len({r["image_id"] for r in frames}) != len(frames):
        raise ValueError("a frame was drawn twice")
    return frames


def freeze_sample(root, p694, rows, file_exists, now=None):
    """Write the create-only sample and its receipt; return counts and hashes only."""
    root = Path(root)
    receipt = load_freeze(root)
    for name in (SAMPLE, SAMPLE_RECEIPT):
        if (root / name).exists():
            raise FileExistsError(name)
    pools, stops, missing = classify(rows, file_exists)
    if stops:
        raise ValueError(f"hard stop: {stops}")
    excluded, evidence, sample694 = exclusions(p694, receipt)
    frames = draw(pools, excluded, sample694, file_exists)
    items = mixed_order([r["image_id"] for r in frames], seed=SEED_ORDER, batch_size=BATCH_SIZE)
    if len(items) != PER_BAND * len(BANDS) + REPEATS_PER_BAND * len(BANDS) or items[-1]["batch"] != BATCHES:
        raise ValueError("sample does not fill the frozen batches")
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_new(root / SAMPLE, {"freeze_sha256": FREEZE_SHA256, "drawn_at": now, "frames": frames, "items": items})
    counts = {"population": {b: len(pools[b]) for b in BANDS}, "missing_files": missing,
              "eligible": {b: len([r for r in pools[b] if r["image_id"] not in excluded]) for b in BANDS},
              "frames": dict(Counter(r["kind"] for r in frames))}
    write_new(root / SAMPLE_RECEIPT, {"freeze_sha256": FREEZE_SHA256, "sample": SAMPLE,
                                      "sample_sha256": sha256(root / SAMPLE), "drawn_at": now,
                                      "exclusion_sources": evidence, **counts})
    return {**counts, "sample_sha256": sha256(root / SAMPLE), "receipt_sha256": sha256(root / SAMPLE_RECEIPT)}


def load_sample(root):
    root = Path(root)
    load_freeze(root)
    receipt = json.loads((root / SAMPLE_RECEIPT).read_text(encoding="utf-8"))
    if sha256(root / SAMPLE) != receipt["sample_sha256"]:
        raise ValueError("frozen #851 sample changed")
    sample = json.loads((root / SAMPLE).read_text(encoding="utf-8"))
    if sample["items"] != mixed_order([r["image_id"] for r in sample["frames"]], SEED_ORDER, BATCH_SIZE):
        raise ValueError("frozen order does not match the sample")
    return sample


def render_sample(root, repo, sample, render):
    """Render missing pairs, then write the manifest (with kinds) and a public sheet (tokens only)."""
    from scripts.research.detector_benchmark.promotion_694_controls import _render_pair

    root, repo = Path(root), Path(repo)
    out = root / BLIND
    out.mkdir(exist_ok=True)
    by_id = {r["image_id"]: r for r in sample["frames"]}
    rendered = 0
    for item in sample["items"]:
        overview, crop = out / f"{item['token']}_overview.jpg", out / f"{item['token']}_crop.jpg"
        if not (overview.exists() and crop.exists()):
            _render_pair(render, by_id[item["image_id"]], overview, crop)
            rendered += 1
    rows, hashes = [], {}
    for item in sample["items"]:
        files = [str((out / f"{item['token']}_{k}.jpg").relative_to(repo)).replace("\\", "/")
                 for k in ("overview", "crop")]
        hashes.update({name: sha256(repo / name) for name in files})
        frame = by_id[item["image_id"]]
        rows.append({"id": item["token"], **{k: frame[k] for k in IDENTITY}, "kind": frame["kind"],
                     "batch": item["batch"], "files": files})
    write_new(root / MANIFEST, {"freeze_sha256": FREEZE_SHA256, "items": rows, "sha256": hashes})
    write_new(out / "sheet.json", {"batches": {str(b): [{"token": r["id"], "files": [Path(f).name for f in r["files"]]}
                                                        for r in rows if r["batch"] == b]
                                               for b in range(1, BATCHES + 1)}})
    return rendered


def record(root, batch, labels, notes, original_sha256):
    """Append one batch through the #694 recorder, checked against the #851 order."""
    sample = load_sample(root)
    result = record_batch(Path(root) / RECORD, sample["items"], batch, labels, notes,
                          original_sha256=original_sha256)
    return {**result, "batches_left": BATCHES - result["batches_done"]}


def summarize(rows):
    """Usable over resolved frames (``unsure`` unresolved), the bar, and the conservative bound."""
    resolved = [r for r in rows if r["label"] != "unsure"]
    usable = sum(r["label"] == "usable" for r in rows)
    lower, upper = wilson(usable, len(resolved))
    return {"total": len(rows), "resolved": len(resolved), "usable": usable,
            "unresolved": len(rows) - len(resolved), "wilson": [lower, upper],
            "conservative_wilson": list(wilson(usable, len(rows))), "passed": lower >= BAR}


def newcombe(x1, n1, x2, n2):
    """Newcombe hybrid Wilson-score 95% interval for p1 - p2 (method 10)."""
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson(x1, n1)
    l2, u2 = wilson(x2, n2)
    diff = p1 - p2
    return [diff - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), diff + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)]


def labels_by_token(record_path, batches):
    data = json.loads(Path(record_path).read_text(encoding="utf-8"))
    if [b["batch"] for b in data["batches"]] != list(range(1, batches + 1)):
        raise ValueError(f"the record must hold batches 1 to {batches}")
    return {row["token"]: row["label"] for b in data["batches"] for row in b["rows"]}


def verdict(bands, compare):
    """The frozen interpretation rule, read over large and medium."""
    if any(not bands[b]["passed"] for b in ("large", "medium")):
        return "standard_explains"
    if all(compare[b]["usable_diff_ci"][0] > 0 for b in ("large", "medium")):
        return "yolo_cohort_crops_worse"
    return "inconclusive"


def analyze(root, p694):
    """Production bands, repeat consistency, the per-band #694 comparison and the verdict."""
    root, p694 = Path(root), Path(p694)
    load_sample(root)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    labels = labels_by_token(root / RECORD, BATCHES)
    items = manifest["items"]
    if set(labels) != {r["id"] for r in items}:
        raise ValueError("the record must cover every #851 frame")
    rows = [{**r, "label": labels[r["id"]]} for r in items]
    production = [r for r in rows if r["kind"] == "production"]
    bands = {}
    for band in BANDS:
        in_band = [r for r in production if r["band"] == band]
        folders = {}
        for row in in_band:
            folders.setdefault(row["folder_id"], row)
        bands[band] = {**summarize(in_band), "one_per_folder": summarize(list(folders.values()))}
    old_manifest = json.loads((p694 / owner694.MANIFEST).read_text(encoding="utf-8"))["items"]
    old_labels = labels_by_token(p694 / owner694.RECORD, owner694.BATCHES)
    old = {int(r["image_id"]): {"band": r["band"], "label": old_labels[r["id"]]} for r in old_manifest}
    repeats = [r for r in rows if r["kind"] == "repeat"]
    exact = sum(r["label"] == old[int(r["image_id"])]["label"] for r in repeats)
    binary = sum((r["label"] == "usable") == (old[int(r["image_id"])]["label"] == "usable") for r in repeats)
    consistency = {"repeats": len(repeats), "exact": exact, "exact_wilson": list(wilson(exact, len(repeats))),
                   "usable_agreement": binary, "usable_wilson": list(wilson(binary, len(repeats)))}
    compare = {}
    for band in BANDS:
        new = [r["label"] for r in production if r["band"] == band and r["label"] != "unsure"]
        was = [v["label"] for v in old.values() if v["band"] == band and v["label"] != "unsure"]
        compare[band] = {
            "usable_diff": new.count("usable") / len(new) - was.count("usable") / len(was),
            "usable_diff_ci": newcombe(new.count("usable"), len(new), was.count("usable"), len(was)),
            "poor_crop_diff": new.count("poor_crop") / len(new) - was.count("poor_crop") / len(was),
            "poor_crop_diff_ci": newcombe(new.count("poor_crop"), len(new), was.count("poor_crop"), len(was))}
    return {"status": "analyzed", "bands": bands, "consistency": consistency, "compare_694": compare,
            "verdict": verdict(bands, compare), "record_sha256": sha256(root / RECORD),
            "manifest_sha256": sha256(root / MANIFEST), "freeze_sha256": FREEZE_SHA256, "selection_changes": 0}


def fetch_rows():
    """Read the active rule/3 and rule/4 selections in one read-only repeatable-read snapshot."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    from modules.db_postgres import get_pg_config

    conn = psycopg2.connect(**get_pg_config(), connect_timeout=10)
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SET LOCAL statement_timeout = '120s'")
            cur.execute(SQL)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.rollback()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--p694", type=Path, default=P694)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze-sample")
    sub.add_parser("render")
    rec = sub.add_parser("record")
    rec.add_argument("--batch", type=int, required=True)
    rec.add_argument("--labels", type=Path, required=True,
                     help='JSON {"labels": {token: label}, "notes": {token: text}}, the owner\'s paste as sent')
    sub.add_parser("status")
    sub.add_parser("note-check").add_argument("--labels", type=Path, required=True)
    sub.add_parser("analyze").add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, repo = args.root.resolve(), Path(__file__).resolve().parents[3]
    if args.command == "freeze-sample":
        print(json.dumps(freeze_sample(root, args.p694.resolve(), fetch_rows(), lambda p: Path(p).is_file())))
    elif args.command == "render":
        sample = load_sample(root)
        print(json.dumps({"rendered": render_sample(root, repo, sample, owner694.sample_renderer(sample["frames"])),
                          "frames": len(sample["items"])}))
    elif args.command == "record":
        owner = json.loads(args.labels.read_text(encoding="utf-8"))
        print(json.dumps(record(root, args.batch, owner["labels"], owner.get("notes", {}), sha256(args.labels))))
    elif args.command == "note-check":
        owner = json.loads(args.labels.read_text(encoding="utf-8"))
        print(json.dumps({"flagged": note_conflicts(owner["labels"], owner.get("notes", {}))}))
    elif args.command == "status":
        path = root / RECORD
        done = len(json.loads(path.read_text(encoding="utf-8"))["batches"]) if path.exists() else 0
        print(json.dumps({"batches_done": done, "batches_left": BATCHES - done}))
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_new(args.output, analyze(root, args.p694.resolve()))
        print(json.dumps({"status": "analyzed", "output": str(args.output)}))


if __name__ == "__main__":
    main()
