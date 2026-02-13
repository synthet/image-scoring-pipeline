#!/usr/bin/env python3
import csv
import sys
import numpy as np
from collections import defaultdict
from pathlib import Path
from scipy import stats

def analyze_results(csv_path, output_md_path):
    print(f"Reading {csv_path}...")
    
    data = []
    try:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('score') and row.get('score') != 'None':
                    try:
                        row['score'] = float(row['score'])
                        row['score_norm'] = float(row['score_norm']) if row.get('score_norm') else 0.0
                        data.append(row)
                    except ValueError:
                        continue
    except FileNotFoundError:
        print(f"File not found: {csv_path}")
        return

    if not data:
        print("No valid data found.")
        return

    # 2. Aggregations per Config
    configs = defaultdict(list)
    
    for row in data:
        # Schema: conversion, resolution, resize_method, aspect_ratio
        cfg = (row['conversion'], row['resolution'], row['resize_method'], row['aspect_ratio'])
        configs[cfg].append(row)
        
    print(f"Found {len(configs)} unique configurations.")
    
    with open(output_md_path, 'w') as f:
        f.write("# Research Summary: Image Scoring Input Formats\n\n")
        f.write(f"**Total Samples**: {len(data)}\n")
        f.write(f"**Unique Images**: {len(set(r['image_id'] for r in data))}\n")
        f.write(f"**Configurations**: {len(configs)}\n\n")
        
        # --- Section 1: Ranking Consistency (Spearman) ---
        f.write("## 1. Rank Consistency with 'Original'\n")
        
        f.write("| Model | Resolution | Spearman vs Original |\n")
        f.write("| :--- | :--- | :--- |\n")
        
        models = set(r['model'] for r in data)
        resolutions = set(r['resolution'] for r in data if r['resolution'] != 'ORIGINAL')
        
        for model in sorted(models):
            for res in sorted(resolutions):
                x = []
                y = []
                for img_id in set(r['image_id'] for r in data):
                    # Compare variants. Reference: LANCZOS + PAD
                    # Resolution string in CSV is like "(224, 224)" or "ORIGINAL"
                    # We accept whatever is in the CSV.
                    
                    var_r = next((r for r in data 
                                  if r['image_id'] == img_id and r['model'] == model and r['resolution'] == res 
                                  and r['resize_method'] == 'LANCZOS' and r['aspect_ratio'] == 'PAD'), None)
                    
                    var_orig = next((r for r in data 
                                     if r['image_id'] == img_id and r['model'] == model and r['resolution'] == 'ORIGINAL'
                                     and r['resize_method'] == 'LANCZOS' and r['aspect_ratio'] == 'PAD'), None)
                                     
                    if var_r and var_orig:
                        x.append(var_r['score'])
                        y.append(var_orig['score'])
                
                if len(x) > 2:
                    corr, _ = stats.spearmanr(x, y)
                    f.write(f"| **{model}** | {res} | {corr:.4f} |\n")
        f.write("\n")

        # --- Section 2: Sensitivity to Pre-processing ---
        f.write("## 2. Sensitivity Analysis\n")
        
        f.write("| Parameter | Variant A | Variant B | Avg Diff (Norm Score) |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        
        # Compare Conversion: rawpy_half vs exiftool_jpg (at 224x224, LANCZOS, PAD)
        diffs = []
        target_res = '(224, 224)' # Default target resolution string
        # Check one record to see resolution format
        if data:
             # Just pick one that isn't ORIGINAL
             non_orig = next((r['resolution'] for r in data if r['resolution'] != 'ORIGINAL'), None)
             if non_orig: target_res = non_orig

        for img_id in set(r['image_id'] for r in data):
            for model in models:
                r_raw = next((r for r in data if r['image_id']==img_id and r['model']==model and r['conversion']=='rawpy_half' and r['resolution']==target_res), None)
                r_jpg = next((r for r in data if r['image_id']==img_id and r['model']==model and r['conversion']=='exiftool_jpg' and r['resolution']==target_res), None)
                if r_raw and r_jpg:
                    diffs.append(abs(r_raw['score_norm'] - r_jpg['score_norm']))
        
        if diffs:
            f.write(f"| Conversion | rawpy_half | exiftool_jpg | {np.mean(diffs):.4f} |\n")

        # Compare Resize: LANCZOS vs BICUBIC
        diffs = []
        for img_id in set(r['image_id'] for r in data):
            for model in models:
                r_lusz = next((r for r in data if r['image_id']==img_id and r['model']==model and r['resize_method']=='LANCZOS' and r['resolution']==target_res), None)
                r_bic = next((r for r in data if r['image_id']==img_id and r['model']==model and r['resize_method']=='BICUBIC' and r['resolution']==target_res), None)
                if r_lusz and r_bic:
                    diffs.append(abs(r_lusz['score_norm'] - r_bic['score_norm']))
        if diffs:
            f.write(f"| Resize | LANCZOS | BICUBIC | {np.mean(diffs):.4f} |\n")

        # Compare Aspect: PAD vs PRESERVE
        diffs = []
        for img_id in set(r['image_id'] for r in data):
            for model in models:
                r_pad = next((r for r in data if r['image_id']==img_id and r['model']==model and r['aspect_ratio']=='PAD' and r['resolution']==target_res), None)
                r_pre = next((r for r in data if r['image_id']==img_id and r['model']==model and r['aspect_ratio']=='PRESERVE' and r['resolution']==target_res), None)
                if r_pad and r_pre:
                    diffs.append(abs(r_pad['score_norm'] - r_pre['score_norm']))
        if diffs:
            f.write(f"| Aspect | PAD | PRESERVE | {np.mean(diffs):.4f} |\n")
            
        f.write("\n")
        
        # --- Section 3: Value Distribution ---
        f.write("## 3. Score Ranges (Normalized)\n")
        f.write("| Model | Mean | Std Dev | Min | Max |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for model in sorted(models):
            scores = [r['score_norm'] for r in data if r['model'] == model]
            if scores:
                f.write(f"| {model} | {np.mean(scores):.3f} | {np.std(scores):.3f} | {min(scores):.3f} | {max(scores):.3f} |\n")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        pass
    else:
        analyze_results(sys.argv[1], sys.argv[2])
