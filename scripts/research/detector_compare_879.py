#!/usr/bin/env python3
"""#879: false positives and false negatives of the v0 and v1 bird detectors on one unconditioned sample.

Earlier samples were drawn from frames where v0 already had a box, so they could only see v0 false positives and v1
misses. This study draws bird-tagged frames without regard to either detector, runs both detectors read-only under one
decode and one config (only the weights differ), and has the owner label the frames where they disagree plus a fixed
spot check of the frames where they agree.

Strata from the two rank-0 boxes at the production confidence:
  N  neither detector has a box      A  both, same place (IoU >= 0.5)    P  both, partial (0.1 <= IoU < 0.5)
  D  both, different object (< 0.1)  O0 only v0 has a box                O1 only v1 has a box

Modes (run ``sample`` and ``run`` in gpu-shell from /app; no DB writes anywhere):

  python scripts/research/detector_compare_879.py sample --out S.json --seed 879 --size 300 --cap 5 --exclude IDS.json
  python scripts/research/detector_compare_879.py run --sample S.json --out R.jsonl
  python scripts/research/detector_compare_879.py review --results R.jsonl --out REVIEW.json --spot 20 --seed 879
  python scripts/research/detector_compare_879.py analyze --results R.jsonl --review REVIEW.json --labels L.json --out A.json

``analyze`` reports, per detector, the false-positive rate (boxes on something that is not a bird, over its boxes) and
the false-negative rate (frames with a bird where it has no box on a bird, over frames with a bird), weighted back to
the whole sample by stratum, with seeded bootstrap intervals. No verdict: the policy is the owner's (#810).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SCHEMA = "detector-compare-879/1"
V0_FILE = "bird_detect_v0.pt"
V1_FILE = "bird_detect_v1.pt"
#: Config hashes of the library's current bird runs; ``run`` refuses to start unless both detectors reproduce them, so
#: the comparison uses exactly the models and settings that wrote those runs.
EXPECTED_CONFIG_HASH = {"v0": "dff447b1aad63d1fe683bb628a2baa129be9a970a434a441f8ba65b4a8b674d2",
                        "v1": "eb5935e79706aa109fae521cb5859db190f485ceaef3093a403d9f5e3f70b6e1"}
SAME_IOU, DIFFERENT_IOU = 0.5, 0.1
DISAGREE = ("P", "D", "O0", "O1")
SPOT = ("A", "N")
STRATA = ("N", "A", "P", "D", "O0", "O1")


# --------------------------------------------------------------------------- pure helpers (tested)

def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def stratum(v0_box, v1_box) -> str:
    if v0_box is None and v1_box is None:
        return "N"
    if v1_box is None:
        return "O0"
    if v0_box is None:
        return "O1"
    v = iou(v0_box, v1_box)
    return "A" if v >= SAME_IOU else "P" if v >= DIFFERENT_IOU else "D"


def draw_capped(pool: list[dict], *, seed: int, size: int, cap: int) -> list[dict]:
    """Seeded shuffle of the pool (sorted by id first), taking frames until ``size``, at most ``cap`` per shoot."""
    rng = random.Random(seed)
    order = sorted(pool, key=lambda f: f["image_id"])
    rng.shuffle(order)
    per, out = Counter(), []
    for f in order:
        if len(out) == size:
            break
        if per[f["shoot"]] >= cap:
            continue
        per[f["shoot"]] += 1
        out.append(f)
    if len(out) < size:
        raise ValueError(f"only {len(out)} frames under cap {cap}")
    return sorted(out, key=lambda f: f["image_id"])


def select_for_review(rows: list[dict], *, spot: int, seed: int) -> dict:
    """Every disagreement frame, plus a seeded spot check of ``spot`` frames from each agreement stratum."""
    rng = random.Random(seed)
    by = {s: sorted(r["image_id"] for r in rows if r["stratum"] == s) for s in STRATA}
    chosen = {s: list(by[s]) for s in DISAGREE}
    for s in SPOT:
        chosen[s] = sorted(rng.sample(by[s], min(spot, len(by[s]))))
    return {"schema": SCHEMA, "counts": {s: len(by[s]) for s in STRATA},
            "review": {s: chosen[s] for s in STRATA}, "spot": spot, "seed": seed}


def frame_outcome(row: dict, label: dict) -> dict | None:
    """One labelled frame -> what each detector got right. ``label``: bird ('yes'|'no'|'unsure'), v0/v1 box
    verdicts ('bird'|'not'|None when that detector had no box). Unsure frames are left out (None)."""
    if label.get("bird") not in ("yes", "no"):
        return None
    bird = label["bird"] == "yes"
    out = {"bird": bird}
    for d in ("v0", "v1"):
        has_box = row[d]["box"] is not None
        on_bird = has_box and label.get(d) == "bird"
        out[d] = {"box": has_box, "fp": has_box and label.get(d) == "not", "hit": on_bird, "miss": bird and not on_bird}
    return out


def estimate(rows: list[dict], review: dict, labels: dict) -> dict:
    """Stratum-weighted FP and FN rates per detector, from labelled frames, as point estimates."""
    counts = review["counts"]
    by_id = {r["image_id"]: r for r in rows}
    per_stratum = {}
    for s in STRATA:
        outs = [frame_outcome(by_id[i], labels[str(i)]) for i in review["review"][s] if str(i) in labels]
        outs = [o for o in outs if o is not None]
        per_stratum[s] = outs
    return _estimate_from(per_stratum, counts)


def _estimate_from(per_stratum: dict, counts: dict) -> dict:
    res = {}
    for d in ("v0", "v1"):
        boxes = fp = birds = miss = 0.0
        for s, outs in per_stratum.items():
            if not outs:
                continue
            w = counts[s] / len(outs)
            boxes += w * sum(o[d]["box"] for o in outs)
            fp += w * sum(o[d]["fp"] for o in outs)
            birds += w * sum(o["bird"] for o in outs)
            miss += w * sum(o[d]["miss"] for o in outs)
        res[d] = {"fp_rate": fp / boxes if boxes else None, "fn_rate": miss / birds if birds else None,
                  "est_boxes": boxes, "est_birds": birds}
    return res


def bootstrap(rows: list[dict], review: dict, labels: dict, *, iters: int = 2000, seed: int = 879) -> dict:
    """Seeded within-stratum bootstrap: 2.5th and 97.5th percentiles of each rate."""
    by_id = {r["image_id"]: r for r in rows}
    base = {}
    for s in STRATA:
        outs = [frame_outcome(by_id[i], labels[str(i)]) for i in review["review"][s] if str(i) in labels]
        base[s] = [o for o in outs if o is not None]
    rng = random.Random(seed)
    draws = {d: {"fp_rate": [], "fn_rate": []} for d in ("v0", "v1")}
    for _ in range(iters):
        sample = {s: [rng.choice(o) for _ in o] if o else [] for s, o in base.items()}
        est = _estimate_from(sample, review["counts"])
        for d in draws:
            for k in draws[d]:
                if est[d][k] is not None:
                    draws[d][k].append(est[d][k])
    out = {}
    for d, ks in draws.items():
        out[d] = {}
        for k, vals in ks.items():
            vals.sort()
            out[d][k] = [vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]] if vals else None
    return out


# --------------------------------------------------------------------------- DB / GPU modes

_POOL_SQL = """
WITH bird AS (SELECT DISTINCT ik.image_id FROM image_keywords ik JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
              WHERE kd.keyword_norm LIKE 'bird%')
