"""Scene route benchmark (spec 05 AC-1 to AC-4, #412). Reads the library; writes only scene labels.

``pool``     deterministic library-wide pool, at most 3 images per folder, previously labelled sets excluded
``predict``  decode the localization rendition, classify with both backends, save each resolved class
             to ``image_scene_labels`` and to ``predictions.jsonl`` (gpu-shell)
``freeze``   stratify by the B/32 top label; frozen cohort + sampling weights
``page``     blind owner page: primary scene (1-8, 0 = can't tell) and "bird visible anywhere?" (Y/N)
``analyze``  per backend: weighted per-label precision/recall, confusion matrix, bird-route skip sweep
             (AC-3), the frozen run threshold meeting AC-4 (<= 2% of bird-visible images skipped)

    python scripts/research/scene_route/scene_benchmark.py pool
    python scripts/research/scene_route/scene_benchmark.py predict --limit 50
    python scripts/research/scene_route/scene_benchmark.py predict --extra-v1

Artifacts live in gitignored ``.agent/scratch/scene_route/``.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from modules.scene_route import LABELS as SCENE_LABELS
from scripts.research.detector_benchmark.v1_promotion_gate import (
    _read_csv,
    _write_csv,
    _write_new_json,
    folder_of,
    sample_strata,
    sha256_file,
    wilson,
)

OUT_ROOT = Path(".agent/scratch/scene_route")
BACKENDS = ("hf_clip_b32", "openclip_b32_laion", "openclip_l14", "siglip2_base")
STRATIFY_BACKEND = "hf_clip_b32"
LABELS = list(SCENE_LABELS)
ANIMAL_LABELS = ("wildlife_bird", "other_animal", "wildlife_insect")
#: Supervised-transfer arm: ImageNet-22k ConvNeXt, class probabilities summed into animal groups
#: (index ranges checked against timm's ImageNetInfo). It has no people/landscape classes, so it only
#: scores the bird and animal routes.
IMAGENET_ARM = "imagenet_convnext"
IMAGENET_MODEL = "convnext_base.fb_in22k_ft_in1k"
_RANGES = {
    "wildlife_bird": ((7, 24), (80, 100), (127, 146)),
    "wildlife_insect": ((70, 79), (300, 326)),
    "other_animal": ((0, 6), (25, 68), (101, 126), (147, 299), (327, 397)),
}
IMAGENET_GROUPS = {g: [i for a, b in rs for i in range(a, b + 1)] for g, rs in _RANGES.items()}
MAX_SKIP_RATE = 0.02  # AC-4
#: Earlier labelled sets: excluded from the pool so this sample is new to the owner.
PRIOR_COHORTS = (
    Path(".agent/scratch/detector_benchmark/cohort.csv"),
    Path(".agent/scratch/detector_benchmark/eagle_cohort.csv"),
    Path(".agent/scratch/bird_detect_compare/compare_labels.csv"),
    Path(".agent/scratch/bird_v1_owner_labels/cohort.csv"),
    Path(".agent/scratch/bird_v1_promotion/validation/cohort.csv"),
)
#: Owner bird/no-bird labels from the v1 work, re-used as a side check (selection-biased).
V1_PRESENCE = (
    (Path(".agent/scratch/bird_v1_owner_labels/labels.csv"), "label"),
    (Path(".agent/scratch/bird_v1_promotion/validation/labels.csv"), "presence"),
)


def _order_key(seed: str, image_id: int) -> str:
    return hashlib.md5(f"{image_id}{seed}".encode()).hexdigest()


def prior_ids(paths=PRIOR_COHORTS) -> set[int]:
    return {int(r["image_id"]) for p in paths if p.exists() for r in _read_csv(p)}


def build_pool(rows: list[dict], excluded: set[int], seed: str, size: int, per_folder: int) -> list[dict]:
    """Deterministic pool: hash order, previously labelled images out, at most ``per_folder`` per folder."""
    pool, used = [], Counter()
    for r in sorted(rows, key=lambda r: _order_key(seed, int(r["id"]))):
        if len(pool) >= size:
            break
        iid, folder = int(r["id"]), folder_of(r["file_path"])
        if iid in excluded or not r["file_path"] or used[folder] >= per_folder:
            continue
        used[folder] += 1
        pool.append({"image_id": iid, "file_path": r["file_path"]})
    return pool


def pool(root: Path, seed: str, size: int, per_folder: int) -> int:
    from modules import db

    rows = db.get_connector().query("SELECT id, file_path FROM images WHERE file_path IS NOT NULL")
    members = build_pool(rows, prior_ids(), seed, size, per_folder)
    if (root / "pool.csv").exists():
        raise FileExistsError(f"pool already frozen: {root / 'pool.csv'}")
    _write_csv(root / "pool.csv", ("image_id", "file_path"), members)
    _write_new_json(root / "pool.json", {"seed": seed, "size": len(members), "per_folder": per_folder,
                                         "library_images": len(rows),
                                         "created_utc": datetime.now(timezone.utc).isoformat()})
    return len(members)


def load_predictions(path: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                out[int(row["image_id"])] = row
    return out


def _v1_presence() -> dict[int, str]:
    labels: dict[int, str] = {}
    for path, col in V1_PRESENCE:
        if path.exists():
            for r in _read_csv(path):
                labels[int(r["image_id"])] = r[col]
    return labels


def imagenet_groups(probs) -> dict[str, float]:
    """Sum ImageNet-1k class probabilities into animal groups; the remainder is ``non_animal``."""
    groups = {g: round(float(sum(probs[i] for i in idx)), 6) for g, idx in IMAGENET_GROUPS.items()}
    groups["non_animal"] = round(max(0.0, 1.0 - sum(groups.values())), 6)
    return groups


def _imagenet_arm():
    import timm
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = timm.create_model(IMAGENET_MODEL, pretrained=True).to(device).eval()
    transform = timm.data.create_transform(**timm.data.resolve_model_data_config(model), is_training=False)

    def run(img) -> dict[str, float]:
        with torch.no_grad():
            logits = model(transform(img.convert("RGB")).unsqueeze(0).to(device))
        return imagenet_groups(torch.softmax(logits.float(), dim=1)[0].cpu().tolist())
    return run


def predict(root: Path, limit: int, extra_v1: bool) -> Counter:
    from modules import db
    from modules.localization import decode_for_localization
    from modules.scene_route import SceneClassifier, save_scene_label

    if extra_v1:
        ids = sorted(_v1_presence())
        rows = db.get_connector().query(
            f"SELECT id AS image_id, file_path FROM images WHERE id IN ({', '.join('?' for _ in ids)})", ids)
        out = root / "predictions_v1.jsonl"
    else:
        rows = _read_csv(root / "pool.csv")
        out = root / "predictions.jsonl"
    done = load_predictions(out)
    todo = [r for r in rows if int(r["image_id"]) not in done]
    if limit > 0:
        todo = todo[:limit]
    classifiers = {b: SceneClassifier(b) for b in BACKENDS}
    for c in classifiers.values():
        c.load()
    imagenet = _imagenet_arm()

    counts: Counter = Counter()
    t0 = time.perf_counter()
    emb_out = out.with_name(out.stem.replace("predictions", "embeddings") + ".jsonl")
    with out.open("a", encoding="utf-8") as handle, emb_out.open("a", encoding="utf-8") as emb_handle:
        for n, r in enumerate(todo, 1):
            iid = int(r["image_id"])
            rec = {"image_id": iid}
            try:
                decoded = decode_for_localization(r["file_path"])
                rec["rendition_hash"] = decoded.descriptor.rendition_hash
                for backend, clf in classifiers.items():
                    result = clf.classify(decoded.image)
                    save_scene_label(iid, result, backend=backend, rendition_hash=rec["rendition_hash"])
                    rec[backend] = {"version": result.version, "top_label": result.top_label,
                                    "probs": result.probs, "cosines": result.cosines}
                rec[IMAGENET_ARM] = {"version": IMAGENET_MODEL, "probs": imagenet(decoded.image)}
                vectors = {b: [round(float(v), 5) for v in c.last_embedding] for b, c in classifiers.items()}
                emb_handle.write(json.dumps({"image_id": iid, **vectors}) + "\n")
                emb_handle.flush()
                counts["ok"] += 1
            except Exception as exc:  # noqa: BLE001 — a bad file must not end the run
                rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
                counts["error"] += 1
            handle.write(json.dumps(rec) + "\n")
            handle.flush()
            if n % 50 == 0 or n == len(todo):
                rate = n / (time.perf_counter() - t0)
                print(f"classified {n}/{len(todo)} {dict(counts)} {rate:.2f} img/s", flush=True)
    return counts


def freeze(root: Path, seed: str, per_label: int) -> dict:
    preds = load_predictions(root / "predictions.jsonl")
    pool_rows = {int(r["image_id"]): r for r in _read_csv(root / "pool.csv")}
    population: dict[str, list[dict]] = defaultdict(list)
    errors = 0
    for iid, rec in sorted(preds.items()):
        if rec.get("error"):
            errors += 1
            continue
        stratum = rec[STRATIFY_BACKEND]["top_label"]
        population[stratum].append({"image_id": iid, "folder": folder_of(pool_rows[iid]["file_path"]),
                                    "file_path": pool_rows[iid]["file_path"]})
    picked = sample_strata(population, seed, {s: per_label for s in population})
    out = root / "sample"
    if (out / "cohort.csv").exists():
        raise FileExistsError(f"sample already frozen: {out / 'cohort.csv'}")
    _write_csv(out / "cohort.csv", ("image_id", "stratum", "file_path"),
               [{"image_id": m["image_id"], "stratum": s, "file_path": m["file_path"]}
                for s, members in picked.items() for m in members])
    sampling = {"seed": seed, "stratify_backend": STRATIFY_BACKEND, "pool_predictions": len(preds),
                "prediction_errors": errors, "frozen_utc": datetime.now(timezone.utc).isoformat(),
                "population": {s: len(m) for s, m in sorted(population.items())},
                "sample": {s: len(m) for s, m in sorted(picked.items())}}
    _write_new_json(out / "sampling.json", sampling)
    return sampling


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scene labels</title><style>
:root{--bg:#f6f6f4;--fg:#1d1d1b;--muted:#6b6b66;--on:#2563eb}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#a3a29b;--on:#60a5fa}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif}main{max-width:1320px;margin:0 auto;padding:16px}
img{display:block;max-width:100%;max-height:74vh}.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0}
button{font:inherit;padding:5px 10px}button.on{outline:3px solid var(--on)}.hint{color:var(--muted)}</style></head><body><main>
<div class="bar"><strong id="pos"></strong><span id="state" class="hint"></span></div>
<div class="bar" id="scenes"></div>
<div class="bar"><span>Bird visible anywhere?</span><button data-b="yes">Y — yes</button><button data-b="no">N — no</button></div>
<img id="photo" alt="Photo to label">
<div class="bar"><button id="prev">← Previous</button><button id="next">Next →</button><button id="download">Download labels.csv</button><span id="done" class="hint"></span></div>
<p class="hint">Pick the main scene (keys 1–8, 0 = can't tell), then answer Y/N for any bird, however small. Moves on when both are set.</p>
</main><script>
const ITEMS=__ITEMS__;const LABELS=__LABELS__;const KEY="__KEY__";let labels={};try{labels=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){}
let i=0;const $=id=>document.getElementById(id);function save(){try{localStorage.setItem(KEY,JSON.stringify(labels))}catch(e){}}
LABELS.forEach((l,k)=>{const b=document.createElement("button");b.dataset.s=l;b.textContent=(l==="cant_tell"?"0":String(k+1))+" — "+l.replace("_"," ");b.onclick=()=>set("scene",l);$("scenes").append(b)});
function done(v){return v&&v.scene&&v.bird}
function render(){const it=ITEMS[i],v=labels[it.id]||{};$("photo").src=it.img;$("pos").textContent=`${i+1} / ${ITEMS.length}`;
 document.querySelectorAll("[data-s]").forEach(b=>b.classList.toggle("on",b.dataset.s===v.scene));
 document.querySelectorAll("[data-b]").forEach(b=>b.classList.toggle("on",b.dataset.b===v.bird));
 $("state").textContent=done(v)?"complete":"";$("done").textContent=`${Object.values(labels).filter(done).length} complete`}
function set(k,val){const it=ITEMS[i];labels[it.id]={...(labels[it.id]||{}),[k]:val};save();if(done(labels[it.id])&&i<ITEMS.length-1)i++;render()}
document.querySelectorAll("[data-b]").forEach(b=>b.onclick=()=>set("bird",b.dataset.b));
$("prev").onclick=()=>{if(i>0)i--;render()};$("next").onclick=()=>{if(i<ITEMS.length-1)i++;render()};
document.addEventListener("keydown",e=>{const k=e.key.toLowerCase();const n=parseInt(k,10);
 if(k==="0")set("scene","cant_tell");else if(n>=1&&n<LABELS.length)set("scene",LABELS[n-1]);else if(k==="y")set("bird","yes");else if(k==="n")set("bird","no");
 else if(e.key==="ArrowLeft")$("prev").click();else if(e.key==="ArrowRight")$("next").click()});
$("download").onclick=()=>{const rows=[["image_id","scene","bird_visible"]].concat(ITEMS.map(it=>[it.id,(labels[it.id]||{}).scene||"",(labels[it.id]||{}).bird||""]));
 const url=URL.createObjectURL(new Blob([rows.map(r=>r.join(",")).join("\\n")+"\\n"],{type:"text/csv"}));const a=document.createElement("a");a.href=url;a.download="labels.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
render();
</script></body></html>"""


