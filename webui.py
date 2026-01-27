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
    
    # Create Main FastAPI App with comprehensive OpenAPI documentation
    app = FastAPI(
        title="Image Scoring WebUI API",
        description="""
        REST API for the Image Scoring WebUI application.
        
        This API provides programmatic access to image quality assessment and tagging operations.
        
        ## Features
        
        - **Image Scoring**: Multi-model AI quality assessment (SPAQ, AVA, KonIQ, PaQ2PiQ, LIQE)
        - **Image Tagging**: Automatic keyword extraction using CLIP
        - **Caption Generation**: BLIP-based image captioning
        - **Job Management**: Start, stop, and monitor batch operations
        - **Status Monitoring**: Real-time progress tracking
        
        ## Authentication
        
        Currently, the API does not require authentication. Consider adding authentication
        for production deployments.
        
        ## Base URL
        
        All endpoints are prefixed with `/api`. The base URL is:
        - Development: `http://127.0.0.1:7860/api`
        - Production: `http://your-server:7860/api`
        
        ## OpenAPI Schema
        
        The complete OpenAPI schema is available at:
        - JSON: `/openapi.json`
        - YAML: `/openapi.yaml`
        - Interactive Docs: `/docs` (Swagger UI)
        - Alternative Docs: `/redoc` (ReDoc)
        
        ## LLM Agent Usage
        
        LLM agents can use this API by:
        1. Reading the OpenAPI schema from `/openapi.json`
        2. Using the schema to understand available endpoints and request/response formats
        3. Making HTTP requests to trigger operations and monitor status
        
        All endpoints return JSON responses following REST conventions.
        """,
        version="1.0.0",
        contact={
            "name": "Image Scoring WebUI",
            "url": "https://github.com/your-repo/image-scoring"
        },
        license_info={
            "name": "MIT",
        },
        openapi_tags=[
            {
                "name": "Image Scoring API",
                "description": "Endpoints for image quality assessment and scoring operations."
            },
            {
                "name": "Tagging API",
                "description": "Endpoints for image tagging and keyword extraction."
            },
            {
                "name": "General API",
                "description": "General endpoints for health checks, status, and job management."
            }
        ]
    )
    
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
    app_module.setup_server_endpoints(app, runner, tagging_runner)
    
    # Mount Gradio App onto FastAPI
    # This creates a completely new routing structure where Gradio sits at /
    # and our custom endpoints sit at /source-image etc.
    app = gr.mount_gradio_app(app, demo, path="/", allowed_paths=allowed_paths, favicon_path="static/favicon.ico")
    
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