SELECT i.id AS image_id, i.file_path, f.path AS shoot
FROM images i JOIN bird b ON b.image_id = i.id LEFT JOIN folders f ON f.id = i.folder_id
ORDER BY i.id
"""


def sample(out: Path, *, seed: int, size: int, cap: int, exclude: Path | None) -> dict:
    import os

    from modules import db

    if out.exists():
        raise FileExistsError(out)
    excluded = set(json.loads(exclude.read_text())) if exclude else set()
    rows = db.get_connector().query(_POOL_SQL)
    pool = [{"image_id": int(r["image_id"]), "file_path": r["file_path"], "shoot": r["shoot"] or ""}
            for r in rows if int(r["image_id"]) not in excluded and r["file_path"] and os.path.exists(r["file_path"])]
    frames = draw_capped(pool, seed=seed, size=size, cap=cap)
    out.write_text(json.dumps({"schema": SCHEMA, "seed": seed, "size": size, "cap": cap, "pool": len(pool),
                               "bird_tagged": len(rows), "excluded": len(excluded), "frames": frames}, indent=1))
    meta = {"frames": len(frames), "pool": len(pool), "shoots": len({f["shoot"] for f in frames}),
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
    print(json.dumps(meta))
    return meta


def _detectors(v0_weights: str | None = None):
    """Both detectors under the production config, differing only in weights. ``v0_weights`` is a local file, so the
    v0 model is never downloaded; each detector must reproduce its library config hash."""
    from modules import config as cfg
    from modules.bird_detection import BirdDetector
    from modules.localization import detector_config_hash, weights_sha256

    base = cfg.get_config_section("bird_detection") or {}
    dets = {}
    for name, fname, local in (("v0", V0_FILE, v0_weights or ""), ("v1", V1_FILE, "")):
        d = BirdDetector(config={**base, "model_file": fname, "local_path": local})
        h = detector_config_hash(weights_sha256(d._resolve_weights_path()), d.imgsz, d.confidence, d.max_det)
        if h != EXPECTED_CONFIG_HASH[name]:
            raise RuntimeError(f"{name}: config hash {h[:16]} does not match the library runs")
        d.load_model()
        dets[name] = d
    return dets


def run(sample_path: Path, out: Path, v0_weights: str | None = None) -> Counter:
    from modules.localization import decode_for_localization, weights_sha256

    frames = json.loads(sample_path.read_text())["frames"]
    dets = _detectors(v0_weights)
    weights = {k: {"file": Path(d._resolve_weights_path()).name, "sha256": weights_sha256(d._resolve_weights_path()),
                   "confidence": d.confidence, "imgsz": d.imgsz} for k, d in dets.items()}
    done = set()
    if out.exists():
        done = {json.loads(line)["image_id"] for line in out.read_text().splitlines() if line}
    counts: Counter = Counter()
    with out.open("a", encoding="utf-8") as fh:
        for n, f in enumerate(frames, 1):
            if f["image_id"] in done:
                continue
            rec = {"schema": SCHEMA, "image_id": f["image_id"], "shoot": f["shoot"], "weights": weights}
            try:
                decoded = decode_for_localization(f["file_path"])
                rec["display"] = [decoded.descriptor.display_width, decoded.descriptor.display_height]
                for k, d in dets.items():
                    boxes = d.detect_boxes(decoded.image)
                    rec[k] = {"box": list(boxes[0]["region"]) if boxes else None,
                              "conf": boxes[0]["conf"] if boxes else None, "n_boxes": len(boxes)}
                rec["stratum"] = stratum(rec["v0"]["box"], rec["v1"]["box"])
            except Exception as exc:  # noqa: BLE001 -- recorded per frame
                rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
            counts[rec.get("stratum", "error")] += 1
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 25 == 0:
                print(f"compare {n}/{len(frames)} {dict(counts)}", flush=True)
    return counts


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--size", type=int, default=300)
    s.add_argument("--cap", type=int, default=5)
    s.add_argument("--exclude", type=Path)
    r = sub.add_parser("run")
    r.add_argument("--sample", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--v0-weights", help="local bird_detect_v0.pt (no download); must reproduce the v0 config hash")
    v = sub.add_parser("review")
    v.add_argument("--results", type=Path, required=True)
    v.add_argument("--out", type=Path, required=True)
    v.add_argument("--spot", type=int, default=20)
    v.add_argument("--seed", type=int, default=879)
    a = sub.add_parser("analyze")
    a.add_argument("--results", type=Path, required=True)
    a.add_argument("--review", type=Path, required=True)
    a.add_argument("--labels", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.mode == "sample":
        sample(args.out, seed=args.seed, size=args.size, cap=args.cap, exclude=args.exclude)
    elif args.mode == "run":
        print(dict(run(args.sample, args.out, args.v0_weights)))
    elif args.mode == "review":
        rows = [x for x in _load(args.results) if "stratum" in x]
        rev = select_for_review(rows, spot=args.spot, seed=args.seed)
        args.out.write_text(json.dumps(rev, indent=1))
        print(json.dumps({"counts": rev["counts"], "to_label": sum(len(v) for v in rev["review"].values())}))
    else:
        rows = [x for x in _load(args.results) if "stratum" in x]
        rev = json.loads(args.review.read_text())
        labels = json.loads(args.labels.read_text())
        rep = {"schema": SCHEMA, "estimate": estimate(rows, rev, labels), "interval95": bootstrap(rows, rev, labels),
               "counts": rev["counts"], "labelled": len(labels)}
        args.out.write_text(json.dumps(rep, indent=1))
        print(json.dumps(rep["estimate"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
