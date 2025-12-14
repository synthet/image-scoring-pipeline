
import os
import queue
import time
import threading
import logging
from datetime import datetime
from modules import pipeline, db
from scripts.python.run_all_musiq_models import MultiModelMUSIQ

class BatchImageProcessor:
    """
    Refactored Batch Processor using Threaded Pipeline.
    """
    def __init__(self, output_dir=None, skip_existing=False, write_json=False, 
                 json_stdout=False, skip_predicate=None, scorer=None):
        self.output_dir = output_dir
        self.skip_existing = skip_existing
        self.scorer = scorer
        self.logger = logging.getLogger(__name__)
        self.stop_event = threading.Event()
        
    def log(self, msg, level="INFO"):
        lvl = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(lvl, msg)
            
    def process_directory(self, input_dir, output_dir_unused, callback=None):
        """
        Main entry point for batch processing.
        """
        # 1. Setup
        if not self.scorer:
            self.log("Error: Scorer not provided!", "ERROR")
            return

        # 2. Find Images
        import glob
        extensions = ['*.jpg', '*.jpeg', '*.png', '*.nef', '*.NEF', '*.nrw', '*.dng', '*.cr2', '*.arw']
        files = []
        for ext in extensions:
            files.extend(glob.glob(os.path.join(input_dir, "**", ext), recursive=True))
        files = sorted(list(set(files))) # Dedup
        
        if not files:
            self.log("No images found.")
            return

        self.log(f"Found {len(files)} images to process.")
        
        # 3. Setup Queues and Workers
        prep_queue = queue.Queue(maxsize=50)
        scoring_queue = queue.Queue(maxsize=10) # Keep small to avoid VRAM overload if buffering
        result_queue = queue.Queue(maxsize=50) # Just for sync
        
        self.stop_event.clear()
        
        # Workers
        prep_worker = pipeline.PrepWorker(prep_queue, scoring_queue, self.stop_event, self.scorer)
        scoring_worker = pipeline.ScoringWorker(scoring_queue, result_queue, self.stop_event, self.scorer)
        
        # Result callback wrapper
        def result_logger(msg):
            self.log(msg)
            # If we want to yield to the UI generator, we strictly can't "return" from here
            # but the log_func passed from ScoringRunner is capturing this.
            
        result_worker = pipeline.ResultWorker(result_queue, None, self.stop_event, scorer_instance=self.scorer, progress_callback=result_logger)
        
        workers = [prep_worker, scoring_worker, result_worker]
        for w in workers:
            w.start()
            
        # 4. Feed the Beast
        # Creates a Job ID for this batch run (optional, or per file?)
        # db.py create_job was called by webui. 
        # But upsert_image needs a job_id. 
        # We need to pass the job_id down.
        # Wait, the current architecture passed `job_id` into `run_batch` in `scoring.py`.
        # But `process_directory` doesn't accept `job_id`. 
        # We need to hack/fix this.
        # I'll update `process_directory` signature or assume we can get it.
        # Actually `scoring.py` calls `process_directory`.
        
        # HACK: Retrieve job_id from somewhere or update signature?
        # Update signature is better but requires changing base class or calls.
        # Let's check `scoring.py` again. It calls `processor.process_directory`.
        # I can update `scoring.py` to inject job_id into the processor instance OR pass it.
        # I will inject it into the processor instance before calling process_directory.
        
        current_job_id = getattr(self, "current_job_id", 0) 
        
        for i, f in enumerate(files):
            if self.stop_event.is_set():
                break
            
            job = pipeline.ImageJob(
                image_path=f,
                job_id=current_job_id,
                skip_existing=self.skip_existing
            )
            
            try:
                prep_queue.put(job, timeout=2.0)
                # Check status periodically
                while prep_queue.full() and not self.stop_event.is_set():
                     time.sleep(0.1)
            except KeyboardInterrupt:
                self.stop_event.set()
                break
                
        # 5. Wait for completion
        # Send sentinels
        if not self.stop_event.is_set():
            prep_queue.put(None)
        
        # Wait for workers
        prep_worker.join()
        # After prep is done, it sends sentinel to scoring
        # Wait for scoring
        scoring_queue.put(None) # Safety incase prep didn't? No, Prep logic should.
        # Actually my PrepWorker implementation sends None when it gets None.
        
        scoring_worker.join()
        result_queue.put(None) # Sentinel for result
        result_worker.join()
        
        self.log("Batch processing finished.")
