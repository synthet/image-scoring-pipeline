import gradio as gr
import html
import json
from modules import db
from modules import ui_tree
from modules.phases import PhaseRegistry

# Cache for timer-based status updates to avoid unnecessary SSE pushes
_last_status_cache = {"state": None}


def _parse_phase_summary(folder_path, force_refresh=False):
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

    summary_list = db.get_folder_phase_summary(folder_path, force_refresh=force_refresh)
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

                gr.HTML("<div class='section-divider'></div>")

            # MAIN DASHBOARD
            with gr.Column(scale=3):
                # QUICK START PANEL
                components["quick_start_html"] = gr.HTML(
                    _build_quick_start_html(None),
                    elem_classes=["animate-in"],
                )

                # PANEL: Pipeline Progress
                with gr.Group(elem_classes=["panel"]):
                    gr.HTML(
                        """
                        <div class="panel-header">
                            <h2 class="panel-title">Pipeline Progress</h2>
                        </div>
                        <div class="pipeline-overview" role="region" aria-label="Pipeline explanation">
                            <p class="section-microcopy">
                                <strong>5 phases</strong> run in order: <strong>1. Index</strong> (discover & register images) →
                                <strong>2. Meta</strong> (extract EXIF/XMP) →
                                <strong>3. Scoring</strong> (AI quality scores) →
                                <strong>4. Culling</strong> (pick best per stack) →
                                <strong>5. Keywords</strong> (tagging). Each phase shows <em>done / total</em> images for that phase.
                                Index and Meta run inside Scoring; their counts can differ until Scoring completes.
                            </p>
                        </div>
                        """
                    )
                    with gr.Column(elem_classes=["panel-body"]):
                        components["stepper_html"] = gr.HTML(_build_pipeline_stepper_html(None))
                        with gr.Row(elem_classes=["pipeline-actions"]):
                            components["run_all_btn"] = gr.Button("Run All Pending", variant="primary", elem_classes=["primary-btn"])
                            components["stop_all_btn"] = gr.Button("Stop All", variant="stop", elem_classes=["danger-btn"])
                            components["repair_index_meta_btn"] = gr.Button("Repair Index/Meta", variant="secondary", elem_classes=["secondary-btn"])
                            components["run_metadata_btn"] = gr.Button("Run Metadata", variant="secondary", elem_classes=["secondary-btn"])
                        gr.HTML(
                            "<p class='section-microcopy'>"
                            "<strong>Run All Pending</strong> \u2014 starts Scoring, Culling, and Keywords for images not yet processed. "
                            "<strong>Stop All</strong> \u2014 halts the active job; progress is preserved. "
                            "<strong>Repair Index/Meta</strong> \u2014 backfills Index and Meta status for images with Scoring done but missing phase status. "
                            "<strong>Run Metadata</strong> \u2014 extracts EXIF/XMP and creates thumbnails for images missing metadata (no scoring)."
                            "</p>"
                        )
                        # Stop All confirmation (hidden until Stop All clicked)
                        with gr.Row(visible=False, elem_classes=["confirm-row"]) as stop_confirm_row:
                            gr.HTML(
                                "<span class='confirm-text'>"
                                "This will halt all active jobs immediately. The current batch will not complete."
                                "</span>"
                            )
                            stop_confirm_yes = gr.Button("Yes, Stop All", elem_classes=["danger-btn"], size="sm")
                            stop_confirm_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                        components["stop_confirm_row"] = stop_confirm_row
                        components["stop_confirm_yes"] = stop_confirm_yes
                        components["stop_confirm_cancel"] = stop_confirm_cancel

                        with gr.Row():
                            components["skip_reason"] = gr.Textbox(label="Skip reason", value="", placeholder="optional reason")
                            components["skip_actor"] = gr.Textbox(label="Actor", value="ui_user", placeholder="who skipped")

                # PANEL: Phases (Card Grid)
                with gr.Group(elem_classes=["panel"]):
                    with gr.Row(elem_classes=["panel-body", "phase-grid"]):

                        # Scoring Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["scoring_card_html"] = gr.HTML(_build_phase_card_html("SCORING", "Not Started", 0, 0))
                            components["scoring_run_btn"] = gr.Button("Run Scoring", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["scoring_force"] = gr.Checkbox(label="Force Re-score", value=False)
                            components["scoring_skip_btn"] = gr.Button("Skip Scoring", elem_classes=["danger-btn"])
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as scoring_skip_confirm:
                                gr.HTML("<span class='confirm-text'>Marks Scoring as skipped for this folder.</span>")
                                scoring_skip_yes = gr.Button("Yes, Skip", elem_classes=["danger-btn"], size="sm")
                                scoring_skip_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["scoring_skip_confirm"] = scoring_skip_confirm
                            components["scoring_skip_yes"] = scoring_skip_yes
                            components["scoring_skip_cancel"] = scoring_skip_cancel
                            components["scoring_retry_btn"] = gr.Button("Retry Skipped", elem_classes=["secondary-btn"])
                            gr.HTML("<p class='action-help'>Run \u2014 scores unprocessed images. Skip \u2014 marks done without running. Retry \u2014 re-queues skipped.</p>")

                        # Culling Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["culling_card_html"] = gr.HTML(_build_phase_card_html("CULLING", "Not Started", 0, 0))
                            components["culling_run_btn"] = gr.Button("Run Culling", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["culling_force"] = gr.Checkbox(label="Force Re-run", value=False)
                            components["culling_skip_btn"] = gr.Button("Skip Culling", elem_classes=["danger-btn"])
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as culling_skip_confirm:
                                gr.HTML("<span class='confirm-text'>Marks Culling as skipped for this folder.</span>")
                                culling_skip_yes = gr.Button("Yes, Skip", elem_classes=["danger-btn"], size="sm")
                                culling_skip_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["culling_skip_confirm"] = culling_skip_confirm
                            components["culling_skip_yes"] = culling_skip_yes
                            components["culling_skip_cancel"] = culling_skip_cancel
                            components["culling_retry_btn"] = gr.Button("Retry Skipped", elem_classes=["secondary-btn"])
                            gr.HTML("<p class='action-help'>Run \u2014 selects picks by composition score. Skip \u2014 marks done. Retry \u2014 re-runs on skipped.</p>")

                        # Keywords Card
                        with gr.Column(elem_classes=["phase-card"]):
                            components["keywords_card_html"] = gr.HTML(_build_phase_card_html("KEYWORDS", "Not Started", 0, 0))
                            components["keywords_run_btn"] = gr.Button("Run Keywords", elem_classes=["secondary-btn"])
                            with gr.Accordion("Options", open=False, elem_classes=["options-accordion"]):
                                components["keywords_overwrite"] = gr.Checkbox(label="Overwrite Existing", value=False)
                                components["keywords_captions"] = gr.Checkbox(label="Generate Captions", value=False)
                            components["keywords_skip_btn"] = gr.Button("Skip Keywords", elem_classes=["danger-btn"])
                            with gr.Row(visible=False, elem_classes=["confirm-row"]) as keywords_skip_confirm:
                                gr.HTML("<span class='confirm-text'>Marks Keywords as skipped for this folder.</span>")
                                keywords_skip_yes = gr.Button("Yes, Skip", elem_classes=["danger-btn"], size="sm")
                                keywords_skip_cancel = gr.Button("Cancel", elem_classes=["secondary-btn"], size="sm")
                            components["keywords_skip_confirm"] = keywords_skip_confirm
                            components["keywords_skip_yes"] = keywords_skip_yes
                            components["keywords_skip_cancel"] = keywords_skip_cancel
                            components["keywords_retry_btn"] = gr.Button("Retry Skipped", elem_classes=["secondary-btn"])
                            gr.HTML("<p class='action-help'>Run \u2014 generates keyword tags. Skip \u2014 skips tagging. Retry \u2014 re-tags skipped.</p>")

                # PANEL: Active Job Monitor
                with gr.Group(elem_classes=["panel", "monitor-card"]):
                    components["monitor_html"] = gr.HTML(_build_idle_html(recovery_info=app_config.get("job_recovery"), queued_jobs=[]))
                    with gr.Accordion("Console Output", open=False):
                        components["console_output"] = gr.Textbox(
                            lines=12, label="", max_lines=12, interactive=False, elem_classes=["console-code"]
                        )

    # Wire up folder selection to update HTML rendering (force_refresh to avoid stale cache)
    components["selected_path"].change(
        fn=lambda p: _update_folder_selection(p, force_refresh=True)[:6],
        inputs=[components["selected_path"]],
        outputs=[
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"],
            components["quick_start_html"],
        ]
    )

    def _on_refresh_click(selected_path):
        """Refresh tree and invalidate folder phase cache so next fetch is live."""
        if selected_path and selected_path.strip():
            db.invalidate_folder_phase_aggregates(folder_path=selected_path)
        tree_html = ui_tree.get_tree_html()
        folder_outputs = _update_folder_selection(selected_path or "", force_refresh=True)
        # Outputs: tree_view + 6 UI components (folder_outputs has 7th elem total_count for internal use)
        return (tree_html,) + folder_outputs[:6]

    def _on_repair_index_meta(selected_path):
        """Backfill Index/Meta for images with Scoring done but missing phase status."""
        if not selected_path or not selected_path.strip():
            return _on_refresh_click("")
        updated = db.backfill_index_meta_for_folder(selected_path)
        return _on_refresh_click(selected_path)

    components["repair_index_meta_btn"].click(
        fn=_on_repair_index_meta,
        inputs=[components["selected_path"]],
        outputs=[
            components["tree_view"],
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"],
            components["quick_start_html"],
        ],
    )

    components["refresh_btn"].click(
        fn=_on_refresh_click,
        inputs=[components["selected_path"]],
        outputs=[
            components["tree_view"],
            components["folder_summary_html"],
            components["stepper_html"],
            components["scoring_card_html"],
            components["culling_card_html"],
            components["keywords_card_html"],
            components["quick_start_html"],
        ],
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

    def _run_metadata(path):
        """Run indexing and metadata extraction only (no scoring)."""
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="scoring",
            job_type="scoring",
            queue_payload={
                "input_path": path,
                "skip_existing": False,
                "target_phases": ["indexing", "metadata"],
            },
        )

    def _run_culling(path, force):
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="culling",
            job_type="selection",
            queue_payload={"input_path": path, "force_rescan": force},
        )

    def _run_tagging(path, overwrite, captions):
        if not path:
            return
        db.enqueue_job(
            path,
            phase_code="keywords",
            job_type="tagging",
            queue_payload={"input_path": path, "overwrite": overwrite, "generate_captions": captions},
        )


    def _stop_runner_for_phase(phase_code):
        if phase_code == "scoring":
            scoring_runner.stop()
        elif phase_code == "culling":
            selection_runner.stop()
        elif phase_code == "keywords":
            tagging_runner.stop()

    def _skip_phase(path, phase_code, reason, actor):
        if not path:
            return
        _stop_runner_for_phase(phase_code)
        db.set_folder_phase_status(
            folder_path=path,
            phase_code=phase_code,
            status="skipped",
            reason=reason or "manual_skip",
            actor=actor or "ui_user",
        )

    def _retry_phase(path, phase_code):
        if not path:
            return
        db.set_folder_phase_status(
            folder_path=path,
            phase_code=phase_code,
            status="running",
        )
        if phase_code == "scoring":
            _run_scoring(path, force=False)
        elif phase_code == "culling":
            _run_culling(path, force=True)
        elif phase_code == "keywords":
            _run_tagging(path, overwrite=False, captions=False)

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
    components["run_metadata_btn"].click(
        fn=_run_metadata,
        inputs=[components["selected_path"]],
        outputs=[]
    )
    # Stop All: two-step confirmation
    components["stop_all_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["stop_confirm_row"]],
    )
    components["stop_confirm_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["stop_confirm_row"]],
    )
    components["stop_confirm_yes"].click(
        fn=_stop_all,
        inputs=[],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["stop_confirm_row"]],
    )

    # Scoring skip: two-step confirmation
    components["scoring_skip_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["scoring_skip_confirm"]],
    )
    components["scoring_skip_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["scoring_skip_confirm"]],
    )
    components["scoring_skip_yes"].click(
        fn=lambda p, r, a: _skip_phase(p, "scoring", r, a),
        inputs=[components["selected_path"], components["skip_reason"], components["skip_actor"]],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["scoring_skip_confirm"]],
    )

    # Culling skip: two-step confirmation
    components["culling_skip_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["culling_skip_confirm"]],
    )
    components["culling_skip_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["culling_skip_confirm"]],
    )
    components["culling_skip_yes"].click(
        fn=lambda p, r, a: _skip_phase(p, "culling", r, a),
        inputs=[components["selected_path"], components["skip_reason"], components["skip_actor"]],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["culling_skip_confirm"]],
    )

    # Keywords skip: two-step confirmation
    components["keywords_skip_btn"].click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[components["keywords_skip_confirm"]],
    )
    components["keywords_skip_cancel"].click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["keywords_skip_confirm"]],
    )
    components["keywords_skip_yes"].click(
        fn=lambda p, r, a: _skip_phase(p, "keywords", r, a),
        inputs=[components["selected_path"], components["skip_reason"], components["skip_actor"]],
        outputs=[],
    ).then(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[components["keywords_skip_confirm"]],
    )
    components["scoring_retry_btn"].click(
        fn=lambda p: _retry_phase(p, "scoring"),
        inputs=[components["selected_path"]],
        outputs=[]
    )
    components["culling_retry_btn"].click(
        fn=lambda p: _retry_phase(p, "culling"),
        inputs=[components["selected_path"]],
        outputs=[]
    )
    components["keywords_retry_btn"].click(
        fn=lambda p: _retry_phase(p, "keywords"),
        inputs=[components["selected_path"]],
        outputs=[]
    )

    return components


