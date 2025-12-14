"""
Core scoring engine module.
Refactored from batch_process_images.py to support modular execution.
"""
import json
import os
import sys
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Callable, Optional

# Add project root to Python path if needed
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Handle import from scripts/python
try:
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ
except ImportError:
    # Fallback if scripts/python is in path
    try:
        from run_all_musiq_models import MultiModelMUSIQ
    except ImportError:
        # Add scripts/python to path and try again (last resort)
        sys.path.insert(0, str(project_root / "scripts" / "python"))
        from run_all_musiq_models import MultiModelMUSIQ

# Import LIQE Scorer
try:
    from modules.liqe import LiqeScorer
except ImportError:
    # Graceful fallback if module setup is still in flux
    LiqeScorer = None
    print("Warning: Could not import LiqeScorer from modules.liqe")

class BatchImageProcessor:
    """Batch process images with callback support and comprehensive logging."""
    
    def __init__(self, log_file: str = None, output_dir: str = None, 
                 skip_existing: bool = False, json_stdout: bool = False,
                 write_json: bool = True, skip_predicate: Callable[[str], bool] = None,
                 scorer: 'MultiModelMUSIQ' = None):
        self.json_stdout = json_stdout
        self.write_json = write_json
        self.skip_predicate = skip_predicate
        self.external_scorer = scorer
        
        if log_file is None:
            log_file = f"musiq_batch_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # If output_dir is provided and log_file is relative, put it in output_dir
        if output_dir and not os.path.isabs(log_file):
            log_file = os.path.join(output_dir, log_file)
        elif not os.path.isabs(log_file):
            log_file = os.path.abspath(log_file)
        
        self.log_file = log_file
        self.skip_existing = skip_existing
        self.processed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        # Print to console (stderr if streaming JSON mode)
        if self.json_stdout:
            print(log_entry, file=sys.stderr)
        else:
            print(log_entry)
        
        # Write to log file
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except:
            pass 

    def find_images(self, directory: str) -> List[str]:
        """Find all image files in the specified directory (including RAW files)."""
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.tif', '*.webp']
        raw_extensions = ['*.nef', '*.NEF', '*.nrw', '*.NRW', '*.cr2', '*.CR2', '*.cr3', '*.CR3', 
                         '*.arw', '*.ARW', '*.dng', '*.DNG', '*.orf', '*.ORF', '*.pef', '*.PEF', 
                         '*.raf', '*.RAF', '*.rw2', '*.RW2', '*.x3f', '*.X3F']
        all_extensions = image_extensions + raw_extensions
        
        image_files = []
        
        for ext in all_extensions:
            pattern = os.path.join(directory, ext)
            image_files.extend(glob.glob(pattern))
            pattern = os.path.join(directory, '**', ext)
            image_files.extend(glob.glob(pattern, recursive=True))
        
        return sorted(list(set(image_files)))
    
    def score_liqe_external(self, image_path: str) -> dict:
        """Run LIQE scoring via external script."""
        try:
            # Assume score_liqe.py is in scripts/python/ relative to project root
            # or in the same dir as the original script. 
            # We need to find it robustly.
            
            # Since this is now in modules/, we look in ../scripts/python/
            script_path = project_root / "scripts" / "python" / "score_liqe.py"
            
            if not script_path.exists():
                # Fallback to old location? Or just fail?
                self.log(f"LIQE script not found at {script_path}", "WARNING")
                return {"error": "LIQE script not found", "status": "failed"}

            cmd = [sys.executable, str(script_path), image_path, "--json"]
            
            import subprocess
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120) 
            
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    return data
                except json.JSONDecodeError:
                    self.log(f"LIQE JSON decode error. Output: {result.stdout[:100]}...", "WARNING")
                    return {"error": "Invalid JSON output from LIQE", "status": "failed"}
            else:
                self.log(f"LIQE script error: {result.stderr}", "WARNING")
                return {"error": f"LIQE script failed: {result.stderr}", "status": "failed"}
                
        except Exception as e:
            self.log(f"LIQE execution exception: {str(e)}", "ERROR")
            return {"error": str(e), "status": "failed"}

    def process_single_image(self, image_path: str, scorer: MultiModelMUSIQ, output_dir: str, liqe_scorer: LiqeScorer = None) -> dict:
        """Process a single image and return results."""
        try:
            self.log(f"Processing: {image_path}")
            
            # Check if likely already processed
            json_path = os.path.join(output_dir, f"{Path(image_path).stem}.json")
            should_skip = False
            skip_reason = ""
            
            # Logic: If we are writing JSONs, we check for JSON existence.
            # If NOT writing JSONs (DB mode), the CALLER likely handles skip checks 
            # (via DB query), or we blindly re-process.
            # But let's keep the file check if file exists.
            
            if self.skip_existing:
                 # Check predicate first (e.g. DB check)
                 if self.skip_predicate and self.skip_predicate(image_path):
                     should_skip = True
                     skip_reason = "already in database"
                 # Fallback to file check
                 elif os.path.exists(json_path):
                     should_skip = True
                     skip_reason = "existing result found (skipping version check)"
            elif scorer.is_already_processed(image_path, output_dir):
                 should_skip = True
                 skip_reason = f"already processed with version {scorer.VERSION}"
            
            if should_skip:
                self.log(f"Skipping {image_path} - {skip_reason}")
                
                # Attempt to load existing result to return it
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                        
                        summary = {
                            "image_path": image_path,
                            "image_name": Path(image_path).stem,
                            "json_path": json_path,
                            "status": "skipped",
                            "models_successful": existing_data.get("summary", {}).get("successful_predictions", 0),
                            "models_failed": existing_data.get("summary", {}).get("failed_predictions", 0),
                            "models_failed": existing_data.get("summary", {}).get("failed_predictions", 0),
                            "score": existing_data.get("summary", {}).get("weighted_scores", {}).get("general", 0),
                            "individual_scores": {},
                            "version": existing_data.get("version", "unknown")
                        }
                        
                        # Add individual model scores
                        if "models" in existing_data:
                            for model_name, model_result in existing_data["models"].items():
                                if isinstance(model_result, dict) and model_result.get("status") == "success":
                                    summary["individual_scores"][model_name] = {
                                        "score": model_result.get("score", 0),
                                        "normalized_score": model_result.get("normalized_score", 0)
                                    }
                        
                        self.log(f"Skipped: {image_path} - Version: {summary['version']} - Score: {summary.get('score', 'N/A')}")
                        return summary
                    except:
                        pass
                
                return {"image_path": image_path, "status": "skipped"}


            
            # --- LIQE ---
            liqe_score_data = None
            liqe_path = image_path
            if scorer.is_raw_file(image_path):
                temp_jpg = scorer.convert_raw_to_jpeg(image_path)
                if temp_jpg:
                    liqe_path = temp_jpg
                else:
                    self.log(f"Failed to convert RAW for LIQE: {image_path}", "WARNING")
                    liqe_score_data = {"error": "RAW conversion failed", "status": "failed"}

            if not liqe_score_data:
                if liqe_scorer and liqe_scorer.available:
                    liqe_score_data = liqe_scorer.predict(liqe_path)
                else:
                    # Fallback to external script if internal scorer not available?
                    # Or just fail since we are optimizing
                    liqe_score_data = self.score_liqe_external(liqe_path)
            
            # Run models
            external_scores = {}
            if liqe_score_data:
                external_scores['liqe'] = liqe_score_data
            
            # Clear PyTorch cache to free up VRAM for TensorFlow
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            
            results = scorer.run_all_models(image_path, external_scores=external_scores, logger=self.log)
            
            # Save results if enabled
            if self.write_json:
                image_name = Path(image_path).stem
                json_path = os.path.join(output_dir, f"{image_name}.json")
                scorer.save_results(results, json_path)
            
            # Also dump to stdout if requested
            if self.json_stdout:
                 print(json.dumps(results))
                 sys.stdout.flush()

            # Construct summary
            # Use 'general' weighted score as the primary score for logging/DB
            ws = results["summary"]["weighted_scores"]
            primary_score = ws["general"]
            
            summary = {
                "image_path": image_path,
                "image_name": Path(image_path).stem,
                "status": "success",
                "models_successful": results["summary"]["successful_predictions"],
                "models_failed": results["summary"]["failed_predictions"],
                "score": primary_score,
                "score_general": ws.get("general", 0),
                "score_technical": ws.get("technical", 0),
                "score_aesthetic": ws.get("aesthetic", 0),
                "individual_scores": {},
                "full_results": results # Include full results for callback
            }
            
            for model_name, model_result in results["models"].items():
                if model_result["status"] == "success":
                    summary["individual_scores"][model_name] = {
                        "score": model_result["score"],
                        "normalized_score": model_result["normalized_score"]
                    }
            
            self.log(f"Completed: {image_path} - General Score: {summary['score']}")
            return summary
            
        except Exception as e:
            error_msg = f"Failed to process {image_path}: {str(e)}"
            self.log(error_msg, "ERROR")
            return {
                "image_path": image_path,
                "image_name": Path(image_path).stem,
                "status": "failed",
                "error": str(e)
            }
    
    def process_directory(self, input_dir: str, output_dir: str = None, 
                          callback: Optional[Callable[[dict], None]] = None):
        """
        Process all images in a directory.
        Optionally call callback(result) for each processed image.
        """
        if output_dir is None:
            output_dir = input_dir
        
        os.makedirs(output_dir, exist_ok=True)
        
        self.log("=" * 80)
        self.log("BATCH PROCESSING STARTED")
        self.log("=" * 80)
        self.log(f"Input directory: {input_dir}")
        self.log(f"Output directory: {output_dir}")
        self.log(f"Log file: {self.log_file}")
        
        self.log("Scanning for images...")
        image_files = self.find_images(input_dir)
        
        if not image_files:
            self.log("No image files found.", "WARNING")
            return
        
        self.log(f"Found {len(image_files)} image files")
        
        if self.external_scorer:
            self.log("Using pre-loaded MUSIQ models.")
            scorer = self.external_scorer
        else:
            self.log("Initializing MUSIQ models (SPAQ, AVA, KONIQ, PAQ2PIQ)...")
            try:
                scorer = MultiModelMUSIQ()
                musiq_models = ['spaq', 'ava', 'koniq', 'paq2piq']
                load_results = {}
                for model_name in musiq_models:
                    load_results[model_name] = scorer.load_model(model_name)
                
                successful_loads = sum(1 for success in load_results.values() if success)
                self.log(f"Loaded {successful_loads}/{len(load_results)} models")
                
                if successful_loads == 0:
                    self.log("No models loaded. Aborting.", "ERROR")
                    return
                    
            except Exception as e:
                self.log(f"Failed to initialize models: {str(e)}", "ERROR")
                return
        
        self.log("Initializing LIQE model...")
        liqe_scorer = LiqeScorer()
        if not liqe_scorer.available:
            self.log("LIQE model failed to load or not available. Will fallback to script.", "WARNING")

        self.log("Starting image processing...")
        self.log("-" * 80)
        
        for i, image_path in enumerate(image_files, 1):
            if callback:
                # Optional Check for Abort via callback return? 
                # For now let's just assume void callback.
                pass

            self.log(f"Progress: {i}/{len(image_files)}")
            
            result = self.process_single_image(image_path, scorer, output_dir, liqe_scorer=liqe_scorer)
            self.results.append(result)
            
            if result["status"] == "success":
                self.processed_count += 1
            elif result["status"] == "skipped":
                self.skipped_count += 1
            else:
                self.failed_count += 1
            
            # Invoke Callback
            # Invoke Callback
            if callback:
                try:
                    callback(result)
                except InterruptedError:
                    self.log("Batch processing stopped by user.")
                    break
                except Exception as cb_err:
                    self.log(f"Callback error: {cb_err}", "ERROR")

            self.log("-" * 40)
        
        self.log("=" * 80)
        self.log("BATCH PROCESSING COMPLETED")
        self.log("=" * 80)
        
        self.log("Cleaning up temporary files...")
        scorer.cleanup_temp_files()
