import os
import platform
import warnings
import logging
from contextlib import asynccontextmanager
import gradio as gr
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from modules.ui import app as app_module
from modules.events import event_manager

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
    # Load config to check for debug mode
    try:
        from modules import config
        app_config = config.load_config()
        debug_mode = app_config.get('debug', False)
        
        # Configure logging
        log_level = logging.DEBUG if debug_mode else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler("webui.log", mode='a')
            ]
        )
        
        if debug_mode:
            print("🐞 Debug mode enabled. Performance metrics will be logged to webui.log")
            logging.getLogger("image_scoring.performance").setLevel(logging.DEBUG)
    except Exception as e:
        print(f"Error configuring logging: {e}")
        debug_mode = False

    # Cache platform check
    is_windows = platform.system() == "Windows"
    
    # MCP Server Integration (optional - for Cursor debugging)
    # Default ON for local development; set ENABLE_MCP_SERVER=0 to disable.
    mcp_enabled = os.environ.get('ENABLE_MCP_SERVER', '1') == '1'
    mcp_available = False
    try:
        from modules import mcp_server
        mcp_available = True
    except ImportError:
        pass
    
    print(f"MCP Server: enabled={mcp_enabled} available={mcp_available}")
    if mcp_enabled and not mcp_available:
        print("MCP Server: not available (missing dependency). Install with: pip install mcp")
    
    mcp_mount_error: str | None = None

    @asynccontextmanager
    async def lifespan(app):
        import asyncio
        loop = asyncio.get_running_loop()
        event_manager.set_loop(loop)
        print("EventManager: Event loop attached.")
        yield

    # Create Main FastAPI App with comprehensive OpenAPI documentation
    app = FastAPI(
        lifespan=lifespan,
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
    
    # Add CORS middleware to allow requests from the Electron/Vite frontend
    # Note: allow_origins=["*"] with allow_credentials=True is invalid in Starlette/FastAPI
    origins = [
        "http://127.0.0.1:7860",
        "http://localhost:7860",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/mcp-status")
    def mcp_status():
        return {
            "enabled": mcp_enabled,
            "available": mcp_available,
            "mount_error": mcp_mount_error,
            "expected_sse_url": "http://127.0.0.1:7860/mcp/sse",
        }
    
    # Create UI and initialize engines (Gradio App)
    import modules.clustering as clustering
    clustering_runner = clustering.ClusteringRunner()
    demo, runner, tagging_runner, selection_runner, orchestrator = app_module.create_ui()

    
    # Setup MCP server if enabled
    mcp_sse_app = None
    if mcp_available and mcp_enabled:
        mcp_server.set_runners(runner, tagging_runner, clustering_runner)
        try:

            # Expose MCP over HTTP/SSE so Cursor can connect via:
            #   http://localhost:7860/mcp/sse
            # NOTE: we mount *after* Gradio is mounted; gr.mount_gradio_app()
            # may wrap/replace the FastAPI app instance.
            mcp_sse_app = mcp_server.create_mcp_sse_app(mount_path="/mcp")
        except Exception as e:
            mcp_mount_error = str(e)
            print(f"MCP Server: Failed to mount SSE endpoint: {e}")
    
    # Define allowed paths from config
    system_config = config.get_config_section('system')
    config_allowed = system_config.get('allowed_paths', [])
    
    allowed_paths = []
    if config_allowed:
        allowed_paths.extend(config_allowed)
        # Always ensure current dir and thumbnails are allowed
        allowed_paths.append(os.path.abspath("."))
        allowed_paths.append(os.path.abspath("thumbnails"))
    else:
        # Fallback to dynamic defaults if config is empty
        allowed_paths = config.get_default_allowed_paths()
        
    print(f"Starting WebUI on {platform.system()}...")
    
    # Configure server endpoints using the FastAPI app directly
    app_module.setup_server_endpoints(app, runner, tagging_runner, clustering_runner, selection_runner)
    
    # Mount MCP SSE endpoints (if enabled) onto the final app instance.
    # MUST be mounted BEFORE Gradio to avoid being shadowed by Gradio's catch-all route at /
    if mcp_sse_app is not None:
        app.mount("/mcp", mcp_sse_app)
        print("MCP Server: SSE endpoint mounted at /mcp/sse")
        try:
            has_mcp_mount = any(getattr(r, "path", None) == "/mcp" for r in app.routes)
            print(f"MCP Server: mount_registered={has_mcp_mount}")
        except Exception:
            pass
    
    # WebSocket Endpoint for Real-time Events
    @app.websocket("/ws/updates")
    async def websocket_endpoint(websocket: WebSocket):
        await event_manager.connect(websocket)
        try:
            while True:
                # Keep connection alive and listen for any incoming messages (though we mainly push)
                # We can also handle simple pings or subscription requests here if needed
                data = await websocket.receive_text()
                # Echo back or handle commands if necessary
                pass 
        except WebSocketDisconnect:
            event_manager.disconnect(websocket)
        except Exception as e:
            logging.error(f"WebSocket error: {e}")
            event_manager.disconnect(websocket)

    # Mount Gradio App onto FastAPI
    # This creates a completely new routing structure where Gradio sits at /
    # and our custom endpoints sit at /source-image etc.
    app = gr.mount_gradio_app(app, demo, path="/", allowed_paths=allowed_paths, favicon_path="static/favicon.ico")
    
    # Apply logging filter to suppress repetitive Gradio queue polling messages


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