def _update_folder_selection(folder_path: str, force_refresh=False, is_running=False):
    """Updates the static UI components when a new folder is selected.

    Returns: (summary_html, stepper_html, scoring_card, culling_card, keywords_card, quick_start_html, total_count)
    """
    if not folder_path:
        return (
            _build_folder_summary(None, 0),
            _build_pipeline_stepper_html(None),
            _build_phase_card_html("SCORING", "Not Started", 0, 0),
            _build_phase_card_html("CULLING", "Not Started", 0, 0),
            _build_phase_card_html("KEYWORDS", "Not Started", 0, 0),
            _build_quick_start_html(None, is_running=is_running),
            0,
        )

    summary_by_code, total_count = _parse_phase_summary(folder_path, force_refresh=force_refresh)

    sc = summary_by_code.get("scoring", {})
    cu = summary_by_code.get("culling", {})
    kw = summary_by_code.get("keywords", {})

    return (
        _build_folder_summary(folder_path, total_count),
        _build_pipeline_stepper_html(folder_path, summary_by_code, total_count),
        _build_phase_card_html("SCORING", sc.get("status", "not_started"), sc.get("done_count", 0), total_count),
        _build_phase_card_html("CULLING", cu.get("status", "not_started"), cu.get("done_count", 0), total_count),
        _build_phase_card_html("KEYWORDS", kw.get("status", "not_started"), kw.get("done_count", 0), total_count),
        _build_quick_start_html(folder_path, summary_by_code, is_running=is_running),
        total_count,
    )


