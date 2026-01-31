import logging
import torch

try:
    import pyiqa
except ImportError:
    pyiqa = None

class TopiqScore:
    def __init__(self, device='cuda', weight_path=None):
        self.device = device if torch.cuda.is_available() else 'cpu'
        self.model = None
        self.metric_name = 'topiq_iaa' 
        
        if not pyiqa:
            logging.warning("pyiqa not installed. TOPIQ scoring will be disabled.")
            return

        try:
            self.model = pyiqa.create_metric(self.metric_name, device=self.device)
            logging.info(f"TOPIQ-IAA model loaded on {self.device}")
        except Exception as e:
            logging.error(f"Failed to load TOPIQ-IAA model: {e}")

    def predict(self, image_path):
        if not self.model:
            return 0.0
            
        try:
            # Clear cache before inference
            if self.device != 'cpu':
                torch.cuda.empty_cache()

            with torch.no_grad():
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
            logging.error(f"OOM Error scoring {image_path} with TOPIQ. Retrying on CPU...")
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
            logging.error(f"Error scoring {image_path} with TOPIQ: {e}")
            return 0.0
