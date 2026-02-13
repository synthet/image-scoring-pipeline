#!/usr/bin/env python3
"""
Research script to evaluate MUSIQ and LIQE model performance across different input permutations.
Examines:
- NEF Conversion Strategy (rawpy, exiftool)
- Resolution (224, 384, 512, Original)
- Resize Method (Lanczos, Bicubic, Nearest)
- Aspect Ratio Handling (Pad, Crop, Preserve)
- File Format (JPEG Q95, JPEG Q80, PNG)

Generates:
- research_results.csv
- research_summary.md
"""

import os
import sys
import json
import time
import csv
import random
import logging
import argparse
import subprocess
import shutil
import tempfile
import io
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from itertools import product

import numpy as np
from PIL import Image, ImageOps

# Add project root to sys.path
# This script is located at scripts/python/research_models.py
# Project root is ../../
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(project_root / "scripts" / "python") not in sys.path:
    sys.path.insert(0, str(project_root / "scripts" / "python"))

try:
    from run_all_musiq_models import MultiModelMUSIQ
except ImportError as e:
    print(f"Error: Could not import MultiModelMUSIQ from run_all_musiq_models.py: {e}")
    sys.exit(1)

try:
    from modules.liqe import LiqeScorer
except ImportError:
    print("Warning: LiqeScorer not found in modules.liqe, LIQE will be skipped.")
    LiqeScorer = None

try:
    from modules.db import get_db
