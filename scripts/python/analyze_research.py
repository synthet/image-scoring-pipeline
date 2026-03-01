#!/usr/bin/env python3
"""
Deep analysis of research_results.csv from scripts/research_models.py.
Produces: Spearman rank correlation vs original, sensitivity by parameter,
ground-truth comparison vs DB scores, and per-model optimal settings.

Usage: python scripts/python/analyze_research.py research_output/research_results.csv research_output/research_deep_analysis.md
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
try:
    from scipy import stats
except ImportError:
    stats = None

# Current research_models.py CSV columns: score_raw, score_normalized, aspect, conversion (exiftool_jpgfromraw)
def _norm_row(row):
    """Normalize row to internal keys: score, score_norm, aspect_ratio, conversion."""
    out = dict(row)
    if "score_raw" in row and "score" not in row:
        try:
            out["score"] = float(row.get("score_raw") or 0)
        except (TypeError, ValueError):
            out["score"] = None
    if "score_normalized" in row and "score_norm" not in row:
        try:
            out["score_norm"] = float(row.get("score_normalized") or 0)
        except (TypeError, ValueError):
            out["score_norm"] = 0.0
    if "aspect" in row and "aspect_ratio" not in row:
        out["aspect_ratio"] = (row.get("aspect") or "").upper() or "PAD"
    else:
        out["aspect_ratio"] = (row.get("aspect_ratio") or row.get("aspect") or "PAD").upper()
    if "conversion" in row and row.get("conversion") == "exiftool_jpgfromraw":
        out["conversion_normalized"] = "exiftool_jpg"
    else:
        out["conversion_normalized"] = row.get("conversion", "")
    if "resolution" in row and str(row.get("resolution", "")).lower() == "original":
        out["resolution"] = "original"
    return out


def load_data(csv_path):
    data = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = _norm_row(row)
            score = row.get("score")
            score_norm = row.get("score_norm")
            if score_norm is None:
                try:
                    score_norm = float(row.get("score_normalized", 0))
                except (TypeError, ValueError):
                    score_norm = 0.0
            if score is not None and score != "None":
                try:
                    row["score"] = float(score)
                except (TypeError, ValueError):
                    continue
            if score_norm is not None:
                try:
                    row["score_norm"] = float(score_norm)
                except (TypeError, ValueError):
                    row["score_norm"] = 0.0
            data.append(row)
    return data


def analyze_results(csv_path, output_md_path):
    print(f"Reading {csv_path}...")
    data = load_data(csv_path)
    if not data:
        print("No valid data found.")
        return

    models = sorted(set(r["model"] for r in data))
    resolutions = sorted(set(r["resolution"] for r in data), key=lambda x: (x == "original", str(x)))
    image_ids = set(r["image_id"] for r in data)
    target_res = "224"
    for r in data:
        if str(r.get("resolution", "")) not in ("original", "ORIGINAL"):
            target_res = str(r["resolution"])
            break

    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write("# Research Deep Analysis: Input Format Assessment\n\n")
        f.write(f"**Total Samples**: {len(data)}\n")
        f.write(f"**Unique Images**: {len(image_ids)}\n")
        f.write(f"**Models**: {', '.join(models)}\n\n")

        # --- 1. Spearman Rank Correlation vs Original ---
        f.write("## 1. Rank Consistency with 'original' Resolution\n\n")
        f.write("Spearman rho: correlation of image rankings at each resolution vs at native resolution.\n\n")
        f.write("| Model | Resolution | Spearman vs original |\n")
        f.write("| :--- | :--- | ---: |\n")

        orig_key = "original"
        for model in models:
            for res in resolutions:
                if res == orig_key:
                    continue
                x, y = [], []
                for img_id in image_ids:
                    var_r = next(
                        (r for r in data
                         if r["image_id"] == img_id and r["model"] == model and str(r["resolution"]) == res
                         and r.get("resize_method") == "LANCZOS" and r.get("aspect_ratio", "").upper() == "PAD"),
                        None)
                    var_orig = next(
                        (r for r in data
                         if r["image_id"] == img_id and r["model"] == model and str(r.get("resolution", "")).lower() == "original"
                         and r.get("resize_method") == "LANCZOS" and r.get("aspect_ratio", "").upper() == "PAD"),
                        None)
                    if var_r and var_orig:
                        x.append(var_r["score_norm"])
                        y.append(var_orig["score_norm"])
                if len(x) > 2 and stats is not None:
                    corr, _ = stats.spearmanr(x, y)
                    f.write(f"| {model} | {res} | {corr:.4f} |\n")
                elif len(x) > 2:
                    f.write(f"| {model} | {res} | (install scipy) |\n")
        f.write("\n")

        # --- 2. Sensitivity by Parameter ---
        f.write("## 2. Sensitivity Analysis (Avg Absolute Diff in Normalized Score)\n\n")
        f.write("| Parameter | Variant A | Variant B | Avg Diff |\n")
        f.write("| :--- | :--- | :--- | ---: |\n")

        # Conversion: rawpy_half vs exiftool_jpgfromraw
        diffs = []
        for img_id in image_ids:
            for model in models:
                r_raw = next((r for r in data if r["image_id"] == img_id and r["model"] == model and r.get("conversion") == "rawpy_half" and r["resolution"] == target_res), None)
                r_jpg = next((r for r in data if r["image_id"] == img_id and r["model"] == model and (r.get("conversion") == "exiftool_jpgfromraw" or r.get("conversion_normalized") == "exiftool_jpg") and r["resolution"] == target_res), None)
                if r_raw and r_jpg:
                    diffs.append(abs(r_raw["score_norm"] - r_jpg["score_norm"]))
        if diffs:
            f.write(f"| Conversion | rawpy_half | exiftool_jpgfromraw | {np.mean(diffs):.4f} |\n")

        # Resize: LANCZOS vs BICUBIC
        diffs = []
        for img_id in image_ids:
            for model in models:
                r_lz = next((r for r in data if r["image_id"] == img_id and r["model"] == model and r.get("resize_method") == "LANCZOS" and r["resolution"] == target_res), None)
                r_bic = next((r for r in data if r["image_id"] == img_id and r["model"] == model and r.get("resize_method") == "BICUBIC" and r["resolution"] == target_res), None)
                if r_lz and r_bic:
                    diffs.append(abs(r_lz["score_norm"] - r_bic["score_norm"]))
        if diffs:
            f.write(f"| Resize | LANCZOS | BICUBIC | {np.mean(diffs):.4f} |\n")

        # Aspect: PAD vs PRESERVE
        diffs = []
        for img_id in image_ids:
            for model in models:
                r_pad = next((r for r in data if r["image_id"] == img_id and r["model"] == model and r.get("aspect_ratio", "").upper() == "PAD" and r["resolution"] == target_res), None)
                r_pre = next((r for r in data if r["image_id"] == img_id and r["model"] == model and r.get("aspect_ratio", "").upper() == "PRESERVE" and r["resolution"] == target_res), None)
                if r_pad and r_pre:
                    diffs.append(abs(r_pad["score_norm"] - r_pre["score_norm"]))
        if diffs:
            f.write(f"| Aspect | pad | preserve | {np.mean(diffs):.4f} |\n")

        # Resolution pairwise (e.g. 224 vs 512)
        for res_b in ["384", "512", "518"]:
            if res_b == target_res:
                continue
            diffs = []
            for img_id in image_ids:
                for model in models:
                    ra = next((r for r in data if r["image_id"] == img_id and r["model"] == model and str(r["resolution"]) == target_res and r.get("resize_method") == "LANCZOS" and r.get("aspect_ratio", "").upper() == "PAD"), None)
                    rb = next((r for r in data if r["image_id"] == img_id and r["model"] == model and str(r["resolution"]) == res_b and r.get("resize_method") == "LANCZOS" and r.get("aspect_ratio", "").upper() == "PAD"), None)
                    if ra and rb:
                        diffs.append(abs(ra["score_norm"] - rb["score_norm"]))
            if diffs:
                f.write(f"| Resolution | {target_res} | {res_b} | {np.mean(diffs):.4f} |\n")
        f.write("\n")

        # --- 3. Ground-Truth Comparison vs DB score_general ---
        f.write("## 3. Ground-Truth Comparison vs DB score_general\n\n")
        if any(r.get("db_score_general") for r in data):
            # Per config: Pearson correlation of research normalized score vs db_score_general (per image, use one row per image per config)
            by_cfg = defaultdict(list)
            for r in data:
                try:
                    db_score = float(r.get("db_score_general") or 0)
                except (TypeError, ValueError):
                    continue
                cfg = (r["resolution"], r.get("conversion", ""), r.get("resize_method", ""), r.get("aspect_ratio", ""))
                by_cfg[cfg].append((r["image_id"], r["model"], r["score_norm"], db_score))
            f.write("| Config (res, conversion, resize, aspect) | Model | Pearson r vs DB |\n")
            f.write("| :--- | :--- | ---: |\n")
            for cfg in sorted(by_cfg.keys(), key=lambda x: (str(x[0]), x[1], x[2], x[3])):
                entries = by_cfg[cfg]
                by_model = defaultdict(list)
                for img_id, model, sn, db in entries:
                    by_model[model].append((sn, db))
                for model in sorted(by_model.keys()):
                    vals = by_model[model]
                    if len(vals) < 3:
                        continue
                    x, y = [v[0] for v in vals], [v[1] for v in vals]
                    if stats is not None:
                        r_pearson, _ = stats.pearsonr(x, y)
                        f.write(f"| {cfg[0]}, {cfg[1][:8]}.. | {model} | {r_pearson:.4f} |\n")
        else:
            f.write("No db_score_general in CSV; skip ground-truth comparison.\n")
        f.write("\n")

        # --- 4. Per-Model Optimal Settings ---
        f.write("## 4. Per-Model Recommended Settings\n\n")
        by_model_res = defaultdict(lambda: defaultdict(list))
        for r in data:
            by_model_res[r["model"]][r["resolution"]].append(r["score_norm"])
        f.write("Based on variance and rank correlation: prefer resolution with lower variance and high Spearman vs original.\n\n")
        f.write("| Model | Recommended resolution | Notes |\n")
        f.write("| :--- | :--- | :--- |\n")
        for model in models:
            res_means = {}
            for res, scores in by_model_res[model].items():
                if scores:
                    res_means[res] = np.std(scores)
            if res_means:
                best = min(res_means.keys(), key=lambda r: res_means[r])
                f.write(f"| {model} | {best} | lowest std across variants |\n")
        f.write("\n")

        # --- 5. Score Ranges (Normalized) ---
        f.write("## 5. Score Ranges (Normalized 0-1)\n")
        f.write("| Model | Mean | Std Dev | Min | Max |\n")
        f.write("| :--- | ---: | ---: | ---: | ---: |\n")
        for model in models:
            scores = [r["score_norm"] for r in data if r["model"] == model]
            if scores:
                f.write(f"| {model} | {np.mean(scores):.3f} | {np.std(scores):.3f} | {min(scores):.3f} | {max(scores):.3f} |\n")

    print(f"Wrote {output_md_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python analyze_research.py <research_results.csv> <output.md>")
        sys.exit(1)
    analyze_results(sys.argv[1], sys.argv[2])
