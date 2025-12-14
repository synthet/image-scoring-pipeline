
import os
import threading
from modules import db, thumbnails
from modules.engine import BatchImageProcessor
import sys
from pathlib import Path

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
        
    def run_batch(self, input_path, job_id, skip_existing=False):
        """
        Generator that runs the batch process and yields log lines.
        """
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
            yield f"Error: Path not found: {input_path}"
            return

        yield f"Starting batch processing..."
        yield f"Input: {input_path}"
        yield "-" * 20
        
        # Checking/Loading Models
        if self.shared_scorer is None:
            yield "Initializing models first (this happens once)..."
            try:
                new_scorer = MultiModelMUSIQ()
                
                # Load models
                musiq_models = ['spaq', 'ava', 'koniq', 'paq2piq']
                for model_name in musiq_models:
                    yield f"Loading model: {model_name.upper()}..."
                    success = new_scorer.load_model(model_name)
                    if not success:
                         yield f"Warning: Failed to load {model_name}"
                
                self.shared_scorer = new_scorer
                yield "Models initialized successfully."
                
            except Exception as e:
                yield f"Error loading models: {str(e)}"
                return

        # Initialize processor
        processor = BatchImageProcessor(
            output_dir=input_path,
            skip_existing=skip_existing,
            scorer=self.shared_scorer
        )
        self.current_processor = processor
        
        # Inject job_id for DB upserts (Engine HACK)
        processor.current_job_id = job_id
        
        # Setup log capture
        import queue
        log_queue = queue.Queue()
        
        def log_capture(msg):
            log_queue.put(msg)
            print(msg, flush=True) # Still print to stdout for debugging
            
        processor.log_func = log_capture
        
        # Database Backup before starting
        yield "Creating database backup..."
        db.backup_database()
        
        # Run processing in background thread so we can yield logs
        def target():
            try:
                # process_directory now blocks until all workers are done
                processor.process_directory(input_path, input_path)
                log_queue.put(None) # Signal done
            except Exception as e:
                log_queue.put(f"Error: {e}")
                log_queue.put(None)
                
        t = threading.Thread(target=target)
        t.start()
        
        # Yield from queue
        while True:
            try:
                line = log_queue.get(timeout=0.1)
                if line is None:
                    break
                yield line
            except queue.Empty:
                if not t.is_alive():
                    break
                continue
                
        t.join()
        
        # Cleanup
        self.current_processor = None
        yield "Processing finished."
        
        # Backup after
        db.backup_database()

    def stop(self):
        if self.current_processor:
            self.current_processor.stop_event.set()
