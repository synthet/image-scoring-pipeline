"""Build a local, blind labelling page for the detector benchmark cohort (#377).

    python scripts/research/detector_benchmark/make_label_page.py \
        --cohort <dir>/cohort.csv --out <dir>/label

Writes ``<out>/index.html`` plus ``<out>/img/<image_id>.jpg``. Open ``index.html`` in a
browser straight from disk -- nothing is uploaded anywhere.

Why these choices:

* **Blind.** The page shows only the photo. No stratum, no stored box, no detector
  output: a labeller who can see what the detector said drifts toward agreeing with it,
  which is the one bias a detector benchmark cannot afford.
* **Shuffled.** Frames appear in a seeded random order, not grouped by stratum. Fifty
  "detected small subject" frames in a row would teach the labeller what to expect.
* **Large enough to see small birds.** Images are 1280 px on the long edge. The subjects
  this benchmark exists to measure can cover ~1% of the frame; at a 384 px thumbnail
  that is a few dozen pixels, too small to label honestly. Click an image to zoom 2x.
* **Same decode as production and the benchmark** (``open_rendition_for_ml`` ->
  ``.convert("RGB")`` -> ``bake_orientation``), so the labeller sees the upright frame
  the detector saw.
* The eagle slice is excluded: those frames are already verified positives.

Labels are kept in the browser's localStorage as you go and exported with the
"Download labels.csv" button. The export is ``image_id,label`` with ``label`` in
``bird | no_bird | unsure``.
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

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("make_label_page")

EDGE = 1280
QUALITY = 82
SEED = 377

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bird Presence Labelling</title>
<style>
:root {
  --bg: #f3f4f1; --panel: #ffffff; --ink: #1d2320; --muted: #5f6b64; --line: #d6dbd6;
  --bird: #2f7d4f; --nobird: #9a3b2e; --unsure: #8a6d1f; --focus: #1f5fa8;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141816; --panel: #1c211f; --ink: #e6ebe7; --muted: #9aa69f; --line: #2e3531;
    --bird: #5fbf86; --nobird: #e0806f; --unsure: #d8b65a; --focus: #7fb1ff;
    color-scheme: dark;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.45 "Segoe UI", system-ui, -apple-system, sans-serif; }
header { position: sticky; top: 0; z-index: 2; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 10px 16px;
  display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; }
h1 { font-size: 16px; margin: 0; font-weight: 600; }
.progress { font-variant-numeric: tabular-nums; color: var(--muted); }
.bar { flex: 1 1 160px; height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: var(--bird); width: 0; }
button { font: inherit; border: 1px solid var(--line); background: var(--panel); color: var(--ink);
  border-radius: 6px; padding: 8px 14px; cursor: pointer; }
button:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
main { max-width: 1320px; margin: 0 auto; padding: 16px; display: grid; gap: 14px; }
.frame { position: relative; display: flex; justify-content: center; background: #000;
  border-radius: 6px; overflow: auto; max-height: 76vh; }
.frame img { max-width: 100%; max-height: 76vh; object-fit: contain; cursor: zoom-in; }
.frame.zoom img { max-width: none; max-height: none; width: 200%; cursor: zoom-out; }
.choices { display: flex; flex-wrap: wrap; gap: 10px; }
.choices button { flex: 1 1 140px; padding: 14px; font-weight: 600; }
.choices button[data-v="bird"] { border-color: var(--bird); color: var(--bird); }
.choices button[data-v="no_bird"] { border-color: var(--nobird); color: var(--nobird); }
.choices button[data-v="unsure"] { border-color: var(--unsure); color: var(--unsure); }
.choices button.on { color: #fff; }
.choices button.on[data-v="bird"] { background: var(--bird); }
.choices button.on[data-v="no_bird"] { background: var(--nobird); }
.choices button.on[data-v="unsure"] { background: var(--unsure); }
.nav { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; color: var(--muted); }
.hint { font-size: 13px; color: var(--muted); max-width: 70ch; }
kbd { border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px; padding: 0 5px;
  font: 12px ui-monospace, monospace; }
</style>
</head>
<body>
<header>
  <h1>Bird Presence Labelling</h1>
  <span class="progress" id="progress"></span>
  <div class="bar" aria-hidden="true"><i id="barfill"></i></div>
  <button id="download" type="button">Download labels.csv</button>
</header>
<main>
  <p class="hint">Is there a bird anywhere in this photo, however small, distant or partly hidden?
  Look carefully: some subjects cover about 1% of the frame. Click the photo to zoom 2&times;.
  Keys: <kbd>B</kbd> bird &middot; <kbd>N</kbd> no bird &middot; <kbd>U</kbd> unsure &middot;
  <kbd>&larr;</kbd>/<kbd>&rarr;</kbd> move. Your answers save in this browser as you go.</p>
  <div class="frame" id="frame"><img id="img" alt="Photo to label"></div>
  <div class="choices" role="group" aria-label="Label">
    <button type="button" data-v="bird">Bird (B)</button>
    <button type="button" data-v="no_bird">No bird (N)</button>
    <button type="button" data-v="unsure">Unsure (U)</button>
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
const KEY = "detector-benchmark-377-labels";
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { labels = {}; }
let i = 0;
const firstOpen = ITEMS.findIndex(id => !labels[id]);
if (firstOpen >= 0) i = firstOpen;

const $ = s => document.querySelector(s);
function save() { try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {} }
function render() {
  const id = ITEMS[i];
  $("#img").src = "img/" + id + ".jpg";
  $("#frame").classList.remove("zoom");
  document.querySelectorAll(".choices button").forEach(b =>
    b.classList.toggle("on", labels[id] === b.dataset.v));
  const done = ITEMS.filter(x => labels[x]).length;
  $("#progress").textContent = done + " / " + ITEMS.length + " labelled";
  $("#barfill").style.width = (100 * done / ITEMS.length) + "%";
  $("#pos").textContent = "Photo " + (i + 1) + " of " + ITEMS.length;
}
function setLabel(v) {
  labels[ITEMS[i]] = v; save();
  if (i < ITEMS.length - 1) i++;
  render();
}
function move(d) { i = Math.max(0, Math.min(ITEMS.length - 1, i + d)); render(); }
document.querySelectorAll(".choices button").forEach(b =>
  b.addEventListener("click", () => setLabel(b.dataset.v)));
$("#prev").addEventListener("click", () => move(-1));
$("#next").addEventListener("click", () => move(1));
$("#skip").addEventListener("click", () => {
  const n = ITEMS.findIndex(x => !labels[x]);
  if (n >= 0) { i = n; render(); }
});
$("#img").addEventListener("click", () => $("#frame").classList.toggle("zoom"));
document.addEventListener("keydown", e => {
  const k = e.key.toLowerCase();
  if (k === "b") setLabel("bird");
  else if (k === "n") setLabel("no_bird");
  else if (k === "u") setLabel("unsure");
  else if (e.key === "ArrowLeft") move(-1);
  else if (e.key === "ArrowRight") move(1);
});
$("#download").addEventListener("click", () => {
  const rows = ["image_id,label"].concat(ITEMS.filter(x => labels[x]).map(x => x + "," + labels[x]));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([rows.join("\\n") + "\\n"], {type: "text/csv"}));
  a.download = "labels.csv";
  a.click();
});
render();
</script>
</body>
</html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from modules.thumbnails import bake_orientation, open_rendition_for_ml

    with open(args.cohort, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["stratum"] != "eagle"]

    out = Path(args.out)
    img_dir = out / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    ids = []
    for n, r in enumerate(rows, 1):
        target = img_dir / f"{r['image_id']}.jpg"
        if not target.exists():
            try:
                img, _route = open_rendition_for_ml(r["file_path"])
                img = img.convert("RGB")
                try:
                    img = bake_orientation(img, r["file_path"])
                except Exception as exc:  # noqa: BLE001 -- mirror production
                    logger.debug("bake_orientation failed for %s: %s", r["file_path"], exc)
                img.thumbnail((EDGE, EDGE))
                img.save(target, "JPEG", quality=QUALITY)
            except Exception as exc:  # noqa: BLE001 -- leave it out of the page, say so
                logger.warning("skipping %s: %s", r["file_path"], exc)
                continue
        ids.append(int(r["image_id"]))
        if n % 25 == 0:
            logger.info("%d/%d images", n, len(rows))

    random.Random(SEED).shuffle(ids)
    page = PAGE.replace("__ITEMS__", html.escape(json.dumps(ids), quote=False))
    (out / "index.html").write_text(page, encoding="utf-8")
    logger.info("wrote %s with %d photos", out / "index.html", len(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
