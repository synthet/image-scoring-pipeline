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
    gallery as gallery_tab, 
    stacks as stacks_tab, 
    settings as settings_tab,
    culling as culling_tab
)

# Cache platform check
IS_WINDOWS = platform.system() == "Windows"

# Component count constants (must match common.get_empty_details())
DETAIL_OUTPUTS_COUNT = 19  # From common.get_empty_details()
GALLERY_SIGNAL_COUNT = 4   # current_page, gallery, page_label, current_paths
TOTAL_LOAD_OUTPUTS = DETAIL_OUTPUTS_COUNT + GALLERY_SIGNAL_COUNT  # 23

def create_ui():
    """Main function to build the WebUI."""
    # Initialize DB and Config
    db.init_db()
    app_config = config.load_config()
    
    # Initialize Engines
    runner = scoring.ScoringRunner()
    tagging_runner = tagging.TaggingRunner()
    
    # UI Elements from Assets
    tree_js = assets.get_tree_js()
    custom_css = assets.get_css()
    
    with gr.Blocks(title="Image Scoring WebUI", css=custom_css, head=tree_js) as demo:
        gr.Markdown("# Image Scoring WebUI")
        
        # Shared States
        # IMPORTANT: All gr.State modifications must be done via Gradio events to maintain
        # synchronization across tabs. Direct assignment (e.g., state.value = new_value) will
        # not trigger UI updates and can cause desynchronization.
        #
        # State components:
        # - current_page: Current page number in gallery (int)
        # - current_paths: List of file paths currently displayed in gallery (List[str])
        # - image_details: Dictionary containing metadata for currently selected image (dict)
        # - current_folder_state: Currently filtered folder path or None (str | None)
        current_page = gr.State(value=1)
        current_paths = gr.State(value=[])
        image_details = gr.State(value={})
        current_folder_state = gr.State(value=None)
        current_stack_state = gr.State(value=None)
        
        # Polling Timer for status
        status_timer = gr.Timer(value=1.0)
        
        with gr.Tabs() as main_tabs:
            # 1. Scoring Tab
            scoring_components = scoring_tab.create_tab(runner, app_config)
            
            # 2. Keywords Tab
            tagging_components = tagging_tab.create_tab(tagging_runner, app_config)
            
            # 3. Gallery Tab
            gallery_components = gallery_tab.create_tab(
                (current_page, current_paths, image_details), 
                current_folder_state, 
                current_stack_state,
                runner, 
                tagging_runner, 
                app_config
            )
            
            gallery = gallery_components['gallery']
            folder_context_group = gallery_components['folder_context_group']
            folder_display = gallery_components['folder_display']
            page_label = gallery_components['page_label']
            detail_outputs = gallery_components['detail_outputs']
            filter_inputs = gallery_components['filter_inputs']
            update_gallery = gallery_components['update_gallery_fn']
            
            # Unpack detail outputs for wiring
            (res_info, d_score_gen, d_score_weighted, d_score_models, d_details_state, 
             delete_btn, d_title, d_desc, d_keywords, d_rating, d_label, save_status, 
             gallery_selected_path, d_culling_status, fix_btn, fix_status, 
             rerun_score_btn, rerun_tags_btn, current_selection_index) = detail_outputs

            # 4. Folder Tree Tab
            folder_tree_components = folder_tree.create_tab(app_config)
            
            # 5. Stacks Tab
            stacks_components = stacks_tab.create_stacks_tab()
            
            # 6. Culling Tab
            culling_components = culling_tab.create_tab(app_config)
            
            # 7. Settings Tab
            settings_tab.create_tab(app_config)
            
        # --- Cross-Tab Navigation Wiring ---
        
        # Folder Tree -> Gallery
        folder_tree_components['open_gallery_btn'].click(
            fn=lambda *args: navigation.open_folder_in_gallery(*args, update_gallery_fn=update_gallery),
            inputs=[folder_tree_components['selected_path'], *filter_inputs[:-2]], # Exclude folder_state and stack_state
            outputs=[main_tabs, current_folder_state, current_stack_state, folder_context_group, folder_display, current_page, gallery, page_label, current_paths] + detail_outputs
        )
        
        # Folder Tree -> Stacks
        folder_tree_components['open_stacks_btn'].click(
            fn=navigation.open_folder_in_stacks,
            inputs=[folder_tree_components['selected_path']],
            outputs=[main_tabs, stacks_components['input_dir']]
        )
        
        # Folder Tree -> Keywords
        folder_tree_components['open_keywords_btn'].click(
            fn=navigation.open_folder_in_keywords,
            inputs=[folder_tree_components['selected_path']],
            outputs=[main_tabs, tagging_components['input_dir']]
        )
        
        # Stacks -> Gallery
        # Stacks -> Gallery
        # Inputs: stack_id, sort_by, order, (filters...), update_fn
        # filter_inputs: [sort, order, rating, label, keyword, gen, aes, tech, start, end, folder, stack]
        # We use Stacks tab sort/order, keeping other filters from Gallery
        stacks_components["open_gallery_btn"].click(
            fn=lambda stack_id, sort, order, *args: navigation.open_stack_in_gallery(
                stack_id, sort, order, *args, update_gallery_fn=update_gallery
            ),
            inputs=[stacks_components["current_stack_id"], stacks_components["sort_by"], stacks_components["order"]] + filter_inputs[2:-2],
            outputs=[main_tabs, current_folder_state, current_stack_state, folder_context_group, folder_display, current_page, gallery, page_label, current_paths] + detail_outputs
        )

        # --- Initialization Logic ---
        
        def load_initial_gallery():
            """Load the first page of images when the app starts."""
            default_sort = app_config.get('ui', {}).get('default_sort', 'score_general')
            default_order = app_config.get('ui', {}).get('default_order', 'desc')
            
            result = (1, *update_gallery(
                page=1,
                sort_by=default_sort,
                sort_order=default_order,
                rating_filter=None,
                label_filter=None,
                keyword_filter=None,
                min_gen=0.0, min_aes=0.0, min_tech=0.0,
                start_date=None, end_date=None,
                folder=None
            ))
            return result
        
        def load_initial_gallery_with_paths():
            return load_initial_gallery()
        
        # Sync outputs: current_page (1) + gallery signals (3) + detail_outputs (19) = 23
        # Using constants to ensure consistency across all event handlers
        load_outputs = [current_page, gallery, page_label, current_paths] + detail_outputs
        assert len(load_outputs) == TOTAL_LOAD_OUTPUTS, f"Expected {TOTAL_LOAD_OUTPUTS} outputs, got {len(load_outputs)}"
        
        demo.load(fn=load_initial_gallery_with_paths, inputs=[], outputs=load_outputs)

        # Monitor Loop
        def monitor_status_wrapper():
            s_res = scoring_tab.get_status_update(runner)
            t_res = tagging_tab.get_status_update(tagging_runner)
            stacks_res = stacks_tab.get_status_update()
            return list(s_res) + list(t_res) + list(stacks_res)

        status_timer.tick(
            fn=monitor_status_wrapper,
            inputs=[],
            outputs=[
                scoring_components['log_output'], scoring_components['status_html'], 
                scoring_components['run_btn'], scoring_components['stop_btn'], scoring_components['fix_btn'],
                tagging_components['log_output'], tagging_components['status_html'], 
                tagging_components['run_btn'], tagging_components['stop_btn'],
                stacks_components['status_html'], stacks_components['run_btn'], stacks_components['refresh_btn']
            ]
        )

    return demo, runner, tagging_runner

def setup_server_endpoints(fastapi_app):
    """Configures FastAPI endpoints for the Gradio app."""
    
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
