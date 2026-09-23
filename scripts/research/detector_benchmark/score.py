"""Score the detector benchmark: join human labels to per-arm results (#377).

    python scripts/research/detector_benchmark/score.py --dir <benchmark dir>

Reads ``results.csv`` (from ``run_benchmark.py``), ``labels.csv`` (``image_id,label`` with
``label`` in ``bird|no_bird|unsure``) and ``gpu_peak_bytes.csv``; writes ``metrics.md``.

Rules, stated so the numbers can't be over-read:

* A frame counts as a **detection** when the arm returned at least one box.
* **Recall** is over frames labelled ``bird``; **false-positive rate** is over frames
  labelled ``no_bird``. ``unsure`` is excluded from both and reported as a count.
* Presence only: labels say whether a bird is in the frame, not where. A detection on a
  ``bird`` frame is credited even if the box is on the wrong bird -- the report says so.
* Rates carry **Wilson 95%** intervals. With n in the tens per stratum these are wide,
  and the report must not quote a point estimate without its interval.
* The ``det_*`` strata were sampled from frames the *production* detector already fired
  on, so ``a640`` recall there is near 1 by construction. They exist to catch regressions
  in the other arms, not to estimate library recall. Nothing is pooled across strata.
* The ``eagle`` slice is scored as verified positives (every frame visibly contains the
  bird -- Sept 7 audit) and reported separately, never pooled.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

ARMS = ("a640", "a1280", "tile")


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, centre - half), min(1.0, centre + half)


def fmt(k, n):
    if n == 0:
        return "—"
    p, lo, hi = wilson(k, n)
    return f"{k}/{n} = **{p:.0%}** ({lo:.0%}–{hi:.0%})"


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    args = ap.parse_args(argv)
    d = Path(args.dir)

    with open(d / "results.csv", newline="", encoding="utf-8") as fh:
        results = {int(r["image_id"]): r for r in csv.DictReader(fh)}
    labels = {}
    with open(d / "labels.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            labels[int(r["image_id"])] = r["label"]
    for iid, r in results.items():
        if r["stratum"] == "eagle":
            labels.setdefault(iid, "bird")

    missing = [i for i in results if i not in labels]
    extra = [i for i in labels if i not in results]

    by_stratum = defaultdict(list)
    for iid, r in results.items():
        by_stratum[r["stratum"]].append((r, labels.get(iid)))

    out = []
    out.append("# Detector benchmark — metrics\n")
    out.append(f"Frames with results: {len(results)} · labelled: {len(results) - len(missing)} · "
               f"unlabelled: {len(missing)} · labels without a result: {len(extra)}\n")

    order = ["det_small", "det_medium", "det_large", "miss_birdkw", "miss_nokw", "eagle"]
    out.append("## Recall on frames labelled `bird`\n")
    out.append("| Stratum | " + " | ".join(ARMS) + " |")
    out.append("|---|" + "---|" * len(ARMS))
    for s in order:
        rows = [r for r, lab in by_stratum.get(s, []) if lab == "bird"]
        cells = [fmt(sum(int(r[f"{a}_n"]) > 0 for r in rows), len(rows)) for a in ARMS]
        out.append(f"| `{s}` | " + " | ".join(cells) + " |")

    out.append("\n## False-positive rate on frames labelled `no_bird`\n")
    out.append("| Stratum | " + " | ".join(ARMS) + " |")
    out.append("|---|" + "---|" * len(ARMS))
    for s in order:
        rows = [r for r, lab in by_stratum.get(s, []) if lab == "no_bird"]
        if not rows:
            continue
        cells = [fmt(sum(int(r[f"{a}_n"]) > 0 for r in rows), len(rows)) for a in ARMS]
        out.append(f"| `{s}` | " + " | ".join(cells) + " |")

    out.append("\n## Label composition\n")
    out.append("| Stratum | bird | no_bird | unsure | unlabelled |")
    out.append("|---|---|---|---|---|")
    for s in order:
        labs = [lab for _r, lab in by_stratum.get(s, [])]
        out.append(f"| `{s}` | {labs.count('bird')} | {labs.count('no_bird')} | "
                   f"{labs.count('unsure')} | {labs.count(None)} |")

    out.append("\n## Cost\n")
    peaks = {}
    pk = d / "gpu_peak_bytes.csv"
    if pk.exists():
        with open(pk, newline="", encoding="utf-8") as fh:
            peaks = {r["arm"]: int(r["peak_bytes"]) for r in csv.DictReader(fh)}
    out.append("| Arm | p50 ms | p95 ms | peak GPU MiB | near-full-frame frames |")
    out.append("|---|---|---|---|---|")
    for a in ARMS:
        ms = [float(r[f"{a}_ms"]) for r in results.values()]
        susp = sum(int(r[f"{a}_suspicious"] or 0) for r in results.values())
        out.append(f"| `{a}` | {pct(ms, .5):.0f} | {pct(ms, .95):.0f} | "
                   f"{peaks.get(a, 0) / 2**20:.0f} | {susp} |")
    tile_runs = sum(int(r["tile_ran"]) for r in results.values())
    dec = [float(r["decode_ms"]) for r in results.values()]
    out.append(f"\nThe tile pass ran on {tile_runs} of {len(results)} frames (only on an `a640` miss). "
               f"Decode, shared by all arms: p50 {pct(dec, .5):.0f} ms, p95 {pct(dec, .95):.0f} ms.\n")

    out.append("## Diagnostic — would lowering `conf` alone help?\n")
    missed = [r for iid, r in results.items() if labels.get(iid) == "bird" and int(r["a640_n"]) == 0]
    bands = [(0.20, 0.25), (0.15, 0.20), (0.10, 0.15), (0.05, 0.10)]
    out.append(f"Of **{len(missed)}** `bird` frames `a640` missed, the best sub-threshold confidence "
               "at `conf=0.05`:\n")
    out.append("| Best conf | Frames |")
    out.append("|---|---|")
    for lo, hi in bands:
        out.append(f"| {lo:.2f}–{hi:.2f} | {sum(lo <= float(r['diag_max_conf']) < hi for r in missed)} |")
    out.append(f"| none above 0.05 | {sum(float(r['diag_max_conf']) < 0.05 for r in missed)} |")

    routes = defaultdict(int)
    dims = defaultdict(int)
    for r in results.values():
        routes[r["decode_route"]] += 1
        dims[(r["img_w"], r["img_h"])] += 1
    out.append("\n## Decode\n")
    out.append("Routes: " + ", ".join(f"`{k}` {v}" for k, v in sorted(routes.items())) + ".  ")
    top = sorted(dims.items(), key=lambda kv: -kv[1])[:5]
    out.append("Most common decoded sizes: " + ", ".join(f"{w}×{h} ({n})" for (w, h), n in top) + ".")
    med_long = statistics.median(max(int(r["img_w"]), int(r["img_h"])) for r in results.values())
    out.append(f" Median long edge {med_long:.0f} px, i.e. `imgsz=640` downscales by "
               f"~{med_long / 640:.1f}× and `imgsz=1280` by ~{med_long / 1280:.1f}×.")

    (d / "metrics.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