def get_status_update(scoring_runner, tagging_runner, selection_runner, orchestrator, selected_folder):
    """Called regularly by the main app timer to update components."""
    # Process Orchestrator tick
    orchestrator.on_tick()

    is_running, mon_name, mon_msg, mon_cur, mon_tot, console_out, pipeline_depth = _unified_monitor_status(
        scoring_runner, tagging_runner, selection_runner
    )

    queued_jobs = db.get_queued_jobs(limit=5)

    # Rebuild stepper/cards from current folder state (force_refresh when running for real-time updates)
    res_summary, res_stepper, res_sc, res_cu, res_kw, res_qs, folder_total = _update_folder_selection(
        selected_folder, force_refresh=is_running, is_running=is_running
    )

    if is_running:
        monitor_html = _build_monitor_html(
            mon_name, mon_msg, mon_cur, mon_tot, queued_jobs,
            folder_total=folder_total, pipeline_depth=pipeline_depth
        )
    else:
        status = orchestrator.get_status()
        monitor_html = _build_idle_html(
            recovery_info=status.get("recovery"),
            queued_jobs=queued_jobs,
        )

    not_running = not is_running

    # Return order must match monitor_outputs in app.py:
    # stepper, scoring_card, culling_card, keywords_card,
    # monitor, console, run_all, stop_all, sc_run, cu_run, kw_run, repair, run_meta, quick_start
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
        gr.update(interactive=not_running),  # repair_index_meta
        gr.update(interactive=not_running),  # run_metadata
        res_qs,                              # quick_start
    )

    # Skip SSE push if nothing changed since last tick
    cache_key = (res_stepper, res_sc, res_cu, res_kw, monitor_html, console_out, is_running)
    if cache_key == _last_status_cache["state"]:
        return tuple(gr.skip() for _ in range(14))
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
        result = runner_obj.get_status()
        is_running, log, msg, cur, tot = result[:5]
        depth = result[5] if len(result) > 5 else 0
        if is_running:
            return True, name, msg, cur, tot, log, depth
    return False, "", "", 0, 0, "", 0


