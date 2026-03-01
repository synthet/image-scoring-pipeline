#!/usr/bin/env python3
"""
Verify that SPAQ, AVA, and LIQE models load and produce a score on a tiny input.
Used by setup_wsl_research_env.sh and for manual sanity checks.
"""
import os
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

def make_dummy_jpeg(path, size=224):
    from PIL import Image
    img = Image.new("RGB", (size, size), color=(128, 128, 128))
    img.save(path, "JPEG", quality=95)
    return path

def main():
    results = {}
    with tempfile.TemporaryDirectory(prefix="verify_") as td:
        dummy = os.path.join(td, "dummy.jpg")
        make_dummy_jpeg(dummy)

        # MUSIQ (SPAQ, AVA)
        try:
            sys.path.insert(0, str(project_root / "scripts" / "python"))
            from run_all_musiq_models import MultiModelMUSIQ
            musiq = MultiModelMUSIQ(skip_gpu=True)
            for m in ["spaq", "ava"]:
                if m in musiq.model_sources and musiq.model_sources[m].get("type") != "pyiqa":
                    ok = musiq.load_model(m)
                    if ok:
                        score = musiq.predict_quality(dummy, m)
                        results[m] = "OK" if score is not None else "predict failed"
                    else:
                        results[m] = "load failed"
        except Exception as e:
            results["musiq"] = str(e)[:80]

        # LIQE
        try:
            from modules.liqe import LiqeScorer
            liqe = LiqeScorer()
            if liqe.available:
                r = liqe.predict(dummy)
                results["liqe"] = "OK" if r.get("status") == "success" else r.get("error", "failed")
            else:
                results["liqe"] = "model not available"
        except Exception as e:
            results["liqe"] = str(e)[:80]

    for name, status in results.items():
        print(f"  {name}: {status}")
    ok_count = sum(1 for v in results.values() if v == "OK")
    if ok_count >= 2:
        print("Verification: at least 2 models OK")
        return 0
    print("Verification: not enough models OK")
    return 1

if __name__ == "__main__":
    sys.exit(main())
