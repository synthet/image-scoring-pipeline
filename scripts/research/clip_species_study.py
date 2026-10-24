"""Frozen, read-only BioCLIP species study over the #377 presence cohort.

Run in image-scoring-gpu-shell from /app. Outputs under reports/clip-species-study/
are private: the frozen thumbnails and judge crops are never committed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "docs/reports/detector-benchmark-2026-09"
DEFAULT_OUT = ROOT / "reports/clip-species-study"
MODEL_ID = "hf-hub:imageomics/bioclip-2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def decide(scores, candidates, *, confidence_floor=0.5, similarity_floor=None, outside_gap=None):
    """A candidate softmax plus optional absolute and full-vocabulary gates."""
    scores = np.asarray(scores, dtype=float)
    candidates = np.asarray(candidates, dtype=int)
    if scores.ndim != 1 or not len(candidates) or not np.all(np.isfinite(scores)):
        raise ValueError("scores must be a finite vector with nonempty candidates")
    if np.any(candidates < 0) or np.any(candidates >= len(scores)):
        raise ValueError("candidate index outside vocabulary")
    chosen = candidates[int(np.argmax(scores[candidates]))]
    best = float(scores[chosen])
    confidence = float(1 / np.exp((scores[candidates] - best) * 100).sum())
    gap = float(np.max(scores) - best)
    reason = None
    if similarity_floor is not None and best < similarity_floor:
        reason = "low_similarity"
    elif outside_gap is not None and gap > outside_gap:
        reason = "outside_list"
    elif confidence < confidence_floor:
        reason = "low_confidence"
    return {"name_index": int(chosen), "confidence": confidence, "similarity": best,
            "outside_gap": gap, "accepted": reason is None, "reason": reason}


def evaluate(scores, truth, names, candidates, *, confidence_floor=0.5,
             similarity_floor=None, outside_gap=None):
    """Score labels without treating unknown or unreviewed frames as truth."""
    counts = Counter()
    name_norm = [n.casefold().strip() for n in names]
    for vector, label in zip(scores, truth):
        if label is None or label in ("unknown", "uncertain"):
            continue
        prediction = decide(vector, candidates, confidence_floor=confidence_floor,
                            similarity_floor=similarity_floor, outside_gap=outside_gap)
        counts["n_evaluable"] += 1
        if prediction["accepted"]:
            key = "correct_tags" if label.casefold().strip() == name_norm[prediction["name_index"]] else "wrong_tags"
            counts[key] += 1
        else:
            counts["abstained"] += 1
            counts[f"abstain_{prediction['reason']}"] += 1
    return dict(counts)


def select_sample(rows, hard_ids, *, bird_count, no_bird_count, hard_count, seed):
    """Deterministic model-blind random controls plus a separate hard-case stratum."""
    rng = random.Random(seed)
    ordered = sorted(rows, key=lambda r: int(r["image_id"]))
    birds = [r for r in ordered if r["presence"] == "bird"]
    nonbirds = [r for r in ordered if r["presence"] == "no_bird"]
    if len(birds) < bird_count + hard_count or len(nonbirds) < no_bird_count:
        raise ValueError("requested sample exceeds available labelled frames")
    controls = rng.sample(birds, bird_count)
    used = {int(r["image_id"]) for r in controls}
    hard = [r for r in birds if int(r["image_id"]) in hard_ids and int(r["image_id"]) not in used]
    if len(hard) < hard_count:
        raise ValueError("too few unused hard cases")
    selected = ([(r, "random_bird") for r in controls] +
                [(r, "no_bird_control") for r in rng.sample(nonbirds, no_bird_count)] +
                [(r, "hard_bird") for r in rng.sample(hard, hard_count)])
    return sorted([{"image_id": int(r["image_id"]), "reason": reason,
                    "presence": r["presence"]} for r, reason in selected], key=lambda r: r["image_id"])


def _local_path(stored: str) -> Path:
    path = Path(stored)
    if path.is_file():
        return path
    prefix = "/mnt/d/Projects/image-scoring-pipeline/"
    if stored.startswith(prefix):
        return ROOT / stored[len(prefix):]
    return path


def _bbox(value):
    if not isinstance(value, dict):
        return None
    width, height = value.get("img_w"), value.get("img_h")
    if not width or not height:
        return None
    try:
        box = [float(value[k]) / (width if k.startswith("x") else height)
               for k in ("x1", "y1", "x2", "y2")]
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        return None
    return {"xyxy": box, "wh": [width, height]}


def freeze(out: Path) -> None:
    from modules import db

    if out.exists():
        raise ValueError("study directory already exists; choose a fresh --out")
    cohort = list(csv.DictReader((COHORT / "cohort.csv").open(encoding="utf-8", newline="")))
    labels = {int(r["image_id"]): r["label"] for r in
              csv.DictReader((COHORT / "labels.csv").open(encoding="utf-8", newline=""))}
    ids = sorted(int(r["image_id"]) for r in cohort)
    query = "SELECT id, thumbnail_path, bird_bbox FROM images WHERE id IN (" + ",".join("?" for _ in ids) + ")"
    database_rows = {int(r["id"]): r for r in db.get_connector().query(query, tuple(ids))}
    if len(database_rows) != len(ids):
        raise ValueError("cohort images missing from database")
    out.mkdir(parents=True)
    inputs = out / "inputs"
    inputs.mkdir()
    frozen = []
    for row in sorted(cohort, key=lambda r: int(r["image_id"])):
        image_id = int(row["image_id"])
        source = _local_path(database_rows[image_id]["thumbnail_path"])
        if not source.is_file():
            raise FileNotFoundError(f"thumbnail missing for image_id={image_id}")
        target = inputs / f"img_{image_id}.jpg"
        shutil.copyfile(source, target)
        frozen.append({"image_id": image_id, "stratum": row["stratum"],
                       "presence": "bird" if row["stratum"] == "eagle" else labels.get(image_id, "unknown"),
                       "input": target.name, "input_sha256": sha256(target),
                       "bbox": _bbox(database_rows[image_id]["bird_bbox"])})
    species = ROOT / "data/bird_species_list.txt"
    shutil.copyfile(species, out / "species.txt")
    write_json(out / "manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "cohort_sha256": sha256(COHORT / "cohort.csv"),
        "presence_labels_sha256": sha256(COHORT / "labels.csv"),
        "species_sha256": sha256(out / "species.txt"),
        "model_id": MODEL_ID,
        "model_input": "frozen 512px production thumbnails, oriented before preprocessing",
        "rows": frozen,
    })
    print(f"frozen {len(frozen)} images; {sum(r['bbox'] is not None for r in frozen)} stored boxes")


def _crop(image, bbox, padding=0.10):
    if bbox is None:
        return None
    width, height = image.size
    bw, bh = bbox["wh"]
    if (bw >= bh) != (width >= height):
        return None
    x1, y1, x2, y2 = bbox["xyxy"]
    dx, dy = (x2 - x1) * padding, (y2 - y1) * padding
    box = (max(0, round((x1 - dx) * width)), max(0, round((y1 - dy) * height)),
           min(width, round((x2 + dx) * width)), min(height, round((y2 + dy) * height)))
    return image.crop(box) if box[2] - box[0] >= 8 and box[3] - box[1] >= 8 else None


def infer(out: Path) -> None:
    import open_clip
    import torch
    from huggingface_hub import snapshot_download
    from PIL import Image, ImageOps

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    if (out / "scores.npz").exists():
        raise ValueError("scores already exist; preserve frozen study results")
    names = [line.strip() for line in (out / "species.txt").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    model_dir = Path(snapshot_download("imageomics/bioclip-2", local_files_only=True))
    model_file = model_dir / "open_clip_model.safetensors"
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_ID)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()
    tokenizer = open_clip.get_tokenizer(MODEL_ID)
    prompts = [f"a photo of {name}, a bird species" for name in names]
    with torch.no_grad():
        texts = []
        for start in range(0, len(prompts), 128):
            value = model.encode_text(tokenizer(prompts[start:start + 128]).to(device)).float()
            texts.append(value / value.norm(dim=-1, keepdim=True))
        text_features = torch.cat(texts)

    def score(image):
        with torch.no_grad():
            value = model.encode_image(preprocess(image).unsqueeze(0).to(device)).float()
            value /= value.norm(dim=-1, keepdim=True)
            return (value @ text_features.T)[0].cpu().numpy()

    full = np.empty((len(manifest["rows"]), len(names)), dtype=np.float32)
    cropped = np.full_like(full, np.nan)
    for index, row in enumerate(manifest["rows"]):
        path = out / "inputs" / row["input"]
        if sha256(path) != row["input_sha256"]:
            raise ValueError(f"frozen input changed for image_id={row['image_id']}")
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        full[index] = score(image)
        bird_crop = _crop(image, row["bbox"])
        if bird_crop is not None:
            cropped[index] = score(bird_crop)
        if (index + 1) % 25 == 0:
            print(f"scored {index + 1}/{len(manifest['rows'])}", flush=True)
    np.savez_compressed(out / "scores.npz", full=full, cropped=cropped)
    write_json(out / "inference.json", {
        "model_id": MODEL_ID, "model_revision": model_dir.name,
        "model_weights_sha256": sha256(model_file), "species_sha256": manifest["species_sha256"],
        "input_manifest_sha256": sha256(out / "manifest.json"), "scores_sha256": sha256(out / "scores.npz"),
        "open_clip_version": getattr(open_clip, "__version__", "unknown"),
        "torch_version": torch.__version__, "device": device,
        "preprocess": repr(preprocess), "n_images": len(manifest["rows"]),
        "n_crop_available": int(np.isfinite(cropped).all(axis=1).sum()),
    })
    print(f"scored {len(manifest['rows'])} images, {len(names)} names")


def sample(out: Path, *, seed: int, bird_count: int, no_bird_count: int, hard_count: int) -> None:
    from modules import db
    from modules.thumbnails import open_oriented_for_ml
    from PIL import Image

    if (out / "sample.json").exists():
        raise ValueError("sample already exists; preserve judge selection")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    data = np.load(out / "scores.npz")
    full, cropped = data["full"], data["cropped"]
    primary = np.where(np.isfinite(cropped), cropped, full)
    hard = set()
    for index, (row, broad, crop_score) in enumerate(zip(manifest["rows"], primary, cropped)):
        if row["presence"] != "bird":
            continue
        if decide(broad, range(len(broad)))["confidence"] < 0.5 or (
                np.isfinite(crop_score).all() and int(np.argmax(crop_score)) != int(np.argmax(full[index]))):
            hard.add(row["image_id"])
    selected = select_sample(manifest["rows"], hard, bird_count=bird_count,
                             no_bird_count=no_bird_count, hard_count=hard_count, seed=seed)
    ids = [r["image_id"] for r in selected]
    query = "SELECT id, file_path FROM images WHERE id IN (" + ",".join("?" for _ in ids) + ")"
    paths = {int(r["id"]): _local_path(r["file_path"]) for r in db.get_connector().query(query, tuple(ids))}
    row_by_id = {r["image_id"]: r for r in manifest["rows"]}
    judge_dir = out / "judge_images"
    judge_dir.mkdir()
    for item in selected:
        image_id = item["image_id"]
        if image_id not in paths or not paths[image_id].is_file():
            raise FileNotFoundError(f"source missing for image_id={image_id}")
        image = open_oriented_for_ml(str(paths[image_id]))
        crop = _crop(image, row_by_id[image_id]["bbox"], padding=0.35)
        if crop is not None:
            image = crop
        image.thumbnail((768, 768), Image.Resampling.LANCZOS)
        target = judge_dir / f"img_{image_id}.jpg"
        image.save(target, quality=90)
        item["judge_input_sha256"] = sha256(target)
        item["judge_crop"] = crop is not None
    write_json(out / "sample.json", {"seed": seed, "scores_sha256": sha256(out / "scores.npz"),
                                     "items": selected})
    print(f"selected {len(selected)} judge images; {len(hard)} hard-bird candidates")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "infer", "sample"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--bird-count", type=int, default=30)
    parser.add_argument("--no-bird-count", type=int, default=10)
    parser.add_argument("--hard-count", type=int, default=20)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.out)
    elif args.command == "infer":
        infer(args.out)
    else:
        sample(args.out, seed=args.seed, bird_count=args.bird_count,
               no_bird_count=args.no_bird_count, hard_count=args.hard_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
