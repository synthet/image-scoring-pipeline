import os
import platform
import warnings
import logging
import gradio as gr
from fastapi import FastAPI
import uvicorn
from modules.ui import app as app_module

# Suppress TensorFlow logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Suppress Gradio 6.0 deprecation warnings
warnings.filterwarnings("ignore", message="The 'css' parameter in the Blocks constructor")
warnings.filterwarnings("ignore", message="The 'head' parameter in the Blocks constructor")

# Custom logging filter to suppress Gradio queue polling messages
class SuppressGradioQueueFilter(logging.Filter):
    def filter(self, record):
        # Suppress logs for Gradio queue polling endpoints
        message = record.getMessage()
        if '/gradio_api/queue/data' in message or '/gradio_api/queue/join' in message:
            return False
        return True

def main():
    # Cache platform check
    is_windows = platform.system() == "Windows"
    
    # MCP Server Integration (optional - for Cursor debugging)
    mcp_enabled = os.environ.get('ENABLE_MCP_SERVER', '0') == '1'
    mcp_available = False
    try:
        from modules import mcp_server
        mcp_available = True
    except ImportError:
        pass
    
    # Create Main FastAPI App
    app = FastAPI()
    
    # Create UI and initialize engines (Gradio App)
    demo, runner, tagging_runner = app_module.create_ui()
    
    # Setup MCP server if enabled
    if mcp_available and mcp_enabled:
        mcp_server.set_runners(runner, tagging_runner)
        mcp_server.start_mcp_server_background()
        print("MCP Server: Started in background for debugging access")
    
    # Define allowed paths
    allowed_paths = [os.path.abspath("."), os.path.abspath("thumbnails")]
    if is_windows:
        allowed_paths.append("D:/")
    else:
        allowed_paths.append("/mnt/")
        
    print(f"Starting WebUI on {platform.system()}...")
    
    # Configure server endpoints using the FastAPI app directly
    app_module.setup_server_endpoints(app)
    
    # Mount Gradio App onto FastAPI
    # This creates a completely new routing structure where Gradio sits at /
    # and our custom endpoints sit at /source-image etc.
    app = gr.mount_gradio_app(app, demo, path="/", allowed_paths=allowed_paths)
    
    # Apply logging filter to suppress repetitive Gradio queue polling messages
    logging.getLogger("uvicorn.access").addFilter(SuppressGradioQueueFilter())
    
    # Create lock file
    import json
    import atexit
    
    lock_file = "webui.lock"
    try:
        with open(lock_file, "w") as f:
            json.dump({"pid": os.getpid(), "port": 7860}, f)
    except Exception as e:
        print(f"Warning: Could not create lock file: {e}")
        
    def remove_lock():
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except:
            pass
            
    atexit.register(remove_lock)

    # Launch using Uvicorn
    # Note: inbrowser=False is default for uvicorn, handled by user opening browser
    print("Launching Uvicorn server at http://127.0.0.1:7860")
    try:
        uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")
    finally:
        remove_lock()

if __name__ == "__main__":
    main()
