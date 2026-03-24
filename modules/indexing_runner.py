import os
import threading
import logging
from typing import List, Dict, Optional
from modules import db
from modules.version import APP_VERSION
from modules.phases import PhaseCode, PhaseStatus
from modules.events import event_manager, broadcast_run_log_line

logger = logging.getLogger(__name__)

INDEXING_VERSION = "1.0.0"

SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.tif',
    '.nef', '.nrw', '.arw', '.cr2', '.cr3', '.dng'
}

class IndexingRunner:
    """
    Independent runner for the Indexing (Discovery) phase.
    Walks directories, computes basic info, and inserts rows into the `images` table.
    """
    def __init__(self):
        self.stop_event = threading.Event()
        self.is_running = False
        self.log_history = []
        self.status_message = "Idle"
        self._thread = None
        self.current_count = 0
        self.total_count = 0

    def get_status(self):
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count

    def start_batch(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None):
        if self.is_running:
            return "Error: Already running."
            
        self.is_running = True
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0
        
        if job_id is None:
            job_id = db.create_job(input_path or "ALL_IMAGES_INDEXING", job_type="indexing")
            
        def target():
            try:
                self._run_batch_internal(input_path, job_id, skip_existing, resolved_image_ids)
            except Exception:
                logger.exception("IndexingRunner thread crashed (job_id=%s)", job_id)
                self.status_message = "Failed"
            finally:
                self.is_running = False
            if "Error" in self.status_message:
                self.status_message = "Failed"
            elif not self.status_message.startswith("Done"):
                self.status_message = "Done"

        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def discover_files(self, directory: str) -> List[str]:
        valid_files = []
        if os.path.isfile(directory):
             ext = os.path.splitext(directory)[1].lower()
             if ext in SUPPORTED_EXTENSIONS:
                 valid_files.append(directory)
             return valid_files

        for root, _, files in os.walk(directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    valid_files.append(os.path.join(root, file))
        return valid_files

    def _run_batch_internal(self, input_path: str, job_id: int = None, skip_existing: bool = True, resolved_image_ids: List[int] = None):
        def log(msg):
            self.log_history.append(msg)
            if job_id:
                broadcast_run_log_line(job_id, msg)

        # Handle WSL path conversion if needed
        if input_path and ":" in input_path and len(input_path) > 1 and input_path[1] == ":":
            drive = input_path[0].lower()
            path = input_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{path}"
            if os.path.exists("/mnt/") and os.path.exists(wsl_path):
                input_path = wsl_path

        self.stop_event.clear()
        log(f"Starting Indexing process on {input_path or 'Selected Images'}...")
        self.status_message = "Running..."
        
        if job_id:
            db.update_job_status(job_id, "running")
            event_manager.broadcast_threadsafe("job_started", {
                "job_id": job_id, 
                "job_type": "indexing", 
                "input_path": input_path
            })

        all_files = []
        
        if resolved_image_ids is not None:
             try:
                 rows = db.get_all_images(limit=-1)
                 selected_ids = {int(i) for i in resolved_image_ids}
                 all_files = [row['file_path'] for row in rows if row.get('id') in selected_ids]
                 log(f"Selector mode enabled. Matched {len(all_files)} images by ID.")
             except Exception as e:
                 log(f"Error fetching from DB: {e}")
                 self.status_message = "Error DB"
                 return
        elif not input_path or not input_path.strip():
             log("Input path empty. Cannot index entire DB from scratch currently.")
             self.status_message = "Error Path"
             return
        elif os.path.exists(input_path):
             all_files = self.discover_files(input_path)
        else:
            log(f"Input path not found: {input_path}")
            self.status_message = "Error Path"
            return

        log(f"Found {len(all_files)} files to potentially index.")
        self.total_count = len(all_files)
        self.current_count = 0
        
        processed_count = 0
        skipped_count = 0
        
        for file_path in all_files:
            if self.stop_event.is_set():
                log("Indexing stopped by user.")
                break
                
            self.current_count += 1
            
            # Fast-path check: if skip_existing and file is already in DB
            if skip_existing:
                existing_record = db.get_image_details(file_path)
                if existing_record and existing_record.get('id'):
                    # Check if 'indexing' phase is already DONE
                    phase_status = db.get_image_phase_status(existing_record['id'], PhaseCode.INDEXING)
                    if phase_status and phase_status.get('status') == PhaseStatus.DONE:
                        skipped_count += 1
                        continue

            from modules.utils import calculate_image_hash
            
            try:
                # Need hash for initial upsert
                image_hash = calculate_image_hash(file_path)
                
                # Check if hash exists but path is different (moved file)
                existing = db.get_image_by_hash(image_hash)
                if existing:
                    image_id = existing.get('id')
                    db.register_image_path(image_id, file_path)
                else:
                    # Create new placeholder record
                    # We upsert an empty payload since scoring comes later
                    image_id = db.upsert_image(job_id, {
                        "file_path": file_path,
                        "image_hash": image_hash,
                        "folder_id": None
                    })
                
                # Set Phase Status
                if image_id:
                    db.set_image_phase_status(
                        image_id,
                        PhaseCode.INDEXING,
                        PhaseStatus.DONE,
                        app_version=APP_VERSION,
                        executor_version=INDEXING_VERSION,
                        job_id=job_id
                    )
                    processed_count += 1
                else:
                    skipped_count += 1

            except Exception as e:
                log(f"Error indexing {file_path}: {e}")
                skipped_count += 1

            if self.current_count % 50 == 0:
                event_manager.broadcast_threadsafe(
                    "job_progress",
                    {
                        "job_id": job_id,
                        "job_type": "indexing",
                        "phase_code": "indexing",
                        "current": self.current_count,
                        "total": self.total_count,
                    },
                )
                
        log(f"Done. Processed: {processed_count}, Skipped: {skipped_count}")

        if job_id:
            db.update_job_status(job_id, "completed")
            event_manager.broadcast_threadsafe("job_completed", {
                "job_id": job_id, 
                "status": "completed"
            })

    def stop(self):
        self.stop_event.set()
