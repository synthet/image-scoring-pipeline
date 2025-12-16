
import threading
import queue
import time
import os
import sys
import logging
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# Local imports
from modules import db, thumbnails
from scripts.python.run_all_musiq_models import MultiModelMUSIQ
from modules.liqe import LiqeScorer

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class ImageJob:
    image_path: str
    job_id: int
    skip_existing: bool = False
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    temp_files: List[str] = field(default_factory=list)
    retry_count: int = 0
    error: Optional[str] = None
    
    # Pre-calculated data
    is_raw: bool = False
    process_path: str = "" # Path to actual image to score (original or temp jpeg)
    external_scores: Dict[str, Any] = field(default_factory=dict)
    thumbnail_path: Optional[str] = None
    
class PipelineWorker(threading.Thread):
    def __init__(self, name, input_queue, output_queue, stop_event):
        super().__init__(name=name)
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.daemon = True

    def run(self):
        logger.info(f"{self.name} started.")
        while not self.stop_event.is_set():
            try:
                # Timeout allows checking stop_event periodically
                item = self.input_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None: # Sentinel
                if self.output_queue:
                    self.output_queue.put(None)
                break
            
            try:
                self.process(item)
            except Exception as e:
                logger.error(f"Error in {self.name}: {e}")
                traceback.print_exc()
                if isinstance(item, ImageJob):
                    item.status = "failed"
                    item.error = str(e)
                    # Pass it along to handle failure in DB/Cleanup
                    if self.output_queue:
                         self.output_queue.put(item)
            finally:
                self.input_queue.task_done()
        logger.info(f"{self.name} stopped.")

    def process(self, item):
        raise NotImplementedError

