import logging
import torch

try:
    import pyiqa
except ImportError:
    pyiqa = None

class MusiqScore:
    def __init__(self, device='cuda', weight_path=None):
        self.device = device if torch.cuda.is_available() else 'cpu'
        self.model = None
        self.metric_name = 'musiq' # Defaults to musiq-spaq in pyiqa usually, or we can be specific
        
        if not pyiqa:
            logging.warning("pyiqa not installed. MUSIQ (PyIQA) scoring will be disabled.")
            return

        try:
            self.model = pyiqa.create_metric(self.metric_name, device=self.device)
            logging.info(f"MUSIQ (PyIQA) model loaded on {self.device}")
        except Exception as e:
            logging.error(f"Failed to load MUSIQ (PyIQA) model: {e}")

    def predict(self, image_path):
        if not self.model:
            return 0.0
            
        try:
            with torch.no_grad():
                score = self.model(image_path)
                if isinstance(score, torch.Tensor):
                    return score.item()
                return float(score)
        except Exception as e:
            logging.error(f"Error scoring {image_path} with MUSIQ (PyIQA): {e}")
            return 0.0