def build_page(root: Path, seed: str, long_edge: int = 1280) -> int:
    """Blind page: only image ids and pictures reach the HTML -- no stratum or prediction."""
    from modules.localization import decode_for_localization

    out = root / "sample"
    img_dir = out / "page" / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for row in _read_csv(out / "cohort.csv"):
        iid = int(row["image_id"])
        target = img_dir / f"{iid}.jpg"
        if not target.exists():
            img = decode_for_localization(row["file_path"]).image
            img.thumbnail((long_edge, long_edge))
            img.save(target, "JPEG", quality=90)
        items.append({"id": iid, "img": f"img/{iid}.jpg"})
    random.Random(seed).shuffle(items)
    page = (_PAGE.replace("__ITEMS__", json.dumps(items))
            .replace("__LABELS__", json.dumps(LABELS + ["cant_tell"]))
            .replace("__KEY__", html.escape(f"scene-route-labels-{seed}")))
    (out / "page" / "index.html").write_text(page, encoding="utf-8")
    return len(items)


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

def skip_sweep(scored: list[tuple[float, bool, float]], thresholds: list[float]) -> list[dict]:
    """``scored``: (score, bird_visible, weight). Skip = score below the threshold."""
    rows = []
    for t in thresholds:
        bird = [(s, w) for s, b, w in scored if b]
        other = [(s, w) for s, b, w in scored if not b]
        bw, ow = sum(w for _, w in bird), sum(w for _, w in other)
        skipped_n = sum(1 for s, _ in bird if s < t)
        lo, hi = wilson(skipped_n, len(bird))
        rows.append({"threshold": t,
                     "bird_skip_rate": round(sum(w for s, w in bird if s < t) / bw, 4) if bw else None,
                     "bird_skipped": skipped_n, "bird_n": len(bird), "bird_skip_wilson_hi": round(hi, 4),
                     "other_run_rate": round(sum(w for s, w in other if s >= t) / ow, 4) if ow else None})
    return rows