class PrepWorker(PipelineWorker):
    """
    Scans for existence, generates thumbnails, converts RAWs.
    """
    def __init__(self, input_queue, output_queue, stop_event, scorer_ref):
        super().__init__("PrepWorker", input_queue, output_queue, stop_event)
        self.scorer = scorer_ref # Reference to scorer class for static methods (is_raw, etc)
        
    def process(self, job: ImageJob):
        image_hash = None
        
        # Optimization: Check DB by Path first to avoid File I/O (Hash calculation)
        if job.skip_existing:
            try:
                # If we trust the path (User Request), reusing the hash from the DB is safe
                # This makes skipping near-instantaneous
                path_record = db.get_image_details(job.image_path)
                if path_record and path_record.get('image_hash'):
                     image_hash = path_record.get('image_hash')
                     job.external_scores["image_hash"] = image_hash
            except Exception as e:
                logger.error(f"Path lookup failed for {job.image_path}: {e}")

        # Compute Hash (New deduplication logic) - Only if not found by path
        try:
            from modules import utils
            if not image_hash:
                image_hash = utils.compute_file_hash(job.image_path)
                job.external_scores["image_hash"] = image_hash # Store for result
            
            if image_hash:
                # Check DB by Hash
                existing_record = db.get_image_by_hash(image_hash)
                if existing_record:
                    # Update Path if different (Portability)
                    db_path = existing_record.get('file_path')
                    image_id = existing_record.get('id')
                    
                    # Register this path as well
                    db.register_image_path(image_id, job.image_path)

                    if db_path != job.image_path:
                        logger.info(f"Relocating image {image_hash[:8]}... from {db_path} to {job.image_path}")
                        db.update_image_path(image_hash, job.image_path)
                    
                    # Skip Logic
                    if job.skip_existing:
                        # Check version/validity
                        current_ver = self.scorer.VERSION
                        db_ver = existing_record.get('model_version')
                        
                        # Smart Backfill Logic
                        # Check if ALL required scores are present
                        required_models = ['spaq', 'ava', 'koniq', 'paq2piq', 'liqe']
                        missing_models = []
                        valid_scores = {}
                        
                        for m in required_models:
                            key = f"score_{m}"
                            val = existing_record.get(key)
                            # Check if value is valid (non-zero)
                            if val and isinstance(val, (int, float)) and val > 0:
                                valid_scores[m] = {
                                    "score": val,
                                    "status": "success"
                                }
                            else:
                                missing_models.append(m)
                                
                        # Check Metadata presence (Rating/Label)
                        # User requirement: If rating or label is missing, we must NOT skip, 
                        # even if all scores are present.
                        has_rating = existing_record.get('rating') is not None and existing_record.get('rating') > 0
                        has_label = bool(existing_record.get('label'))
                        
                        # If everything is present AND version matches AND metadata exists, then skip
                        if not missing_models and db_ver == current_ver and has_rating and has_label:
                             job.status = "skipped"
                             self.output_queue.put(job)
                             return
                        
                        # If we have some valid scores but missing others (or missing metadata), 
                        # proceed but backfill valid scores to avoid re-calculation.
                        if valid_scores:
                             logger.info(f"Backfilling {job.image_path}: Missing models {missing_models}, Missing Meta: {not (has_rating and has_label)}. Reuse: {list(valid_scores.keys())}")
                             job.external_scores.update(valid_scores)

        except Exception as e:
            logger.error(f"Hashing failed for {job.image_path}: {e}")

        # 1. Check if should skip (Legacy Path Check - Fallback)
        if job.skip_existing and not image_hash:
             if db.image_exists(job.image_path, current_version=self.scorer.VERSION):
                 job.status = "skipped"
                 # Forward to ResultWorker to log/count skip, bypass Scoring
                 # But we need a way to bypass scoring queue.
                 # Actually, we can put it in ScoringQueue and have ScoringWorker skip it?
                 # Or better: Have a Router?
                 # Simplest: ScoringWorker checks status.
                 self.output_queue.put(job)
                 return

        # 2. Identify Type
        job.is_raw = self.scorer.is_raw_file(job.image_path)
        job.process_path = job.image_path
        
        # 3. Operations for processing
        try:
            # Generate Thumbnail (CPU bound but distinct from scoring)
            # We do this here to offload Scoring thread
            thumb = thumbnails.get_thumb_path(job.image_path)
            if not os.path.exists(thumb):
                # If RAW, we might need conversion anyway
                # But thumbnails.py handles RAW roughly
                generated = thumbnails.generate_thumbnail(job.image_path)
                if generated:
                    thumb = generated
            
            job.thumbnail_path = thumb

            # RAW Conversion for Scoring
            if job.is_raw:
                # We need a temp JPEG for scoring models (all expect standard image)
                # Use util from scorer class (static/instance method?)
                # We can create a lightweight instance or use static methods if refactored.
                # Currently convert_raw_to_jpeg is an instance method using self.temp_dir.
                # We should instantiate a temporary helper or use the shared one cautiously?
                # Thread safety issue if we use shared scorer instance for conversion concurrently impacting its state.
                # Solution: Create a localized helper or refactor scorer to have static conversion.
                # For now: New instance of scaler just for utils? No, heavy.
                # Let's assume we can use a fresh instance of helper logic or just call the method if its safe.
                # Looking at code: convert_raw_to_jpeg uses self.setup_temp_directory() and self.temp_files.
                # We should manage temp files in the Job object.
                
                # Custom conversion logic here to avoid sharing state
                temp_dir = job.image_path + "_temp_musiq" 
                # Actually, let's just make a temp dir
                import tempfile
                t_dir = tempfile.mkdtemp(prefix="musiq_prep_")
                job.temp_files.append(t_dir)
                
                # Create a specialized mini-instance for conversion? 
                # Or just manually call the logic.
                # To save time, we will create a dummy wrapper that mimics the necessary parts or 
                # just instantiate the class but NOT load models.
                converter = MultiModelMUSIQ(skip_gpu=True) 
                # The constructor loads nothing heavy, just dicts.
                converter.temp_dir = t_dir
                
                jpg = converter.convert_raw_to_jpeg(job.image_path)
                if jpg:
                    job.process_path = jpg
                    job.temp_files.append(jpg)
                else:
                    job.status = "failed"
                    job.error = "RAW Conversion Failed"
                    # Forward to result to log error
                    self.output_queue.put(job)
                    return

            # LIQE Score (CPU/PyTorch?)
            # LIQE is often lighter or CPU based in this repo logic?
            # actually logic was: if LIQE scorer available. 
            # If we want to parallelize LIQE (CPU) vs MUSIQ (GPU/TF), we can do it here.
            # But let's keep it simple for now and do LIQE in Scoring thread unless it bottlenecks.
            
            self.output_queue.put(job)
            
        except Exception as e:
            job.status = "failed"
            job.error = f"Prep failed: {str(e)}"
            self.output_queue.put(job)

