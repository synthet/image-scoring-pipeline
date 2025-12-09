
import os
import threading
from modules import db, thumbnails
from modules.engine import BatchImageProcessor

class ScoringRunner:
    """
    Runs scoring in a local thread using modules.engine.
    """
    def __init__(self):
        self.stop_event = threading.Event()
        self.current_thread = None
        
    def run_batch(self, input_path, job_id, skip_existing=False):
        """
        Generator that runs the batch process and yields log lines.
        Upserts results to DB and generates thumbnails via callback.
        """
        # Convert Windows path to WSL path if running in WSL
        # User input: D:\Photos\... -> /mnt/d/Photos/...
        if ":" in input_path and input_path[1] == ":":
            drive = input_path[0].lower()
            path = input_path[2:].replace("\\", "/")
            wsl_path = f"/mnt/{drive}{path}"
            if os.path.exists(wsl_path):
                input_path = wsl_path
            else:
                 yield f"Error: Converted WSL path not found: {wsl_path}"
                 # Fallback to original path just in case
                 if not os.path.exists(input_path):
                     yield f"Error: Original path not found: {input_path}"
                     return
        elif not os.path.exists(input_path):
            yield f"Error: Path not found: {input_path}"
            return

        yield f"Starting batch processing..."
        yield f"Input: {input_path}"
        yield "-" * 20
        
        self.stop_event.clear()
        
        # Define callback to handle results
        def result_callback(result):
            if self.stop_event.is_set():
                raise InterruptedError("Stopped by user")
                
            if result.get("status") in ["success", "skipped"]:
                # Handle DB Upsert
                # Need to normalize result format if needed, but engine returns what we need
                # Ensure image_path is absolute/correct
                
                # Check for existing thumbnail or generate one
                image_path = result.get("image_path")
                thumb_path = thumbnails.get_thumb_path(image_path)
                if not os.path.exists(thumb_path):
                     generated = thumbnails.generate_thumbnail(image_path)
                     if generated:
                         thumb_path = generated
                     else:
                         thumb_path = None
                
                result["thumbnail_path"] = thumb_path
                
                # DB Upsert
                db.upsert_image(job_id, result)
        
        # Initialize processor
        # We generally do NOT write JSON files in this mode, only DB.
        processor = BatchImageProcessor(
            output_dir=input_path,
            skip_existing=skip_existing,
            write_json=False, # DB only
            json_stdout=False
        )
        
        # Override log method to yield to generator?
        # Typically generators are pulled.
        # We can use a queue or shared buffer if we want to stream logs realtime.
        # Simplest: Just run it and rely on the fact that `run_batch` generator architecture
        # expects to yield lines. 
        # But `process_directory` blocks. 
        
        # Solution: We can monkeypatch processor.log to append to a list, 
        # but that doesn't yield realtime.
        # Better: run processor in a thread, and consume a queue in this generator.
        
        import queue
        log_queue = queue.Queue()
        
        def log_capture(msg, level="INFO"):
            log_queue.put(f"[{level}] {msg}")
            
        processor.log = log_capture
        
        # Run processing in background thread so we can yield logs
        def target():
            try:
                processor.process_directory(input_path, input_path, callback=result_callback)
                log_queue.put(None) # Signal done
            except InterruptedError:
                log_queue.put("Stopped.")
                log_queue.put(None)
            except Exception as e:
                log_queue.put(f"Error: {e}")
                log_queue.put(None)
                
        t = threading.Thread(target=target)
        self.current_thread = t
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
        yield "Processing finished."

    def stop(self):
        self.stop_event.set()