def _build_quick_start_html(folder_path, summary_by_code=None, is_running=False):
    """Context-aware Quick Start guide: 1. Select folder → 2. Run All → 3. Gallery."""
    summary_by_code = summary_by_code or {}

    if not folder_path:
        steps = [
            ("current", "Select a folder from the tree"),
            ("", "Run all pending pipeline phases"),
            ("", "Open Gallery and review results"),
        ]
    elif is_running:
        steps = [
            ("done", "Folder selected"),
            ("current", "Pipeline is running\u2026"),
            ("", "Open Gallery and review results"),
        ]
    else:
        pending = any(
            summary_by_code.get(c, {}).get("status") not in ("done", "skipped")
            for c in ("scoring", "culling", "keywords")
        )
        if pending:
            steps = [
                ("done", "Folder selected"),
                ("current", "Run All Pending to process images"),
                ("", "Open Gallery and review results"),
            ]
        else:
            steps = [
                ("done", "Folder selected"),
                ("done", "All phases complete"),
                ("current", "Open Gallery and review results"),
            ]

    parts = [
        "<div class='quick-start-panel'>",
        "<strong style='font-size:0.9rem;color:var(--text-primary)'>Quick Start</strong>",
        "<div class='quick-start-steps'>",
    ]
    for i, (state, label) in enumerate(steps):
        parts.append(
            f"<div class='qs-step {state}' role='listitem'>"
            f"<span class='qs-step-num'>{i + 1}</span>"
            f"<span>{label}</span>"
            f"</div>"
        )
        if i < len(steps) - 1:
            parts.append("<span class='qs-arrow' aria-hidden='true'>\u203a</span>")
    parts.append("</div></div>")
    return "".join(parts)


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
        return "<p class='phase-stats'>Job queue: empty</p>"

    lines = ["<div class='phase-stats'>Job queue:</div>", "<ul class='phase-stats'>"]
    for job in queued_jobs:
        lines.append(
            f"<li>#{job.get('id')} {job.get('job_type') or 'job'} "
            f"(position {job.get('queue_position')})</li>"
        )
    lines.append("</ul>")
    return "".join(lines)


