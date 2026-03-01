#!/usr/bin/env python3
"""
Research script for MUSIQ and LIQE input format assessment.

Builds a diverse test set from Firebird DB (grouped by Camera/Lens via exiftool),
generates input variants (conversion x resolution x resize x aspect),
runs all models on each variant, and produces research_results.csv + research_summary.md.

Usage (WSL or Windows):
    python scripts/research_models.py [--limit 500] [--test-size 20] [--output-dir research_output]
    python scripts/research_models.py --dry-run          # pipeline validation only
    python scripts/research_models.py --no-gpu           # force CPU inference
"""

import argparse
import csv
import io
import itertools
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from PIL import Image

from modules import db, utils

IS_WSL = platform.system() == "Linux"

# ---------------------------------------------------------------------------
# Configuration: Permutation dimensions
# ---------------------------------------------------------------------------

RESOLUTIONS = [224, 384, 512, 518, "original"]
RESIZE_METHODS = ["LANCZOS", "BICUBIC"]
ASPECT_STRATEGIES = ["preserve", "pad"]
FORMAT_QUALITY = 95
CONVERSION_METHODS = ["rawpy_half", "exiftool_jpgfromraw"]

MODEL_RANGES = {
    "spaq": (0.0, 100.0),
    "ava": (1.0, 10.0),
    "koniq": (0.0, 100.0),
    "paq2piq": (0.0, 100.0),
    "liqe": (1.0, 5.0),
}


def _normalize_score(model_name: str, raw_score: float) -> float:
    if raw_score is None:
        return None
    mn, mx = MODEL_RANGES.get(model_name, (0, 1))
    return max(0.0, min(1.0, (raw_score - mn) / (mx - mn)))


# ---------------------------------------------------------------------------
# Exiftool metadata extraction
# ---------------------------------------------------------------------------