class ScoringWorker(PipelineWorker):
    """
    Runs GPU Inference.
    """
    def __init__(self, input_queue, output_queue, stop_event, scorer_instance):
        super().__init__("ScoringWorker", input_queue, output_queue, stop_event)
        self.scorer = scorer_instance # The actual loaded heavy model
        self.liqe_scorer = LiqeScorer() # Keep LIQE loaded

        
    def process(self, job: ImageJob):
        if job.status in ["skipped", "failed"]:
            self.output_queue.put(job)
            return

        # Prepare external scores container
        external = job.external_scores if job.external_scores else {}
        
        # Check/Run LIQE if missing
        if "liqe" not in external:
            try:
                # Run LIQE
                # Ensure we have a process path
                path = job.process_path
                liqe_result = self.liqe_scorer.predict(path)
                external["liqe"] = liqe_result
            except Exception as e:
                logger.error(f"LIQE failed for {job.image_path}: {e}")
                external["liqe"] = {"status": "failed", "error": str(e)}

        try:
            # Run All Models
            # We assume scorer.run_all_models is thread safe if called serially by this single worker
            # (TF sessions can be tricky but single thread consumption is fine)
            
            # Clear Cache
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except: pass

            results = self.scorer.run_all_models(
                job.process_path, 
                external_scores=external, 
                logger=lambda x: None, # We don't want stdout spam, we'll log summary
                write_metadata=False # Handled in ResultWorker to avoid I/O blocking GPU
            )
            
            job.result = results
            
            # Post-check
            if results["summary"]["failed_predictions"] == results["summary"]["total_models"]:
                 job.status = "failed"
                 job.error = "All models failed"
            else:
                 job.status = "success"
                 
            self.output_queue.put(job)
            
        except Exception as e:
            job.status = "failed"
            job.error = f"Scoring failed: {str(e)}"
            self.output_queue.put(job)

class ResultWorker(PipelineWorker):
    """
    Upserts to DB, cleans up, logs.
    Also handles writing metadata to NEF files (I/O bound).
    """
    def __init__(self, input_queue, output_queue, stop_event, scorer_instance, progress_callback=None):
        super().__init__("ResultWorker", input_queue, output_queue, stop_event) # Output queue unused
        self.progress_callback = progress_callback # func(str) -> log
        self.scorer = scorer_instance
        
    def process(self, job: ImageJob):
        # 1. Handle Status
        if job.status == "skipped":
            if self.progress_callback:
                self.progress_callback(f"Skipped: {job.image_path}")
                
        elif job.status == "failed":
            if self.progress_callback:
                self.progress_callback(f"FAILED: {job.image_path} - {job.error}")
                
        elif job.status == "success":
            # Write Metadata (NEF) if applicable
            # Doing this here takes I/O off the GPU thread
            if self.scorer and job.is_raw and "weighted_scores" in job.result["summary"]:
                try:
                    # Calculate Rating/Label using scorer helpers
                    # Access logic strictly if we know scorer is loaded
                    # We reuse logic from run_all_musiq_models but externally
                    
                    # Reconstruct normalized_scores_dict for label calculation
                    normalized_scores_dict = {}
                    for m_name, m_res in job.result["models"].items():
                         if m_res.get("status") == "success":
                             normalized_scores_dict[m_name] = m_res.get("normalized_score", 0)
                    
                    avg_score = job.result["summary"]["weighted_scores"].get("general", 0)
                    
                    rating = self.scorer.score_to_rating(avg_score)
                    label = self.scorer.determine_lightroom_label(normalized_scores_dict)
                    
                    # Write to file
                    # Use original image path, not temp path
                    success = self.scorer.write_metadata_to_nef(job.image_path, rating, label)
                    
                    if success:
                        # CRITICAL FIX: Inject metadata into result for DB upsert
                        job.result["nef_metadata"] = {
                            "rating": rating,
                            "label": label
                        }
                        
                        if self.progress_callback:
                            # Maybe detailed log?
                            pass
                except Exception as e:
                    if self.progress_callback:
                        self.progress_callback(f"Metadata Write Failed: {e}")

            # Upsert
            try:
                # Add original path to result so DB knows
                job.result["image_path"] = job.image_path
                job.result["image_name"] = Path(job.image_path).name
                if "image_hash" in job.external_scores:
                    job.result["image_hash"] = job.external_scores["image_hash"]
                
                
                if job.thumbnail_path:
                    job.result["thumbnail_path"] = job.thumbnail_path
                
                db.upsert_image(job.job_id, job.result)
                
                score = job.result["summary"]["weighted_scores"].get("general", 0)
                if self.progress_callback:
                    self.progress_callback(f"Scored: {Path(job.image_path).name} - {score:.2f}")
            except Exception as e:
                if self.progress_callback:
                    self.progress_callback(f"DB Error: {e}")
        
        # 2. Cleanup
        for p in job.temp_files:
            try:
                # If directory
                if os.path.isdir(p):
                    import shutil
                    shutil.rmtree(p)
                else:
                    if os.path.exists(p):
                        os.remove(p)
            except: pass
