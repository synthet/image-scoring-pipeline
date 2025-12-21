import os
import torch
import logging
import threading
import queue
from PIL import Image
from transformers import CLIPProcessor, CLIPModel, BlipProcessor, BlipForConditionalGeneration
from typing import List, Dict, Optional, Tuple
from modules import db, thumbnails

# Setup logging
logger = logging.getLogger(__name__)

class KeywordScorer:
    """
    Uses CLIP (Contrastive Language-Image Pre-Training) to tag images with keywords.
    """
    
    DEFAULT_KEYWORDS = [
        "landscape", "portrait", "urban", "cityscape", "nature", "wildlife", 
        "architecture", "macro", "street", "night", "black and white", 
        "sunset", "sunrise", "beach", "forest", "mountain", "water", 
        "flowers", "animals", "birds", "insect", "people", "abstract", "minimal",
        "aerial", "transportation"
    ]

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32", device: str = None):
        self.model_name = model_name
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        logger.info(f"KeywordScorer initialized. Device: {self.device}")

    def load_model(self):
        """Lazy load the model."""
        if self.model is None:
            try:
                logger.info(f"Loading CLIP model: {self.model_name}...")
                self.model = CLIPModel.from_pretrained(self.model_name).to(self.device)
                self.processor = CLIPProcessor.from_pretrained(self.model_name)
                logger.info("CLIP model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load CLIP model: {e}")
                raise

    def predict(self, image_path: str, keywords: List[str] = None, threshold: float = 0.2, top_k: int = 5) -> List[str]:
        """
        Predict keywords for an image using zero-shot classification.
        """
        self.load_model()
        
        target_keywords = keywords if keywords else self.DEFAULT_KEYWORDS
        prompts = [f"a photo of {k}" for k in target_keywords]
        
        try:
            image = Image.open(image_path)
            
            inputs = self.processor(text=prompts, images=image, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            logits_per_image = outputs.logits_per_image 
            probs = logits_per_image.softmax(dim=1) 
            
            probs_list = probs[0].tolist()
            
            valid_results = []
            for i, score in enumerate(probs_list):
                 valid_results.append((target_keywords[i], score))
            
            valid_results.sort(key=lambda x: x[1], reverse=True)
            final_keywords = [k for k, s in valid_results[:top_k]]
            
            return final_keywords
            
        except Exception as e:
            logger.error(f"Error processing {image_path}: {e}")
            return []


class CaptionGenerator:
    """
    Uses BLIP for image captioning.
    """
    def __init__(self, model_name: str = "Salesforce/blip-image-captioning-base", device: str = None):
        import torch
        self.model_name = model_name
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        logger.info(f"CaptionGenerator initialized. Device: {self.device}")

    def load_model(self):
        if self.model is None:
            try:
                logger.info(f"Loading BLIP model: {self.model_name}...")
                self.processor = BlipProcessor.from_pretrained(self.model_name)
                self.model = BlipForConditionalGeneration.from_pretrained(self.model_name).to(self.device)
                logger.info("BLIP model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load BLIP model: {e}")
                raise

    def generate(self, image_path: str) -> str:
        self.load_model()
        try:
            image = Image.open(image_path).convert('RGB')
            import torch
            inputs = self.processor(image, return_tensors="pt").to(self.device)
            context_tokens = self.model.generate(**inputs, max_new_tokens=50)
            caption = self.processor.decode(context_tokens[0], skip_special_tokens=True)
            return caption.capitalize()
        except Exception as e:
            logger.error(f"Caption generation failed for {image_path}: {e}")
            return ""

class TaggingRunner:
    """
    Runs tagging in a local thread, yielding logs.
    """
    def __init__(self):
        self.stop_event = threading.Event()
        self.scorer = None
        self.captioner = None
        
    def run_batch(self, input_path: str, custom_keywords: List[str] = None, overwrite: bool = False, generate_captions: bool = False):
        """
        Generator for tagging process.
        """
        # Convert Windows path to WSL path if running in WSL
        if ":" in input_path and input_path[1] == ":":
            drive = input_path[0].lower()
            path = input_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{path}"
            # Check if we are actually in WSL context (mnt exists)
            if os.path.exists("/mnt/"): 
                 if os.path.exists(wsl_path):
                     input_path = wsl_path
                     
        self.stop_event.clear()
        yield f"Starting Tagging process on {input_path}..."
        
        # Initialize Scorer
        if not self.scorer:
            try:
                yield "Loading CLIP model (this may take a while)..."
                self.scorer = KeywordScorer()
                self.scorer.load_model()
                yield "Model loaded."
            except Exception as e:
                yield f"Error loading model: {e}"
                return

        if generate_captions and not self.captioner:
            try:
                yield "Loading Captioning model (BLIP)..."
                self.captioner = CaptionGenerator()
                self.captioner.load_model()
                yield "Captioning model loaded."
            except Exception as e:
                yield f"Error loading captioning model: {e}"
                return

        yield "Scanning for images..."
        all_images = []
        
        # Fetch all images from DB (limit=-1 for no limit)
        # We need all potential candidates first if we are filtering by path, 
        # or just all of them if no path is provided.
        try:
            rows = db.get_all_images(limit=-1)
        except Exception as e:
            yield f"Error fetching from DB: {e}"
            return

        if not input_path or not input_path.strip():
             yield "Input path empty. Processing all images in DB..."
             all_images = [row for row in rows]
        elif os.path.isdir(input_path):
             import pathlib
             p_in = pathlib.Path(input_path).resolve()
             
             # Filter rows by path
             for row in rows:
                 f_path = pathlib.Path(row['file_path']).resolve()
                 # Check if file is inside input_path
                 try:
                     f_path.relative_to(p_in)
                     all_images.append(row)
                 except ValueError:
                     continue
        else:
            yield f"Input path not found or not a directory: {input_path}"
            return

        yield f"Found {len(all_images)} images to process."
        
        processed_count = 0
        skipped_count = 0
        
        for row in all_images:
            if self.stop_event.is_set():
                yield "Tagging stopped by user."
                break
                
            path = row['file_path']
            
            # Convert DB path to WSL path for processing if needed
            original_windows_path = path
            if ":" in path and path[1] == ":" and os.path.exists("/mnt/"):
                drive = path[0].lower()
                p = path[2:].replace("\\", "/")
                wsl_p = f"/mnt/{drive}{p}"
                path = wsl_p

            # Check overwrite
            
            # Check overwrite
            existing = row['keywords']
            if existing and not overwrite:
                skipped_count += 1
                continue
                
            if not os.path.exists(path):
                yield f"Skipping missing file: {path}"
                continue
                
            # Process
            yield f"Tagging: {os.path.basename(path)}..."
            
            # Determine inference path (use thumbnail for NEF/RAW)
            inference_path = path
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.nef', '.nrw', '.arw', '.cr2', '.cr3', '.dng']:
                 thumb_path = row['thumbnail_path']
                 
                 # Convert thumb path to WSL if needed
                 if thumb_path and ":" in thumb_path and thumb_path[1] == ":" and os.path.exists("/mnt/"):
                     drive_t = thumb_path[0].lower()
                     p_t = thumb_path[2:].replace("\\", "/")
                     thumb_path = f"/mnt/{drive_t}{p_t}"

                 if thumb_path and os.path.exists(thumb_path):
                     inference_path = thumb_path
                     # logger.debug(f"Using thumbnail for inference: {thumb_path}")
                 else:
                     yield f"  [Warning] No thumbnail found for RAW file, inference might fail: {os.path.basename(path)}"
            
            try:
                tags = self.scorer.predict(inference_path, keywords=custom_keywords)
                caption = ""
                title = ""
                
                if generate_captions:
                     caption = self.captioner.generate(inference_path)
                     import textwrap
                     title = textwrap.shorten(caption, width=50, placeholder="...")
                     
                if tags or caption:
                    tags_str = ",".join(tags)
                    # Update DB
                    conn = db.get_db()
                    c = conn.cursor()
                    
                    if caption:
                         c.execute("UPDATE images SET keywords = ?, title = ?, description = ? WHERE id = ?", 
                                   (tags_str, title, caption, row['id']))
                         yield f"  -> Caption: {caption}"
                    else:
                         c.execute("UPDATE images SET keywords = ? WHERE id = ?", (tags_str, row['id']))
                         
                    conn.commit()
                    conn.close()
                    yield f"  -> Tags: {tags_str}"
                    processed_count += 1
                    
                    # Write Metadata
                    if self.write_metadata(path, tags, title, caption):
                         yield "  -> Metadata written to file."
                    else:
                         yield "  -> Metadata write failed (check connection/permissions)."
                    
                else:
                    yield "  -> No tags found."
            except Exception as e:
                yield f"Request failed: {e}"
                
        yield f"Done. Processed: {processed_count}, Skipped: {skipped_count}"

    def write_metadata(self, image_path: str, keywords: List[str], title: str = "", description: str = "") -> bool:
        """
        Write keywords to image metadata (XMP/IPTC).
        """
        import subprocess
        
        # Try ExifTool (most robust for Keywords)
        try:
            # Flatten keywords
            # ExifTool expects: -CurrentIPTCDigest= -Subject={tag} -HierarchicalSubject={tag} ...
            # Actually -Subject="tag1, tag2" works or multiple -Subject args
            # Safest is -Subject and -Keywords and -XMP:Subject
            
            cmd = ['exiftool', '-overwrite_original', '-sep', ',']
            
            if keywords:
                kw_str = ",".join(keywords)
                cmd.append(f'-Subject={kw_str}')
                cmd.append(f'-Keywords={kw_str}')
                cmd.append(f'-XMP:Subject={kw_str}')

            if title:
                cmd.append(f'-Title={title}')
                cmd.append(f'-XMP:Title={title}')
                cmd.append(f'-XPTitle={title}')
                
            if description:
                cmd.append(f'-Description={description}')
                cmd.append(f'-ImageDescription={description}')
                cmd.append(f'-XMP:Description={description}')
                # XPComment matching Windows "Comments" often used for description too
                cmd.append(f'-XPComment={description}') 
                # Caption-Abstract for old IPTC
                cmd.append(f'-IPTC:Caption-Abstract={description}')
            # Hierarchical keywords often used by Lightroom
            # cmd.append(f'-HierarchicalSubject={kw_str}') 
            
            cmd.append(image_path)
            
            # Run
            # We assume 'exiftool' is in path (WSL or Windows)
            # If running in python in WSL, 'exiftool' checks WSL path.
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                return True
            else:
                logger.warning(f"Exiftool failed: {res.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Metadata write failed: {e}")
            return False
        
    def stop(self):
        self.stop_event.set()
