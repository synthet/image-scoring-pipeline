"""Stage 5 gate G5d (#592): no-write dry run of the production species path on cohort images.

For a seeded sample of the frozen 369-species / 0.5 comparison, call the same functions the
runner calls (``species_input_for_image`` -> ``_resolve_inference_path`` -> ``classify`` with
the selected region, reading the mounted source as production does) and compare the stored-floor
label with the frozen result. Nothing is written to the database.

Run in gpu-shell:

    python scripts/research/bird_crop/stage5_dryrun.py --full <full.json> --species-list <369.txt> --out <json>
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--full", type=Path, required=True)
    p.add_argument("--species-list", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=20261011)
    a = p.parse_args()

    from modules import bird_species as bs
    from modules import db

    frozen = {int(r["image_id"]): r for r in json.loads(a.full.read_text(encoding="utf-8"))["images"]}
    ids = random.Random(a.seed).sample(sorted(frozen), a.n)
    species = [ln.strip() for ln in a.species_list.read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.startswith("#")]
    floor = bs.min_confidence()
    clf = bs.BioCLIPClassifier()
    clf.load_model()
    rows, t0 = [], time.monotonic()
    for n, image_id in enumerate(ids, 1):
        row = db.get_connector().query_one("SELECT id, file_path FROM images WHERE id = ?", (image_id,))
        choice = bs.species_input_for_image(image_id)
        path = bs._resolve_inference_path(row, row["file_path"])
        # threshold 0 separates "classify failed" ([]) from abstention; the floor is applied below
        # with the runner's comparison.
        preds = clf.classify(path, species, threshold=0.0, top_k=1, region=choice.get("region"),
                             use_detector=choice["mode"] == "legacy")
        label = preds[0][0] if preds and preds[0][1] > floor else None
        rows.append({"image_id": image_id, "mode": choice["mode"], "failed": not preds,
                     "label": label, "p": preds[0][1] if preds else None, "frozen": frozen[image_id].get("new"),
                     "match": bool(preds) and (label or "").lower() == (frozen[image_id].get("new") or "").lower()})
        if n % 25 == 0:
            print(f"dryrun: {n}/{len(ids)} matches={sum(r['match'] for r in rows)}", flush=True)
    summary = {"n": len(rows), "floor": floor, "species": len(species),
               "region_mode": sum(r["mode"] == "region" for r in rows),
               "failed": sum(r["failed"] for r in rows), "match": sum(r["match"] for r in rows),
               "elapsed_s": round(time.monotonic() - t0, 1)}
    summary["match_rate"] = summary["match"] / summary["n"]
    summary["fail_rate"] = summary["failed"] / summary["n"]
    summary["pass"] = summary["match_rate"] >= 0.99 and summary["fail_rate"] <= 0.01
    a.out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
