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
from modules import scoring, db, tagging, config, clustering, thumbnails, utils, culling
from modules.ui import assets, navigation, common
from modules.ui.tabs import (
    scoring as scoring_tab,
    tagging as tagging_tab,
    folder_tree,
    stacks as stacks_tab,
    settings as settings_tab,
    culling as culling_tab,
    selection as selection_tab,
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
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/favicon-180.png">
"""
    with gr.Blocks(title="Image Scoring WebUI", css=custom_css, head=tree_js + favicon_links) as demo:
        gr.Markdown("# Image Scoring WebUI")
        
        # Shared States
        # Status Polling Timer
        status_timer = gr.Timer(value=1.0)

        
        with gr.Tabs() as main_tabs:
            # 1. Folder Tree Tab (Default) — receives runners for direct job launch
            folder_tree_components = folder_tree.create_tab(
                app_config,
                scoring_runner=runner,
                tagging_runner=tagging_runner,
                selection_runner=selection_runner,
            )
            
            # 2. Scoring Tab
            scoring_components = scoring_tab.create_tab(runner, app_config)
            
            # 3. Keywords Tab
            tagging_components = tagging_tab.create_tab(tagging_runner, app_config)
            
            # 4. Stacks Tab (legacy - hidden when selection.legacy_tabs_enabled is False)
            legacy_enabled = app_config.get("selection", {}).get("legacy_tabs_enabled", False)
            stacks_components = None
            if legacy_enabled:
                stacks_components = stacks_tab.create_stacks_tab()
            
            # 5. Culling Tab (legacy - hidden when selection.legacy_tabs_enabled is False)
            culling_components = None
            if legacy_enabled:
                culling_components = culling_tab.create_tab(app_config)
            
            # 6. Selection Tab
            selection_components = selection_tab.create_tab(selection_runner, app_config)
            
            # 7. Settings Tab
            settings_tab.create_tab(app_config)
            
        # --- Cross-Tab Navigation Wiring ---
        # (Folder Tree Run buttons now launch jobs directly — no tab navigation needed)

        # Monitor Loop
        def monitor_status_wrapper():
            s_res = scoring_tab.get_status_update(runner)
            t_res = tagging_tab.get_status_update(tagging_runner)
            stacks_res = stacks_tab.get_status_update() if stacks_components else []
            sel_res = selection_tab.get_status_update(selection_runner)
            return list(s_res) + list(t_res) + list(stacks_res) + list(sel_res)

        monitor_outputs = [
            scoring_components['log_output'], scoring_components['status_html'],
            scoring_components['run_btn'], scoring_components['stop_btn'], scoring_components['fix_btn'],
            tagging_components['log_output'], tagging_components['status_html'],
            tagging_components['run_btn'], tagging_components['stop_btn'],
        ]
        if stacks_components:
            monitor_outputs.extend([stacks_components['status_html'], stacks_components['run_btn'], stacks_components['refresh_btn']])
        monitor_outputs.extend([
            selection_components['log_output'], selection_components['status_html'],
            selection_components['run_btn'], selection_components['stop_btn'],
        ])

        status_timer.tick(
            fn=monitor_status_wrapper,
            inputs=[],
            outputs=monitor_outputs
        )

    return demo, runner, tagging_runner, selection_runner

def setup_server_endpoints(fastapi_app, scoring_runner=None, tagging_runner=None):
    """Configures FastAPI endpoints for the Gradio app."""
    
    # Setup REST API endpoints
    from modules import api
    api.set_runners(scoring_runner, tagging_runner)
    api_router = api.create_api_router()
    fastapi_app.include_router(api_router)
    
    @fastapi_app.get("/manifest.json")
    async def manifest_endpoint():
        """Serve a minimal web app manifest to prevent 404 errors."""
        from fastapi.responses import JSONResponse
        return JSONResponse({
            "name": "Image Scoring WebUI",
            "short_name": "Image Scoring",
            "start_url": "/",
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
        
        # Basic security check - only allow SELECT
        if not query or not query.strip().upper().startswith("SELECT"):
             raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")

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