def _build_idle_html(recovery_info=None, queued_jobs=None):
    base = "<div class='panel-body'><p>No active jobs in the pipeline.</p>"
    if recovery_info:
        recovered = recovery_info.get("recovered_running_jobs") or []
        interrupted = recovery_info.get("interrupted_pipeline_jobs") or []
        auto_resumed = recovery_info.get("auto_resumed")
        if recovered or interrupted or auto_resumed:
            base += (
                f"<p><strong>Recovery:</strong> marked {len(recovered)} running job(s) as interrupted; "
                f"found {len(interrupted)} interrupted pipeline job(s); "
                f"auto-resumed: {'yes' if auto_resumed else 'no'}.</p>"
            )
    queued_jobs = queued_jobs or []
    return base + _render_queue_html(queued_jobs) + "</div>"


def _build_monitor_html(name, msg, current, total, queued_jobs=None, folder_total=None, pipeline_depth=0):
    """Build monitor HTML. Numbers show current batch progress; folder_total adds folder-scope context."""
    queued_jobs = queued_jobs or []
    pct = (current / total * 100) if total > 0 else 0
    batch_line = f"{msg} ({current}/{total})"
    folder_line = ""
    if folder_total is not None and folder_total > 0 and folder_total != total:
        folder_line = f"<p class='section-microcopy'>Batch: {current}/{total} · Folder total: {folder_total} images</p>"
    else:
        folder_line = "<p class='section-microcopy'>Processing images in current batch. See Console Output for per-image progress.</p>"
    pipeline_line = ""
    if pipeline_depth > 0:
        pipeline_line = f"<p class='section-microcopy'>Pipeline: {pipeline_depth} image(s) in queue</p>"
    return f"""
    <div class="panel-body">
      <div class="phase-head">
        <div class="phase-title">{name} Progress</div>
      </div>
      <div class="phase-stats">{batch_line}</div>
      {folder_line}
      {pipeline_line}
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
    "skipped": "Skipped",
}


_STATUS_BADGE_CLASS = {
    "done": "success",
    "partial": "info",
    "running": "info",
    "failed": "error",
    "skipped": "warning",
    "not_started": "",
}


def _build_phase_card_html(title, status, done, total):
    pct = (done / total * 100) if total > 0 else 0
    initial = title[0]
    status_label = _STATUS_LABELS.get(status, status.replace("_", " ").title())
    badge_class = _STATUS_BADGE_CLASS.get(status, "")
    badge_cls = f"phase-status status-badge {badge_class}" if badge_class else "phase-status"
    running_cls = " phase-card running" if status in ("running", "partial") else ""
    return f"""
    <div class="phase-card{running_cls}" role="region" aria-label="{title} phase: {status_label}">
      <div class="phase-head">
        <div class="phase-title">
          <div class="phase-icon">{initial}</div>
          {title}
        </div>
        <div class="{badge_cls}">{status_label}</div>
      </div>
      <div class="phase-stats">{done}/{total} images processed</div>
      <div class="progress"><div class="progress-fill" style="width: {pct:.1f}%;"></div></div>
    </div>
    """


def _build_pipeline_stepper_html(folder_path, summary_by_code=None, total=0):
    if not folder_path:
        return "<p>Select a folder from the tree to view pipeline progress.</p>"

    if not summary_by_code or total == 0:
        return (
            "<p class='section-microcopy'>No images in this folder. "
            "Run Scoring first to index images from disk.</p>"
        )

    phase_defs = db.get_all_phases(enabled_only=True) or []
    if not phase_defs:
        return "<p class='section-microcopy'>No enabled phases found.</p>"

    summary_by_code = summary_by_code or {}
    registry = {}
    for executor in PhaseRegistry.get_all():
        code = executor.code.value if hasattr(executor.code, "value") else str(executor.code)
        registry[code] = executor

    retry_totals = _get_folder_phase_retry_totals(folder_path)
    selected_targets, step_runs_by_phase = _get_folder_step_run_breakdowns(folder_path)

    phase_codes = [p.get("code") for p in phase_defs if p.get("code")]
    x_positions = {code: (idx * 180) + 72 for idx, code in enumerate(phase_codes)}
    svg_w = max(220, len(phase_codes) * 180)

    edge_lines = []
    for phase in phase_defs:
        code = phase.get("code")
        executor = registry.get(code)
        dependencies = executor.depends_on if executor and executor.depends_on else []
        for dep in dependencies:
            dep_code = dep.value if hasattr(dep, "value") else str(dep)
            if dep_code in x_positions and code in x_positions:
                x1 = x_positions[dep_code] + 54
                x2 = x_positions[code] - 54
                edge_lines.append(
                    f"<line x1='{x1}' y1='70' x2='{x2}' y2='70' stroke='var(--border-color-primary)' stroke-width='2' marker-end='url(#phaseArrow)' />"
                )

    node_html = []
    for idx, phase in enumerate(phase_defs, start=1):
        code = phase.get("code")
        name = phase.get("name") or code
        info = summary_by_code.get(code, {})
        status = info.get("status", "not_started")
        status_label = _STATUS_LABELS.get(status, status.replace("_", " ").title())
        done = info.get("done_count", 0)
        failed = info.get("failed_count", 0)
        skipped = info.get("skipped_count", 0)
        retries = retry_totals.get(code, 0)
        is_selected = (not selected_targets) or (code in selected_targets)
        selected_label = "Selected in run" if is_selected else "Not selected"
        executor = registry.get(code)
        deps = executor.depends_on if executor and executor.depends_on else []
        dep_labels = []
        for dep in deps:
            dep_code = dep.value if hasattr(dep, "value") else str(dep)
            dep_labels.append(dep_code)
        dep_line = ", ".join(dep_labels) if dep_labels else "None"
        run_rows = step_runs_by_phase.get(code, [])
        run_items = []
        if run_rows:
            for run in run_rows:
                err = html.escape((run.get("error") or "").strip())
                err_line = f"<div><strong>Error:</strong> {err}</div>" if err else ""
                run_items.append(
                    "<li>"
                    f"<div><strong>Job #{run.get('job_id')}</strong> · {run.get('job_status')} · {run.get('duration')}</div>"
                    f"<div>Sub-phase state: {run.get('step_state')}</div>"
                    f"<div>Started: {run.get('started')}</div>"
                    f"<div>Finished: {run.get('finished')}</div>"
                    f"{err_line}"
                    "</li>"
                )
        else:
            run_items.append("<li>No recorded StepRun data for this phase in this folder yet.</li>")

        node_html.append(
            f"""
            <details class="pipeline-node status-{status} {'selected' if is_selected else 'not-selected'}" style="left:{x_positions[code]-62}px;" open={"open" if status in ("running", "failed") else ""}>
              <summary>
                <div class="node-title">{idx}. {html.escape(name)}</div>
                <div class="node-meta">{status_label} · {selected_label}</div>
                <div class="node-mini-stats">{done}/{total} · failed {failed} · skipped {skipped} · retries {retries}</div>
              </summary>
              <div class="node-breakdown">
                <div><strong>Dependencies:</strong> {html.escape(dep_line)}</div>
                <div><strong>Executor:</strong> {html.escape(getattr(executor, 'executor_version', 'unbound') if executor else 'unbound')}</div>
                <div><strong>StepRun breakdown:</strong></div>
                <ul>{''.join(run_items)}</ul>
              </div>
            </details>
            """
        )

    return f"""
    <div class="pipeline-graph-view">
      <style>
        .pipeline-graph-view .graph-canvas {{ position: relative; min-height: 300px; overflow-x: auto; padding: 8px 0 0; }}
        .pipeline-graph-view .pipeline-node {{ position: absolute; width: 124px; border: 1px solid var(--border-color-primary); border-radius: 10px; background: var(--panel-background-fill); }}
        .pipeline-graph-view .pipeline-node summary {{ list-style: none; cursor: pointer; padding: 8px; }}
        .pipeline-graph-view .pipeline-node summary::-webkit-details-marker {{ display:none; }}
        .pipeline-graph-view .node-title {{ font-weight: 600; font-size: 0.82rem; }}
        .pipeline-graph-view .node-meta, .pipeline-graph-view .node-mini-stats {{ font-size: 0.72rem; color: var(--body-text-color-subdued); }}
        .pipeline-graph-view .node-breakdown {{ padding: 0 8px 8px; font-size: 0.74rem; }}
        .pipeline-graph-view .node-breakdown ul {{ margin: 6px 0 0 16px; padding: 0; }}
        .pipeline-graph-view .status-done {{ border-color: #27ae60; }}
        .pipeline-graph-view .status-partial, .pipeline-graph-view .status-running {{ border-color: #3498db; }}
        .pipeline-graph-view .status-failed {{ border-color: #e74c3c; }}
        .pipeline-graph-view .status-skipped {{ border-color: #f39c12; }}
        .pipeline-graph-view .pipeline-node.not-selected {{ opacity: 0.6; }}
      </style>
      <div class="section-microcopy">Graph view from <code>pipeline_phases</code> + executor bindings. Click a node to inspect StepRun breakdown (sub-phases, timings, errors).</div>
      <div class="graph-canvas" role="group" aria-label="Pipeline phase graph">
        <svg width="{svg_w}" height="250" viewBox="0 0 {svg_w} 250" aria-hidden="true">
          <defs>
            <marker id="phaseArrow" markerWidth="8" markerHeight="8" refX="5" refY="3" orient="auto">
              <polygon points="0 0, 6 3, 0 6" fill="var(--border-color-primary)" />
            </marker>
          </defs>
          {''.join(edge_lines)}
        </svg>
        {''.join(node_html)}
      </div>
    </div>
    """


def _get_folder_phase_retry_totals(folder_path):
    """Aggregate retry totals (attempt_count - 1) per phase for folder descendants."""
    from modules import utils

    wsl_path = utils.convert_path_to_wsl(folder_path) if hasattr(utils, "convert_path_to_wsl") else folder_path
    target_path = wsl_path if wsl_path else folder_path
    if not target_path:
        return {}

    retries = {}
    conn = db.get_db()
    c = conn.cursor()
    try:
        path_like_unix = target_path + "/%"
        path_like_win = target_path + "\\%"
        c.execute(
            """
            SELECT pp.code, COALESCE(SUM(CASE WHEN ips.attempt_count > 1 THEN ips.attempt_count - 1 ELSE 0 END), 0) AS retries
            FROM image_phase_status ips
            JOIN pipeline_phases pp ON pp.id = ips.phase_id
            JOIN images i ON i.id = ips.image_id
            JOIN folders f ON f.id = i.folder_id
            WHERE f.path = ? OR f.path LIKE ? OR f.path LIKE ?
            GROUP BY pp.code
            """,
            (target_path, path_like_unix, path_like_win),
        )
        for row in c.fetchall():
            code = row[0].strip() if isinstance(row[0], str) else row[0]
            retries[code] = row[1] or 0
    except Exception:
        return {}
    finally:
        conn.close()
    return retries


def _get_folder_step_run_breakdowns(folder_path):
    """Return (selected_target_phases, phase->recent step runs) for a folder."""
    selected_targets = set()
    phase_runs = {}
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute(
            """
            SELECT id, status, created_at, started_at, finished_at, queue_payload
            FROM jobs
            WHERE input_path = ?
            ORDER BY COALESCE(started_at, created_at) DESC
            FETCH FIRST 20 ROWS ONLY
            """,
            (folder_path,),
        )
        jobs = c.fetchall()
        for row in jobs:
            job_id = row[0]
            job_status = (row[1] or "unknown").strip()
            queue_payload = row[5]
            payload = None
            if queue_payload:
                try:
                    payload = json.loads(queue_payload)
                except Exception:
                    payload = None
            if payload and isinstance(payload, dict) and not selected_targets:
                for code in payload.get("target_phases") or []:
                    selected_targets.add(str(code))

            c.execute(
                """
                SELECT phase_code, state, started_at, completed_at, error_message
                FROM job_phases
                WHERE job_id = ?
                ORDER BY phase_order
                """,
                (job_id,),
            )
            step_rows = c.fetchall()
            if not step_rows and payload and isinstance(payload, dict):
                codes = payload.get("target_phases") or []
                for code in codes:
                    phase_runs.setdefault(str(code), [])
                continue

            for step in step_rows:
                code = step[0]
                if not code:
                    continue
                started = step[2] or row[3]
                finished = step[3] or row[4]
                phase_runs.setdefault(code, []).append({
                    "job_id": job_id,
                    "job_status": job_status,
                    "step_state": step[1] or "unknown",
                    "started": str(started) if started else "-",
                    "finished": str(finished) if finished else "-",
                    "duration": _format_duration(started, finished),
                    "error": step[4] or "",
                })

        for code in phase_runs:
            phase_runs[code] = phase_runs[code][:3]
    except Exception:
        return selected_targets, phase_runs
    finally:
        conn.close()
    return selected_targets, phase_runs


def _format_duration(started, finished):
    if not started:
        return "-"
    if not finished:
        return "running"
    try:
        delta = finished - started
        total = int(delta.total_seconds())
        mins, secs = divmod(max(total, 0), 60)
        hrs, mins = divmod(mins, 60)
        if hrs:
            return f"{hrs}h {mins}m {secs}s"
        if mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"
    except Exception:
        return "-"
