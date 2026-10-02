"""Classify a frozen cohort with one scene-route backend and save each resolved class (#472).

Reads image ids from a JSON snapshot (``images[].image_id`` / ``file_path``, as written by
``v1_promotion_gate.py snapshot``), decodes the localization rendition, classifies it, and saves
the result to ``image_scene_labels``. A JSONL log makes the run resumable. Writes nothing else.

    python scripts/research/scene_route/classify_cohort.py \\
        --snapshot .agent/scratch/bird_v1_promotion/snapshot.json \\
        --out .agent/scratch/bird_v1_regate/scene_siglip2.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path


def classify(snapshot: Path, out: Path, backend: str, limit: int, prompt_set: str = "scene_v2") -> Counter:
    from modules.localization import decode_for_localization
    from modules.scene_route import SceneClassifier, save_scene_label

    images = json.loads(snapshot.read_text(encoding="utf-8"))["images"]
    done = set()
    if out.exists():
        done = {json.loads(line)["image_id"] for line in out.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [i for i in images if int(i["image_id"]) not in done]
    if limit > 0:
        todo = todo[:limit]
    clf = SceneClassifier(backend, prompt_set=prompt_set)
    clf.load()
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    t0 = time.perf_counter()
    with out.open("a", encoding="utf-8") as handle:
        for n, item in enumerate(todo, 1):
            iid = int(item["image_id"])
            rec: dict = {"image_id": iid}
            try:
                decoded = decode_for_localization(item["file_path"])
                result = clf.classify(decoded.image)
                save_scene_label(iid, result, backend=backend, rendition_hash=decoded.descriptor.rendition_hash)
                rec.update(rendition_hash=decoded.descriptor.rendition_hash, version=result.version,
                           top_label=result.top_label, probs=result.probs)
                counts["ok"] += 1
            except Exception as exc:  # noqa: BLE001 — one bad file must not end the run
                rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
                counts["error"] += 1
            handle.write(json.dumps(rec) + "\n")
            handle.flush()
            if n % 200 == 0 or n == len(todo):
                print(f"classified {n}/{len(todo)} {dict(counts)} {n / (time.perf_counter() - t0):.2f} img/s", flush=True)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", default="siglip2_base")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--prompt-set", default="scene_v2")
    args = parser.parse_args()
    print(json.dumps(classify(args.snapshot, args.out, args.backend, args.limit, args.prompt_set)))


if __name__ == "__main__":
    main()
