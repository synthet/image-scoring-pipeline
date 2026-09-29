"""Blind side-by-side labeller: bird_detect_v0 vs bird_detect_v1 primary boxes.

Run in ``image-scoring-gpu-shell`` (decode + YOLO inference). If the model repo
requires Hugging Face authentication, make ``HF_TOKEN`` available in the container
before inference.

    python scripts/research/detector_benchmark/make_compare_label_page.py infer \\
        --cohort <dir>/cohort.csv --out <dir>/compare

    python scripts/research/detector_benchmark/make_compare_label_page.py build \\
        --cache <dir>/compare/compare_cache.csv --out <dir>/compare/page

``build`` writes ``<out>/index.html`` and ``<out>/img/*.jpg``. Open ``index.html`` from
disk. The page shows two boxed photos labelled **Option A** and **Option B** only; which
weight produced which side is recorded in ``mapping.json`` (for scoring), not in the HTML.

Labels live in browser ``localStorage`` and export as ``compare_labels.csv`` with
``pick`` in ``a | b | tie | neither | unsure`` (screen positions, not model names).

Inference uses the same decode path as production and ``run_benchmark.py``
(``open_rendition_for_ml`` -> RGB -> ``bake_orientation``). Both detectors use
``BirdDetector`` defaults for ``confidence`` / ``imgsz`` / ``max_det``.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import random
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("make_compare_label_page")

EDGE = 1280
QUALITY = 82
ITEM_SEED = 3771
SWAP_SEED = 3772
BOX_COLOR = "#ff4d00"
DEFAULT_V0 = "bird_detect_v0.pt"
DEFAULT_V1 = "bird_detect_v1.pt"

CACHE_FIELDS = [
    "image_id",
    "stratum",
    "file_path",
    "img_w",
    "img_h",
    "v0_n",
    "v0_conf",
    "v0_x1",
    "v0_y1",
    "v0_x2",
    "v0_y2",
    "v1_n",
    "v1_conf",
    "v1_x1",
    "v1_y1",
    "v1_x2",
    "v1_y2",
]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird box comparison</title>
<style>
:root {
  --bg: #f0f2ef; --panel: #fff; --ink: #1a211c; --muted: #5c675f; --line: #cfd6d0;
  --a: #2f6fad; --b: #8a4a12; --tie: #5a6270; --focus: #1f5fa8;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #121614; --panel: #1b211e; --ink: #e8ece9; --muted: #9aa39c; --line: #343b37;
    --a: #7fb1ff; --b: #ffb46c; --tie: #b8c0b8; --focus: #9ec5ff;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.45 "Segoe UI", system-ui, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 10px 16px;
  display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; }
h1 { font-size: 16px; margin: 0; font-weight: 600; }
.progress { font-variant-numeric: tabular-nums; color: var(--muted); }
.bar { flex: 1 1 160px; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: var(--a); width: 0; }
button { font: inherit; border: 1px solid var(--line); background: var(--panel); color: var(--ink);
  border-radius: 6px; padding: 8px 14px; cursor: pointer; }
button:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
main { max-width: 1500px; margin: 0 auto; padding: 16px; }
.hint { max-width: 78ch; color: var(--muted); font-size: 13px; margin: 0 0 14px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .pair { grid-template-columns: 1fr; } }
.panel { background: #000; border-radius: 6px; overflow: hidden; display: flex; flex-direction: column; }
.panel h2 { margin: 0; font-size: 14px; font-weight: 600; padding: 8px 10px; background: var(--panel);
  border-bottom: 1px solid var(--line); }
.panel h2.a { color: var(--a); }
.panel h2.b { color: var(--b); }
.frame { display: flex; justify-content: center; align-items: center; min-height: 200px;
  max-height: 62vh; overflow: auto; cursor: zoom-in; }
.frame.zoom img { max-width: none; max-height: none; width: 200%; cursor: zoom-out; }
.frame img { max-width: 100%; max-height: 62vh; object-fit: contain; display: block; }
.choices { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.choices button { flex: 1 1 130px; padding: 14px 10px; font-weight: 600; }
.choices button[data-v="a"] { border-color: var(--a); color: var(--a); }
.choices button[data-v="b"] { border-color: var(--b); color: var(--b); }
.choices button[data-v="tie"], .choices button[data-v="neither"], .choices button[data-v="unsure"] {
  border-color: var(--tie); color: var(--tie); }
.choices button.on { color: #fff; }
.choices button.on[data-v="a"] { background: var(--a); }
.choices button.on[data-v="b"] { background: var(--b); }
.choices button.on[data-v="tie"], .choices button.on[data-v="neither"],
.choices button.on[data-v="unsure"] { background: var(--tie); }
.nav { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 12px; color: var(--muted); }
kbd { border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px; padding: 0 5px;
  font: 12px ui-monospace, monospace; }
</style>
</head>
<body>
<header>
  <h1>Bird box comparison</h1>
  <span class="progress" id="progress"></span>
  <div class="bar" aria-hidden="true"><i id="barfill"></i></div>
  <button id="download" type="button">Download compare_labels.csv</button>
</header>
<main>
  <p class="hint" id="empty" hidden><strong>No pairs to label.</strong> Re-run <code>build</code> without
  <code>--only-divergent</code>, or run <code>infer</code> first so <code>compare_cache.csv</code> is filled.
  Then rebuild the page.</p>
  <p class="hint" id="guide">Two detectors drew a primary box on the same photo (orange rectangle). You are not told
  which model is which. Pick the box you would rather use for cropping — tighter on the bird, correct target,
  fewer false positives. <kbd>1</kbd> Option A &middot; <kbd>2</kbd> Option B &middot; <kbd>T</kbd> tie
  &middot; <kbd>N</kbd> neither &middot; <kbd>U</kbd> unsure. Click a photo to zoom 2&times;.
  Progress saves in this browser.</p>
  <div class="pair">
    <div class="panel"><h2 class="a">Option A</h2><div class="frame" id="frameA"><img id="imgA" alt="Option A"></div></div>
    <div class="panel"><h2 class="b">Option B</h2><div class="frame" id="frameB"><img id="imgB" alt="Option B"></div></div>
  </div>
  <div class="choices" role="group" aria-label="Preference">
    <button type="button" data-v="a">Prefer A (<kbd>1</kbd>)</button>
    <button type="button" data-v="b">Prefer B (<kbd>2</kbd>)</button>
    <button type="button" data-v="tie">Tie (<kbd>T</kbd>)</button>
    <button type="button" data-v="neither">Neither (<kbd>N</kbd>)</button>
    <button type="button" data-v="unsure">Unsure (<kbd>U</kbd>)</button>
  </div>
  <div class="nav">
    <button type="button" id="prev">&larr; Previous</button>
    <button type="button" id="next">Next &rarr;</button>
    <button type="button" id="skip">Next unlabelled</button>
    <span id="pos"></span>
  </div>
</main>
<script>
const ITEMS = __ITEMS__;
const KEY = "__STORAGE_KEY__";
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { labels = {}; }
let i = 0;
const firstOpen = ITEMS.findIndex(x => !labels[x.image_id]);
if (firstOpen >= 0) i = firstOpen;
const $ = s => document.querySelector(s);
function save() { try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {} }
function render() {
  if (!ITEMS.length) {
    $("#empty").hidden = false;
    $("#guide").hidden = true;
    document.querySelector(".pair").hidden = true;
    document.querySelector(".choices").hidden = true;
    document.querySelector(".nav").hidden = true;
    $("#progress").textContent = "0 / 0 pairs";
    return;
  }
  $("#empty").hidden = true;
  $("#guide").hidden = false;
  document.querySelector(".pair").hidden = false;
  document.querySelector(".choices").hidden = false;
  document.querySelector(".nav").hidden = false;
  const id = ITEMS[i].image_id;
  $("#imgA").src = "img/" + ITEMS[i].a_file;
  $("#imgB").src = "img/" + ITEMS[i].b_file;
  $("#frameA").classList.remove("zoom");
  $("#frameB").classList.remove("zoom");
  document.querySelectorAll(".choices button").forEach(b =>
    b.classList.toggle("on", labels[id] === b.dataset.v));
  const done = ITEMS.filter(x => labels[x.image_id]).length;
  $("#progress").textContent = done + " / " + ITEMS.length + " compared";
  $("#barfill").style.width = (100 * done / ITEMS.length) + "%";
  $("#pos").textContent = "Pair " + (i + 1) + " of " + ITEMS.length;
}
function setLabel(v) {
  if (!ITEMS.length) return;
  labels[ITEMS[i].image_id] = v; save();
  if (i < ITEMS.length - 1) i++;
  render();
}
function move(d) { i = Math.max(0, Math.min(ITEMS.length - 1, i + d)); render(); }
document.querySelectorAll(".choices button").forEach(b =>
  b.addEventListener("click", () => setLabel(b.dataset.v)));
$("#prev").addEventListener("click", () => move(-1));
$("#next").addEventListener("click", () => move(1));
$("#skip").addEventListener("click", () => {
  const n = ITEMS.findIndex(x => !labels[x.image_id]);
  if (n >= 0) { i = n; render(); }
});
$("#frameA").addEventListener("click", () => $("#frameA").classList.toggle("zoom"));
$("#frameB").addEventListener("click", () => $("#frameB").classList.toggle("zoom"));
document.addEventListener("keydown", e => {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const k = e.key.toLowerCase();
  if (k === "1") setLabel("a");
  else if (k === "2") setLabel("b");
  else if (k === "t") setLabel("tie");
  else if (k === "n") setLabel("neither");
  else if (k === "u") setLabel("unsure");
  else if (e.key === "ArrowLeft") move(-1);
  else if (e.key === "ArrowRight") move(1);
});
$("#download").addEventListener("click", () => {
  const rows = ["image_id,pick"];
  ITEMS.filter(x => labels[x.image_id]).forEach(x =>
    rows.push(x.image_id + "," + labels[x.image_id]));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([rows.join("\\n") + "\\n"], {type: "text/csv"}));
  a.download = "compare_labels.csv";
  a.click();
});
render();
</script>
</body>
</html>
"""


