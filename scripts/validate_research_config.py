#!/usr/bin/env python3
"""
Re-score a subset of images with current config and compare to existing DB score_general.
Verifies that config changes (e.g. raw_conversion) preserve rank correlation.

Usage: python scripts/validate_research_config.py [--count 15]
"""
import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "scripts" / "python"))

from modules import db, utils

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=15, help="Number of images to re-score")
    args = parser.parse_args()

    rows = db.get_nef_paths_for_research(limit=args.count)
    if not rows:
        print("No NEF paths from DB.")
        return 1

    # Resolve paths and collect existing scores
    pairs = []
    for row in rows:
        try:
            path = row["file_path"]
        except (KeyError, TypeError):
            path = row[1] if len(row) > 1 else None
        try:
            score_old = row["score_general"]
            if score_old is not None:
                score_old = float(score_old)
        except (KeyError, TypeError):
            score_old = float(row[2]) if len(row) > 2 and row[2] is not None else None
        if not path or score_old is None:
            continue
        local = utils.convert_path_to_local(path)
        if local and __import__("os").path.exists(local):
            pairs.append((local, score_old))

    if len(pairs) < 3:
        print(f"Need at least 3 resolved images with scores, got {len(pairs)}")
        return 1

    # Load scorer (uses config for preprocess)
    try:
        from run_all_musiq_models import MultiModelMUSIQ
    except Exception as e:
        print(f"MultiModelMUSIQ: {e}")
        return 1
    try:
        from modules.liqe import LiqeScorer
        liqe = LiqeScorer()
    except Exception:
        liqe = None

    musiq = MultiModelMUSIQ(skip_gpu=True)
    for m in ["spaq", "ava"]:
        if m in musiq.model_sources and musiq.model_sources[m].get("type") != "pyiqa":
            musiq.load_model(m)

    old_scores = []
    new_scores = []
    for path, old in pairs:
        try:
            preprocessed = musiq.preprocess_image(path, output_dir=None)
            if not preprocessed:
                continue
            external = {}
            if liqe and liqe.available:
                r = liqe.predict(preprocessed)
                if r.get("status") == "success":
                    external["liqe"] = {"score": r["score"], "status": "success", "score_range": "1.0-5.0"}
                    mn, mx = 1.0, 5.0
                    external["liqe"]["normalized_score"] = max(0, min(1, (r["score"] - mn) / (mx - mn)))
            result = musiq.run_all_models(preprocessed, external_scores=external, logger=lambda x: None, write_metadata=False)
            ws = result.get("summary", {}).get("weighted_scores", {})
            gen = ws.get("general")
            if gen is not None:
                old_scores.append(old)
                new_scores.append(gen)
        except Exception as e:
            print(f"  Skip {path}: {e}")
            continue

    if len(old_scores) < 3:
        print(f"Only {len(old_scores)} successful re-scores, need 3+")
        return 1

    try:
        from scipy.stats import spearmanr
        rho, p = spearmanr(old_scores, new_scores)
        print(f"Re-scored {len(old_scores)} images. Spearman rho (old vs new): {rho:.4f} (p={p:.4f})")
        if rho >= 0.95:
            print("Rank correlation >= 0.95: config validation PASSED")
        else:
            print("Rank correlation < 0.95: consider reviewing config or running larger research.")
    except ImportError:
        print("scipy not installed; cannot compute Spearman. Install scipy and re-run.")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
