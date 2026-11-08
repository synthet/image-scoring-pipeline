"""Classify a frozen cohort with one scene-route backend and save each resolved class (#472).

Reads image ids from a JSON snapshot (``images[].image_id`` / ``file_path``, as written by
``v1_promotion_gate.py snapshot``), decodes the localization rendition, classifies it, and saves
the result to ``image_scene_labels``. A JSONL log makes the run resumable. Writes nothing else.

    python scripts/research/scene_route/classify_cohort.py \\
        --snapshot .agent/scratch/bird_v1_promotion/snapshot.json \\
        --out .agent/scratch/bird_v1_regate/scene_siglip2.jsonl

Add ``--remote`` to classify on the GPU runner at ``gpu_runner.url``. Decoding and the database
writes stay on this host.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path


def make_classifier(backend: str, prompt_set: str, remote: bool):
    """The local classifier, or the towers on the configured GPU runner (#809).

    Remote runs use the runner alone, never the local fallback, so a pilot times the machine it
    names and stops if that runner is down. The readiness check also compares the runner's
    localization config with this host's.
    """
    from modules.scene_route import SceneClassifier

    if not remote:
        clf = SceneClassifier(backend, prompt_set=prompt_set)
        clf.load()
        return clf
    from modules.remote_gpu.client import FallbackGpuClient, get_client
    from modules.remote_gpu.proxies import RemoteSceneClassifier

    client = get_client()
    if isinstance(client, FallbackGpuClient):
        client = client.backends[0]
    client.check_phase("localization")
    return RemoteSceneClassifier(client, backend, prompt_set=prompt_set)


def classify(snapshot: Path, out: Path, backend: str, limit: int, prompt_set: str = "scene_v2",
             remote: bool = False) -> Counter:
    from modules.localization import decode_for_localization
    from modules.scene_route import save_scene_label

    images = json.loads(snapshot.read_text(encoding="utf-8"))["images"]
    done = set()
    if out.exists():
        done = {json.loads(line)["image_id"] for line in out.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [i for i in images if int(i["image_id"]) not in done]
    if limit > 0:
        todo = todo[:limit]
    clf = make_classifier(backend, prompt_set, remote)
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
    parser.add_argument("--remote", action="store_true",
                        help="classify on gpu_runner.url, with no local fallback; gpu_runner.enabled need not be on")
    args = parser.parse_args()
    print(json.dumps(classify(args.snapshot, args.out, args.backend, args.limit, args.prompt_set,
                              remote=args.remote)))


if __name__ == "__main__":
    main()