def choose_threshold(sweep: list[dict]) -> dict | None:
    """Largest threshold whose weighted bird skip rate stays within AC-4."""
    ok = [r for r in sweep if r["bird_skip_rate"] is not None and r["bird_skip_rate"] <= MAX_SKIP_RATE]
    return max(ok, key=lambda r: r["threshold"]) if ok else None


def weighted_confusion(rows: list[tuple[str, str, float]]) -> dict:
    """rows: (owner_label, predicted_label, weight) -> per-label precision/recall and the matrix."""
    matrix: dict[str, Counter] = defaultdict(Counter)
    for truth, pred, w in rows:
        matrix[truth][pred] += w
    per_label = {}
    for lab in LABELS:
        tp = matrix[lab][lab]
        pred_total = sum(matrix[t][lab] for t in matrix)
        true_total = sum(matrix[lab].values())
        per_label[lab] = {"precision": round(tp / pred_total, 4) if pred_total else None,
                          "recall": round(tp / true_total, 4) if true_total else None}
    return {"per_label": per_label,
            "matrix": {t: {p: round(w, 2) for p, w in sorted(c.items())} for t, c in sorted(matrix.items())}}


THRESHOLDS = {"prob": [round(0.005 * k, 3) for k in range(1, 41)] + [round(0.05 * k, 2) for k in range(5, 20)],
              "cosine": [round(0.12 + 0.005 * k, 3) for k in range(0, 41)]}
