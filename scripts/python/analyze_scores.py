
import os
import sys
import json
import glob
import numpy as np
from typing import Dict, List
import argparse

def analyze_folder(folder_path: str):
    print(f"Analyzing JSON files in: {folder_path}")
    
    json_files = glob.glob(os.path.join(folder_path, "*.json"))
    print(f"Found {len(json_files)} JSON files")
    
    if not json_files:
        return
        
    # Data structure: {model_name: [scores...]}
    model_scores: Dict[str, List[float]] = {}
    filenames = []
    
    for jf in json_files:
        try:
            with open(jf, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Skip summary files
            if "batch_summary" in jf:
                continue
                
            if "models" not in data:
                continue
                
            filenames.append(os.path.basename(jf))
            
            for model, result in data["models"].items():
                if model not in model_scores:
                    model_scores[model] = []
                
                # Use normalized score
                if result.get("status") == "success":
                    model_scores[model].append(result.get("normalized_score", 0.0))
                else:
                    model_scores[model].append(None)
                    
        except Exception as e:
            print(f"Error reading {jf}: {e}")

    # Convert to numpy arrays for stats (filtering Nones)
    valid_models = []
    stats = {}
    
    print("\n--- Model Statistics (Normalized 0-1) ---")
    print(f"{'Model':<10} | {'Count':<5} | {'Mean':<6} | {'StdDev':<6} | {'Min':<6} | {'Max':<6}")
    print("-" * 60)
    
    clean_data = {} # For correlation: only images where ALL valid models have scores
    
    for model, scores in model_scores.items():
        valid_scores = [s for s in scores if s is not None]
        if not valid_scores:
            print(f"{model:<10} | 0     | N/A    | N/A    | N/A    | N/A")
            continue
            
        valid_models.append(model)
        mean = np.mean(valid_scores)
        std = np.std(valid_scores)
        min_v = np.min(valid_scores)
        max_v = np.max(valid_scores)
        
        stats[model] = {"mean": mean, "std": std}
        
        print(f"{model:<10} | {len(valid_scores):<5} | {mean:.4f} | {std:.4f} | {min_v:.4f} | {max_v:.4f}")

    # Prepare data for correlation (intersection of images)
    # Re-iterate to build a matrix where rows=images, cols=models
    # We need to make sure we align by index, so let's rebuild carefuly
    
    # Identify images that have scores for ALL valid models
    # (Exclude VILA if it has 0 scores)
    
    actually_valid_models = [m for m in valid_models if len([x for x in model_scores[m] if x is not None]) > 0]
    
    matrix_rows = []
    
    for i in range(len(filenames)):
        row = []
        complete = True
        for model in actually_valid_models:
            score = model_scores[model][i]
            if score is None:
                complete = False
                break
            row.append(score)
        
        if complete:
            matrix_rows.append(row)
            
    if not matrix_rows:
        print("\nNot enough common data for correlation analysis.")
        return

    matrix = np.array(matrix_rows)
    # Shape: (n_images, n_models)
    
    print("\n--- Correlation Matrix (Pearson) ---")
    # Header
    print(" " * 10 + "".join([f"{m:>10}" for m in actually_valid_models]))
    
    corr_matrix = np.corrcoef(matrix, rowvar=False)
    
    # If there's only one model, corrcoef returns a scalar
    if len(actually_valid_models) == 1:
        print(f"{actually_valid_models[0]:<10} 1.00")
    else:
        for i, model_row in enumerate(actually_valid_models):
            row_str = f"{model_row:<10}"
            for j in range(len(actually_valid_models)):
                row_str += f"{corr_matrix[i, j]:>10.2f}"
            print(row_str)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_folder(sys.argv[1])
    else:
        print("Usage: python analyze_scores.py <folder_path>")
