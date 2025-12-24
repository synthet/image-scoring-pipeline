import torch
import json
import os
import contextlib
import io
import sys
from PIL import Image

try:
    from torchvision.transforms import functional as TF
except ImportError:
    pass

class LiqeScorer:
    """
    Persistent LIQE scorer class to avoid re-loading model for every image.
    """
    def __init__(self, device='cuda'):
        self.device = device
        self.available = False
        self.metric = None
        
        # Check torch availability
        if not torch.cuda.is_available() and self.device == 'cuda':
            print("LIQE: CUDA not available, falling back to CPU")
            self.device = 'cpu'
            
        try:
            import pyiqa
            # Suppress "Loading pretrained model..." output
            with contextlib.redirect_stdout(io.StringIO()):
                self.metric = pyiqa.create_metric('liqe', device=self.device)
            self.available = True
            print(f"LIQE model loaded on {self.device}")
        except ImportError:
            print("LIQE: pyiqa not installed. Install with 'pip install pyiqa'")
        except Exception as e:
            print(f"LIQE: Failed to load model: {e}")

    def predict(self, image_path):
        """
        Score a single image.
        """
        if not self.available:
            return {"error": "Model not loaded", "status": "failed"}

        try:
             # Load and resize logic from original script
             # using PIL to ensure consistent loading
             img = Image.open(image_path).convert('RGB')
             
             # Resize if too large (LIQE optimization)
             if max(img.size) > 518:
                ratio = 518 / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.BICUBIC)
             
             # Convert to tensor
             # We assume torchvision is available if pyiqa is available (it's a dep)
             img_tensor = TF.to_tensor(img).unsqueeze(0).to(self.device)
             
             with torch.no_grad():
                 score = self.metric(img_tensor).item()
                 
             return {
                "score": score,
                "status": "success",
                "device": self.device,
                "score_range": "1.0-5.0"
            }
            
        except Exception as e:
            # Fallback for complex failures
            try:
                # Direct file path fallback if something went wrong with PIL/Tensor
                if self.metric:
                     with torch.no_grad():
                        score = self.metric(image_path).item()
                     return {
                        "score": score,
                        "status": "success",
                        "device": self.device,
                        "note": "fallback_path",
                        "score_range": "1.0-5.0"
                    }
            except:
                pass
                
            return {
                "error": str(e),
                "status": "failed"
            }