def exiftool_extract_metadata(file_path: str) -> dict:
    """Extract Camera Model and Lens Model via exiftool."""
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
    Group images by (Camera, Lens), sample with score mix.
    Returns list of dicts with resolved local paths.
    """
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

    groups = defaultdict(list)
    for r in resolved:
        key = (r["camera"], r["lens"])
        groups[key].append(r)

    for key in groups:
        groups[key].sort(key=lambda x: (x["score_general"] or 0), reverse=True)

    test_set = []
    for key, items in groups.items():
        n = min(samples_per_group, len(items))
        if n <= 2:
            chosen = items[:n]
        else:
            idx = [0, 1, -2, -1]
            if n >= 5:
                idx.append(len(items) // 2)
            chosen = []
            seen = set()
            for i in idx:
                if 0 <= i < len(items) and i not in seen:
                    chosen.append(items[i])
                    seen.add(i)
                if len(chosen) >= n:
                    break
        test_set.extend(chosen)
        if len(test_set) >= target_size:
            break

    return test_set[:target_size]


# ---------------------------------------------------------------------------
# NEF conversion
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
    except Exception as e:
        print(f"      rawpy conversion failed: {str(e)[:60]}")
        return False


def convert_nef_exiftool_jpg(nef_path: str, output_path: str) -> bool:
    exiftool = shutil.which("exiftool")
    if not exiftool:
        print("      exiftool not found in PATH")
        return False
    for tag in ["-JpgFromRaw", "-PreviewImage"]:
        try:
            cmd = [exiftool, "-b", tag, nef_path]
            r = subprocess.run(cmd, capture_output=True, text=False, timeout=30)
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
# Variant generation
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
                canvas = Image.new("RGB", (res, res), (0, 0, 0))
                canvas.paste(img, ((res - new_w) // 2, (res - new_h) // 2))
                img = canvas
            else:
                img = img.resize((res, res), _get_resize_method(resize_method))
        elif aspect == "pad" and w != h:
            side = max(w, h)
            canvas = Image.new("RGB", (side, side), (0, 0, 0))
            canvas.paste(img, ((side - w) // 2, (side - h) // 2))
            img = canvas

        img.save(output_path, "JPEG", quality=FORMAT_QUALITY, optimize=True)
        return True
    except Exception as e:
        print(f"      variant failed: {str(e)[:60]}")
        return False


# ---------------------------------------------------------------------------
# Model execution
# ---------------------------------------------------------------------------

def run_musiq_on_image(musiq, image_path: str) -> dict:
    """Run available MUSIQ models on image. Returns {model: {score, normalized, time_ms}}."""
    if musiq is None:
        return {}
    scores = {}
    for model_name in list(musiq.models.keys()):
        try:
            t0 = time.perf_counter()
            raw = musiq.predict_quality(image_path, model_name)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if raw is not None:
                scores[model_name] = {
                    "score": raw,
                    "normalized": _normalize_score(model_name, raw),
                    "time_ms": round(elapsed_ms, 1),
                }
        except Exception as e:
            print(f"      MUSIQ/{model_name} failed: {str(e)[:60]}")
    return scores


def run_liqe_on_image(liqe, image_path: str) -> dict:
    """Run LIQE on image. Returns {liqe: {score, normalized, time_ms}}."""
    if liqe is None:
        return {}
    try:
        t0 = time.perf_counter()
        result = liqe.predict(image_path)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if result.get("status") == "success":
            raw = result.get("score")
            return {"liqe": {"score": raw, "normalized": _normalize_score("liqe", raw), "time_ms": round(elapsed_ms, 1)}}
    except Exception as e:
        print(f"      LIQE failed: {str(e)[:60]}")
    return {}


# ---------------------------------------------------------------------------
# Variant config generation (spread evenly across resolutions)
# ---------------------------------------------------------------------------

def build_variant_configs(max_variants: int) -> list:
    """
    Build variant configs spread evenly across resolutions via round-robin,
    so even a small max_variants covers all resolutions.
    """
    combos_per_res = list(itertools.product(RESIZE_METHODS, ASPECT_STRATEGIES))
    all_configs = []
    for res in RESOLUTIONS:
        for rsz, asp in combos_per_res:
            all_configs.append({"resolution": res, "resize": rsz, "aspect": asp})

    if len(all_configs) <= max_variants:
        return all_configs

    # Round-robin across resolutions
    by_res = defaultdict(list)
    for cfg in all_configs:
        by_res[cfg["resolution"]].append(cfg)

    selected = []
    iterators = {r: iter(cfgs) for r, cfgs in by_res.items()}
    while len(selected) < max_variants and iterators:
        exhausted = []
        for res in list(iterators.keys()):
            if len(selected) >= max_variants:
                break
            try:
                selected.append(next(iterators[res]))
            except StopIteration:
                exhausted.append(res)
        for r in exhausted:
            del iterators[r]

    return selected


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_results(csv_path: Path) -> dict:
    """Analyze CSV results: score distribution, sensitivity, recommendations, timing."""
    analysis = {"distribution": {}, "sensitivity": {}, "recommended": {}, "timing": {}}
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
    by_res_model = defaultdict(lambda: defaultdict(list))
    time_by_model = defaultdict(list)

    for r in rows:
        try:
            sn = float(r.get("score_normalized", 0) or 0)
        except (TypeError, ValueError):
            continue
        model = r.get("model", "")
        res = r.get("resolution", "")
        by_model[model].append(sn)
        by_res_model[res][model].append(sn)
        try:
            t = r.get("inference_time_ms")
            if t is not None and str(t).strip():
                time_by_model[model].append(float(t))
        except (TypeError, ValueError):
            pass

    for model, scores in by_model.items():
        if scores:
            analysis["distribution"][model] = {
                "count": len(scores),
                "min": min(scores),
                "max": max(scores),
                "mean": statistics.mean(scores),
                "std": statistics.stdev(scores) if len(scores) > 1 else 0,
            }
            analysis["sensitivity"][model] = (
                statistics.variance(scores) if len(scores) > 1 else 0
            )

    for model, times in time_by_model.items():
        if times:
            analysis["timing"][model] = {
                "count": len(times),
                "mean_ms": statistics.mean(times),
                "min_ms": min(times),
                "max_ms": max(times),
            }

    # Per-resolution breakdown (useful for choosing optimal resolution)
    analysis["by_resolution"] = {}
    for res, models in by_res_model.items():
        res_stats = {}
        for model, scores in models.items():
            if scores:
                res_stats[model] = {
                    "mean": statistics.mean(scores),
                    "std": statistics.stdev(scores) if len(scores) > 1 else 0,
                }
        analysis["by_resolution"][res] = res_stats

    # Recommend: find the resolution with the lowest average cross-model std dev
    best_res = "512"
    best_std = float("inf")
    for res, model_stats in analysis["by_resolution"].items():
        stds = [s["std"] for s in model_stats.values() if s.get("std") is not None]
        if stds:
            avg_std = statistics.mean(stds)
            if avg_std < best_std:
                best_std = avg_std
                best_res = res
    analysis["recommended"] = {
        "resolution": best_res,
        "resize": "LANCZOS",
        "aspect": "preserve",
        "conversion": "rawpy_half",
        "note": "Lowest cross-model variance",
    }

    return analysis


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MUSIQ/LIQE input format research")
    parser.add_argument("--limit", type=int, default=500, help="Max NEF paths from DB")
    parser.add_argument("--test-size", type=int, default=20, help="Target test set size")
    parser.add_argument("--max-variants", type=int, default=20,
                        help="Max variants per image (spread across resolutions)")
    parser.add_argument("--output-dir", default="research_output", help="Output directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip model loading; generate CSV structure with placeholder scores")
    parser.add_argument("--no-gpu", action="store_true",
                        help="Force CPU inference (default: auto-detect GPU)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "research_results.csv"
    report_path = out_dir / "research_summary.md"

    print("=" * 60)
    print("Research Models: Input Format Assessment")
    print(f"  Platform: {platform.system()} ({'WSL' if IS_WSL else 'native'})")
    print(f"  GPU: {'disabled by flag' if args.no_gpu else 'auto-detect'}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Fetch from DB
    # ------------------------------------------------------------------
    print("\n[1/5] Fetching NEF paths from DB...")
    rows = db.get_nef_paths_for_research(limit=args.limit)
    print(f"  Fetched {len(rows)} paths")

    if not rows:
        print("ERROR: No NEF paths found in database. Exiting.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Build test set
    # ------------------------------------------------------------------
    print("\n[2/5] Building test set (exiftool metadata, grouping)...")
    test_set = build_test_set(rows, target_size=args.test_size)
    print(f"  Test set: {len(test_set)} images")
    if test_set:
        cameras = set(t["camera"] for t in test_set)
        lenses = set(t["lens"] for t in test_set)
        print(f"  Cameras: {len(cameras)} | Lenses: {len(lenses)}")

    if not test_set:
        print("ERROR: Could not resolve any NEF files locally. Check paths.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 3. Load models
    # ------------------------------------------------------------------
    musiq = None
    liqe = None
    available_musiq_models = []

    if not args.dry_run:
        print("\n[3/5] Loading models...")
        sys.path.insert(0, str(_project_root / "scripts" / "python"))

        # MUSIQ (TensorFlow)
        try:
            from run_all_musiq_models import MultiModelMUSIQ
            musiq = MultiModelMUSIQ(skip_gpu=args.no_gpu)
            for m in musiq.model_sources:
                if musiq.model_sources[m].get("type") == "pyiqa":
                    continue
                ok = musiq.load_model(m)
                if ok:
                    available_musiq_models.append(m)
                    print(f"    Loaded MUSIQ/{m}")
                else:
                    print(f"    MUSIQ/{m}: load failed (skipped)")
            if not available_musiq_models:
                print("  WARNING: No MUSIQ models loaded")
                musiq = None
        except Exception as e:
            msg = repr(e).encode("ascii", errors="replace").decode("ascii")
            print(f"  MUSIQ unavailable: {msg[:150]}")

        # LIQE (PyTorch / PyIQA)
        try:
            from modules.liqe import LiqeScorer
            liqe = LiqeScorer()
            if liqe.available:
                print(f"    LIQE loaded on {liqe.device}")
            else:
                print("    LIQE: model not available (check pyiqa install)")
                liqe = None
        except Exception as e:
            msg = repr(e).encode("ascii", errors="replace").decode("ascii")
            print(f"  LIQE unavailable: {msg[:150]}")
            liqe = None

        if musiq is None and liqe is None:
            print("\nERROR: No models available. Use --dry-run to test pipeline.")
            sys.exit(1)

        model_list = available_musiq_models + (["liqe"] if liqe else [])
        print(f"  Active models: {model_list}")
    else:
        print("\n[3/5] Dry-run: skipping model loading")
        available_musiq_models = ["spaq", "ava"]

    # ------------------------------------------------------------------
    # 4. Generate variants and run models
    # ------------------------------------------------------------------
    variant_configs = build_variant_configs(args.max_variants)
    total_work = len(test_set) * len(CONVERSION_METHODS) * len(variant_configs)
    print(f"\n[4/5] Generating variants and scoring...")
    print(f"  {len(test_set)} images x {len(CONVERSION_METHODS)} conversions "
          f"x {len(variant_configs)} variants = {total_work} combinations")

    t_start = time.time()

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "image_id", "camera", "lens", "db_score_general",
            "conversion", "resolution", "resize_method", "aspect",
            "model", "score_raw", "score_normalized", "inference_ok", "inference_time_ms",
        ])

        for i, item in enumerate(test_set):
            nef_path = item["file_path"]
            if not os.path.exists(nef_path):
                print(f"  Skip missing: {nef_path}")
                continue

            # For each conversion method, generate a base JPEG
            for conv_method in CONVERSION_METHODS:
                td = tempfile.mkdtemp(prefix=f"research_{conv_method}_")
                base_jpeg = os.path.join(td, "base.jpg")
                try:
                    if not convert_nef(nef_path, conv_method, base_jpeg):
                        continue
                    if not os.path.exists(base_jpeg):
                        continue

                    for vcfg in variant_configs:
                        vd = tempfile.mkdtemp(prefix="research_v_")
                        vpath = os.path.join(vd, "variant.jpg")
                        try:
                            if not generate_variant(
                                base_jpeg,
                                vcfg["resolution"],
                                vcfg["resize"],
                                vcfg["aspect"],
                                vpath,
                            ):
                                continue

                            common = [
                                item["id"], item["camera"], item["lens"],
                                item.get("score_general"),
                                conv_method, vcfg["resolution"],
                                vcfg["resize"], vcfg["aspect"],
                            ]

                            # MUSIQ models
                            musiq_scores = run_musiq_on_image(musiq, vpath)
                            if args.dry_run and not musiq_scores:
                                musiq_scores = {
                                    m: {"score": 50.0, "normalized": 0.5, "time_ms": 0}
                                    for m in available_musiq_models
                                }
                            for mn, data in musiq_scores.items():
                                writer.writerow(
                                    common + [mn, data.get("score"),
                                              data.get("normalized"), 1,
                                              data.get("time_ms", "")]
                                )

                            # LIQE
                            liqe_scores = run_liqe_on_image(liqe, vpath)
                            if args.dry_run and not liqe_scores:
                                liqe_scores = {
                                    "liqe": {"score": 3.0, "normalized": 0.5, "time_ms": 0}
                                }
                            for mn, data in liqe_scores.items():
                                writer.writerow(
                                    common + [mn, data.get("score"),
                                              data.get("normalized"), 1,
                                              data.get("time_ms", "")]
                                )
                        finally:
                            shutil.rmtree(vd, ignore_errors=True)
                finally:
                    shutil.rmtree(td, ignore_errors=True)

            elapsed = time.time() - t_start
            print(f"  [{i+1}/{len(test_set)}] {Path(nef_path).name}  ({elapsed:.0f}s)")

    # ------------------------------------------------------------------
    # 5. Analyze and generate report
    # ------------------------------------------------------------------
    print("\n[5/5] Analyzing results and generating report...")
    analysis = analyze_results(csv_path)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Research Summary: MUSIQ/LIQE Input Format Assessment\n\n")
        f.write(f"- **Platform**: {platform.system()} ({'WSL' if IS_WSL else 'native'})\n")
        f.write(f"- **Test set**: {len(test_set)} images\n")
        f.write(f"- **Conversion methods**: {CONVERSION_METHODS}\n")
        f.write(f"- **Variants per image per conversion**: {len(variant_configs)}\n")
        f.write(f"- **Results CSV**: `{csv_path}`\n")
        if args.dry_run:
            f.write("- **Mode**: DRY-RUN (placeholder scores)\n")
        f.write("\n")

        f.write("## Score Distribution (per model, normalized 0-1)\n\n")
        f.write("| Model | Count | Min | Max | Mean | StdDev |\n")
        f.write("|-------|------:|----:|----:|-----:|-------:|\n")
        for model_name, stats in analysis.get("distribution", {}).items():
            fmt = lambda x: f"{x:.4f}" if x is not None else "N/A"
            f.write(
                f"| {model_name} | {stats.get('count', 0)} "
                f"| {fmt(stats.get('min'))} | {fmt(stats.get('max'))} "
                f"| {fmt(stats.get('mean'))} | {fmt(stats.get('std'))} |\n"
            )

        f.write("\n## Sensitivity (variance across all permutations)\n\n")
        for model_name, var in analysis.get("sensitivity", {}).items():
            f.write(f"- **{model_name}**: variance = {var:.6f}\n")

        timing = analysis.get("timing", {})
        if timing:
            f.write("\n## Inference timing (per model)\n\n")
            f.write("| Model | Count | Mean (ms) | Min | Max |\n")
            f.write("|-------|------:|---------:|---:|---:|\n")
            for model_name, st in timing.items():
                f.write(
                    f"| {model_name} | {st.get('count', 0)} "
                    f"| {st.get('mean_ms', 0):.1f} | {st.get('min_ms', 0):.1f} | {st.get('max_ms', 0):.1f} |\n"
                )

        f.write("\n## Per-Resolution Breakdown\n\n")
        for res, model_stats in analysis.get("by_resolution", {}).items():
            f.write(f"### Resolution: {res}\n\n")
            for model_name, st in model_stats.items():
                f.write(f"- {model_name}: mean={st['mean']:.4f}, std={st['std']:.4f}\n")
            f.write("\n")

        f.write("## Recommended Input Format\n\n")
        rec = analysis.get("recommended", {})
        if rec:
            f.write(f"- **Resolution**: {rec.get('resolution', 'TBD')}\n")
            f.write(f"- **Resize**: {rec.get('resize', 'TBD')}\n")
            f.write(f"- **Aspect**: {rec.get('aspect', 'TBD')}\n")
            f.write(f"- **Conversion**: {rec.get('conversion', 'TBD')}\n")
            f.write(f"- **Rationale**: {rec.get('note', '')}\n")
        else:
            f.write("Run without --dry-run for real scores to populate recommendations.\n")

    print(f"\nDone ({time.time() - t_start:.0f}s total).")
    print(f"  Results: {csv_path}")
    print(f"  Report:  {report_path}")


if __name__ == "__main__":
    main()