def _embed_json(value: Any) -> str:
    """JSON for inline <script> (do not html.escape — it breaks string keys)."""
    return json.dumps(value).replace("</", "<\\/")


def _save_thumb(img, path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    thumb = img.copy()
    thumb.thumbnail((EDGE, EDGE), Image.Resampling.LANCZOS)
    thumb.save(path, "JPEG", quality=QUALITY)


def _load_label_image(row: dict, thumb_dir: Path):
    from PIL import Image

    iid = int(row["image_id"])
    thumb = thumb_dir / f"{iid}.jpg"
    if thumb.is_file():
        with Image.open(thumb) as opened:
            return opened.convert("RGB")
    img, _ = _decode(row["file_path"])
    _save_thumb(img, thumb)
    with Image.open(thumb) as opened:
        return opened.convert("RGB")


def _decode(path: str):
    from modules.thumbnails import bake_orientation, open_rendition_for_ml

    img, route = open_rendition_for_ml(path)
    img = img.convert("RGB")
    try:
        img = bake_orientation(img, path)
    except Exception as exc:  # noqa: BLE001 -- mirror production
        logger.debug("bake_orientation failed for %s: %s", path, exc)
    return img, route


def _box_from_ranked(top: Optional[dict]) -> tuple[int, str, str, str, str, str]:
    if not top:
        return 0, "", "", "", "", ""
    region = top.get("region")
    if isinstance(region, (tuple, list)) and len(region) >= 4:
        x1, y1, x2, y2 = region[0], region[1], region[2], region[3]
    elif isinstance(region, dict):
        x1, y1, x2, y2 = (
            region.get("x1", ""),
            region.get("y1", ""),
            region.get("x2", ""),
            region.get("y2", ""),
        )
    else:
        return 0, "", "", "", "", ""
    return (1, f"{top.get('conf', '')}", f"{x1}", f"{y1}", f"{x2}", f"{y2}")


def _parse_box_row(row: dict, prefix: str) -> Optional[tuple[float, float, float, float]]:
    if int(row.get(f"{prefix}_n") or 0) < 1:
        return None
    try:
        x1, y1, x2, y2 = (float(row[f"{prefix}_{k}"]) for k in ("x1", "y1", "x2", "y2"))
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        return None
    return x1, y1, x2, y2


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


def boxes_divergent(
    v0: Optional[tuple[float, float, float, float]],
    v1: Optional[tuple[float, float, float, float]],
    *,
    iou_threshold: float = 0.85,
) -> bool:
    """True when the two primaries differ enough to show in a comparison set."""
    if v0 is None and v1 is None:
        return False
    if v0 is None or v1 is None:
        return True
    return _iou(v0, v1) < iou_threshold


def assign_sides(image_id: int, *, swap_seed: int = SWAP_SEED) -> bool:
    """Return True when v0 should appear on the left (Option A) screen side."""
    rng = random.Random(swap_seed ^ (image_id * 2654435761))
    return rng.random() < 0.5


def _draw_box(img, box: Optional[tuple[float, float, float, float]]):
    from PIL import ImageDraw

    out = img.copy()
    w, h = out.size
    draw = ImageDraw.Draw(out)
    stroke = max(3, round(max(w, h) / 350))
    if box is not None:
        x1, y1, x2, y2 = box
        px = tuple(round(v * d) for v, d in zip((x1, y1, x2, y2), (w, h, w, h), strict=True))
        draw.rectangle(px, outline=BOX_COLOR, width=stroke)
    else:
        draw.text((12, 12), "No box", fill=BOX_COLOR)
    return out


def _predict_primary(det, img) -> dict:
    from modules.bird_detection import rank_boxes

    iw, ih = img.size
    raw = det._predict_raw_boxes(img)
    ranked = rank_boxes(raw, iw, ih, det.max_det)
    top = ranked[0] if ranked else None
    n_boxes, conf, x1, y1, x2, y2 = _box_from_ranked(top)
    return {
        "n": n_boxes,
        "conf": conf,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "img_w": iw,
        "img_h": ih,
    }


def _done_ids(cache_csv: Path) -> set[int]:
    if not cache_csv.exists():
        return set()
    with cache_csv.open(newline="", encoding="utf-8") as fh:
        return {int(r["image_id"]) for r in csv.DictReader(fh)}


def run_infer(args: argparse.Namespace) -> int:
    from modules.bird_detection import BirdDetector

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache_csv = out / "compare_cache.csv"

    with open(args.cohort, newline="", encoding="utf-8") as fh:
        cohort = list(csv.DictReader(fh))
    done = _done_ids(cache_csv)
    todo = [r for r in cohort if int(r["image_id"]) not in done]
    if args.limit:
        todo = todo[: args.limit]
    logger.info("%d frames to infer (%d cached)", len(todo), len(done))

    v0_cfg: dict[str, Any] = {"model_file": args.v0}
    v1_cfg: dict[str, Any] = {"model_file": args.v1}
    if args.v0_path:
        v0_cfg["local_path"] = args.v0_path
    if args.v1_path:
        v1_cfg["local_path"] = args.v1_path

    detectors = {
        "v0": BirdDetector(config=v0_cfg),
        "v1": BirdDetector(config=v1_cfg),
    }
    for det in detectors.values():
        det.load_model()

    thumb_dir = out / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    new_file = not cache_csv.exists()
    with cache_csv.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CACHE_FIELDS)
        if new_file:
            w.writeheader()
        for n, row in enumerate(todo, 1):
            iid = int(row["image_id"])
            try:
                img, _route = _decode(row["file_path"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("decode failed %s: %s", row["file_path"], exc)
                v0 = v1 = {"n": 0}
            else:
                v0 = _predict_primary(detectors["v0"], img)
                v1 = _predict_primary(detectors["v1"], img)
                thumb_path = thumb_dir / f"{iid}.jpg"
                if not thumb_path.is_file():
                    _save_thumb(img, thumb_path)
            rec = {
                "image_id": iid,
                "stratum": row.get("stratum", ""),
                "file_path": row["file_path"],
                "img_w": v0.get("img_w") or v1.get("img_w") or "",
                "img_h": v0.get("img_h") or v1.get("img_h") or "",
            }
            for prefix, data in (("v0", v0), ("v1", v1)):
                for k in ("n", "conf", "x1", "y1", "x2", "y2"):
                    rec[f"{prefix}_{k}"] = data.get(k, "")
            w.writerow(rec)
            if n % 25 == 0:
                logger.info("inferred %d/%d", n, len(todo))
    logger.info("wrote %s", cache_csv)
    return 0


def run_build(args: argparse.Namespace) -> int:
    with open(args.cache, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    out = Path(args.out)
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    thumb_dir = Path(args.cache).resolve().parent / "thumbs"
    skipped_agree = 0
    skipped_decode = 0

    for row in rows:
        iid = int(row["image_id"])
        v0_box = _parse_box_row(row, "v0")
        v1_box = _parse_box_row(row, "v1")
        if args.only_divergent and not boxes_divergent(v0_box, v1_box, iou_threshold=args.iou_threshold):
            skipped_agree += 1
            continue

        try:
            img = _load_label_image(row, thumb_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip %s: %s", row["file_path"], exc)
            skipped_decode += 1
            continue
        v0_left = assign_sides(iid)
        left_box, right_box = (v0_box, v1_box) if v0_left else (v1_box, v0_box)
        left_model = args.v0_label if v0_left else args.v1_label
        right_model = args.v1_label if v0_left else args.v0_label

        a_name = f"{iid}_a.jpg"
        b_name = f"{iid}_b.jpg"
        _draw_box(img, left_box).save(img_dir / a_name, "JPEG", quality=QUALITY)
        _draw_box(img, right_box).save(img_dir / b_name, "JPEG", quality=QUALITY)

        items.append({"image_id": iid, "a_file": a_name, "b_file": b_name})
        mapping_rows.append({
            "image_id": iid,
            "stratum": row.get("stratum", ""),
            "option_a_model": left_model,
            "option_b_model": right_model,
            "v0_on_screen": "a" if v0_left else "b",
        })

    random.Random(ITEM_SEED).shuffle(items)
    mapping = {
        "purpose": "blind bird_detect_v0 vs bird_detect_v1 primary-box preference",
        "option_a_screen": "left column in labeller",
        "option_b_screen": "right column in labeller",
        "models": {"v0": args.v0_label, "v1": args.v1_label},
        "rows": mapping_rows,
    }
    (out / "mapping.json").write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")

    page = PAGE.replace("__ITEMS__", _embed_json(items)).replace(
        "__STORAGE_KEY__", html.escape(args.storage_key, quote=True)
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "README.md").write_text(
        "# Bird detector v0 vs v1 (blind comparison)\n\n"
        "Open `index.html` locally. Choose **Option A** or **Option B** (or tie / neither / unsure).\n"
        "Model names are not shown on the page; see `mapping.json` to score exports.\n\n"
        "Export `compare_labels.csv` from the page, then join:\n"
        "`pick=a` -> `option_a_model`, `pick=b` -> `option_b_model`.\n",
        encoding="utf-8",
    )
    logger.info(
        "wrote %s with %d pairs (%d rows in cache, %d skipped similar, %d decode errors)",
        out / "index.html",
        len(items),
        len(rows),
        skipped_agree,
        skipped_decode,
    )
    if not items:
        logger.error(
            "no pairs rendered — drop --only-divergent or run infer in gpu-shell first "
            "(thumbs under %s)",
            thumb_dir,
        )
        return 1
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    inf = sub.add_parser("infer", help="Run v0 and v1 on a cohort; write compare_cache.csv")
    inf.add_argument("--cohort", required=True)
    inf.add_argument("--out", required=True)
    inf.add_argument("--v0", default=DEFAULT_V0, help="v0 weights filename in HF repo")
    inf.add_argument("--v1", default=DEFAULT_V1, help="v1 weights filename in HF repo")
    inf.add_argument("--limit", type=int, default=None)
    inf.add_argument("--v0-path", default="", help="Optional local bird_detect_v0.pt path")
    inf.add_argument("--v1-path", default="", help="Optional local bird_detect_v1.pt path")

    bld = sub.add_parser("build", help="Render blind side-by-side page from cache")
    bld.add_argument("--cache", required=True)
    bld.add_argument("--out", required=True)
    bld.add_argument("--only-divergent", action="store_true",
                     help="Skip pairs where both models agree (IoU >= threshold)")
    bld.add_argument("--iou-threshold", type=float, default=0.85)
    bld.add_argument("--storage-key", default="bird-detect-v0-v1-compare-labels",
                     help="localStorage key (change if rebuilding a new study)")
    bld.add_argument("--v0-label", default=DEFAULT_V0, help="Recorded in mapping.json only")
    bld.add_argument("--v1-label", default=DEFAULT_V1, help="Recorded in mapping.json only")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "infer":
        return run_infer(args)
    return run_build(args)


if __name__ == "__main__":
    raise SystemExit(main())
