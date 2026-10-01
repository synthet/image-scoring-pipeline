"""Build a private, read-only review page for bird-v1 shadow-rescan failures.

Run ``prepare``, ``probe``, then ``build`` in gpu-shell. The probe uses the
already-rendered review JPEGs to avoid re-decoding RAWs; its RTMDet and refine
boxes are diagnostic candidates, not production-rendition measurements.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from modules.localization_cascade import REFINE_MIN_IOU, iou

VERSION = "synthet/bird-detect-v0/bird_detect_v1.pt"
SENTINEL = {"detected": False}
CAUSES = ("animal", "scene_texture", "other_object", "label_correction", "unsure")
GRADES = ("usable", "poor_crop", "wrong_target", "unsure")


def read_csv(path: Path) -> dict[int, dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    indexed = {int(row["image_id"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f"duplicate image IDs in {path}")
    return indexed


def load_cases(root: Path) -> list[dict]:
    cohort = read_csv(root / "cohort.csv")
    presence = read_csv(root / "labels.csv")
    boxes = read_csv(root / "box_page" / "box_labels.csv")
    if set(cohort) != set(presence) or len(cohort) != 216:
        raise ValueError("presence labels must cover the frozen 216-image cohort")
    expected_box_ids = {iid for iid, row in cohort.items()
                        if row["stratum"].startswith("det_") and presence[iid]["label"] == "bird"}
    if set(boxes) != expected_box_ids or len(boxes) != 65:
        raise ValueError("primary-box labels must cover the 65 detected bird frames")
    cases = []
    for iid, row in cohort.items():
        if not row["stratum"].startswith("det_"):
            continue
        p = presence[iid]["label"]
        grade = boxes[iid]["box_label"] if iid in boxes else ""
        if p == "no_bird":
            kind = "false_detection"
        elif grade in {"poor_crop", "wrong_target"}:
            kind = "bad_primary"
        else:
            continue
        cases.append({"image_id": iid, "kind": kind, "stratum": row["stratum"],
                      "presence": p, "primary_grade": grade,
                      "run_id": int(boxes[iid]["run_id"]) if iid in boxes else None,
                      "primary_region_id": int(boxes[iid]["region_id"]) if iid in boxes else None})
    counts = Counter(case["kind"] for case in cases)
    if counts != {"false_detection": 79, "bad_primary": 35}:
        raise ValueError(f"review case counts changed: {counts}")
    return cases


def prepare(root: Path, out: Path) -> None:
    cases = load_cases(root)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cohort.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("image_id", "stratum"))
        writer.writeheader()
        writer.writerows({key: case[key] for key in ("image_id", "stratum")} for case in cases)
    with (out / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("image_id", "label"))
        writer.writeheader()
        writer.writerows({"image_id": case["image_id"], "label": case["presence"]} for case in cases)
    print(f"Prepared {len(cases)} cases ({Counter(c['kind'] for c in cases)}) in {out}")


def _bbox(value):
    return json.loads(value) if isinstance(value, str) else value


def _box(region: dict) -> list[float]:
    box = [float(region[key]) for key in ("x1", "y1", "x2", "y2")]
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError(f"invalid normalized region: {box}")
    return box


def _candidate(candidate_id: str, provider: str, box, confidence: float, *, primary=False,
               note="") -> dict:
    coords = [float(v) for v in box]
    if not (len(coords) == 4 and 0 <= coords[0] < coords[2] <= 1
            and 0 <= coords[1] < coords[3] <= 1):
        raise ValueError(f"invalid candidate box: {candidate_id}")
    return {"id": candidate_id, "provider": provider, "box": coords,
            "confidence": round(float(confidence), 4), "primary": primary, "note": note}


def _cascade_candidates(record: dict) -> list[dict]:
    candidates = []
    coco = [b for b in record.get("coco", []) if float(b["conf"]) >= 0.25][:6]
    for n, box in enumerate(coco):
        conf = float(box["conf"])
        note = "candidate confidence ≥0.40" if conf >= 0.40 else "below 0.40 candidate threshold"
        candidates.append(_candidate(f"coco:{n}", "RTMDet animal", box["region"], conf, note=note))
    for n, item in enumerate(record.get("refine", [])):
        parent = tuple(item["coco_region"])
        best = max(item.get("yolo", []),
                   key=lambda box: iou(tuple(box["region"]), parent), default=None)
        if best and iou(tuple(best["region"]), parent) >= REFINE_MIN_IOU:
            # The crop-relative detector may extend beyond its padded crop. Its mapped
            # frame box must be clipped before drawing over the review JPEG.
            mapped = tuple(float(v) for v in best["region"])
            clipped = tuple(max(0.0, min(1.0, v)) for v in mapped)
            if clipped[0] < clipped[2] and clipped[1] < clipped[3]:
                note = f"parent IoU {iou(mapped, parent):.2f}"
                if clipped != mapped:
                    note += "; clipped to frame"
                candidates.append(_candidate(f"refine:{n}", "YOLO refined RTMDet",
                                             clipped, best["conf"], note=note))
    return candidates


def _read_raw(path: Path, case_ids: set[int]) -> dict[int, dict]:
    records = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            iid = int(row["image_id"])
            if iid in records or iid not in case_ids:
                raise ValueError(f"duplicate or out-of-cohort cascade result: {iid}")
            records[iid] = row
    if set(records) != case_ids:
        raise ValueError(f"cascade results missing {len(case_ids - set(records))} review cases")
    return records


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(root: Path, out: Path, weights: Path) -> None:
    """Infer RTMDet and small-box YOLO refine on local review JPEGs, resumably."""
    from PIL import Image

    from modules.bird_detection import BirdDetector
    from modules.detectors.rtmdet import load_rtmdet
    from scripts.research.detector_benchmark.rtmdet_probe import probe_image

    cases = load_cases(root)
    case_ids = {case["image_id"] for case in cases}
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if out.exists():
        with out.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                iid = int(row["image_id"])
                if iid in done or iid not in case_ids:
                    raise ValueError(f"duplicate or out-of-cohort probe result: {iid}")
                if row.get("image_source") != "review_jpeg":
                    raise ValueError(f"unexpected image source in probe cache: {iid}")
                done[iid] = row

    rt = load_rtmdet(str(weights))
    if not rt.enabled:
        raise RuntimeError(f"RTMDet unavailable: {rt.error_code} {rt.error_detail}")
    yolo = BirdDetector()
    if yolo.model_file != "bird_detect_v1.pt":
        raise RuntimeError(f"expected v1 YOLO for refine, got {yolo.model_file}")
    yolo.load_model()

    with out.open("a", encoding="utf-8") as handle:
        for n, case in enumerate(cases, 1):
            iid = case["image_id"]
            if iid in done:
                continue
            source = root / "page" / "img" / f"{iid}.jpg"
            rec = {"image_id": iid, "image_source": "review_jpeg", "image_sha256": _sha(source)}
            try:
                with Image.open(source) as opened:
                    img = opened.convert("RGB")
                rec.update(probe_image(img, rt, yolo))
            except Exception as exc:  # keep per-image failures visible in the page
                rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
            handle.write(json.dumps(rec) + "\n")
            handle.flush()
            if n % 10 == 0 or n == len(cases):
                print(f"probed {n}/{len(cases)} cases", flush=True)


def build(root: Path, raw_path: Path, out: Path) -> dict:
    from modules import db

    cases = load_cases(root)
    raw = _read_raw(raw_path, {c["image_id"] for c in cases})
    if any(row.get("image_source") != "review_jpeg" for row in raw.values()):
        raise ValueError("probe records must identify review JPEGs as their image source")
    conn = db.get_connector()
    items = []
    for case in cases:
        iid = case["image_id"]
        image = root / "page" / "img" / f"{iid}.jpg"
        if not image.is_file():
            raise FileNotFoundError(image)
        state = conn.query_one(
            """SELECT i.bird_bbox, r.id AS run_id, r.status, r.detector_version
               FROM images i JOIN image_localization_runs r
                 ON r.image_id=i.id AND r.detector_key='bird' AND r.is_current
               WHERE i.id=?""", (iid,))
        if not state or state["status"] != "detected" or state["detector_version"] != VERSION:
            raise ValueError(f"image {iid} no longer has a current v1 detected run")
        if _bbox(state["bird_bbox"]) != SENTINEL:
            raise ValueError(f"image {iid} production bird_bbox changed")
        if case["run_id"] is not None and int(state["run_id"]) != case["run_id"]:
            raise ValueError(f"image {iid} reviewed v1 run changed")
        regions = conn.query(
            """SELECT id, rank, confidence, x1, y1, x2, y2 FROM image_regions
               WHERE localization_run_id=? ORDER BY rank""", (state["run_id"],))
        if not regions or [int(r["rank"]) for r in regions] != list(range(len(regions))):
            raise ValueError(f"image {iid} has missing or non-contiguous v1 regions")
        if (case["primary_region_id"] is not None
                and int(regions[0]["id"]) != case["primary_region_id"]):
            raise ValueError(f"image {iid} reviewed primary region changed")
        candidates = [
            _candidate(f"v1:{r['rank']}", "v1 primary" if r["rank"] == 0 else "v1 secondary",
                       _box(r), r["confidence"], primary=r["rank"] == 0)
            for r in regions
        ]
        record = raw[iid]
        candidates.extend(_cascade_candidates(record) if "error" not in record else [])
        rtmdet_any_025 = any(float(b["conf"]) >= 0.25 for b in record.get("coco", []))
        items.append({**case, "run_id": int(state["run_id"]), "image": f"../page/img/{iid}.jpg",
                      "candidates": candidates, "rtmdet_any_025": rtmdet_any_025,
                      "inference_error": record.get("error", "")})
    out.mkdir(parents=True, exist_ok=True)
    source_hashes = {
        "cohort.csv": _sha(root / "cohort.csv"),
        "labels.csv": _sha(root / "labels.csv"),
        "box_labels.csv": _sha(root / "box_page" / "box_labels.csv"),
        "cascade_raw.jsonl": _sha(raw_path),
    }
    manifest = {"purpose": "development review of v1 false detections and bad primary crops",
                "candidate_source": "RTMDet and refine on review JPEGs, not production inference renditions",
                "source_hashes": source_hashes, "case_count": len(items),
                "counts": dict(Counter(i["kind"] for i in items)), "items": items}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    safe_items = json.dumps(items, separators=(",", ":")).replace("<", "\\u003c")
    html = PAGE.replace("__ITEMS__", safe_items).replace("__KEY__", "v1-failure-review-" + source_hashes["cascade_raw.jsonl"][:16])
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "README.md").write_text(
        "# Bird v1 failure review\n\nOpen `index.html` locally. Review 79 false detections and 35 bad primary crops. "
        "Click candidate grades on bad-primary cases, choose a cause on no-bird cases, then mark each "
        "case done. Progress stays in this browser; export `failure_review.csv` when finished. "
        "RTMDet and refine candidates use the rendered review JPEGs, not the production inference "
        "renditions. The page and photos are private development data. No database values are changed.\n",
        encoding="utf-8")
    return manifest


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bird v1 failure review</title>
<style>
:root{color-scheme:dark;font:15px/1.45 system-ui,sans-serif;--bg:#131a17;--panel:#202b25;--line:#53665b;--ink:#edf4ee;--muted:#b9c8bd}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink)}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0 12px 0 0}button,select{font:inherit;color:var(--ink);background:#304236;border:1px solid #829588;border-radius:6px;padding:7px 11px;cursor:pointer}
button:focus-visible,select:focus-visible{outline:3px solid #ffc178;outline-offset:2px}button.active{background:#c66c28;color:#101710;font-weight:700}
main{max-width:1650px;margin:auto;padding:16px}.meta{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);margin-bottom:12px}.warning{color:#ffbd91}
.whole,.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px}.whole{margin-bottom:14px}.whole img{display:block;max-width:100%;max-height:65vh;margin:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));gap:12px}.card h2{font-size:16px;margin:0 0 5px}.card p{margin:4px 0 8px;color:var(--muted)}
.frame{position:relative;width:max-content;max-width:100%;margin:auto}.frame img{display:block;max-width:100%;max-height:55vh}.frame svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.grade,.causes,.nav{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.grade button{font-size:13px;padding:5px 8px}.section{margin:14px 0}.section h2{font-size:17px;margin:0 0 5px}.hint{color:var(--muted)}
.nav{align-items:center;border-top:1px solid var(--line);padding-top:14px;margin-top:20px}.status{font-variant-numeric:tabular-nums;color:var(--muted)}
</style></head><body>
<header><h1>Bird v1 failure review</h1><label>Show <select id="filter"><option value="all">All cases</option><option value="false_detection">No-bird detections</option><option value="bad_primary">Bad primary crops</option><option value="open">Unreviewed</option></select></label><span class="status" id="progress"></span><button id="download">Download failure_review.csv</button></header>
<main><p class="hint">Development review. RTMDet and refine boxes were inferred from these review JPEGs; verify any promising rule on production renditions and a separate validation sample.</p><div class="meta" id="meta"></div><div class="whole"><strong>Original frame</strong><a id="originalLink" target="_blank"><img id="original" alt="Original photo without overlays"></a></div>
<section class="section" id="causeSection"><h2>Why was this a no-bird detection?</h2><p class="hint">The blind owner label says no bird is visible. Choose the apparent source of the false detection; use label correction only if you now see a bird.</p><div class="causes" id="causes"></div></section>
<section class="section"><h2>Detector boxes</h2><p class="hint" id="boxHint"></p><div class="grid" id="cards"></div></section>
<div class="nav"><button id="prev">← Previous</button><button id="next">Next →</button><button id="nextOpen">Next unreviewed</button><button id="done">Mark reviewed</button><span id="position" class="status"></span></div></main>
<script>
const ITEMS=__ITEMS__,KEY="__KEY__";
const CAUSES={animal:"Other animal",scene_texture:"Scene / texture",other_object:"Object or person",label_correction:"Bird visible: correct old label",unsure:"Unsure"};
const GRADES={usable:"Usable bird crop",poor_crop:"Poor crop",wrong_target:"Wrong target",unsure:"Unsure"};
let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(_){saved={}}
let index=Math.max(0,ITEMS.findIndex(x=>!saved[x.image_id]?.done));const $=s=>document.querySelector(s);
function persist(){try{localStorage.setItem(KEY,JSON.stringify(saved))}catch(_){}}
function state(id){return saved[id]||(saved[id]={grades:{}})}
function filtered(){const f=$("#filter").value;return ITEMS.filter(x=>f==="all"||f==="open"&&!state(x.image_id).done||x.kind===f)}
function chooseVisible(){const list=filtered();if(!list.length){$("#filter").value="all";return ITEMS}return list}
function go(delta){const list=chooseVisible(),at=list.findIndex(x=>x.image_id===ITEMS[index].image_id);
  const next=at<0?(delta>0?0:list.length-1):Math.max(0,Math.min(list.length-1,at+delta));index=ITEMS.indexOf(list[next]);render()}
function button(text,active,click){const b=document.createElement("button");b.type="button";b.textContent=text;b.classList.toggle("active",active);b.addEventListener("click",click);return b}
function render(){const item=ITEMS[index],s=state(item.image_id),list=chooseVisible();
  $("#progress").textContent=`${ITEMS.filter(x=>state(x.image_id).done).length} / ${ITEMS.length} reviewed`;
  $("#position").textContent=`Case ${Math.max(1,list.findIndex(x=>x.image_id===item.image_id)+1)} of ${list.length}`;
  $("#meta").replaceChildren();for(const value of [`Image ${item.image_id}`,item.kind==="false_detection"?"No bird visible":"Bird visible; primary "+item.primary_grade,item.stratum,`RTMDet animal candidate ≥0.25 anywhere in frame: ${item.rtmdet_any_025?"yes":"no"}`]){const span=document.createElement("span");span.textContent=value;$("#meta").append(span)}
  if(item.inference_error){const span=document.createElement("span");span.className="warning";span.textContent="RTMDet inference error: "+item.inference_error;$("#meta").append(span)}
  $("#original").src=item.image;$("#originalLink").href=item.image;
  $("#causeSection").hidden=item.kind!=="false_detection";$("#causes").replaceChildren();
  if(item.kind==="false_detection")for(const [key,label] of Object.entries(CAUSES))$("#causes").append(button(label,s.cause===key,()=>{s.cause=s.cause===key?"":key;persist();render()}));
  $("#boxHint").textContent=item.kind==="false_detection"?"Compare v1 and RTMDet on this bird-free frame. A second detection anywhere in the frame does not establish that both models found the same object.":"Grade every alternative box that could replace the bad v1 primary. The primary's original owner grade is shown but stays unchanged.";
  $("#cards").replaceChildren();for(const c of item.candidates){const card=document.createElement("div");card.className="card";
    const title=document.createElement("h2");title.textContent=`${c.provider} · ${c.id}`;card.append(title);
    const desc=document.createElement("p");desc.textContent=`Confidence ${c.confidence.toFixed(3)}${c.note?" · "+c.note:""}${c.primary&&item.primary_grade?" · original grade: "+item.primary_grade:""}`;card.append(desc);
    const frame=document.createElement("div");frame.className="frame";const img=document.createElement("img");img.src=item.image;img.alt=title.textContent;frame.append(img);
    const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox","0 0 1 1");svg.setAttribute("preserveAspectRatio","none");
    const rect=document.createElementNS("http://www.w3.org/2000/svg","rect");rect.setAttribute("x",c.box[0]);rect.setAttribute("y",c.box[1]);rect.setAttribute("width",c.box[2]-c.box[0]);rect.setAttribute("height",c.box[3]-c.box[1]);rect.setAttribute("fill","none");rect.setAttribute("stroke",c.provider.startsWith("v1")?"#ff6b34":c.provider.startsWith("RTMDet")?"#b47cff":"#65edb1");rect.setAttribute("stroke-width","0.004");svg.append(rect);frame.append(svg);card.append(frame);
    if(item.kind==="bad_primary"&&!c.primary){const grades=document.createElement("div");grades.className="grade";for(const [key,label] of Object.entries(GRADES))grades.append(button(label,s.grades[c.id]===key,()=>{s.grades[c.id]=s.grades[c.id]===key?"":key;persist();render()}));card.append(grades)}
    $("#cards").append(card)}
  $("#done").textContent=s.done?"Reviewed ✓":"Mark reviewed";$("#done").classList.toggle("active",!!s.done);
}
$("#filter").addEventListener("change",()=>{const list=chooseVisible();index=ITEMS.indexOf(list[0]);render()});
$("#prev").addEventListener("click",()=>go(-1));$("#next").addEventListener("click",()=>go(1));
$("#nextOpen").addEventListener("click",()=>{const n=ITEMS.findIndex(x=>!state(x.image_id).done);if(n>=0){index=n;render()}});
$("#done").addEventListener("click",()=>{const item=ITEMS[index],s=state(item.image_id);
  if(!s.done&&item.kind==="false_detection"&&!s.cause){alert("Choose a cause or Unsure first.");return}
  const ungraded=item.candidates.filter(c=>!c.primary&&!s.grades[c.id]);
  if(!s.done&&item.kind==="bad_primary"&&ungraded.length){alert(`Grade ${ungraded.length} remaining alternative box(es), using Unsure if needed.`);return}
  s.done=!s.done;persist();render();if(s.done)go(1)});
document.addEventListener("keydown",e=>{if(e.target.tagName==="SELECT"||e.altKey||e.ctrlKey||e.metaKey)return;if(e.key==="ArrowLeft")go(-1);if(e.key==="ArrowRight")go(1)});
$("#download").addEventListener("click",()=>{const rows=[["image_id","kind","original_primary_grade","cause","candidate_id","provider","candidate_grade","reviewed"]];
  for(const item of ITEMS){const s=state(item.image_id);let any=false;for(const c of item.candidates){if(c.primary)continue;const grade=s.grades[c.id]||"";if(grade){rows.push([item.image_id,item.kind,item.primary_grade,s.cause||"",c.id,c.provider,grade,s.done?1:0]);any=true}}
    if(!any)rows.push([item.image_id,item.kind,item.primary_grade,s.cause||"","","","",s.done?1:0])}
  const csv=rows.map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(",")).join("\n")+"\n";
  const url=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));const a=document.createElement("a");a.href=url;a.download="failure_review.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
render();
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("prepare", "probe", "build"))
    parser.add_argument("--root", type=Path, default=Path(".agent/scratch/bird_v1_owner_labels"))
    parser.add_argument("--raw", type=Path, help="probe JSONL (defaults to failure_review/probe_review.jsonl)")
    parser.add_argument("--weights", type=Path, default=Path("models/rtmdet_tiny_coco.onnx"))
    args = parser.parse_args()
    out = args.root / "failure_review"
    if args.action == "prepare":
        prepare(args.root, out / "inference_input")
    elif args.action == "probe":
        probe(args.root, out / "probe_review.jsonl", args.weights)
    else:
        result = build(args.root, args.raw or out / "probe_review.jsonl", out)
        print(f"Built {result['case_count']} cases at {out / 'index.html'}")


if __name__ == "__main__":
    main()
