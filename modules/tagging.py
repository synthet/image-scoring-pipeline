import os
import torch
import logging
import threading
import queue
from PIL import Image
from transformers import CLIPProcessor, CLIPModel, BlipProcessor, BlipForConditionalGeneration
from typing import List, Dict, Optional, Tuple
from modules import db, thumbnails, utils, xmp
from modules.events import event_manager
from modules.phases import PhaseCode, PhaseStatus
from modules.version import APP_VERSION
from modules.phases_policy import explain_phase_run_decision

TAGGER_VERSION = "1.0.0"  # bump when CLIP model or tagging logic changes

# Setup logging
logger = logging.getLogger(__name__)


def propagate_tags(
    folder_path: str = None,
    dry_run: bool = True,
    k: int = None,
    min_similarity: float = None,
    min_keyword_confidence: float = None,
    min_support_neighbors: int = None,
    write_mode: str = None,
    max_keywords: int = None,
) -> Dict:
    """
    Propagate keywords from tagged images to untagged neighbors using embedding similarity.

    For each untagged image with a stored embedding:
      1. Find k nearest *tagged* neighbors by cosine similarity.
      2. Aggregate neighbor keywords with similarity-weighted voting.
      3. Apply keywords that pass confidence, support, and anchor thresholds.

    Args:
        folder_path: Optional folder scope (None = all images).
        dry_run: If True, compute candidates but do not write to DB.
        k: Number of nearest neighbors to consider.
        min_similarity: Minimum cosine similarity for the top neighbor (anchor).
        min_keyword_confidence: Minimum weighted keyword score to accept.
        min_support_neighbors: Minimum number of neighbors that must contain the keyword.
        write_mode: 'replace_missing_only' (default) or 'append'.
        max_keywords: Maximum keywords to propagate per image.

    Returns:
        Dict with 'propagated', 'skipped', 'total_untagged', and 'candidates' (dry_run only).
    """
    import numpy as np
    from modules import config
    from modules.similar_search import _normalize

    # Load defaults from config
    cfg = config.get_config_section("tagging")
    k = k if k is not None else cfg.get("propagation_k", 5)
    min_similarity = min_similarity if min_similarity is not None else cfg.get("propagation_min_similarity", 0.85)
    min_keyword_confidence = min_keyword_confidence if min_keyword_confidence is not None else cfg.get("propagation_min_keyword_confidence", 0.60)
    min_support_neighbors = min_support_neighbors if min_support_neighbors is not None else cfg.get("propagation_min_support_neighbors", 2)
    write_mode = write_mode or cfg.get("propagation_write_mode", "replace_missing_only")
    max_keywords = max_keywords if max_keywords is not None else cfg.get("propagation_max_keywords", 10)

    # Fetch data
    untagged, tagged = db.get_images_for_tag_propagation(folder_path=folder_path)

    result = {
        "propagated": 0,
        "skipped": 0,
        "total_untagged": len(untagged),
        "total_tagged": len(tagged),
    }

    if not untagged:
        logger.info("Tag propagation: no untagged images with embeddings found.")
        return result
    if not tagged:
        logger.info("Tag propagation: no tagged images with embeddings found.")
        result["skipped"] = len(untagged)
        return result

    # Build tagged matrix once
    tagged_ids = [t[0] for t in tagged]
    tagged_keywords = [t[3].split(",") for t in tagged]  # list of keyword lists
    tagged_vecs = np.stack([np.frombuffer(t[2], dtype=np.float32) for t in tagged])
    tagged_norm = _normalize(tagged_vecs)

    # Collect all unique keywords across tagged images for indexing
    all_kw = sorted({kw.strip() for kwl in tagged_keywords for kw in kwl if kw.strip()})
    kw_to_idx = {kw: i for i, kw in enumerate(all_kw)}

    # Build keyword presence matrix: (num_tagged, num_keywords) bool
    kw_matrix = np.zeros((len(tagged_ids), len(all_kw)), dtype=np.float32)
    for row_i, kwl in enumerate(tagged_keywords):
        for kw in kwl:
            kw = kw.strip()
            if kw and kw in kw_to_idx:
                kw_matrix[row_i, kw_to_idx[kw]] = 1.0

    candidates_list = []  # for dry-run reporting

    conn = None
    cur = None
    if not dry_run:
        conn = db.get_db()
        cur = conn.cursor()

    try:
        for img_id, file_path, emb_bytes in untagged:
            query_vec = np.frombuffer(emb_bytes, dtype=np.float32)
            query_norm = _normalize(query_vec)

            # Cosine similarities to all tagged images
            sims = tagged_norm @ query_norm  # shape: (num_tagged,)

            # Top-k indices
            top_k_idx = np.argsort(-sims)[:k]
            top_sims = sims[top_k_idx]

            # Anchor check: best neighbor must meet min_similarity
            if top_sims[0] < min_similarity:
                result["skipped"] += 1
                continue

            # Filter neighbors below min_similarity
            valid_mask = top_sims >= min_similarity
            top_k_idx = top_k_idx[valid_mask]
            top_sims = top_sims[valid_mask]

            if len(top_k_idx) == 0:
                result["skipped"] += 1
                continue

            # Weighted voting for each keyword
            # keyword_score = sum(sim_i * has_keyword_i) / sum(sim_i)
            sim_total = top_sims.sum()
            neighbor_kw = kw_matrix[top_k_idx]  # (n_neighbors, n_keywords)
            weighted_scores = (top_sims[:, None] * neighbor_kw).sum(axis=0) / sim_total  # (n_keywords,)

            # Support count: how many neighbors have each keyword
            support_counts = neighbor_kw.sum(axis=0)  # (n_keywords,)

            # Apply thresholds
            accepted = []
            for kw_idx, kw in enumerate(all_kw):
                score = float(weighted_scores[kw_idx])
                support = int(support_counts[kw_idx])
                if score >= min_keyword_confidence and support >= min_support_neighbors:
                    accepted.append((kw, score))

            if not accepted:
                result["skipped"] += 1
                continue

            # Sort by score descending, cap at max_keywords
            accepted.sort(key=lambda x: -x[1])
            accepted = accepted[:max_keywords]
            new_keywords = [kw for kw, _ in accepted]

            if dry_run:
                candidates_list.append({
                    "image_id": img_id,
                    "file_path": file_path,
                    "keywords": new_keywords,
                    "top_neighbor_similarity": round(float(top_sims[0]), 4),
                })
                result["propagated"] += 1
            else:
                # Write to DB
                tags_str = ",".join(new_keywords)
                cur.execute("UPDATE images SET keywords = ? WHERE id = ?", (tags_str, img_id))
                result["propagated"] += 1
                logger.info("Propagated %d keywords to image %d: %s", len(new_keywords), img_id, tags_str)

        if not dry_run and conn:
            conn.commit()

    except Exception as e:
        logger.error("Tag propagation error: %s", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    if dry_run:
        result["candidates"] = candidates_list

    logger.info(
        "Tag propagation complete: %d propagated, %d skipped, %d untagged, %d tagged (dry_run=%s)",
        result["propagated"], result["skipped"], result["total_untagged"], result["total_tagged"], dry_run,
    )
    return result

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

    def __init__(self, model_name: str = None, device: str = None):
        # Load model name from config if not provided
        if model_name is None:
            from modules import config
            tagging_config = config.get_config_section('tagging')
            model_name = tagging_config.get('clip_model', "openai/clip-vit-base-patch32")
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
            # Load max_new_tokens from config
            from modules import config
            tagging_config = config.get_config_section('tagging')
            max_tokens = tagging_config.get('max_new_tokens', 50)
            context_tokens = self.model.generate(**inputs, max_new_tokens=max_tokens)
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
        
        # State persistence
        self.is_running = False
        self.log_history = []
        self.status_message = "Idle"
        self._thread = None
        self.current_count = 0
        self.total_count = 0
        
    def get_status(self):
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count
        
    def start_batch(self, input_path: str, job_id: int = None, custom_keywords: List[str] = None, overwrite: bool = False, generate_captions: bool = False):
        if self.is_running:
            return "Error: Already running."
            
        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0
        
        if job_id is None:
            from modules import db
            job_id = db.create_job(input_path or "ALL_IMAGES_TAGGING")
            
        def target():
            self._run_batch_internal(input_path, custom_keywords, overwrite, generate_captions, job_id=job_id)
            self.is_running = False
            self.status_message = "Done" if "Error" not in self.status_message else "Failed"
            
        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def _run_batch_internal(self, input_path: str, custom_keywords: List[str] = None, overwrite: bool = False, generate_captions: bool = False, job_id: int = None):
        """
        Internal sync runner for tagging process.
        """
        from modules.events import event_manager
        
        def log(msg):
            self.log_history.append(msg)
            # print(msg, flush=True)

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
        log(f"Starting Tagging process on {input_path}...")
        self.status_message = "Running..."
        
        # Notify job started
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "tagging", 
                "input_path": input_path
            })
        
        # Initialize Scorer
        if not self.scorer:
            try:
                log("Loading CLIP model (this may take a while)...")
                self.scorer = KeywordScorer()
                self.scorer.load_model()
                log("Model loaded.")
            except Exception as e:
                log(f"Error loading model: {e}")
                self.status_message = "Error loading model"
                return

        if generate_captions and not self.captioner:
            try:
                log("Loading Captioning model (BLIP)...")
                self.captioner = CaptionGenerator()
                self.captioner.load_model()
                log("Captioning model loaded.")
            except Exception as e:
                log(f"Error loading captioning model: {e}")
                self.status_message = "Error loading captioning model"
                return

        log("Scanning for images...")
        all_images = []
        
        # Fetch all images from DB (limit=-1 for no limit)
        try:
            rows = db.get_all_images(limit=-1)
        except Exception as e:
            log(f"Error fetching from DB: {e}")
            self.status_message = "Error DB"
            return

        if not input_path or not input_path.strip():
             log("Input path empty. Processing all images in DB...")
             all_images = [row for row in rows]
        elif os.path.isdir(input_path):
             import pathlib
             # Normalize input_path for comparison (handles Windows/WSL)
             p_in_str = utils.convert_path_to_local(input_path)
             p_in = pathlib.Path(p_in_str).resolve()

             # Filter rows by path — convert DB paths to local format for correct matching
             for row in rows:
                 fp_raw = row['file_path']
                 fp_local = utils.convert_path_to_local(fp_raw) if fp_raw else fp_raw
                 f_path = pathlib.Path(fp_local).resolve()
                 try:
                     f_path.relative_to(p_in)
                     all_images.append(row)
                 except (ValueError, TypeError):
                     continue
        else:
            log(f"Input path not found or not a directory: {input_path}")
            self.status_message = "Error Path"
            return

        if len(all_images) == 0 and rows and input_path and os.path.isdir(input_path):
            sample = rows[0].get("file_path", "") if rows else ""
            p_in_str = utils.convert_path_to_local(input_path)
            log(f"Path filter returned 0 images (input={p_in_str}, sample_db_path={str(sample)[:80]}...)")

        # Check folder level status if not overwriting (optimization)
        processed_folders = set()
        if not overwrite and os.path.isdir(input_path):
             if db.is_folder_keywords_processed(input_path):
                 log(f"Skipping fully processed folder: {input_path}")
                 self.status_message = "Skipped (Processed)"
                 return

        log(f"Found {len(all_images)} images to process.")
        self.total_count = len(all_images)
        self.current_count = 0
        
        processed_count = 0
        skipped_count = 0
        
        for row in all_images:
            if self.stop_event.is_set():
                log("Tagging stopped by user.")
                break
                
            path = row['file_path']
            folder = os.path.dirname(path)
            processed_folders.add(folder)
            
            # Convert DB path to WSL path for processing if needed
            original_windows_path = path
            if ":" in path and path[1] == ":" and os.path.exists("/mnt/"):
                drive = path[0].lower()
                p = path[2:].replace("\\", "/")
                wsl_p = f"/mnt/{drive}{p}"
                path = wsl_p

            decision = explain_phase_run_decision(
                row['id'],
                PhaseCode.KEYWORDS,
                current_executor_version=TAGGER_VERSION,
                force_run=overwrite,
            )
            if not decision["should_run"]:
                skipped_count += 1
                self.current_count += 1
                log(f"Skipping {os.path.basename(path)}: {decision['reason']}")
                continue

            # Check overwrite
            existing = row['keywords']
            if existing and not overwrite:
                skipped_count += 1
                self.current_count += 1
                # Do not overwrite phase state here. Policy may request a re-run
                # (e.g. executor_version_changed), but user chose not to overwrite.
                log(f"Skipping {os.path.basename(path)}: existing keywords and overwrite disabled")
                continue
                
            if not os.path.exists(path):
                log(f"Skipping missing file: {path}")
                self.current_count += 1
                continue
                
            # Process
            log(f"Tagging: {os.path.basename(path)}...")
            
            # Determine inference path (use thumbnail for NEF/RAW)
            inference_path = path
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.nef', '.nrw', '.arw', '.cr2', '.cr3', '.dng']:
                 from modules.thumbnails import get_thumb_wsl
                 thumb_path = get_thumb_wsl(row)  # tagging runs in WSL

                 if thumb_path and os.path.exists(thumb_path):
                     inference_path = thumb_path
                 else:
                     log(f"  [Warning] No thumbnail found for RAW file, inference might fail: {os.path.basename(path)}")
            
            try:
                db.set_image_phase_status(
                    row['id'],
                    PhaseCode.KEYWORDS,
                    PhaseStatus.RUNNING,
                    app_version=APP_VERSION,
                    executor_version=TAGGER_VERSION,
                    job_id=job_id,
                )
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
                         log(f"  -> Caption: {caption}")
                    else:
                         c.execute("UPDATE images SET keywords = ? WHERE id = ?", (tags_str, row['id']))
                         
                    conn.commit()
                    conn.close()
                    log(f"  -> Tags: {tags_str}")
                    processed_count += 1
                    self.current_count += 1

                    # Phase E (Keywords) — done for this image
                    db.set_image_phase_status(row['id'], PhaseCode.KEYWORDS, PhaseStatus.DONE,
                                              app_version=APP_VERSION, executor_version=TAGGER_VERSION,
                                              job_id=job_id)
                    
                    # Write Metadata
                    if self.write_metadata(path, tags, title, caption):
                         log("  -> Metadata written to file.")
                    else:
                         log("  -> Metadata write failed (check connection/permissions).")
                    
                else:
                    log("  -> No tags found.")
                    self.current_count += 1
                    db.set_image_phase_status(
                        row['id'],
                        PhaseCode.KEYWORDS,
                        PhaseStatus.SKIPPED,
                        app_version=APP_VERSION,
                        executor_version=TAGGER_VERSION,
                        job_id=job_id,
                    )
            except Exception as e:
                log(f"Request failed: {e}")
                self.current_count += 1
                # Phase E (Keywords) — failed for this image
                try:
                    db.set_image_phase_status(
                        row['id'],
                        PhaseCode.KEYWORDS,
                        PhaseStatus.FAILED,
                        app_version=APP_VERSION,
                        executor_version=TAGGER_VERSION,
                        job_id=job_id,
                        error=str(e),
                    )
                except Exception:
                    pass
            event_manager.broadcast_threadsafe("job_progress", {"job_id": job_id, "current": self.current_count, "total": self.total_count})
                
        log(f"Done. Processed: {processed_count}, Skipped: {skipped_count}")

        # Update Job Status
        if job_id:
            db.update_job_status(job_id, "completed")
            event_manager.broadcast_threadsafe("job_completed", {
                "job_id": job_id, 
                "status": "completed"
            })

        # Update Folder Status
        if processed_folders:
            log("Updating folder completion flags...")
            for f in processed_folders:
                 try:
                     if db.check_and_update_folder_keywords_status(f):
                         log(f"Folder marked as fully processed: {f}")
                 except Exception as e:
                     log(f"Failed to update status for {f}: {e}")

    def write_metadata(self, image_path: str, keywords: List[str], title: str = "", description: str = "", rating: int = 0, label: str = "") -> bool:
        """
        Write keywords and metadata to image using unified XMP module.
        
        Uses XMP sidecar files for non-destructive workflow by default.
        Also writes embedded metadata for maximum compatibility.
        """
        try:
            # Use the unified XMP module for consistent metadata handling
            # Write to both sidecar (non-destructive) and embedded (compatibility)
            success = xmp.write_metadata_unified(
                image_path=image_path,
                rating=rating if rating and rating > 0 else None,
                label=label if label else None,
                keywords=keywords if keywords else None,
                title=title if title else None,
                description=description if description else None,
                use_sidecar=True,   # Non-destructive XMP sidecar
                use_embedded=True   # Also write embedded for compatibility
            )
            
            if success:
                logger.info(f"Metadata written for {os.path.basename(image_path)}")
            return success
            
        except Exception as e:
            logger.error(f"Metadata write failed: {e}")
            return False
        
    def stop(self):
        self.stop_event.set()

    def run_single_image(self, file_path, custom_keywords=None, generate_captions=True):
        """
        Runs tagging/captioning for a single image, blocking.
        Returns: success (bool), message (str)
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        self.status_message = "Tagging (Manual)..."
        
        # Initialize Scorer
        if not self.scorer:
            try:
                self.scorer = KeywordScorer()
                self.scorer.load_model()
            except Exception as e:
                self.status_message = "Error"
                return False, f"Error loading CLIP model: {e}"

        if generate_captions and not self.captioner:
            try:
                self.captioner = CaptionGenerator()
                self.captioner.load_model()
            except Exception as e:
                self.status_message = "Error"
                return False, f"Error loading BLIP model: {e}"

        # Determine inference path (use thumbnail for NEF/RAW)
        inference_path = file_path
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.nef', '.nrw', '.arw', '.cr2', '.cr3', '.dng']:
             row = db.get_image_details(file_path)
             if row:
                from modules.thumbnails import get_thumb_wsl
                thumb_path = get_thumb_wsl(row)  # tagging runs in WSL
                if thumb_path and os.path.exists(thumb_path):
                    inference_path = thumb_path
        
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
                row = db.get_image_details(file_path)
                image_id = row['id'] if row else None
                
                if image_id:
                    if caption:
                         c.execute("UPDATE images SET keywords = ?, title = ?, description = ? WHERE id = ?", 
                                   (tags_str, title, caption, image_id))
                    else:
                         c.execute("UPDATE images SET keywords = ? WHERE id = ?", (tags_str, image_id))
                    conn.commit()
                    success_msg = f"Tags: {len(tags)} found"
                    if caption: success_msg += ", Caption generated"
                else:
                    conn.close()
                    return False, "Image not found in DB"
                
                conn.close()
                
                # Write Metadata
                self.write_metadata(file_path, tags, title, caption)
                
                self.status_message = "Idle"
                return True, success_msg
                
            else:
                self.status_message = "Idle"
                return True, "No tags found."

        except Exception as e:
            self.status_message = "Error"
            return False, f"Error tagging: {e}"
