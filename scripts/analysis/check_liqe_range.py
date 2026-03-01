#!/usr/bin/env python3
"""
Verify PyIQA LIQE model output range.
Run on a real image to confirm raw output is in 1-5 (not 0-1).
Usage: python scripts/analysis/check_liqe_range.py [image_path]
"""
import sys
import os
from pathlib import Path

# Add project root
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pyiqa

def main():
    metric = pyiqa.create_metric('liqe', device='cpu')
    print(f"LIQE metric attributes:")
    print(f"  score_range: {getattr(metric, 'score_range', 'Unknown')}")
    print(f"  lower_bound: {getattr(metric, 'lower_bound', 'Unknown')}")
    print(f"  upper_bound: {getattr(metric, 'upper_bound', 'Unknown')}")

    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        if os.path.exists(img_path):
            # Use LiqeScorer for consistent path handling (resize, etc.)
            try:
                from modules.liqe import LiqeScorer
                scorer = LiqeScorer()
                result = scorer.predict(img_path)
                score = result.get("score") if isinstance(result, dict) else result
            except Exception:
                score = metric(img_path)
                if hasattr(score, 'item'):
                    score = score.item()
            print(f"\nRaw output for {img_path}: {score}")
            if 1.0 <= score <= 5.0:
                print("  OK: Score in expected range 1-5")
            elif 0 <= score <= 1:
                print("  WARNING: Score in 0-1 range; normalization (score-1)/4 would be wrong!")
            else:
                print(f"  UNEXPECTED: Score outside 1-5 and 0-1")
        else:
            print(f"File not found: {img_path}")
    else:
        print("\nPass an image path to verify raw output on a real image.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
