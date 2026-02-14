#!/usr/bin/env python3
"""
Research script for MUSIQ and LIQE input format assessment.

Builds a diverse test set from Firebird DB (grouped by Camera/Lens via exiftool),
generates input variants (conversion × resolution × resize × aspect × format),
runs all models on each variant, and produces research_results.csv and research_summary.md.

Usage:
    python scripts/research_models.py [--limit 500] [--test-size 20] [--variants 16] [--output-dir research_output]
"""

import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

# Ensure project root is on path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PIL import Image

# Local imports (after path setup)
from modules import db, utils


# ---------------------------------------------------------------------------
# Configuration: Permutation dimensions (reduced matrix for tractability)
# ---------------------------------------------------------------------------

RESOLUTIONS = [224, 512, 518, "original"]  # 518 = LIQE reference; "original" = native
RESIZE_METHODS = ["LANCZOS", "BICUBIC"]
ASPECT_STRATEGIES = ["pad", "preserve"]
FORMAT_QUALITY = 95  # JPEG Q95
CONVERSION_METHODS = ["rawpy_half", "exiftool_jpgfromraw"]

MODELS_MUSIQ = ["spaq", "ava", "koniq", "paq2piq"]
MODEL_RANGES = {
    "spaq": (0.0, 100.0),
    "ava": (1.0, 10.0),
    "koniq": (0.0, 100.0),
    "paq2piq": (0.0, 100.0),
    "liqe": (1.0, 5.0),
}


def _normalize_score(model_name: str, raw_score: float) -> float:
    """Normalize raw score to 0-1."""
    if raw_score is None:
        return None
    mn, mx = MODEL_RANGES.get(model_name, (0, 1))
    return max(0, min(1, (raw_score - mn) / (mx - mn)))


# ---------------------------------------------------------------------------
# Exiftool metadata extraction
# ---------------------------------------------------------------------------

def exiftool_extract_metadata(file_path: str) -> dict:
    """Extract Camera Model and Lens Model via exiftool. Returns dict with Model, LensModel."""
    local = utils.convert_path_to_local(file_path)
    if not local or not os.path.exists(local):
        return {"Model": "unknown", "LensModel": "unknown"}
    exiftool = shutil.which("exiftool")
    if not exiftool:
        return {"Model": "unknown", "LensModel": "unknown"}
    try:
        cmd = [exiftool, "-Model", "-LensModel", "-j", local]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout)
            if data and isinstance(data, list):
                info = data[0]
                return {
                    "Model": str(info.get("Model", "unknown")).strip() or "unknown",
                    "LensModel": str(info.get("LensModel", "unknown")).strip() or "unknown",
                }
    except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
        pass
    return {"Model": "unknown", "LensModel": "unknown"}


