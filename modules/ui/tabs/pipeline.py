import datetime
import html
import gradio as gr
from modules import db
from modules import ui_tree

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

    queued_jobs = db.get_queued_jobs(limit=50, include_related=True)

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


def _format_queue_time(raw):
    if not raw:
        return "-"
    if isinstance(raw, datetime.datetime):
        return raw.strftime("%Y-%m-%d %H:%M:%S")
    try:
        return datetime.datetime.fromisoformat(str(raw)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(raw)


def _status_chip(status):
    norm = (status or "unknown").strip().lower()
    label = norm.replace("_", " ").title()
    return f"<span class='queue-chip queue-chip-{norm}'>{html.escape(label)}</span>"


def _render_queue_html(queued_jobs):
    if not queued_jobs:
        return "<p class='phase-stats'>Job queue: empty</p>"

    rows = []
    for job in queued_jobs:
        status = (job.get("status") or "queued").strip().lower()
        rows.append(
            "<tr>"
            f"<td data-sort='{job.get('queue_position')}'>{html.escape(str(job.get('queue_position')))}</td>"
            f"<td data-sort='{job.get('priority')}'>{html.escape(str(job.get('priority')))}</td>"
            f"<td data-sort='{html.escape(str(job.get('enqueued_at') or ''))}'>{html.escape(_format_queue_time(job.get('enqueued_at')))}</td>"
            f"<td>{html.escape(str(job.get('target_scope') or '-'))}</td>"
            f"<td>{html.escape(str(job.get('selected_phases') or '-'))}</td>"
            f"<td>{html.escape(str(job.get('dependency_blockers') or 'None'))}</td>"
            f"<td data-sort='{html.escape(str(job.get('estimated_start') or ''))}'>{html.escape(_format_queue_time(job.get('estimated_start')))}</td>"
            f"<td data-sort='{job.get('retry_count')}'>{html.escape(str(job.get('retry_count') or 0))}</td>"
            f"<td>{_status_chip(status)}</td>"
            "<td>"
            f"<button class='queue-action-btn' {'disabled' if status != 'queued' else ''} title='Move priority'>⬆ Priority</button>"
            f"<button class='queue-action-btn' {'disabled' if status != 'queued' else ''} title='Pause item'>⏸ Pause</button>"
            f"<button class='queue-action-btn' {'disabled' if status not in ('queued','paused') else ''} title='Cancel item'>✖ Cancel</button>"
            f"<button class='queue-action-btn' {'disabled' if status != 'failed' else ''} title='Restart failed'>↻ Restart</button>"
            "</td>"
            "</tr>"
        )

    return (
        "<div class='queue-board'>"
        "<div class='phase-stats'>Job queue board</div>"
        "<div class='queue-board-help section-microcopy'>Sortable columns: Position, Priority, Enqueue Time, ETA, Retry.</div>"
        "<div class='queue-table-wrap'>"
        "<table class='queue-table'>"
        "<thead><tr>"
        "<th data-sort-col='0'>Position</th>"
        "<th data-sort-col='1'>Priority</th>"
        "<th data-sort-col='2'>Enqueue Time</th>"
        "<th>Target Scope</th>"
        "<th>Selected Phases</th>"
        "<th>Dependency Blockers</th>"
        "<th data-sort-col='6'>Estimated Start</th>"
        "<th data-sort-col='7'>Retry</th>"
        "<th>Status</th>"
        "<th>Actions</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
        "<script>(function(){"
        "const tables=document.querySelectorAll('.queue-table');"
        "tables.forEach((table)=>{"
        "if(table.dataset.sortBound==='1') return; table.dataset.sortBound='1';"
        "const headers=table.querySelectorAll('th[data-sort-col]');"
        "headers.forEach((th)=>th.addEventListener('click',()=>{"
        "const idx=parseInt(th.dataset.sortCol,10);"
        "const tbody=table.querySelector('tbody');"
        "const rows=Array.from(tbody.querySelectorAll('tr'));"
        "const asc=th.dataset.asc!=='1';"
        "headers.forEach((h)=>delete h.dataset.asc); th.dataset.asc=asc?'1':'0';"
        "rows.sort((a,b)=>{"
        "const va=(a.children[idx].dataset.sort||a.children[idx].innerText||'').trim();"
        "const vb=(b.children[idx].dataset.sort||b.children[idx].innerText||'').trim();"
        "const na=Number(va), nb=Number(vb);"
        "const cmp=(!Number.isNaN(na)&&!Number.isNaN(nb))?(na-nb):va.localeCompare(vb);"
        "return asc?cmp:-cmp;"
        "}); rows.forEach((r)=>tbody.appendChild(r));"
        "}));"
        "});"
        "})();</script>"
        "</div>"
    )


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

    def _phase(phase_code, default_done=0):
        return summary_by_code.get(phase_code, {"done_count": default_done, "status": "not_started", "advance_ready": False})

    idx = _phase("indexing", total)
    met = _phase("metadata", total)
    sco = _phase("scoring")
    cul = _phase("culling")
    key = _phase("keywords")

    idx_done, met_done = idx.get("done_count", total), met.get("done_count", total)
    sco_done, cul_done, key_done = sco.get("done_count", 0), cul.get("done_count", 0), key.get("done_count", 0)

    def get_state(phase_info, total_c):
        done = phase_info.get("done_count", 0)
        status = phase_info.get("status", "not_started")
        advance_ready = phase_info.get("advance_ready", False)
        if total_c == 0:
            return ""
        if status == "done" or done == total_c or advance_ready:
            return "done"
        if status in ("partial", "running", "skipped") or done > 0:
            return "running"
        return ""

    return f"""
    <div class="stepper" role="list" aria-label="Pipeline progress">
      <div class="step {get_state(idx, total)}" role="listitem" aria-label="Index: {idx_done} of {total}">
        <div class="step-dot">1</div>
        <div class="step-label">Index</div>
        <div class="step-count">{idx_done} / {total}</div>
      </div>
      <div class="connector {get_state(idx, total)}" aria-hidden="true"></div>

      <div class="step {get_state(met, total)}" role="listitem" aria-label="Metadata: {met_done} of {total}">
        <div class="step-dot">2</div>
        <div class="step-label">Metadata</div>
        <div class="step-count">{met_done} / {total}</div>
      </div>
      <div class="connector {get_state(met, total)}" aria-hidden="true"></div>

      <div class="step {get_state(sco, total)}" role="listitem" aria-label="Scoring: {sco_done} of {total}">
        <div class="step-dot">3</div>
        <div class="step-label">Scoring</div>
        <div class="step-count">{sco_done} / {total}</div>
      </div>
      <div class="connector {get_state(cul, total)}" aria-hidden="true"></div>

      <div class="step {get_state(cul, total)}" role="listitem" aria-label="Culling: {cul_done} of {total}">
        <div class="step-dot">4</div>
        <div class="step-label">Culling</div>
        <div class="step-count">{cul_done} / {total}</div>
      </div>
      <div class="connector {get_state(key, total)}" aria-hidden="true"></div>

      <div class="step {get_state(key, total)}" role="listitem" aria-label="Keywords: {key_done} of {total}">
        <div class="step-dot">5</div>
        <div class="step-label">Keywords</div>
        <div class="step-count">{key_done} / {total}</div>
      </div>
    </div>
    """
