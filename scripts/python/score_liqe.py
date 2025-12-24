
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
        import contextlib
        import io
        
        # Suppress "Loading pretrained model..." output
        with contextlib.redirect_stdout(io.StringIO()):
             # metric_mode='NR' (No Reference) is default for LIQE
             metric = pyiqa.create_metric('liqe', device=device)
             
        try:
            from PIL import Image
            from torchvision.transforms import functional as TF
            
            # Load and resize image if too large
            img = Image.open(image_path).convert('RGB')
            if max(img.size) > 518:
               ratio = 518 / max(img.size)
               new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
               img = img.resize(new_size, Image.BICUBIC)
            
            # Convert to tensor (0-1, BCHW)
            img_tensor = TF.to_tensor(img).unsqueeze(0).to(device)
            
            # Score
            score = metric(img_tensor).item()
        except Exception as img_err:
             # Fallback to direct path if PIL/Torchvision fails
             print(f"Warning: Resize failed, using original path. Error: {img_err}")
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
