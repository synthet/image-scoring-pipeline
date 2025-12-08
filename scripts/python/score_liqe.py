
import argparse
import sys
import torch
import json
import os
from pathlib import Path

# Add project root to path to ensure we can be called from anywhere
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def score_image_liqe(image_path, device='cuda'):
    """
    Score a single image using the LIQE model from pyiqa.
    Returns the raw score (0-1 range typically, but LIQE might differ).
    """
    try:
        import pyiqa
    except ImportError:
        print(json.dumps({"error": "pyiqa not installed", "status": "failed"}))
        return None

    try:
        # Check for CUDA
        if device == 'cuda' and not torch.cuda.is_available():
            # Fallback to CPU if requested CUDA but not available
            device = 'cpu'
            
        # Initialize LIQE metric
        # metric_mode='NR' (No Reference) is default for LIQE
        metric = pyiqa.create_metric('liqe', device=device)
        
        # Lower case metric name for consistency
        # pyiqa models usually take path or tensor
        score = metric(image_path).item()
        
        return {
            "score": score,
            "status": "success",
            "device": device
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "status": "failed"
        }

def main():
    parser = argparse.ArgumentParser(description="Score image with LIQE model")
    parser.add_argument("image_path", help="Path to the image file")
    parser.add_argument("--device", default="cuda", help="Device to use (cuda/cpu)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image_path):
        result = {"error": f"Image not found: {args.image_path}", "status": "failed"}
    else:
        result = score_image_liqe(args.image_path, args.device)
    
    if args.json:
        print(json.dumps(result))
    else:
        if result and result.get("status") == "success":
            print(f"LIQE Score: {result['score']:.4f}")
        else:
            print(f"Error: {result.get('error')}")

if __name__ == "__main__":
    main()