except ImportError:
    print("Warning: modules.db not found. DB selection may fail.")
    get_db = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ResearchRunner:
    def __init__(self, output_dir: str, limit: int = 50, use_gpu: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.limit = limit
        self.use_gpu = use_gpu
        self.temp_dir = Path(tempfile.mkdtemp(prefix="research_models_"))
        
        # Initialize models
        logger.info("Initializing models...")
        self.musiq = MultiModelMUSIQ(skip_gpu=not use_gpu)
        self.musiq.load_all_models()
        
        self.liqe = None
        if LiqeScorer:
            try:
                self.liqe = LiqeScorer(device='cuda' if use_gpu and self.musiq.gpu_available else 'cpu')
                if not self.liqe.available:
                    self.liqe = None
            except Exception as e:
                logger.warning(f"Failed to init LIQE: {e}")

        # CSV Writer
        self.csv_path = self.output_dir / "research_results.csv"
        self.fieldnames = [
            'image_id', 'camera', 'lens', 'original_path',
            'conversion', 'resolution', 'resize_method', 'aspect_ratio', 'format',
            'model', 'score', 'score_norm', 'inference_time'
        ]
        
        # Initialize CSV if not exists
        if not self.csv_path.exists():
            with open(self.csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()

    def cleanup(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def get_test_set(self) -> List[Dict]:
        """Select diverse test set from DB."""
        cache_path = self.output_dir / "test_set_cache.json"
        
        # Try load cache
        if cache_path.exists():
            logger.info(f"Loading test set from cache: {cache_path}")
            with open(cache_path, 'r') as f:
                return json.load(f)
        
        if not get_db:
            logger.error("DB module missing, cannot select test set.")
            return []

        logger.info("Querying DB for NEF files...")
        conn = get_db()
        cursor = conn.cursor()
        
        # Fetch candidate paths
        cursor.execute("SELECT id, file_path FROM images WHERE file_path LIKE '%.nef' OR file_path LIKE '%.NEF'")
        candidates = cursor.fetchall()  # List of (id, path)
        logger.info(f"Found {len(candidates)} NEF candidates.")
        
        if not candidates:
            return []

        # Random sample to reduce ExifTool load
        sample_pool = random.sample(candidates, min(len(candidates), 500))
        
        grouped = defaultdict(list)
        
        logger.info(f"Extracting metadata for {len(sample_pool)} candidates...")
        count = 0
        for img_id, path_str in sample_pool:
            # Resolve path (Windows/WSL)
            resolved_path = self.resolve_path(path_str)
            if not resolved_path or not os.path.exists(resolved_path):
                continue
                
            cam, lens = self.get_exif_data(resolved_path)
            key = (cam, lens)
            grouped[key].append({
                'id': img_id,
                'path': resolved_path,
                'camera': cam,
                'lens': lens
            })
            count += 1
            if count % 50 == 0:
                print(f"  Processed {count}...")

        # Select diverse set
        final_set = []
        logger.info(f"Found {len(grouped)} distinct Camera/Lens combinations.")
        
        for key, items in grouped.items():
            # Take up to 5 per group
            selected = random.sample(items, min(len(items), 5))
            final_set.extend(selected)
            
            if len(final_set) >= self.limit:
                break
                
        logger.info(f"Selected {len(final_set)} test images.")
        
        # Save cache
        with open(cache_path, 'w') as f:
            json.dump(final_set, f, indent=2)
            
        return final_set

    def resolve_path(self, path_str: str) -> str:
        """Handle WSL/Windows path issues."""
        if os.path.exists(path_str):
            return path_str
        
        # D:/... -> /mnt/d/...
        if len(path_str) > 1 and path_str[1] == ':':
            drive = path_str[0].lower()
            rest = path_str[3:].replace('\\', '/')
            wsl_path = f"/mnt/{drive}/{rest}"
            if os.path.exists(wsl_path):
                return wsl_path
                
        return None

    def get_exif_data(self, path: str) -> Tuple[str, str]:
        try:
            cmd = ['exiftool', '-Model', '-LensModel', '-j', path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                data = json.loads(res.stdout)[0]
                return data.get('Model', 'Unknown'), data.get('LensModel', 'Unknown')
        except Exception:
            pass
        return 'Unknown', 'Unknown'

    def run(self):
        test_set = self.get_test_set()
        
        # Define Reduced Permutation Matrix
        resolutions = [(224, 224), (512, 512), (518, 518), 'ORIGINAL']
        resize_methods = [Image.LANCZOS, Image.BICUBIC]
        aspect_ratios = ['PAD', 'PRESERVE']
        formats = ['JPEG_Q95'] #, 'JPEG_Q80']
        conversions = ['rawpy_half', 'exiftool_jpg']
        
        total_variants = len(resolutions) * len(resize_methods) * len(aspect_ratios) * len(formats) * len(conversions)
        logger.info(f"Running {len(test_set)} images x ~{total_variants} variants each...")
        
        for idx, img_info in enumerate(test_set):
            logger.info(f"Processing image {idx+1}/{len(test_set)}: {Path(img_info['path']).name}")
            
            # 1. Generate Base Conversions (to avoid re-converting NEF for every variant)
            base_images = {} # method -> PIL Image key
            
            for conv_method in conversions:
                try:
                    pil_img = self.convert_nef(img_info['path'], conv_method)
                    if pil_img:
                        base_images[conv_method] = pil_img
                except Exception as e:
                    logger.error(f"Conversion {conv_method} failed for {img_info['path']}: {e}")

            # 2. Iterate Permutations
            for conv_method, pil_img in base_images.items():
                for res, method, aspect, fmt in product(resolutions, resize_methods, aspect_ratios, formats):
                    
                    variant_id = f"{conv_method}_{res}_{method}_{aspect}_{fmt}"
                    
                    # Generate Variant
                    try:
                        variant_path = self.generate_variant(pil_img, res, method, aspect, fmt)
                    except Exception as e:
                        logger.error(f"Variant generation failed {variant_id}: {e}")
                        continue
                        
                    # 3. Process with all models
                    self.score_variant(img_info, variant_path, 
                                     conversion=conv_method,
                                     resolution=str(res),
                                     resize_method=self._get_resize_name(method),
                                     aspect_ratio=aspect,
                                     fmt=fmt)
                    
                    # Cleanup variant file
                    if variant_path and os.path.exists(variant_path):
                        os.remove(variant_path)

    def convert_nef(self, nef_path: str, method: str) -> Image.Image:
        """Convert NEF file to PIL Image using specified method."""
        if method == 'rawpy_half':
            import rawpy
            with rawpy.imread(nef_path) as raw:
                rgb = raw.postprocess(half_size=True, use_camera_wb=True)
                return Image.fromarray(rgb)
                
        elif method == 'exiftool_jpg':
            # Extract embedded JPEG
            cmd = ['exiftool', '-b', '-JpgFromRaw', nef_path]
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            if res.returncode == 0 and res.stdout.startswith(b'\xff\xd8'):
                return Image.open(io.BytesIO(res.stdout)).convert('RGB')
            # Fallback to PreviewImage
            cmd = ['exiftool', '-b', '-PreviewImage', nef_path]
            res = subprocess.run(cmd, capture_output=True, timeout=10)
            if res.returncode == 0 and res.stdout.startswith(b'\xff\xd8'):
                 return Image.open(io.BytesIO(res.stdout)).convert('RGB')
            raise Exception("ExifTool extraction failed")
            
        return None

    def generate_variant(self, img: Image.Image, resolution, resize_method, aspect_ratio, fmt) -> str:
        """Process PIL image and save to temp file."""
        import io
        
        processed = img.copy()
        
        # Resize logic
        if resolution != 'ORIGINAL':
            target_w, target_h = resolution
            
            if aspect_ratio == 'PAD':
                processed = ImageOps.pad(processed, (target_w, target_h), method=resize_method, color=(0,0,0))
            elif aspect_ratio == 'CROP':
                processed = ImageOps.fit(processed, (target_w, target_h), method=resize_method)
            elif aspect_ratio == 'SQUISH':
                processed = processed.resize((target_w, target_h), resize_method)
            elif aspect_ratio == 'PRESERVE':
                processed.thumbnail((target_w, target_h), resize_method)
                
        # Save
        ext = '.png' if 'PNG' in fmt else '.jpg'
        out_path = self.temp_dir / f"variant_{random.randint(0,1000000)}{ext}"
        
        if 'JPEG' in fmt:
            quality = 95 if 'Q95' in fmt else 80
            processed.save(str(out_path), quality=quality)
        else:
            processed.save(str(out_path))
            
        return str(out_path)

    def score_variant(self, img_info, variant_path, conversion, resolution, resize_method, aspect_ratio, fmt):
        """Run models on variant and log results."""
        
        # MUSIQ Models
        for model_name in ['spaq', 'ava', 'koniq', 'paq2piq']:
            self._run_single_model(model_name, self.musiq, img_info, variant_path, 
                                 conversion, resolution, resize_method, aspect_ratio, fmt)
            
        # LIQE
        if self.liqe:
             self._run_single_model('liqe', self.liqe, img_info, variant_path,
                                  conversion, resolution, resize_method, aspect_ratio, fmt)

    def _run_single_model(self, model_name, scorer_obj, img_info, variant_path, 
                        conversion, resolution, resize_method, aspect_ratio, fmt):
        start_t = time.time()
        score = None
        score_norm = None
        
        try:
            if model_name == 'liqe':
                res = scorer_obj.predict(variant_path)
                if res.get('status') == 'success':
                    score = res['score']
                    # Normalize LIQE (1-5 -> 0-1)
                    score_norm = max(0.0, min(1.0, (score - 1.0) / 4.0))
            else:
                # MUSIQ
                score = scorer_obj.predict_quality(variant_path, model_name)
                if score is not None:
                    min_s, max_s = scorer_obj.model_ranges.get(model_name, (0, 100))
                    score_norm = (score - min_s) / (max_s - min_s)
                    
        except Exception as e:
            logger.error(f"Inference failed {model_name}: {e}")
            
        duration = time.time() - start_t
        
        # Log to CSV
        with open(self.csv_path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writerow({
                'image_id': img_info['id'],
                'camera': img_info['camera'],
                'lens': img_info['lens'],
                'original_path': img_info['path'],
                'conversion': conversion,
                'resolution': resolution,
                'resize_method': resize_method,
                'aspect_ratio': aspect_ratio,
                'format': fmt,
                'model': model_name,
                'score': score,
                'score_norm': score_norm,
                'inference_time': round(duration, 4)
            })

    def _get_resize_name(self, method):
        if method == Image.LANCZOS: return 'LANCZOS'
        if method == Image.BICUBIC: return 'BICUBIC'
        if method == Image.NEAREST: return 'NEAREST'
        return 'UNKNOWN'

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="research_output", help="Output directory")
    parser.add_argument("--limit", type=int, default=5, help="Number of test images")
    parser.add_argument("--cpu", action="store_true", help="Force CPU")
    args = parser.parse_args()
    
    runner = ResearchRunner(args.output, limit=args.limit, use_gpu=not args.cpu)
    try:
        runner.run()
    finally:
        runner.cleanup()
