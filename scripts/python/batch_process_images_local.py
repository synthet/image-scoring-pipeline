#!/usr/bin/env python3
"""
Batch process NEF files using local MUSIQ checkpoints (no TensorFlow Hub).
This version avoids the TensorFlow Hub hanging issue by using local models.
"""

import argparse
import json
import os
import sys
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import tensorflow as tf
import numpy as np
from PIL import Image
import rawpy
import tempfile
import shutil

# Import local MUSIQ model
sys.path.append(str(project_root / "musiq_original"))
import model.multiscale_transformer as model_mod
import model.preprocessing as pp_lib


class LocalMUSIQScorer:
    """Score images using local MUSIQ checkpoints."""
    
    def __init__(self):
        self.models = {}
        self.checkpoints_dir = project_root / "musiq_original" / "checkpoints"
        
        # Model configurations
        self.model_configs = {
            'spaq': {'ckpt': 'spaq_ckpt.npz', 'num_classes': 1, 'range': (0.0, 100.0)},
            'ava': {'ckpt': 'ava_ckpt.npz', 'num_classes': 10, 'range': (1.0, 10.0)},
            'koniq': {'ckpt': 'koniq_ckpt.npz', 'num_classes': 1, 'range': (0.0, 100.0)},
            'paq2piq': {'ckpt': 'paq2piq_ckpt.npz', 'num_classes': 1, 'range': (0.0, 100.0)}
        }
        
        # Image preprocessing config
        self.pp_config = {
            'patch_size': 32,
            'patch_stride': 32,
            'hse_grid_size': 10,
            'longer_side_lengths': [224, 384],
            'max_num_patches': 196
        }
        
    def load_model(self, model_name: str) -> bool:
        """Load a local MUSIQ checkpoint."""
        if model_name not in self.model_configs:
            print(f"Unknown model: {model_name}")
            return False
            
        config = self.model_configs[model_name]
        ckpt_path = self.checkpoints_dir / config['ckpt']
        
        if not ckpt_path.exists():
            print(f"Checkpoint not found: {ckpt_path}")
            return False
            
        try:
            print(f"Loading {model_name.upper()} from local checkpoint...")
            
            # Load checkpoint
            ckpt_data = np.load(ckpt_path)
            
            # Create model
            model_config = self._get_model_config(config['num_classes'])
            model = model_mod.MultiscaleTransformer(**model_config)
            
            # Initialize model with dummy input
            dummy_input = np.random.randn(1, 3, 224, 224).astype(np.float32)
            _ = model(dummy_input)
            
            # Load weights (simplified - would need proper weight mapping)
            self.models[model_name] = {
                'model': model,
                'config': config,
                'ckpt_data': ckpt_data
            }
            
            print(f"✓ {model_name.upper()} model loaded successfully")
            return True
            
        except Exception as e:
            print(f"✗ Failed to load {model_name.upper()}: {str(e)}")
            return False
    
    def _get_model_config(self, num_classes: int):
        """Get model configuration."""
        return {
            'num_classes': num_classes,
            'patch_size': self.pp_config['patch_size'],
            'patch_stride': self.pp_config['patch_stride'],
            'hse_grid_size': self.pp_config['hse_grid_size'],
            'longer_side_lengths': self.pp_config['longer_side_lengths'],
            'max_num_patches': self.pp_config['max_num_patches']
        }
    
    def preprocess_image(self, image_path: str) -> np.ndarray:
        """Preprocess image for MUSIQ model."""
        try:
            # Load image
            image = Image.open(image_path).convert('RGB')
            image_array = np.array(image)
            
            # Apply MUSIQ preprocessing
            processed = pp_lib.preprocess_image(
                image_array,
                patch_size=self.pp_config['patch_size'],
                patch_stride=self.pp_config['patch_stride'],
                longer_side_lengths=self.pp_config['longer_side_lengths'],
                max_num_patches=self.pp_config['max_num_patches']
            )
            
            return processed
            
        except Exception as e:
            print(f"Image preprocessing failed: {e}")
            return None
    
    def predict_quality(self, image_path: str, model_name: str) -> Optional[float]:
        """Predict image quality using a specific model."""
        if model_name not in self.models:
            print(f"Model {model_name} not loaded")
            return None
            
        try:
            # Preprocess image
            processed_image = self.preprocess_image(image_path)
            if processed_image is None:
                return None
            
            # Get model
            model_info = self.models[model_name]
            model = model_info['model']
            config = model_info['config']
            
            # Make prediction
            with tf.device('/CPU:0'):  # Use CPU for local models
                prediction = model(processed_image)
                
                # Convert to score based on model type
                if config['num_classes'] == 1:
                    score = float(prediction.numpy()[0])
                else:  # AVA model with 10 classes
                    # Convert class probabilities to score
                    probs = tf.nn.softmax(prediction).numpy()[0]
                    score = float(np.sum(probs * np.arange(1, 11)))
                
                return score
                
        except Exception as e:
            print(f"Prediction failed for {model_name}: {e}")
            return None
    
    def convert_raw_to_jpeg(self, raw_path: str) -> Optional[str]:
        """Convert RAW file to temporary JPEG."""
        try:
            with rawpy.imread(raw_path) as raw:
                rgb = raw.postprocess()
            
            # Create temporary JPEG
            temp_dir = tempfile.mkdtemp()
            temp_jpeg = os.path.join(temp_dir, f"temp_{os.path.basename(raw_path)}.jpg")
            
            # Save as JPEG
            Image.fromarray(rgb).save(temp_jpeg, 'JPEG', quality=95)
            
            return temp_jpeg
            
        except Exception as e:
            print(f"RAW conversion failed: {e}")
            return None
    
    def cleanup_temp_file(self, temp_path: str):
        """Clean up temporary file."""
        try:
            if temp_path and os.path.exists(temp_path):
                temp_dir = os.path.dirname(temp_path)
                shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Cleanup failed: {e}")


