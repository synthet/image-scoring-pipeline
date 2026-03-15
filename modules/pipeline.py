
import threading
import queue
import time
import os
import sys
import tempfile
import logging
from datetime import datetime
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# Local imports
from modules import db, thumbnails, xmp
from modules import score_normalization as snorm
from modules import config as app_config
from modules.phases import PhaseCode, PhaseStatus
from modules.phases_policy import explain_phase_run_decision
from modules.version import APP_VERSION
# Lazy imports — these pull in TensorFlow/PyTorch and are deferred to avoid
# slow top-level loads (and to let tests that don't need GPU models collect).
# Actual imports happen in ScoringWorker.__init__ where they are used.

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
    image_id: Optional[int] = None  # DB id, set when image is found/created
    target_phases: List[PhaseCode] = field(default_factory=list) # List of phases to execute in this job


def _is_phase_targeted(target_phases: List[Any], phase_code: PhaseCode) -> bool:
    """
    Return True when a phase should run for this job.

    Accepts mixed target phase representations (PhaseCode enums or strings).
    Empty/None target list means full pipeline behavior (all phases).
    """
    if not target_phases:
        return True

    normalized = set()
    for p in target_phases:
        if p is None:
            continue
        if isinstance(p, PhaseCode):
            normalized.add(p.value)
        else:
            normalized.add(str(p).strip().lower())
    return phase_code.value in normalized

    
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
        self._raw_converter = None  # Lazy-init; reused for RAW conversion to avoid per-image instantiation
        
    def process(self, job: ImageJob):
        try:
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
                         if path_record.get('id'):
                             job.image_id = path_record['id']
                except Exception as e:
                    logger.error(f"Path lookup failed for {job.image_path}: {e}")

            # --- PHASE A: INDEXING ---
            if _is_phase_targeted(job.target_phases, PhaseCode.INDEXING):
                # computed hash and registered path handled above in optimization block
                if not job.image_id and image_hash:
                     # If we didn't find it in the optimization block, do it now
                     existing = db.get_image_by_hash(image_hash)
                     if existing:
                         job.image_id = existing.get('id')
                         db.register_image_path(job.image_id, job.image_path)
                     else:
                         # Create new record (placeholder)
                         # Note: db.upsert_image handles creation, but for indexing phase 
                         # we might want a lighter way. However, upsert is currently the path.
                         # We'll rely on the result worker if we want to bundle, 
                         # but for INDEXING DONE status we need an ID.
                         pass

                if job.image_id:
                    db.set_image_phase_status(job.image_id, PhaseCode.INDEXING, PhaseStatus.DONE,
                                              app_version=APP_VERSION, job_id=job.job_id)

            # --- PHASE B: METADATA (Thumbs + EXIF/XMP) ---
            if _is_phase_targeted(job.target_phases, PhaseCode.METADATA):
                # 1. Image Identity (UUID)
                # Ensure we have a UUID for this image. If not in job, generate it.
                if not job.external_scores.get("image_uuid"):
                    # Extract minimal EXIF to help with deterministic UUID generation
                    from modules import exif_extractor
                    temp_exif = exif_extractor.extract_exif(job.image_path)
                    job.external_scores["image_uuid"] = db.generate_image_uuid(temp_exif)
                
                image_uuid = job.external_scores["image_uuid"]

                # 2. Physical Metadata Sync (EXIF + XMP)
                # Write UUID to original file's EXIF and to XMP sidecar if missing
                try:
                    from modules import exif_extractor
                    # Write to EXIF (Embedded) - This is required per user request
                    exif_extractor.ensure_image_unique_id(job.image_path, image_uuid)
                    
                    # Write to XMP (Sidecar) - Create if doesn't exist, and write UUID
                    # This fulfills "metadata step should create xmp (if doesn't exist)"
                    xmp.write_image_unique_id(job.image_path, image_uuid)
                    
                    # 3. Database Sync (IMAGE_EXIF + IMAGE_XMP)
                    if job.image_id:
                        exif_extractor.extract_and_upsert_exif(job.image_path, job.image_id)
                        xmp.extract_and_upsert_xmp(job.image_path, job.image_id)
                        
                        # Also update the main image record with the UUID if it wasn't there
                        db.update_image_uuid(job.image_id, image_uuid)
                except Exception as ex_meta:
                    logger.error("Physical metadata sync failed for %s: %s", job.image_path, ex_meta)

                # 4. Thumbnails creation (Final prep for scoring)
                thumb = thumbnails.get_thumb_path(job.image_path)
                if not os.path.exists(thumb):
                    generated = thumbnails.generate_thumbnail(job.image_path)
                    if generated:
                        thumb = generated
                job.thumbnail_path = thumb

                # 5. Update Status
                if job.image_id:
                    db.set_image_phase_status(job.image_id, PhaseCode.METADATA, PhaseStatus.DONE,
                                              app_version=APP_VERSION, job_id=job.job_id)

            # --- PHASE C: SCORING (Preparation) ---
            if _is_phase_targeted(job.target_phases, PhaseCode.SCORING):
                # Per-image rerun gate (symmetric with tagging/culling runners)
                if job.image_id:
                    decision = explain_phase_run_decision(
                        job.image_id,
                        PhaseCode.SCORING,
                        current_executor_version=self.scorer.VERSION if self.scorer else None,
                        force_run=False,
                    )
                    if not decision['should_run']:
                        job.status = "skipped"
                        self.output_queue.put(job)
                        return

                # Identify Type
                job.is_raw = self.scorer.is_raw_file(job.image_path) if self.scorer else False
                
                # RAW Conversion for Scoring
                if job.is_raw:
                    # Custom conversion logic here to avoid sharing state
                    t_dir = tempfile.mkdtemp(prefix="musiq_prep_")
                    job.temp_files.append(t_dir)
                    
                    if self._raw_converter is None:
                        from scripts.python.run_all_musiq_models import MultiModelMUSIQ
                        self._raw_converter = MultiModelMUSIQ(skip_gpu=True)
                    self._raw_converter.temp_dir = t_dir
                    
                    jpg = self._raw_converter.convert_raw_to_jpeg(job.image_path)
                    if jpg:
                        job.process_path = jpg
                        job.temp_files.append(jpg)
                    else:
                        job.status = "failed"
                        job.error = "RAW Conversion Failed"
                        self.output_queue.put(job)
                        return

                if job.image_id:
                    db.set_image_phase_status(
                        job.image_id,
                        PhaseCode.SCORING,
                        PhaseStatus.RUNNING,
                        app_version=APP_VERSION,
                        executor_version=self.scorer.VERSION if self.scorer else None,
                        job_id=job.job_id,
                    )

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
        from modules.liqe import LiqeScorer
        self.liqe_scorer = LiqeScorer() # Keep LIQE loaded

        
    def process(self, job: ImageJob):
        if job.status in ["skipped", "failed"]:
            self.output_queue.put(job)
            return

        # Operation-scoped pipeline runs can intentionally omit scoring.
        if not _is_phase_targeted(job.target_phases, PhaseCode.SCORING):
            job.status = "skipped"
            self.output_queue.put(job)
            return

        # Prepare external scores container
        external = job.external_scores if job.external_scores else {}
        
        # Preprocess using config (raw_conversion or scoring.model_preprocessing)
        try:
            temp_dir = tempfile.mkdtemp(prefix="score_512_")
            job.temp_files.append(temp_dir)
            cfg = app_config.load_config()
            model_prep = (cfg.get("scoring") or {}).get("model_preprocessing") or {}
            def get_res(key):
                v = model_prep.get(key)
                if isinstance(v, dict):
                    return v.get("resolution")
                return v
            liqe_res = get_res("liqe")
            musiq_res = get_res("spaq") or get_res("ava")
            # Single path: no per-model preprocessing or same resolution
            if not liqe_res and not musiq_res:
                path_512 = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir)
                if path_512:
                    job.process_path = path_512
            else:
                # Per-model: preprocess at LIQE resolution and at MUSIQ resolution
                res_liqe = int(liqe_res) if liqe_res is not None else None
                res_musiq = int(musiq_res) if musiq_res is not None else None
                if res_liqe is not None and res_musiq is not None and res_liqe != res_musiq:
                    path_liqe = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_liqe)
                    path_musiq = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_musiq)
                    if path_liqe and path_musiq:
                        job.process_path = path_musiq
                        job.external_scores["_liqe_preprocess_path"] = path_liqe
                elif res_liqe is not None:
                    path_liqe = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_liqe)
                    if path_liqe:
                        job.process_path = path_liqe
                        job.external_scores["_liqe_preprocess_path"] = path_liqe
                else:
                    path_512 = self.scorer.preprocess_image(job.process_path, output_dir=temp_dir, resolution_override=res_musiq)
                    if path_512:
                        job.process_path = path_512
        except Exception as e:
            logger.warning("Preprocess failed, using original path: %s", e)
        
        # Check/Run LIQE if missing
        if "liqe" not in external:
            try:
                path = external.get("_liqe_preprocess_path") or job.process_path
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
            except (ImportError, RuntimeError) as e:
                logger.warning("CUDA cache clear failed: %s", e)

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
    def __init__(self, input_queue, output_queue, stop_event, scorer_instance, progress_callback=None, item_finished_callback=None):
        super().__init__("ResultWorker", input_queue, output_queue, stop_event) # Output queue unused
        self.progress_callback = progress_callback # func(str) -> log
        self.item_finished_callback = item_finished_callback # func() -> void
        self.scorer = scorer_instance
        
    def process(self, job: ImageJob):
        # 1. Handle Status
        if job.status == "skipped":
            if self.progress_callback:
                self.progress_callback(f"Skipped: {job.image_path}")
            # Metadata cache removed from here as it's now in PrepWorker/Metadata phase

        elif job.status == "failed":
            if self.progress_callback:
                self.progress_callback(f"FAILED: {job.image_path} - {job.error}")
            if job.image_id:
                db.set_image_phase_status(
                    job.image_id,
                    PhaseCode.SCORING,
                    PhaseStatus.FAILED,
                    app_version=APP_VERSION,
                    executor_version=self.scorer.VERSION if self.scorer else None,
                    job_id=job.job_id,
                    error=job.error,
                )
                
        elif job.status == "success":
            # Write Metadata using unified XMP module
            # Doing this here takes I/O off the GPU thread
            if self.scorer and "weighted_scores" in job.result["summary"]:
                try:
                    normalized_scores_dict = {}
                    for m_name, m_res in job.result["models"].items():
                         if m_res.get("status") == "success":
                             normalized_scores_dict[m_name] = m_res.get("normalized_score", 0)

                    result_all = snorm.compute_all(normalized_scores_dict)
                    avg_score = result_all["general"]
                    rating = result_all["rating"]
                    label = result_all["label"]

                    job.result["summary"]["weighted_scores"] = {
                        "technical": result_all["technical"],
                        "aesthetic": result_all["aesthetic"],
                        "general": result_all["general"],
                    }
                    
                    # Use unified XMP module for consistent metadata handling
                    # Write XMP sidecar (non-destructive) for all images
                    success = xmp.write_metadata_unified(
                        image_path=job.image_path,
                        rating=rating,
                        label=label,
                        use_sidecar=True,  # Always create XMP sidecar
                        use_embedded=job.is_raw  # Only write embedded for RAW files
                    )
                    
                    if success:
                        # Inject metadata into result for DB upsert
                        job.result["nef_metadata"] = {
                            "rating": rating,
                            "label": label
                        }
                        
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
                
                # Resolve image_id for phase tracking (may have been created by upsert)
                if not job.image_id:
                    try:
                        img_rec = db.get_image_details(job.image_path)
                        if img_rec:
                            job.image_id = img_rec['id']
                    except Exception:
                        pass

                # Phase status updates
                if job.image_id:
                    db.set_image_phase_status(job.image_id, PhaseCode.SCORING, PhaseStatus.DONE,
                                              app_version=APP_VERSION,
                                              executor_version=self.scorer.VERSION if self.scorer else None,
                                              job_id=job.job_id)

                score = job.result["summary"]["weighted_scores"].get("general", 0)
                if self.progress_callback:
                    self.progress_callback(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] [ResultWorker] Scored: {Path(job.image_path).name} - {score:.2f}")
            except Exception as e:
                # Phase C (Scoring) — failed
                if job.image_id:
                    db.set_image_phase_status(job.image_id, PhaseCode.SCORING, PhaseStatus.FAILED,
                                              job_id=job.job_id, error=str(e))
                if self.progress_callback:
                    self.progress_callback(f"DB Error: {e}")
        
        # 2. Cleanup
        for p in job.temp_files:
            try:
                if os.path.isdir(p):
                    import shutil
                    shutil.rmtree(p)
                else:
                    if os.path.exists(p):
                        os.remove(p)
            except OSError as e:
                logger.warning("Cleanup failed for %s: %s", p, e)
        
        if self.item_finished_callback:
            self.item_finished_callback()
