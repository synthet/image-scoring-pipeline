
import os
import threading
import json
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
        deleted_count = 0
        for row in records:
             file_path = row['file_path']
             if not os.path.exists(file_path):
                 log(f"Deleting missing file from DB: {file_path}")
                 db.delete_image(file_path)
                 deleted_count += 1
                 continue
                 
             job = pipeline.ImageJob(
                 image_path=file_path,
                 job_id=job_id,
                 skip_existing=False 
             )
             
             # Pre-fill external scores
             models = ['spaq', 'ava', 'koniq', 'paq2piq', 'liqe']
             for m in models:
                 key = f'score_{m}'
                 try:
                     val = row[key]
                     if val is not None and val > 0:
                         job.external_scores[m] = {
                             "score": val,
                             "normalized_score": val, 
                             "status": "success"
                         }
                 except (KeyError, IndexError):
                     pass
             
             try:
                 if row['image_hash']:
                     job.external_scores['image_hash'] = row['image_hash']
             except (KeyError, IndexError):
                 pass
                 
             jobs.append(job)
        
        if deleted_count > 0:
             log(f"Removed {deleted_count} orphaned records from database.")
             
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


    def fix_image_metadata(self, file_path):
        """
        Recalculates scores and updates metadata for a single image 
        without running neural networks, using existing data.
        Returns: Success (bool), Message (str)
        """
        try:
            # 1. File Check
            if not os.path.exists(file_path):
                # Check if it was moved/renamed? 
                # For now just error out
                return False, f"File not found: {file_path}"
                
            # 2. Get existing DB data
            details = db.get_image_details(file_path)
            if not details:
                return False, "Image not found in database"
            
            # Helper to retrieve score from various places
            scores = {}
            # Try DB columns first
            for m in ['spaq', 'ava', 'koniq', 'paq2piq', 'liqe']:
                key = f'score_{m}'
                val = details.get(key)
                if val is not None and val > 0:
                    scores[m] = float(val)
            
            # Fallback to JSON if missing in cols
            if len(scores) < 5:
                try:
                    scores_json = details.get('scores_json')
                    if isinstance(scores_json, str):
                        s_data = json.loads(scores_json)
                        if 'models' in s_data:
                            for m, res in s_data['models'].items():
                                if m not in scores and res.get('status') == 'success':
                                    scores[m] = float(res.get('normalized_score', 0))
                except:
                    pass
            
            # 3. Recalculate if we have enough data
            # We need at least some models to make a meaningful calculation
            # If all missing, we can't do anything without running models
            if not scores:
                return False, "No existing model scores found to recalculate from."
                
            # Use MultiModelMUSIQ static helpers if possible, or reimplement lightweight logic
            # Reimplementing here to avoid instantiating heavy class
            
            def get_s(model):
                return scores.get(model, 0.0)

            # Formulas from run_all_musiq_models.py (v3.0.0)
            
            # Technical: PaQ(0.35), LIQE(0.35), KonIQ(0.15), SPAQ(0.15)
            tech = (0.35 * get_s('paq2piq') + 
                    0.35 * get_s('liqe') + 
                    0.15 * get_s('koniq') + 
                    0.15 * get_s('spaq'))

            # Aesthetic: AVA(0.40), KonIQ(0.30), SPAQ(0.20), PaQ(0.10)
            aes = (0.40 * get_s('ava') + 
                   0.30 * get_s('koniq') + 
                   0.20 * get_s('spaq') + 
                   0.10 * get_s('paq2piq'))

            # General: PaQ(0.25), LIQE(0.25), AVA(0.20), KonIQ(0.20), SPAQ(0.10)
            gen = (0.25 * get_s('paq2piq') + 
                   0.25 * get_s('liqe') + 
                   0.20 * get_s('ava') + 
                   0.20 * get_s('koniq') + 
                   0.10 * get_s('spaq'))
                   
            # Rating Calculation
            rating = 1
            if gen >= 0.85: rating = 5
            elif gen >= 0.70: rating = 4
            elif gen >= 0.55: rating = 3
            elif gen >= 0.40: rating = 2
            
            # Label Calculation (matches determine_lightroom_label)
            # Red=Reject, Purple=Aesthetic beats tech, Blue=Portfolio, Green=Reference, Yellow=Maybe
            label = "Yellow"
            if tech < 0.40: label = "Red"
            elif tech < 0.65 and aes > tech and aes > 0.48: label = "Purple"
            elif aes > 0.55 and tech > 0.65: label = "Blue"
            elif tech > 0.65: label = "Green"
            
            # 4. Update Database
            # We need to construct a partial update or update the whole record
            # Let's verify what DB fields correspond to
            
            # Update specific columns
            conn = db.get_db()
            c = conn.cursor()
            
            c.execute("""
                UPDATE images 
                SET score_general = ?, score_aesthetic = ?, score_technical = ?,
                    rating = ?, label = ?
                WHERE file_path = ?
            """, (gen, aes, tech, rating, label, file_path))
            
            # Also update scores_json summary if possible (complex text manipulation)
            # Maybe skip for now as columns are the source of truth for UI
            
            conn.commit()
            conn.close()
            
            # 5. Write Metadata (XMP)
            # Use xmp module
            from modules import xmp
            is_raw = os.path.splitext(file_path)[1].lower() in ['.nef', '.nrw']
            
            # Retrieve additional metadata from DB
            title = details.get('title', '')
            description = details.get('description', '')
            keywords_str = details.get('keywords', '')
            keywords = [k.strip() for k in keywords_str.split(',')] if keywords_str else []
            
            success = xmp.write_metadata_unified(
                image_path=file_path,
                rating=rating,
                label=label,
                title=title,
                description=description,
                keywords=keywords,
                use_sidecar=True,
                use_embedded=is_raw
            )
            
            # 6. Regenerate Thumbnail (User Request)
            try:
                thumb_path = thumbnails.get_thumb_path(file_path)
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                
                new_thumb = thumbnails.generate_thumbnail(file_path)
                if new_thumb:
                     # Update DB with new thumb path (ensure it is set)
                     # Paths in DB are usually WSL format if running in WSL, 
                     # but thumbnails.py returns local path. 
                     # For now, let's assume we store what generate_thumbnail returns 
                     # or rely on utils.convert_path_to_wsl if needed.
                     # But DB usually stores what is generated.
                     
                     # Actually, db.py usually handles path conversion or we store whatever we get.
                     # Let's just update it.
                     conn = db.get_db()
                     c = conn.cursor()
                     # If running in WSL, we might want to convert to /mnt/...
                     # But existing code likely handles this elsewhere. 
                     # We will just update providing consistency with current env.
                     c.execute("UPDATE images SET thumbnail_path = ? WHERE file_path = ?", (new_thumb, file_path))
                     conn.commit()
                     conn.close()
            except Exception as e:
                print(f"Error regenerating thumbnail: {e}")
                # Don't fail the whole fix for this, but append to msg
                msg += " [Thumb Gen Failed]"
            
            msg = f"Fixed: Gen={gen:.2f} ({rating}*), Tech={tech:.2f}, Aes={aes:.2f} ({label})"
            if new_thumb:
                msg += " [Thumb Updated]"
            
            if not success:
               msg += " [XMP Write Failed]"
               
            return True, msg
            
        except Exception as e:
            return False, f"Error fixing image: {e}"


    def run_single_image(self, file_path):
        """
        Runs full scoring pipeline for a single image, blocking.
        Returns: success (bool), message (str)
        """
        import uuid
        job_id = f"manual_{uuid.uuid4().hex[:8]}"

        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        self.status_message = "Scoring (Manual)..."
        
        # Initialize models if needed
        if self.shared_scorer is None:
            try:
                # Use local import if needed or assume globally imported
                # from run_all_musiq_models import MultiModelMUSIQ
                new_scorer = MultiModelMUSIQ()
                for m in ['spaq', 'ava', 'koniq', 'paq2piq']:
                    new_scorer.load_model(m)
                self.shared_scorer = new_scorer
            except Exception as e:
                return False, f"Error initializing models: {e}"

        # Create Job
        from modules import pipeline
        job = pipeline.ImageJob(
            image_path=file_path,
            job_id=job_id,
            skip_existing=False
        )

        # Capture logs
        log_msgs = []
        def capture_log(msg):
            log_msgs.append(msg)
            
        # Create temporary processor
        processor = BatchImageProcessor(
            scorer=self.shared_scorer,
            progress_callback=lambda c, t: None
        )
        processor.log_func = capture_log
        processor.current_job_id = job_id
        
        try:
            # Create a dummy job entry in DB
            db.create_job(job_id, "manual_scoring", 1, file_path)
            db.update_job_status(job_id, "running")
            
            processor.process_list([job], job_id_override=job_id)
            
            # Check result
            # Retrieve latest data to confirm
            details = db.get_image_details(file_path)
            gen = details.get('score_general', 0)
            
            db.update_job_status(job_id, "completed")
            self.status_message = "Idle"
            return True, f"Scoring Complete. General Score: {gen:.2f}"
            
        except Exception as e:
            self.status_message = "Error"
            return False, f"Error running scoring: {e}"
