
import os
import threading
from modules import db, thumbnails
from modules.engine import BatchImageProcessor
import sys
from pathlib import Path
from modules import pipeline

# Ensure paths are set up to import scripts
project_root = Path(__file__).resolve().parent.parent
if str(project_root / "scripts" / "python") not in sys.path:
    sys.path.insert(0, str(project_root / "scripts" / "python"))

try:
    from run_all_musiq_models import MultiModelMUSIQ
except ImportError:
    print("Warning: Could not import MultiModelMUSIQ for version info")
    class MultiModelMUSIQ:
        VERSION = "0.0.0"

class ScoringRunner:
    """
    Runs scoring in a local thread using modules.engine.
    """
    def __init__(self):
        # We hold the shared scorer here to persist it across runs
        self.shared_scorer = None
        # We keep a ref to the current processor to stop it
        self.current_processor = None
        

    def __init__(self):
        # We hold the shared scorer here to persist it across runs
        self.shared_scorer = None
        # We keep a ref to the current processor to stop it
        self.current_processor = None
        
        # State persistence
        self.is_running = False
        self.job_type = None # 'scoring' or 'fix_db'
        self.log_history = []
        self.status_message = "Idle"
        self._thread = None
        self.current_count = 0
        self.total_count = 0
        
    def get_status(self):
        """
        Returns (is_running, log_text, status_message, current, total)
        """
        return self.is_running, "\n".join(self.log_history), self.status_message, self.current_count, self.total_count

    def start_batch(self, input_path, job_id, skip_existing=False):
        """
        Starts batch processing in a background thread. Non-blocking.
        """
        if self.is_running:
            return "Error: Already running."
            
        self.is_running = True
        self.job_type = 'scoring'
        self.log_history = []
        self.status_message = "Starting..."
        self.current_count = 0
        self.total_count = 0
        
        # Convert Windows path to WSL path if running in WSL (legacy check)
        if ":" in input_path and input_path[1] == ":":
            drive = input_path[0].lower()
            path = input_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{path}"
            # Check if we are actually in WSL context
            if os.path.exists("/mnt/"): 
                 if os.path.exists(wsl_path):
                     input_path = wsl_path
                     
        if not os.path.exists(input_path):
            self.log_history.append(f"Error: Path not found: {input_path}")
            self.is_running = False
            self.status_message = "Failed (Path not found)"
            return "Path not found"

        def target():
            self._run_batch_internal(input_path, job_id, skip_existing)
            self.is_running = False
            self.status_message = "Done" if "Error" not in self.status_message else "Failed"

        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def _run_batch_internal(self, input_path, job_id, skip_existing):
        """
        Internal synchronous runner.
        """
        db.update_job_status(job_id, "running")
        
        def log(msg):
            self.log_history.append(msg)
            # print(msg, flush=True) # Optional debugging
            
        log(f"Starting batch processing...")
        log(f"Input: {input_path}")
        log("-" * 20)
        self.status_message = "Running..."
        
        # Checking/Loading Models
        if self.shared_scorer is None:
            log("Initializing models first (this happens once)...")
            try:
                new_scorer = MultiModelMUSIQ()
                
                # Load models
                musiq_models = ['spaq', 'ava', 'koniq', 'paq2piq']
                for model_name in musiq_models:
                    log(f"Loading model: {model_name.upper()}...")
                    success = new_scorer.load_model(model_name)
                    if not success:
                         log(f"Warning: Failed to load {model_name}")
                
                self.shared_scorer = new_scorer
                log("Models initialized successfully.")
                
            except Exception as e:
                msg = f"Error loading models: {str(e)}"
                log(msg)
                self.status_message = "Error loading models"
                db.update_job_status(job_id, "failed", msg)
                return

        def on_progress(cur, tot):
            self.current_count = cur
            self.total_count = tot
            
        # Initialize processor
        processor = BatchImageProcessor(
            output_dir=input_path,
            skip_existing=skip_existing,
            scorer=self.shared_scorer,
            progress_callback=on_progress
        )
        self.current_processor = processor
        
        # Inject job_id for DB upserts (Engine HACK)
        processor.current_job_id = job_id
        
        # Setup log capture
        # We hook directly to self.log_history via wrapper
        def log_capture(msg):
            log(msg)
            
        processor.log_func = log_capture
        
        # Database Backup before starting
        log("Creating database backup...")
        db.backup_database()
        
        try:
            # process_directory now blocks until all workers are done
            processor.process_directory(input_path, input_path)
            
            # Cleanup
            self.current_processor = None
            log("Processing finished.")
            db.update_job_status(job_id, "completed", "\n".join(self.log_history))
            
        except Exception as e:
            log(f"Error: {e}")
            self.status_message = "Error in processing"
            db.update_job_status(job_id, "failed", "\n".join(self.log_history))
        
        # Backup after
        db.backup_database()


    def stop(self):
        if self.current_processor:
            self.current_processor.stop_event.set()
            self.log_history.append("Stop signal sent...")

    def start_fix_db(self, job_id):
        """
        Starts DB fix in background thread.
        """
        if self.is_running:
            return "Error: Already running."
            
        self.is_running = True
        self.job_type = 'fix_db'
        self.log_history = []
        self.status_message = "Starting Fix DB..."
        
        def target():
            self._fix_db_internal(job_id)
            self.is_running = False
            self.status_message = "Done" if "Error" not in self.status_message else "Failed"
            
        self._thread = threading.Thread(target=target)
        self._thread.start()
        return "Started"

    def _fix_db_internal(self, job_id):
        """
        Internal synchronous fix db runner.
        """
        db.update_job_status(job_id, "running")
        
        def log(msg):
            self.log_history.append(msg)
            
        records = db.get_incomplete_records()
        if not records:
            log("No incomplete records found.")
            db.update_job_status(job_id, "completed", "No incomplete records.")
            return
            
        log(f"Found {len(records)} incomplete records requiring fix.")
        self.status_message = "Fixing..."
        
        # Checking/Loading Models (Same as run_batch)
        if self.shared_scorer is None:
            log("Initializing models...")
            try:
                new_scorer = MultiModelMUSIQ()
                musiq_models = ['spaq', 'ava', 'koniq', 'paq2piq']
                for model_name in musiq_models:
                    success = new_scorer.load_model(model_name)
                    if not success:
                         log(f"Warning: Failed to load {model_name}")
                self.shared_scorer = new_scorer
            except Exception as e:
                msg = f"Error loading models: {str(e)}"
                log(msg)
                self.status_message = "Error loading models"
                db.update_job_status(job_id, "failed", msg)
                return

        # Create Jobs
        jobs = []
        for row in records:
             file_path = row['file_path']
             if not os.path.exists(file_path):
                 log(f"Skipping missing file: {file_path}")
                 continue
                 
             job = pipeline.ImageJob(
                 image_path=file_path,
                 job_id=job_id,
                 skip_existing=False 
             )
             
             # Pre-fill external scores
             models = ['spaq', 'ava', 'koniq', 'paq2piq', 'liqe']
             for m in models:
                 val = row.get(f'score_{m}')
                 if val and val > 0:
                     job.external_scores[m] = {
                         "score": val,
                         "normalized_score": val, 
                         "status": "success"
                     }
             
             if row.get('image_hash'):
                 job.external_scores['image_hash'] = row.get('image_hash')
                 
             jobs.append(job)
             
        if not jobs:
            log("No valid files found to process.")
            db.update_job_status(job_id, "completed", "No valid files.")
            return
            
        log(f"Queueing {len(jobs)} jobs for processing...")
        
        def on_progress(cur, tot):
            self.current_count = cur
            self.total_count = tot

        # Initialize processor
        processor = BatchImageProcessor(
            output_dir=None, # In-place update
            scorer=self.shared_scorer,
            progress_callback=on_progress
        )
        self.current_processor = processor
        processor.current_job_id = job_id
        
        def log_capture(msg):
            log(msg)
        processor.log_func = log_capture
        
        log("Creating database backup...")
        db.backup_database()
        
        try:
            processor.process_list(jobs, job_id_override=job_id)
            self.current_processor = None
            log("DB Fix finished.")
            db.update_job_status(job_id, "completed", "\n".join(self.log_history))
            
        except Exception as e:
            log(f"Error: {e}")
            self.status_message = "Error in processing"
            db.update_job_status(job_id, "failed", "\n".join(self.log_history))

