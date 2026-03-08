import gradio as gr
from modules import db
from modules import ui_tree

# Cache for timer-based status updates to avoid unnecessary SSE pushes
_last_status_cache = {"state": None}


def _parse_phase_summary(folder_path):
    """
    Calls db.get_folder_phase_summary() and converts the list result
    into a dict keyed by phase code for easy lookup.

    Returns: (summary_by_code: dict, total_count: int)
      summary_by_code = {
        "indexing": {"status": ..., "done_count": ..., "total_count": ...},
        "scoring":  { ... },
        ...
      }
    """
    if not folder_path:
        return {}, 0

    summary_list = db.get_folder_phase_summary(folder_path)
    # summary_list is [{code, name, sort_order, status, done_count, total_count}, ...]
    summary_by_code = {}
    total_count = 0
    for item in summary_list:
        code = item.get("code", "")
        summary_by_code[code] = item
        # All phases report the same total_count (number of images in folder)
        tc = item.get("total_count", 0)
        if tc > total_count:
            total_count = tc

    return summary_by_code, total_count


def create_tab(app_config, scoring_runner, tagging_runner, selection_runner, orchestrator) -> dict:
    """Consolidated Pipeline tab containing Folder Tree, Progress Stepper, Phase Controls, and active job monitor."""
    components = {}

    with gr.Tab("Pipeline", id="pipeline"):
        with gr.Row(equal_height=False):
            # SIDEBAR
            with gr.Column(scale=1, min_width=300, elem_classes=["sidebar"]):
                gr.Markdown("### Folders")
                with gr.Row():
                    components["refresh_btn"] = gr.Button("Refresh", elem_classes=["secondary-btn"])

                components["tree_view"] = gr.HTML(
                    value=ui_tree.get_tree_html(),
                    elem_classes=["tree-container"]
                )
                # Must be visible=True for DOM rendering so JS selectFolder() can update it.
                # Hide with CSS (visible=False removes from DOM entirely).
                components["selected_path"] = gr.Textbox(
                    value="",
                    visible=True,
                    elem_id="folder_tree_selection",
                    elem_classes=["hidden-path-storage"],
                    container=False,
                    interactive=False,
                    show_label=False,
                )

                gr.HTML("<div class='section-divider'></div>")

                components["folder_summary_html"] = gr.HTML(
                    _build_folder_summary(None, 0)
                )
                components["open_gallery_btn"] = gr.Button("Open in Gallery", elem_classes=["success-btn"])

                gr.HTML("<div class='section-divider'></div>")

                gr.HTML(
                    """
                    <h3 class="legend-title">Legend</h3>
                    <div class="legend">
                        <span class="legend-item"><strong class="tree-icon done">D</strong> Done</span>
                        <span class="legend-item"><strong class="tree-icon partial">P</strong> Partial</span>
                        <span class="legend-item"><strong class="tree-icon failed">F</strong> Failed</span>
                        <span class="legend-item"><strong class="tree-icon empty">N</strong> Not Started</span>
                    </div>
                    """
                )

            # MAIN DASHBOARD
            with gr.Column(scale=3):
                # PANEL: Pipeline Progress
                with gr.Group(elem_classes=["panel"]):
                    gr.HTML(
                        """
                        <div class="panel-header">
                            <h2 class="panel-title">Pipeline Progress</h2>
                        </div>
                        """
                    )
                    with gr.Column(elem_classes=["panel-body"]):
                        components["stepper_html"] = gr.HTML(_build_pipeline_stepper_html(None))
                        with gr.Row(elem_classes=["pipeline-actions"]):
                            components["run_all_btn"] = gr.Button("Run All Pending", variant="primary", elem_classes=["primary-btn"])
                            components["stop_all_btn"] = gr.Button("Stop All", variant="stop", elem_classes=["danger-btn"])

                # PANEL: Phases (Card Grid)
                with gr.Group(elem_classes=["panel"]):
                    with gr.Row(elem_classes=["panel-body", "phase-grid"]):

                        # Scoring Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["scoring_card_html"] = gr.HTML(_build_phase_card_html("SCORING", "Not Started", 0, 0))
                            components["scoring_run_btn"] = gr.Button("Run Scoring", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["scoring_force"] = gr.Checkbox(label="Force Re-score", value=False)

                        # Culling Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["culling_card_html"] = gr.HTML(_build_phase_card_html("CULLING", "Not Started", 0, 0))
                            components["culling_run_btn"] = gr.Button("Run Culling", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["culling_force"] = gr.Checkbox(label="Force Re-run", value=False)

                        # Keywords Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["keywords_card_html"] = gr.HTML(_build_phase_card_html("KEYWORDS", "Not Started", 0, 0))
                            components["keywords_run_btn"] = gr.Button("Run Keywords", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["keywords_overwrite"] = gr.Checkbox(label="Overwrite Existing", value=False)
                                components["keywords_captions"] = gr.Checkbox(label="Generate Captions", value=False)

                # PANEL: Active Job Monitor
                with gr.Group(elem_classes=["panel", "monitor-card"]):
                    components["monitor_html"] = gr.HTML(_build_idle_html())
                    with gr.Accordion("Console Output", open=False):
                        components["console_output"] = gr.Textbox(
                            lines=12, label="", max_lines=12, interactive=False, elem_classes=["console-code"]
                        )

    # Wire up folder selection to update HTML rendering
    components["selected_path"].change(
        fn=_update_folder_selection,
        inputs=[components["selected_path"]],
        outputs=[
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"]
        ]
    )

    components["refresh_btn"].click(
        fn=ui_tree.get_tree_html,
        outputs=[components["tree_view"]]
    )

    # --- Run button handlers ---
    # All runners use start_batch(input_path, job_id, **kwargs)

    def _run_scoring(path, force):
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="scoring",
            job_type="scoring",
            queue_payload={"input_path": path, "skip_existing": not force},
        )

    def _run_culling(path, force):
        if not path:
            return
        job_id = db.create_job(path, phase_code="culling")
        selection_runner.start_batch(path, job_id, force_rescan=force)

    def _run_tagging(path, overwrite, captions):
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="keywords",
            job_type="tagging",
            queue_payload={"input_path": path, "overwrite": overwrite, "generate_captions": captions},
        )

    def _run_all_pending(path):
        if not path:
            return
        orchestrator.start(path)

    def _stop_all():
        orchestrator.stop()
        # Also stop individual runners in case they were started independently
        scoring_runner.stop()
        selection_runner.stop()
        tagging_runner.stop()

    components["scoring_run_btn"].click(
        fn=_run_scoring,
        inputs=[components["selected_path"], components["scoring_force"]],
        outputs=[]
    )
    components["culling_run_btn"].click(
        fn=_run_culling,
        inputs=[components["selected_path"], components["culling_force"]],
        outputs=[]
    )
    components["keywords_run_btn"].click(
        fn=_run_tagging,
        inputs=[components["selected_path"], components["keywords_overwrite"], components["keywords_captions"]],
        outputs=[]
    )
    components["run_all_btn"].click(
        fn=_run_all_pending,
        inputs=[components["selected_path"]],
        outputs=[]
    )
    components["stop_all_btn"].click(
        fn=_stop_all,
        inputs=[],
        outputs=[]
    )

    return components


def _update_folder_selection(folder_path: str):
    """Updates the static UI components when a new folder is selected."""
    if not folder_path:
        return (
            _build_folder_summary(None, 0),
            _build_pipeline_stepper_html(None),
            _build_phase_card_html("SCORING", "Not Started", 0, 0),
            _build_phase_card_html("CULLING", "Not Started", 0, 0),
            _build_phase_card_html("KEYWORDS", "Not Started", 0, 0),
        )

    summary_by_code, total_count = _parse_phase_summary(folder_path)

    sc = summary_by_code.get("scoring", {})
    cu = summary_by_code.get("culling", {})
    kw = summary_by_code.get("keywords", {})

    return (
        _build_folder_summary(folder_path, total_count),
        _build_pipeline_stepper_html(folder_path, summary_by_code, total_count),
        _build_phase_card_html("SCORING", sc.get("status", "not_started"), sc.get("done_count", 0), total_count),
        _build_phase_card_html("CULLING", cu.get("status", "not_started"), cu.get("done_count", 0), total_count),
        _build_phase_card_html("KEYWORDS", kw.get("status", "not_started"), kw.get("done_count", 0), total_count),
    )


def get_status_update(scoring_runner, tagging_runner, selection_runner, orchestrator, selected_folder):
    """Called regularly by the main app timer to update components."""
    # Process Orchestrator tick
    orchestrator.on_tick()

    is_running, mon_name, mon_msg, mon_cur, mon_tot, console_out = _unified_monitor_status(
        scoring_runner, tagging_runner, selection_runner
    )

    queued_jobs = db.get_queued_jobs(limit=5)

    if is_running:
        monitor_html = _build_monitor_html(mon_name, mon_msg, mon_cur, mon_tot, queued_jobs)
    else:
        monitor_html = _build_idle_html(queued_jobs)

    not_running = not is_running

    # Rebuild stepper/cards from current folder state
    res_summary, res_stepper, res_sc, res_cu, res_kw = _update_folder_selection(selected_folder)

    # Return order must match monitor_outputs in app.py:
    # stepper, scoring_card, culling_card, keywords_card,
    # monitor, console, run_all, stop_all, sc_run, cu_run, kw_run
    result = (
        res_stepper,
        res_sc,
        res_cu,
        res_kw,
        monitor_html,
        console_out,
        gr.update(interactive=not_running),  # run_all
        gr.update(interactive=is_running),   # stop_all
        gr.update(interactive=not_running),  # scoring_run
        gr.update(interactive=not_running),  # culling_run
        gr.update(interactive=not_running),  # keywords_run
    )

    # Skip SSE push if nothing changed since last tick
    cache_key = (res_stepper, res_sc, res_cu, res_kw, monitor_html, console_out, is_running)
    if cache_key == _last_status_cache["state"]:
        return tuple(gr.skip() for _ in range(11))
    _last_status_cache["state"] = cache_key

    return result


# --- HTML Helpers ---

def _unified_monitor_status(scoring_runner, tagging_runner, selection_runner):
    """Finds whichever runner is active and returns data for the monitor."""
    for runner_obj, name in [
        (scoring_runner, "Scoring"),
        (selection_runner, "Culling"),
        (tagging_runner, "Keywords"),
    ]:
        if not runner_obj:
            continue
        is_running, log, msg, cur, tot = runner_obj.get_status()
        if is_running:
            return True, name, msg, cur, tot, log
    return False, "", "", 0, 0, ""


def _build_folder_summary(path, count):
    path_display = path if path else "-"
    return f"""
    <div class="folder-summary">
      <h3>Selected Folder</h3>
      <p><strong>{path_display}</strong><br>{count} images</p>
    </div>
    """


def _render_queue_html(queued_jobs):
    if not queued_jobs:
        return "<p class='phase-stats'>Queue: empty</p>"

    lines = ["<div class='phase-stats'>Queue:</div>", "<ul class='phase-stats'>"]
    for job in queued_jobs:
        lines.append(
            f"<li>#{job.get('id')} {job.get('job_type') or 'job'} "
            f"(position {job.get('queue_position')})</li>"
        )
    lines.append("</ul>")
    return "".join(lines)


def _build_idle_html(queued_jobs=None):
    queued_jobs = queued_jobs or []
    return (
        "<div class='panel-body'><p>No active jobs in the pipeline.</p>"
        + _render_queue_html(queued_jobs)
        + "</div>"
    )


def _build_monitor_html(name, msg, current, total, queued_jobs=None):
    queued_jobs = queued_jobs or []
    pct = (current / total * 100) if total > 0 else 0
    return f"""
    <div class="panel-body">
      <div class="phase-head">
        <div class="phase-title">{name} Progress</div>
      </div>
      <div class="phase-stats">{msg} ({current}/{total})</div>
      <div class="progress"><div class="progress-fill" style="width: {pct:.1f}%;"></div></div>
      {_render_queue_html(queued_jobs)}
    </div>
    """


_STATUS_LABELS = {
    "done": "Done",
    "partial": "In Progress",
    "not_started": "Not Started",
    "failed": "Failed",
    "running": "Running",
}


def _build_phase_card_html(title, status, done, total):
    pct = (done / total * 100) if total > 0 else 0
    initial = title[0]
    status_label = _STATUS_LABELS.get(status, status.replace("_", " ").title())
    return f"""
    <div class="phase-head">
      <div class="phase-title">
        <div class="phase-icon">{initial}</div>
        {title}
      </div>
      <div class="phase-status">{status_label}</div>
    </div>
    <div class="phase-stats">{done}/{total} images processed</div>
    <div class="progress"><div class="progress-fill" style="width: {pct:.1f}%;"></div></div>
    """


def _build_pipeline_stepper_html(folder_path, summary_by_code=None, total=0):
    if not folder_path or not summary_by_code:
        return "<p>Select a folder from the tree to view pipeline progress.</p>"

    def _get(phase_code, default_done=0):
        return summary_by_code.get(phase_code, {}).get("done_count", default_done)

    idx_done = _get("indexing", total)
    met_done = _get("metadata", total)
    sco_done = _get("scoring")
    cul_done = _get("culling")
    key_done = _get("keywords")

    def get_state(done, total_c):
        if total_c == 0:
            return ""
        if done == total_c:
            return "done"
        if done > 0:
            return "running"
        return ""

    return f"""
    <div class="stepper">
      <div class="step {get_state(idx_done, total)}">
        <div class="step-dot">1</div>
        <div class="step-label">Index</div>
        <div class="step-count">{idx_done} / {total}</div>
      </div>
      <div class="connector {get_state(idx_done, total)}"></div>

      <div class="step {get_state(met_done, total)}">
        <div class="step-dot">2</div>
        <div class="step-label">Meta</div>
        <div class="step-count">{met_done} / {total}</div>
      </div>
      <div class="connector {get_state(sco_done, total)}"></div>

      <div class="step {get_state(sco_done, total)}">
        <div class="step-dot">3</div>
        <div class="step-label">Scoring</div>
        <div class="step-count">{sco_done} / {total}</div>
      </div>
      <div class="connector {get_state(cul_done, total)}"></div>

      <div class="step {get_state(cul_done, total)}">
        <div class="step-dot">4</div>
        <div class="step-label">Culling</div>
        <div class="step-count">{cul_done} / {total}</div>
      </div>
      <div class="connector {get_state(key_done, total)}"></div>

      <div class="step {get_state(key_done, total)}">
        <div class="step-dot">5</div>
        <div class="step-label">Keywords</div>
        <div class="step-count">{key_done} / {total}</div>
      </div>
    </div>
    """
