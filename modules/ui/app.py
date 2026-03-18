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
import json
from datetime import datetime
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


def _safe_parse_json(raw_value):
    if not raw_value:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    try:
        return json.loads(raw_value)
    except Exception:
        return {}


def _format_timestamp(value):
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _format_duration_seconds(started_at, ended_at):
    if not started_at:
        return "—"
    end_value = ended_at or datetime.now()
    if isinstance(started_at, str) or isinstance(end_value, str):
        return "—"
    delta = max(0, int((end_value - started_at).total_seconds()))
    hours, remainder = divmod(delta, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _normalize_run_status(status, failed_stages):
    status_value = (status or "unknown").lower()
    if status_value == "failed":
        return "Failed"
    if status_value in {"interrupted", "cancelled"}:
        return "Needs Attention"
    if status_value == "running":
        return "Running"
    if status_value == "queued":
        return "Queued"
    if status_value == "blocked":
        return "Blocked"
    if failed_stages > 0:
        return "Needs Attention"
    if status_value in {"completed", "done"}:
        return "Completed"
    return status_value.title()


def _compute_progress(completed_stages, total_stages):
    if not total_stages:
        return "0%"
    pct = int((completed_stages / total_stages) * 100)
    return f"{pct}% ({completed_stages}/{total_stages})"





def _build_stage_graph_html(phases):
    if not phases:
        return "<div class='text-secondary'>No StageRun data.</div>"
    nodes = []
    for phase in phases:
        state = (phase.get("state") or "pending").lower()
        phase_code = phase.get("phase_code") or "unknown"
        stage_id = phase.get("id")
        deep_link = f"/app?stage_id={stage_id}" if stage_id else "#"
        nodes.append(
            f"<div style='padding:8px;border:1px solid #ddd;border-radius:6px;'>"
            f"<strong>{phase_code}</strong>"
            f"<div>Status: {state.title()}</div>"
            f"<div><a href='{deep_link}'>Stage link</a></div>"
            f"</div>"
        )
    return "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;'>" + "".join(nodes) + "</div>"


def _build_step_timeline_html(phases):
    if not phases:
        return "<div class='text-secondary'>No StepRun timeline data.</div>"
    rows = ["<ol style='margin:0;padding-left:20px;'>"]
    for phase in phases:
        state = (phase.get("state") or "pending").title()
        started = _format_timestamp(phase.get("started_at"))
        done = _format_timestamp(phase.get("completed_at"))
        rows.append(
            f"<li><strong>{phase.get('phase_code')}</strong> — {state} "
            f"<span style='color:#666'>(start: {started}, end: {done})</span></li>"
        )
    rows.append("</ol>")
    return "".join(rows)


def _build_navigation_left_html(run_rows):
    targets = {}
    for run in run_rows:
        target_type = run.get("target_type") or "unknown"
        targets[target_type] = targets.get(target_type, 0) + 1
    target_items = "".join([f"<li>{k}: {v}</li>" for k, v in sorted(targets.items())]) or "<li>No targets</li>"
    return (
        "<div><h4>Targets</h4><ul>" + target_items + "</ul>"
        "<h4>Saved Filters</h4><ul>"
        "<li><a href='/app?wf_filter=Running'>Running</a></li>"
        "<li><a href='/app?wf_filter=Queued'>Queued</a></li>"
        "<li><a href='/app?wf_filter=Blocked'>Blocked</a></li>"
        "<li><a href='/app?wf_filter=Failed'>Failed</a></li>"
        "<li><a href='/app?wf_filter=Needs%20Attention'>Needs Attention</a></li>"
        "<li><a href='/app?wf_filter=Completed'>Completed</a></li>"
        "</ul><h4>Workflow Templates</h4><ul>"
        "<li>Full Pipeline (index → metadata → scoring → culling → keywords)</li>"
        "<li>Metadata + Scoring</li>"
        "<li>Culling + Keywords</li>"
        "</ul></div>"
    )


def _load_workflow_runs(filter_value="All", limit=200):
    jobs = db.get_jobs(limit=limit) or []
    normalized = []
    for row in jobs:
        payload = _safe_parse_json(row.get("queue_payload"))
        phase_rows = db.get_job_phases(row.get("id")) or []
        total = len(phase_rows)
        completed = len([p for p in phase_rows if (p.get("state") or "").lower() == "completed"])
        failed = len([p for p in phase_rows if (p.get("state") or "").lower() == "failed"])
        display_status = _normalize_run_status(row.get("status"), failed)
        run = {
            "id": row.get("id"),
            "status": display_status,
            "status_raw": row.get("status"),
            "queued_time": _format_timestamp(row.get("enqueued_at") or row.get("created_at")),
            "duration": _format_duration_seconds(row.get("started_at"), row.get("finished_at") or row.get("completed_at")),
            "target_type": (payload.get("target_type") if isinstance(payload, dict) else None) or row.get("job_type") or "unknown",
            "progress": _compute_progress(completed, total),
            "owner": (payload.get("actor") if isinstance(payload, dict) else None) or "system",
            "run_link": f"/app?run_id={row.get('id')}",
            "phases": phase_rows,
        }
        normalized.append(run)

    if filter_value and filter_value != "All":
        normalized = [r for r in normalized if r["status"] == filter_value]

    table_data = [[
        r["id"], r["status"], r["queued_time"], r["duration"], r["target_type"], r["progress"], r["owner"], r["run_link"]
    ] for r in normalized]
    return normalized, table_data


def _build_run_details_html(run):
    if not run:
        return "<div>Select a run to view StageRun graph and StepRun timeline.</div>"
    phases = run.get("phases") or []
    stage_graph = _build_stage_graph_html(phases)
    timeline = _build_step_timeline_html(phases)
    return (
        f"<div><h3>Run #{run.get('id')}</h3>"
        f"<p><strong>Status:</strong> {run.get('status')} | <strong>Target:</strong> {run.get('target_type')} | "
        f"<strong>Owner/Actor:</strong> {run.get('owner')}</p>"
        f"<p><a href='{run.get('run_link')}'>Deep link to run</a></p>"
        "<h4>StageRun Graph</h4>" + stage_graph +
        "<h4 style='margin-top:10px;'>StepRun Timeline</h4>" + timeline + "</div>"
    )

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
    with gr.Blocks(title="Image Scoring Runs", css=custom_css, head=tree_js + favicon_links) as demo:
        gr.Markdown("# Image Scoring Runs")
        
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

            with gr.Tab("Workflow Runs"):
                workflow_runs_state = gr.State([])
                selected_run_id_state = gr.State(None)
                with gr.Row():
                    with gr.Column(scale=2):
                        workflow_nav_html = gr.HTML("<div>Loading navigation shell...</div>")
                    with gr.Column(scale=6):
                        with gr.Row():
                            quick_filters = ["Running", "Queued", "Blocked", "Failed", "Needs Attention", "Completed"]
                            filter_buttons = [gr.Button(label, size="sm") for label in quick_filters]
                            clear_filter_btn = gr.Button("All", size="sm")
                        runs_table = gr.Dataframe(
                            headers=["Run ID", "Status", "Queued Time", "Duration", "Target Type", "Progress", "Owner/Actor", "Deep Link"],
                            datatype=["number", "str", "str", "str", "str", "str", "str", "str"],
                            interactive=False,
                            wrap=True,
                            row_count=12,
                            col_count=(8, "fixed"),
                            label="WorkflowRuns"
                        )
                    with gr.Column(scale=4):
                        run_details_html = gr.HTML("<div>Select a run to view details.</div>")

                def refresh_shell(filter_value="All"):
                    run_rows, table_rows = _load_workflow_runs(filter_value=filter_value)
                    nav_html = _build_navigation_left_html(run_rows)
                    return run_rows, table_rows, nav_html, "<div>Select a run to view StageRun graph and StepRun timeline.</div>", None

                def choose_run(table_data, run_rows, evt: gr.SelectData):
                    if evt is None or not evt.index:
                        return "<div>Select a run to view details.</div>", None
                    row_index = evt.index[0]
                    if row_index is None or row_index >= len(table_data):
                        return "<div>Select a run to view details.</div>", None
                    run_id = table_data[row_index][0]
                    selected = next((r for r in run_rows if r.get("id") == run_id), None)
                    return _build_run_details_html(selected), run_id

                demo.load(
                    fn=refresh_shell,
                    outputs=[workflow_runs_state, runs_table, workflow_nav_html, run_details_html, selected_run_id_state],
                )

                for idx, btn in enumerate(filter_buttons):
                    btn.click(
                        fn=lambda i=idx: refresh_shell(quick_filters[i]),
                        outputs=[workflow_runs_state, runs_table, workflow_nav_html, run_details_html, selected_run_id_state],
                    )

                clear_filter_btn.click(
                    fn=lambda: refresh_shell("All"),
                    outputs=[workflow_runs_state, runs_table, workflow_nav_html, run_details_html, selected_run_id_state],
                )

                runs_table.select(
                    fn=choose_run,
                    inputs=[runs_table, workflow_runs_state],
                    outputs=[run_details_html, selected_run_id_state],
                )
            
            # 2. Gallery Tab
            gallery_components = gallery.create_tab(shared_state, current_folder_state, current_stack_state, runner, tagging_runner, app_config)
            
            # 3. Settings Tab
            settings_components = settings_tab.create_tab(app_config)
            
        # Monitor Loop
        def monitor_status_wrapper(selected_folder, telemetry_state, collapse_noisy, pin_critical):
            # Pass the currently selected folder from the Pipeline tree to update cards
            res = pipeline.get_status_update(
                runner,
                tagging_runner,
                selection_runner,
                orchestrator,
                selected_folder,
                telemetry_state,
                collapse_noisy,
                pin_critical,
            )
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
            pipeline_components["keywords_run_btn"],
            pipeline_components["repair_index_meta_btn"],
            pipeline_components["run_metadata_btn"],
            pipeline_components["quick_start_html"],
            pipeline_components["telemetry_html"],
            pipeline_components["telemetry_state"],
        ]

        status_timer.tick(
            fn=monitor_status_wrapper,
            inputs=[
                pipeline_components.get("selected_path"),
                pipeline_components.get("telemetry_state"),
                pipeline_components.get("telemetry_collapse_noisy"),
                pipeline_components.get("telemetry_pin_critical"),
            ],
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

# Security helpers — re-exported from lightweight module so existing imports
# (e.g. ``from modules.ui.app import _check_rate_limit``) keep working.
from modules.ui.security import (          # noqa: F401
    _check_rate_limit,
    _validate_file_path,
    _SQL_FORBIDDEN_PATTERNS,
)


def setup_server_endpoints(fastapi_app, scoring_runner=None, tagging_runner=None, clustering_runner=None, selection_runner=None, orchestrator=None):
    """Configures FastAPI endpoints for the Gradio app."""

    # Setup REST API endpoints
    from modules import api
    api.set_runners(scoring_runner, tagging_runner, clustering_runner, selection_runner, orchestrator)
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