THRESHOLDS["animal_prob"] = THRESHOLDS["prob"]


def arm_view(rec: dict, arm: str) -> tuple[str | None, dict[str, float]]:
    """(top scene label or None, bird-route scores by kind) for one image and arm."""
    if arm == IMAGENET_ARM:
        g = rec[arm]["probs"]
        return None, {"prob": g["wildlife_bird"], "animal_prob": sum(g[k] for k in ANIMAL_LABELS)}
    r = rec[arm]
    scores = {"prob": r["probs"]["wildlife_bird"], "animal_prob": sum(r["probs"].get(k, 0.0) for k in ANIMAL_LABELS)}
    if "cosines" in r:
        scores["cosine"] = r["cosines"]["wildlife_bird"]
    return r["top_label"], scores


def probe_predictions(embeddings: dict[int, list[float]], labels: dict[int, str], folders: dict[int, str],
                      n_splits: int = 5) -> dict[int, dict]:
    """Few-shot linear probe: folder-grouped out-of-fold logistic regression on image embeddings.

    Every image (``cant_tell`` included) is predicted by a model that never saw its folder;
    ``cant_tell`` images are never training targets.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold

    ids = sorted(embeddings)
    x = np.asarray([embeddings[i] for i in ids])
    groups = [folders[i] for i in ids]
    out: dict[int, dict] = {}
    for train, test in GroupKFold(n_splits=n_splits).split(x, groups=groups):
        fit = [k for k in train if labels[ids[k]] in LABELS]
        clf = LogisticRegression(max_iter=2000, C=1.0).fit(x[fit], [labels[ids[k]] for k in fit])
        for k, row in zip(test, clf.predict_proba(x[test])):
            probs = {lab: 0.0 for lab in LABELS}
            probs.update({lab: float(p) for lab, p in zip(clf.classes_, row)})
            out[ids[k]] = {"top_label": max(probs, key=probs.get), "probs": probs}
    return out


def analyze(root: Path, labels_path: Path) -> dict:
    out = root / "sample"
    cohort = {int(r["image_id"]): r for r in _read_csv(out / "cohort.csv")}
    labels = {int(r["image_id"]): r for r in _read_csv(labels_path)}
    if set(labels) != set(cohort) or any(not r["scene"] or not r["bird_visible"] for r in labels.values()):
        raise ValueError("labels must cover every cohort image with both a scene and a bird answer")
    sampling = json.loads((out / "sampling.json").read_text(encoding="utf-8"))
    weight = {s: sampling["population"][s] / sampling["sample"][s] for s in sampling["sample"] if sampling["sample"][s]}
    preds = load_predictions(root / "predictions.jsonl")
    embeddings = load_predictions(root / "embeddings.jsonl")
    v1_preds = load_predictions(root / "predictions_v1.jsonl")
    v1_presence = _v1_presence()

    # Linear-probe arms join the predictions as ordinary arms.
    folders = {i: folder_of(r["file_path"]) for i, r in cohort.items()}
    probe_arms = []
    for backend in BACKENDS:
        arm = f"probe:{backend}"
        oof = probe_predictions({i: embeddings[i][backend] for i in cohort},
                                {i: labels[i]["scene"] for i in cohort}, folders)
        for i, r in oof.items():
            preds[i][arm] = r
        probe_arms.append(arm)
    arms = [*BACKENDS, IMAGENET_ARM, *probe_arms]

    result: dict = {"sampling": sampling, "inputs_sha256": {"labels": sha256_file(labels_path),
                                                             "cohort.csv": sha256_file(out / "cohort.csv")},
                    "owner_scene_counts": dict(Counter(r["scene"] for r in labels.values())),
                    "owner_bird_visible": sum(r["bird_visible"] == "yes" for r in labels.values()),
                    "arms": {}}
    for arm in arms:
        views = {i: arm_view(preds[i], arm) for i in cohort}
        entry: dict = {}
        if views[next(iter(cohort))][0] is not None:
            entry["confusion"] = weighted_confusion([
                (labels[i]["scene"], views[i][0], weight[c["stratum"]])
                for i, c in cohort.items() if labels[i]["scene"] != "cant_tell"])
        routes = {}
        for kind in views[next(iter(cohort))][1]:
            scored = [(views[i][1][kind], labels[i]["bird_visible"] == "yes", weight[c["stratum"]])
                      for i, c in cohort.items()]
            sweep = skip_sweep(scored, THRESHOLDS[kind])
            chosen = choose_threshold(sweep)
            side = None
            if chosen is not None and v1_preds and not arm.startswith("probe:"):
                v1 = [(arm_view(v1_preds[i], arm)[1][kind], v1_presence[i]) for i in v1_preds
                      if not v1_preds[i].get("error") and v1_presence.get(i) in ("bird", "no_bird")]
                side = {"bird_frames": sum(p == "bird" for _, p in v1),
                        "bird_frames_skipped": sum(p == "bird" and s < chosen["threshold"] for s, p in v1),
                        "no_bird_frames": sum(p == "no_bird" for _, p in v1),
                        "no_bird_frames_skipped": sum(p == "no_bird" and s < chosen["threshold"] for s, p in v1)}
            routes[kind] = {"chosen": chosen, "v1_side_check": side, "sweep": sweep}
        entry["bird_route"] = routes
        result["arms"][arm] = entry

    candidates = [(a, k, r["bird_route"][k]["chosen"]) for a, r in result["arms"].items()
                  for k in r["bird_route"] if r["bird_route"][k]["chosen"]]
    # Fewest non-bird images sent to the detector at AC-4; ties prefer earlier (cheaper, training-free) arms.
    best = min(candidates, key=lambda c: (c[2]["other_run_rate"], arms.index(c[0]), c[1]), default=None)
    result["selected"] = ({"arm": best[0], "score": best[1], "threshold": best[2]["threshold"],
                           "bird_skip_rate": best[2]["bird_skip_rate"], "other_run_rate": best[2]["other_run_rate"]}
                          if best else None)
    # Outputs are named after the label source, so AI-judge and owner analyses never overwrite each other.
    tag = labels_path.stem
    (out / f"analysis_{tag}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    if best:
        version = preds[next(iter(cohort))][best[0]].get("version", best[0])
        _write_new_json(out / f"thresholds_{tag}.json", {
            "arm": best[0], "score": best[1], "run_thresholds": {"wildlife_bird": best[2]["threshold"]},
            "scene_version": version, "frozen_utc": datetime.now(timezone.utc).isoformat(),
            "label_source": labels_path.name, "analysis_sha256": sha256_file(out / f"analysis_{tag}.json")})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("pool", "predict", "freeze", "page", "analyze"))
    parser.add_argument("--root", type=Path, default=OUT_ROOT)
    parser.add_argument("--seed", default="scene-route-1")
    parser.add_argument("--size", type=int, default=4000)
    parser.add_argument("--per-folder", type=int, default=3)
    parser.add_argument("--per-label", type=int, default=60)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--extra-v1", action="store_true", help="classify the owner-labelled v1 frames instead")
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    if args.action == "pool":
        print(f"Froze a pool of {pool(args.root, args.seed, args.size, args.per_folder)} images")
    elif args.action == "predict":
        print(json.dumps(predict(args.root, args.limit, args.extra_v1)))
    elif args.action == "freeze":
        print(json.dumps(freeze(args.root, args.seed, args.per_label), indent=1))
    elif args.action == "page":
        print(f"Built {build_page(args.root, args.seed)} items at {args.root / 'sample' / 'page' / 'index.html'}")
    else:
        if args.labels is None:
            parser.error("analyze needs --labels")
        res = analyze(args.root, args.labels)
        print(json.dumps({"selected": res["selected"],
                          "per_label": {a: r["confusion"]["per_label"] for a, r in res["arms"].items()
                                        if "confusion" in r}}, indent=1))


if __name__ == "__main__":
    main()