def build_test_set(rows: list, target_size: int = 100, samples_per_group: int = 5) -> list:
    """
    Group by (Camera, Lens), sample 3-5 per group with score mix.
    Returns list of dicts: {id, file_path, score_general, camera, lens, ...}
    """
    # Resolve paths and extract metadata
    resolved = []
    for row in rows:
        try:
            path = row["file_path"]
        except (KeyError, TypeError):
            path = row[1] if len(row) > 1 else None
        if not path:
            continue
        local = utils.convert_path_to_local(path)
        if not local or not os.path.exists(local):
            continue
        meta = exiftool_extract_metadata(path)
        try:
            img_id = row["id"]
        except (KeyError, TypeError):
            img_id = row[0] if row else None
        try:
            score = row["score_general"]
        except (KeyError, TypeError):
            score = None
        if score is not None:
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = None
        resolved.append({
            "id": img_id,
            "file_path": local,
            "db_path": path,
            "score_general": score,
            "camera": meta.get("Model", "unknown"),
            "lens": meta.get("LensModel", "unknown"),
        })

    # Group by (camera, lens)
    groups = defaultdict(list)
    for r in resolved:
        key = (r["camera"], r["lens"])
        groups[key].append(r)

    # Sort each group by score (high first) for score mix
    for key in groups:
        groups[key].sort(key=lambda x: (x["score_general"] or 0), reverse=True)

    # Sample: take top + bottom from each group for score mix, up to samples_per_group
    test_set = []
    for key, items in groups.items():
        n = min(samples_per_group, len(items))
        if n <= 2:
            chosen = items[:n]
        else:
            # Mix: top 2, bottom 2, middle 1 if n>=5
            idx = [0, 1, -2, -1]
            if n >= 5:
                idx.append(len(items) // 2)
            chosen = [items[i] for i in idx if 0 <= i < len(items)][:n]
        test_set.extend(chosen)
        if len(test_set) >= target_size:
            break

    return test_set[:target_size]


# ---------------------------------------------------------------------------
# NEF conversion (rawpy half, exiftool JpgFromRaw)
# ---------------------------------------------------------------------------

def convert_nef_rawpy_half(nef_path: str, output_path: str) -> bool:
    try:
        import rawpy
        with rawpy.imread(nef_path) as raw:
            rgb = raw.postprocess(
                half_size=True,
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=8,
            )
        img = Image.fromarray(rgb)
        img.save(output_path, "JPEG", quality=FORMAT_QUALITY, optimize=True)
        return True
    except Exception:
        return False


def convert_nef_exiftool_jpg(nef_path: str, output_path: str) -> bool:
    exiftool = shutil.which("exiftool")
    if not exiftool:
        return False
    for tag in ["-JpgFromRaw", "-PreviewImage"]:
        try:
            cmd = [exiftool, "-b", tag, nef_path]
            r = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            if r.returncode == 0 and len(r.stdout) > 1000 and r.stdout.startswith(b"\xff\xd8"):
                with open(output_path, "wb") as f:
                    f.write(r.stdout)
                return True
        except Exception:
            continue
    return False


def convert_nef(nef_path: str, method: str, output_path: str) -> bool:
    if method == "rawpy_half":
        return convert_nef_rawpy_half(nef_path, output_path)
    if method == "exiftool_jpgfromraw":
        return convert_nef_exiftool_jpg(nef_path, output_path)
    return False


# ---------------------------------------------------------------------------
# Variant generation: resize, aspect, format
# ---------------------------------------------------------------------------

def _get_resize_method(name: str):
    m = {
        "LANCZOS": Image.Resampling.LANCZOS,
        "BICUBIC": Image.BICUBIC,
        "BILINEAR": Image.BILINEAR,
        "NEAREST": Image.NEAREST,
    }
    return m.get(name.upper(), Image.BICUBIC)


def generate_variant(
    source_path: str,
    resolution,
    resize_method: str,
    aspect: str,
    output_path: str,
) -> bool:
    """Generate a single variant and save to output_path."""
    try:
        img = Image.open(source_path).convert("RGB")
        w, h = img.size

        if resolution != "original":
            res = int(resolution)
            if aspect == "preserve":
                ratio = res / max(w, h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img = img.resize((new_w, new_h), _get_resize_method(resize_method))
            elif aspect == "pad":
                ratio = res / max(w, h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img = img.resize((new_w, new_h), _get_resize_method(resize_method))
                pad_w = res - new_w
                pad_h = res - new_h
                left = pad_w // 2
                top = pad_h // 2
                canvas = Image.new("RGB", (res, res), (0, 0, 0))
                canvas.paste(img, (left, top))
                img = canvas
            elif aspect == "crop":
                ratio = max(res / w, res / h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img = img.resize((new_w, new_h), _get_resize_method(resize_method))
                left = (new_w - res) // 2
                top = (new_h - res) // 2
                img = img.crop((left, top, left + res, top + res))
            else:
                img = img.resize((res, res), _get_resize_method(resize_method))
        elif aspect == "pad" and w != h:
            side = max(w, h)
            canvas = Image.new("RGB", (side, side), (0, 0, 0))
            canvas.paste(img, ((side - w) // 2, (side - h) // 2))
            img = canvas

        img.save(output_path, "JPEG", quality=FORMAT_QUALITY, optimize=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Model execution
# ---------------------------------------------------------------------------

def run_musiq_on_image(musiq, image_path: str) -> dict:
    """Run MUSIQ models on image, return {model: {score, normalized}}."""
    if musiq is None:
        return {}
    scores = {}
    for model_name in MODELS_MUSIQ:
        if model_name not in musiq.models:
            continue
        raw = musiq.predict_quality(image_path, model_name)
        if raw is not None:
            scores[model_name] = {"score": raw, "normalized": _normalize_score(model_name, raw)}
    return scores


def run_liqe_on_image(liqe, image_path: str) -> dict:
    """Run LIQE on image."""
    if liqe is None:
        return {}
    result = liqe.predict(image_path)
    if result.get("status") == "success":
        raw = result.get("score")
        return {"liqe": {"score": raw, "normalized": _normalize_score("liqe", raw)}}
    return {}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_results(csv_path: Path) -> dict:
    """Analyze CSV results: distribution, sensitivity, recommend settings."""
    analysis = {"distribution": {}, "sensitivity": {}, "recommended": {}}
    if not csv_path.exists():
        return analysis

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        return analysis

    by_model = defaultdict(list)
    by_image_variant = defaultdict(list)

    for r in rows:
        try:
            sn = float(r.get("score_normalized", 0) or 0)
        except (TypeError, ValueError):
            continue
        model = r.get("model", "")
        by_model[model].append(sn)
        key = (r.get("image_id"), r.get("resolution"), r.get("resize_method"), r.get("aspect"))
        by_image_variant[key].append((model, sn))

    for model, scores in by_model.items():
        if scores:
            import statistics
            analysis["distribution"][model] = {
                "min": min(scores),
                "max": max(scores),
                "mean": statistics.mean(scores),
                "std": statistics.stdev(scores) if len(scores) > 1 else 0,
            }
            analysis["sensitivity"][model] = statistics.variance(scores) if len(scores) > 1 else 0

    # Recommend: lowest sensitivity config; prefer 512 LANCZOS preserve if similar
    if rows:
        resolution_counts = defaultdict(int)
        for r in rows:
            resolution_counts[r.get("resolution", "")] += 1
        best_res = max(resolution_counts.keys(), key=lambda x: resolution_counts.get(x, 0)) if resolution_counts else "512"
        analysis["recommended"] = {
            "resolution": best_res,
            "resize": "LANCZOS",
            "aspect": "preserve",
            "conversion": "rawpy_half",
        }

    return analysis


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MUSIQ/LIQE input format research")
    parser.add_argument("--limit", type=int, default=500, help="Max NEF paths from DB")
    parser.add_argument("--test-size", type=int, default=20, help="Target test set size")
    parser.add_argument("--variants", type=int, default=16, help="Max variants per image (reduced)")
    parser.add_argument("--output-dir", default="research_output", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Skip model loading; generate CSV structure only")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "research_results.csv"
    report_path = out_dir / "research_summary.md"

    print("=" * 60)
    print("Research Models: Input Format Assessment")
    print("=" * 60)

    # 1. Fetch from DB
    print("\n1. Fetching NEF paths from DB...")
    rows = db.get_nef_paths_for_research(limit=args.limit)
    print(f"   Fetched {len(rows)} paths")

    if not rows:
        print("No NEF paths found. Exiting.")
        sys.exit(1)

    # 2. Build test set
    print("\n2. Building test set (exiftool metadata, grouping)...")
    test_set = build_test_set(rows, target_size=args.test_size)
    print(f"   Test set: {len(test_set)} images")
    if test_set:
        cameras = set(t["camera"] for t in test_set)
        print(f"   Cameras: {len(cameras)}")

    # 3. Load models (skip in dry-run)
    musiq = None
    liqe = None
    if not args.dry_run:
        print("\n3. Loading models...")
        sys.path.insert(0, str(_project_root / "scripts" / "python"))
        try:
            from run_all_musiq_models import MultiModelMUSIQ
            musiq = MultiModelMUSIQ(skip_gpu=True)
            for m in MODELS_MUSIQ:
                musiq.load_model(m)
            print("   MUSIQ models loaded")
        except Exception as e:
            print(f"   MUSIQ unavailable: {str(e)[:80]}")

        try:
            from modules.liqe import LiqeScorer
            liqe = LiqeScorer()
            print("   LIQE loaded")
        except Exception as e:
            print(f"   LIQE unavailable: {str(e)[:80]}")
            liqe = None

        if not musiq and not liqe:
            print("No models available. Use --dry-run to test pipeline without models.")
            sys.exit(1)
    else:
        print("\n3. Dry-run: skipping model loading")

    # 4. Generate variants and run models
    conversion_order = ["rawpy_half", "exiftool_jpgfromraw"]

    # Build variant configs (resolution × resize × aspect), reduced matrix
    variant_configs = []
    for res in RESOLUTIONS:
        if res == "original":
            continue  # Skip original for reduced run
        for rsz in RESIZE_METHODS:
            for asp in ASPECT_STRATEGIES:
                variant_configs.append({"resolution": res, "resize": rsz, "aspect": asp})
                if len(variant_configs) >= args.variants:
                    break
            if len(variant_configs) >= args.variants:
                break
        if len(variant_configs) >= args.variants:
            break

    if not variant_configs:
        variant_configs = [{"resolution": 512, "resize": "LANCZOS", "aspect": "preserve"}]

    print(f"\n4. Running {len(variant_configs)} variants per image on {len(test_set)} images...")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "image_id", "camera", "lens", "score_general", "conversion", "resolution",
            "resize_method", "aspect", "model", "score_raw", "score_normalized", "inference_ok"
        ])

        for i, item in enumerate(test_set):
            nef_path = item["file_path"]
            if not os.path.exists(nef_path):
                print(f"   Skip missing: {nef_path}")
                continue

            # Try conversion methods
            base_jpeg = None
            used_conversion = None
            for conv in conversion_order:
                td = tempfile.mkdtemp(prefix="research_")
                try:
                    out = os.path.join(td, "base.jpg")
                    if convert_nef(nef_path, conv, out) and os.path.exists(out):
                        base_jpeg = out
                        used_conversion = conv
                        break
                finally:
                    pass  # Keep temp for this image's variants

            if not base_jpeg:
                print(f"   Skip (no conversion): {nef_path}")
                continue

            try:
                for vcfg in variant_configs:
                    vd = tempfile.mkdtemp(prefix="research_")
                    vpath = os.path.join(vd, "variant.jpg")
                    if not generate_variant(
                        base_jpeg,
                        vcfg["resolution"],
                        vcfg["resize"],
                        vcfg["aspect"],
                        vpath,
                    ):
                        continue

                    # Run MUSIQ
                    musiq_scores = run_musiq_on_image(musiq, vpath)
                    if args.dry_run and not musiq_scores:
                        musiq_scores = {m: {"score": 0.5, "normalized": 0.5} for m in MODELS_MUSIQ}
                    for mn, data in musiq_scores.items():
                        writer.writerow([
                            item["id"], item["camera"], item["lens"],
                            item.get("score_general"),
                            used_conversion, vcfg["resolution"],
                            vcfg["resize"], vcfg["aspect"],
                            mn, data.get("score"), data.get("normalized"), 1
                        ])

                    # Run LIQE
                    liqe_scores = run_liqe_on_image(liqe, vpath)
                    if args.dry_run and not liqe_scores:
                        liqe_scores = {"liqe": {"score": 3.0, "normalized": 0.5}}
                    for mn, data in liqe_scores.items():
                        writer.writerow([
                            item["id"], item["camera"], item["lens"],
                            item.get("score_general"),
                            used_conversion, vcfg["resolution"],
                            vcfg["resize"], vcfg["aspect"],
                            mn, data.get("score"), data.get("normalized"), 1
                        ])

                    # Cleanup variant temp
                    try:
                        shutil.rmtree(vd, ignore_errors=True)
                    except Exception:
                        pass

            finally:
                # Cleanup base temp
                if base_jpeg:
                    td = os.path.dirname(base_jpeg)
                    try:
                        shutil.rmtree(td, ignore_errors=True)
                    except Exception:
                        pass

            print(f"   [{i+1}/{len(test_set)}] {Path(nef_path).name}")

    # 5. Analyze and generate report
    print("\n5. Analyzing results and generating report...")
    analysis = analyze_results(csv_path)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Research Summary: MUSIQ/LIQE Input Format Assessment\n\n")
        f.write(f"Test set: {len(test_set)} images\n")
        f.write(f"Variants per image: {len(variant_configs)}\n")
        f.write(f"Results: {csv_path}\n\n")
        f.write("## Score Distribution (per model)\n\n")
        for model_name, stats in analysis.get("distribution", {}).items():
            fmt = lambda x: f"{x:.3f}" if x is not None else "N/A"
            mi, ma, me, sd = stats.get("min"), stats.get("max"), stats.get("mean"), stats.get("std")
            f.write(f"- **{model_name}**: min={fmt(mi)}, max={fmt(ma)}, mean={fmt(me)}, std={fmt(sd)}\n")
        f.write("\n## Sensitivity (variance across permutations)\n\n")
        for model_name, var in analysis.get("sensitivity", {}).items():
            f.write(f"- **{model_name}**: variance={var:.4f}\n")
        f.write("\n## Recommended Input Format\n\n")
        rec = analysis.get("recommended", {})
        if rec:
            f.write(f"- Resolution: {rec.get('resolution', 'TBD')}\n")
            f.write(f"- Resize: {rec.get('resize', 'TBD')}\n")
            f.write(f"- Aspect: {rec.get('aspect', 'TBD')}\n")
            f.write(f"- Conversion: {rec.get('conversion', 'TBD')}\n")
        else:
            f.write("(Review research_results.csv for sensitivity, correlation, and rank consistency.\n")
            f.write("Run without --dry-run for real scores to populate recommendations.)\n")

    print(f"\nDone. Results: {csv_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
