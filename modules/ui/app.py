"""
Main application orchestrator for the WebUI.

This module serves as the central hub for building the Gradio-based WebUI. It:
- Initializes database and configuration
- Creates shared state components (page, paths, image details)
- Instantiates tab modules and wires cross-tab navigation
- Configures server endpoints (RAW preview API)
- Sets up background monitoring for scoring and tagging jobs

The create_ui() function returns the Gradio Blocks instance along with runner
instances for external use (e.g., MCP server integration).
"""
import os
import platform
import gradio as gr
from pathlib import Path
from modules import scoring, db, tagging, config, clustering, thumbnails, utils, culling, pipeline_orchestrator
from modules.ui import assets, navigation, common
from modules.ui.tabs import (
    pipeline,
    gallery,
    settings as settings_tab
)
from modules.selection_runner import SelectionRunner
from modules import phase_executors

# Cache platform check
IS_WINDOWS = platform.system() == "Windows"



def create_ui():
    """Main function to build the WebUI."""
    # Initialize DB and Config
    db.init_db()
    app_config = config.load_config()
    
    # Initialize Engines
    runner = scoring.ScoringRunner()
    tagging_runner = tagging.TaggingRunner()
    selection_runner = SelectionRunner()

    orchestrator = pipeline_orchestrator.PipelineOrchestrator(
        scoring_runner=runner,
        tagging_runner=tagging_runner,
        selection_runner=selection_runner
    )
    recovery_info = orchestrator.recover_interrupted_jobs()
    app_config["job_recovery"] = recovery_info

    # Register phase executors (binds phase codes to runner logic)
    phase_executors.register_all(
        scoring_runner=runner,
        tagging_runner=tagging_runner,
        selection_runner=selection_runner,
    )
    
    # UI Elements from Assets
    tree_js = assets.get_tree_js()
    custom_css = assets.get_css()
    
    favicon_links = """
<link rel="icon" href="/favicon.ico" sizes="any">
"""
    with gr.Blocks(title="Image Scoring WebUI", css=custom_css, head=tree_js + favicon_links) as demo:
        gr.Markdown("# Image Scoring WebUI")
        
        # Shared States
        current_page = gr.State(1)
        current_paths = gr.State([])
        image_details = gr.State({})
        shared_state = (current_page, current_paths, image_details)
        current_folder_state = gr.State(None)
        current_stack_state = gr.State(None)
        
        # Status Polling Timer
        status_timer = gr.Timer(value=2.0)

        
        with gr.Tabs() as main_tabs:
            # 1. Pipeline Tab
            pipeline_components = pipeline.create_tab(
                app_config,
                scoring_runner=runner,
                tagging_runner=tagging_runner,
                selection_runner=selection_runner,
                orchestrator=orchestrator
            )
            
            # 2. Gallery Tab
            gallery_components = gallery.create_tab(shared_state, current_folder_state, current_stack_state, runner, tagging_runner, app_config)
            
            # 3. Settings Tab
            settings_components = settings_tab.create_tab(app_config)
            
        # Monitor Loop
        def monitor_status_wrapper(selected_folder):
            # Pass the currently selected folder from the Pipeline tree to update cards
            res = pipeline.get_status_update(runner, tagging_runner, selection_runner, orchestrator, selected_folder)
            return list(res)

        monitor_outputs = [
            pipeline_components["stepper_html"],
            pipeline_components["scoring_card_html"],
            pipeline_components["culling_card_html"],
            pipeline_components["keywords_card_html"],
            pipeline_components["monitor_html"],
            pipeline_components["console_output"],
            pipeline_components["run_all_btn"],
            pipeline_components["stop_all_btn"],
            pipeline_components["scoring_run_btn"],
            pipeline_components["culling_run_btn"],
            pipeline_components["keywords_run_btn"]
        ]

        status_timer.tick(
            fn=monitor_status_wrapper,
            inputs=[pipeline_components.get("selected_path")],
            outputs=monitor_outputs
        )

    return (
        demo,
        runner,
        tagging_runner,
        selection_runner,
        orchestrator,
        pipeline_components,
        gallery_components,
        settings_components,
        main_tabs,
    )

import re
import time
from collections import defaultdict

# --- Rate limiting ---
_rate_limits: dict = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 10

def _check_rate_limit(endpoint: str):
    """Simple in-memory rate limiter per endpoint."""
    from fastapi import HTTPException
    now = time.time()
    _rate_limits[endpoint] = [t for t in _rate_limits[endpoint] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limits[endpoint]) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _rate_limits[endpoint].append(now)

# --- Path validation ---
_ALLOWED_IMAGE_ROOTS = None

def _validate_file_path(file_path: str) -> str:
    """Validate and resolve a file path, rejecting traversal attempts."""
    from fastapi import HTTPException
    if ".." in file_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    resolved = os.path.realpath(file_path)

    global _ALLOWED_IMAGE_ROOTS
    if _ALLOWED_IMAGE_ROOTS is None:
        _ALLOWED_IMAGE_ROOTS = config.get_config_value("allowed_paths", [])
        _ALLOWED_IMAGE_ROOTS.extend(config.get_default_allowed_paths())

    if _ALLOWED_IMAGE_ROOTS and not any(
        resolved.startswith(os.path.realpath(root)) for root in _ALLOWED_IMAGE_ROOTS
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    return resolved

# --- SQL query validation ---
_SQL_FORBIDDEN_PATTERNS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXECUTE|INTO|GRANT|REVOKE)\b',
    re.IGNORECASE
)


