import logging
import torch

try:
    import pyiqa
except ImportError:
    pyiqa = None

class QAlignScore:
    def __init__(self, device='cuda', weight_path=None):
        self.device = device if torch.cuda.is_available() else 'cpu'
        self.model = None
        self.metric_name = 'qalign' 
        
        if not pyiqa:
            logging.warning("pyiqa not installed. Q-Align scoring will be disabled.")
            return

        try:
            # Create metric - pyiqa handles downloading weights automatically by default
            # akin to timm or torchvision
            self.model = pyiqa.create_metric(self.metric_name, device=self.device)
            logging.info(f"Q-Align model loaded on {self.device}")
        except Exception as e:
            logging.error(f"Failed to load Q-Align model: {e}")
            try:
                available = pyiqa.list_models()
                logging.info(f"Available pyiqa models: {available}")
            except Exception:
                logging.warning("Could not list pyiqa models")

    def predict(self, image_path):
        if not self.model:
            return 0.0
            
        try:
            # pyiqa models typically accept path or tensor
            # returns a tensor score, we want float
            
            # Clear cache before inference to free up fragmented memory
            if self.device != 'cpu':
                torch.cuda.empty_cache()
                
            with torch.no_grad():
                # Try half precision if on cuda to save memory
                # Note: pyiqa models might need explicit .half() call if not done in create_metric
                # But create_metric usually loads in float32. 
                # Let's keep it simple first: just run inference.
                
                score = self.model(image_path)
                
                if isinstance(score, torch.Tensor):
                    val = score.item()
                else:
                    val = float(score)
                    
            # Clear cache after inference
            if self.device != 'cpu':
                torch.cuda.empty_cache()
                
            return val
            
        except torch.cuda.OutOfMemoryError:
            logging.error(f"OOM Error scoring {image_path} with Q-Align. Clearing cache and retrying on CPU...")
            torch.cuda.empty_cache()
            try:
                # Fallback to CPU
                self.model = self.model.cpu()
                with torch.no_grad():
                    score = self.model(image_path)
                    if isinstance(score, torch.Tensor):
                        return score.item()
                    return float(score)
            except Exception as e:
                logging.error(f"Retry on CPU failed: {e}")
                return 0.0
                
        except Exception as e:
            logging.error(f"Error scoring {image_path} with Q-Align: {e}")
            return 0.0