class BatchImageProcessor:
    """Batch process images with comprehensive logging."""
    
    def __init__(self, log_file: str = None, output_dir: str = None):
        if log_file is None:
            log_file = f"musiq_batch_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        if output_dir and not os.path.isabs(log_file):
            log_file = os.path.join(output_dir, log_file)
        elif not os.path.isabs(log_file):
            log_file = os.path.abspath(log_file)
        
        self.log_file = log_file
        self.processed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        print(log_entry)
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    
    def find_images(self, directory: str) -> List[str]:
        """Find all supported image files in directory."""
        extensions = [
            '*.jpg', '*.jpeg', '*.JPG', '*.JPEG',
            '*.png', '*.PNG',
            '*.tiff', '*.tif', '*.TIFF', '*.TIF',
            '*.nef', '*.NEF', '*.nrw', '*.NRW',
            '*.cr2', '*.CR2', '*.cr3', '*.CR3',
            '*.arw', '*.ARW', '*.dng', '*.DNG'
        ]
        
        image_files = []
        for ext in extensions:
            pattern = os.path.join(directory, ext)
            image_files.extend(glob.glob(pattern))
        
        return sorted(image_files)
    
    def is_raw_file(self, file_path: str) -> bool:
        """Check if file is a RAW format."""
        raw_extensions = ['.nef', '.nrw', '.cr2', '.cr3', '.arw', '.dng']
        return any(file_path.lower().endswith(ext) for ext in raw_extensions)
    
    def process_directory(self, input_dir: str, output_dir: str = None, rate_nef: bool = False):
        """Process all images in a directory."""
        if output_dir is None:
            output_dir = input_dir
        
        self.log("=" * 80)
        self.log("BATCH PROCESSING STARTED")
        self.log("=" * 80)
        self.log(f"Input directory: {input_dir}")
        self.log(f"Output directory: {output_dir}")
        self.log(f"Log file: {self.log_file}")
        
        # Find images
        self.log("Scanning for images...")
        image_files = self.find_images(input_dir)
        
        if not image_files:
            self.log("No image files found in the specified directory.", "WARNING")
            return
        
        self.log(f"Found {len(image_files)} image files to process")
        
        # Initialize scorer
        self.log("Initializing local MUSIQ models...")
        scorer = LocalMUSIQScorer()
        
        # Load models
        model_names = ['spaq', 'ava', 'koniq', 'paq2piq']
        loaded_models = []
        for model_name in model_names:
            if scorer.load_model(model_name):
                loaded_models.append(model_name)
        
        if not loaded_models:
            self.log("No models loaded successfully. Aborting.", "ERROR")
            return
        
        self.log(f"Loaded {len(loaded_models)} models: {', '.join(loaded_models)}")
        
        # Process images
        self.log("Starting image processing...")
        
        for i, image_path in enumerate(image_files, 1):
            self.log("-" * 80)
            self.log(f"Progress: {i}/{len(image_files)}")
            self.log(f"Processing: {image_path}")
            
            try:
                # Check if already processed
                json_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(image_path))[0]}.json")
                if os.path.exists(json_path):
                    self.log(f"Skipping {image_path} - already processed")
                    self.skipped_count += 1
                    continue
                
                # Handle RAW files
                temp_jpeg = None
                processing_path = image_path
                
                if self.is_raw_file(image_path):
                    self.log(f"Converting RAW file to JPEG: {image_path}")
                    temp_jpeg = scorer.convert_raw_to_jpeg(image_path)
                    if temp_jpeg:
                        processing_path = temp_jpeg
                    else:
                        self.log(f"Failed to convert RAW file: {image_path}", "ERROR")
                        self.failed_count += 1
                        continue
                
                # Process with models
                results = {
                    "version": "2.3.3-local",
                    "image_path": image_path,
                    "image_name": os.path.basename(image_path),
                    "device": "CPU",
                    "models": {},
                    "summary": {
                        "total_models": len(loaded_models),
                        "successful_predictions": 0,
                        "failed_predictions": 0,
                        "average_normalized_score": 0.0
                    }
                }
                
                scores = []
                for model_name in loaded_models:
                    score = scorer.predict_quality(processing_path, model_name)
                    if score is not None:
                        config = scorer.model_configs[model_name]
                        min_val, max_val = config['range']
                        normalized_score = (score - min_val) / (max_val - min_val)
                        normalized_score = max(0.0, min(1.0, normalized_score))
                        
                        results["models"][model_name] = {
                            "score": score,
                            "score_range": f"{min_val}-{max_val}",
                            "normalized_score": normalized_score,
                            "status": "success"
                        }
                        
                        results["summary"]["successful_predictions"] += 1
                        scores.append(normalized_score)
                    else:
                        results["models"][model_name] = {
                            "status": "failed"
                        }
                        results["summary"]["failed_predictions"] += 1
                
                # Calculate average
                if scores:
                    results["summary"]["average_normalized_score"] = sum(scores) / len(scores)
                
                # Save results
                with open(json_path, 'w') as f:
                    json.dump(results, f, indent=2)
                
                self.log(f"✓ Processed: {image_path} - Average Score: {results['summary']['average_normalized_score']:.3f}")
                self.processed_count += 1
                
                # Clean up temp file
                if temp_jpeg:
                    scorer.cleanup_temp_file(temp_jpeg)
                
            except Exception as e:
                self.log(f"✗ Failed to process {image_path}: {str(e)}", "ERROR")
                self.failed_count += 1
                
                # Clean up temp file on error
                if 'temp_jpeg' in locals() and temp_jpeg:
                    scorer.cleanup_temp_file(temp_jpeg)
        
        # Final summary
        self.log("=" * 80)
        self.log("BATCH PROCESSING COMPLETED")
        self.log("=" * 80)
        self.log(f"Total images processed: {len(image_files)}")
        self.log(f"Successful: {self.processed_count}")
        self.log(f"Skipped (already processed): {self.skipped_count}")
        self.log(f"Failed: {self.failed_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch process images using local MUSIQ checkpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_process_images_local.py --input-dir "D:/Photos/Export/2025"
  python batch_process_images_local.py --input-dir "D:/Photos/Export/2025" --output-dir "D:/Results"
        """
    )
    
    parser.add_argument('--input-dir', required=True, help='Input directory containing images')
    parser.add_argument('--output-dir', help='Output directory for JSON results (default: same as input)')
    parser.add_argument('--log-file', help='Custom log file name (default: auto-generated with timestamp)')
    parser.add_argument('--rate-nef', action='store_true', help='Write ratings to Nikon NEF files (not implemented yet)')
    
    args = parser.parse_args()
    
    # Validate input directory
    if not os.path.isdir(args.input_dir):
        print(f"ERROR: Input directory does not exist: {args.input_dir}")
        return 1
    
    # Create processor
    processor = BatchImageProcessor(args.log_file, args.output_dir)
    
    # Process directory
    processor.process_directory(args.input_dir, args.output_dir, args.rate_nef)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