def setup_server_endpoints(fastapi_app, scoring_runner=None, tagging_runner=None, clustering_runner=None, selection_runner=None):
    """Configures FastAPI endpoints for the Gradio app."""

    # Setup REST API endpoints
    from modules import api
    api.set_runners(scoring_runner, tagging_runner, clustering_runner, selection_runner)
    api_router = api.create_api_router()
    fastapi_app.include_router(api_router)

    @fastapi_app.on_event("shutdown")
    async def _shutdown_dispatcher():
        api.stop_dispatcher()

    @fastapi_app.get("/manifest.json")
    async def manifest_endpoint():
        """Serve a minimal web app manifest to prevent 404 errors."""
        from fastapi.responses import JSONResponse
        return JSONResponse({
            "name": "Image Scoring WebUI",
            "short_name": "Image Scoring",
            "start_url": "/app",
            "display": "standalone",
            "theme_color": "#000000",
            "background_color": "#ffffff"
        })
    
    @fastapi_app.get("/api/raw-preview")
    async def raw_preview_endpoint(path: str):
        import urllib.parse
        from fastapi.responses import Response
        from fastapi import HTTPException
        import io
        
        try:
            file_path = urllib.parse.unquote(path)
            # Conversion logic using unified resolver
            file_path = utils.resolve_file_path(file_path) or utils.convert_path_to_local(file_path)
            file_path = _validate_file_path(file_path)

            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="File not found")

            ext = Path(file_path).suffix.lower()
            if ext not in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']:
                raise HTTPException(status_code=400, detail="Unsupported format")
            
            img = thumbnails.extract_embedded_jpeg(file_path, min_size=1000)
            if img is None:
                raise HTTPException(status_code=500, detail="Extraction failed")
            
            jpeg_bytes = io.BytesIO()
            img.save(jpeg_bytes, format='JPEG', quality=90)
            jpeg_bytes.seek(0)
            
            return Response(
                content=jpeg_bytes.read(),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=3600"}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @fastapi_app.post("/api/query")
    async def query_endpoint(payload: dict):
        """
        Executes a read-only SQL query against the database.
        Payload: {"query": "SELECT ...", "parameters": {"@param": "value"}}
        """
        from fastapi import HTTPException
        import sqlite3
        
        query = payload.get("query")
        parameters = payload.get("parameters", {})
        
        # Security checks
        if not query or not query.strip().upper().startswith("SELECT"):
             raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")
        if _SQL_FORBIDDEN_PATTERNS.search(query):
             raise HTTPException(status_code=400, detail="Query contains forbidden keywords")
        if ";" in query:
             raise HTTPException(status_code=400, detail="Multi-statement queries not allowed")

        try:
            conn = db.get_db()
            # Use dict factory for JSON serialization
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            c = conn.cursor()
            
            # Execute
            c.execute(query, parameters)
            rows = c.fetchall()
            conn.close()
            
            return rows
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @fastapi_app.get("/source-image")
    async def source_image_endpoint(path: str):
        """
        Serves full-resolution source images for fullscreen display.
        For RAW files, generates high-quality JPEG preview on-the-fly.
        For regular images, serves the original file.
        Handles WSL->Windows path conversion.
        """
        import urllib.parse
        from fastapi.responses import Response, FileResponse
        from fastapi import HTTPException
        import io
        
        try:
            file_path = urllib.parse.unquote(path)

            # Convert WSL path to Windows path using resolution logic
            resolved = utils.resolve_file_path(file_path)
            if resolved:
                file_path = resolved
            else:
                # Fallback to conversion if resolve failed
                file_path = utils.convert_path_to_local(file_path)
            file_path = _validate_file_path(file_path)

            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="File not found")
            
            ext = Path(file_path).suffix.lower()
            is_raw = ext in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']
            
            if is_raw:
                # For RAW files, generate or extract high-quality preview
                # Try embedded JPEG first (fast and often full resolution)
                img = thumbnails.extract_embedded_jpeg(file_path, min_size=1000)
                
                # If embedded JPEG is available and large enough, use it
                if img and img.width > 1000:
                    jpeg_bytes = io.BytesIO()
                    img.save(jpeg_bytes, format='JPEG', quality=95)
                    jpeg_bytes.seek(0)
                    return Response(
                        content=jpeg_bytes.read(),
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                
                # Fallback: Try to generate preview using thumbnails module
                # This will do full RAW decode if needed (slower but higher quality)
                preview_path = thumbnails.generate_preview(file_path)
                if preview_path and os.path.exists(preview_path):
                    return FileResponse(
                        preview_path,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                
                # Last resort: try embedded JPEG even if smaller
                if img:
                    jpeg_bytes = io.BytesIO()
                    img.save(jpeg_bytes, format='JPEG', quality=95)
                    jpeg_bytes.seek(0)
                    return Response(
                        content=jpeg_bytes.read(),
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                
                raise HTTPException(status_code=500, detail="Failed to generate RAW preview")
            else:
                # For regular images, serve the original file
                # Determine media type based on extension
                media_types = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                    '.bmp': 'image/bmp',
                    '.tiff': 'image/tiff',
                    '.tif': 'image/tiff'
                }
                media_type = media_types.get(ext, 'image/jpeg')
                
                return FileResponse(
                    file_path,
                    media_type=media_type,
                    headers={"Cache-Control": "public, max-age=3600"}
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
