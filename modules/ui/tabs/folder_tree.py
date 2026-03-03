"""
Folder Tree tab module for hierarchical folder navigation.

Provides:
- Interactive folder tree with selection
- Phase-launch buttons that **directly start jobs** (not just navigate tabs)
- Folder phase status strip showing per-phase completion badges

The create_tab() function accepts runner instances so buttons can launch
jobs directly from the Folder Tree without switching tabs.
"""
import gradio as gr
from modules import ui_tree, utils, db, config, thumbnails
from modules.phases import PhaseCode, PhaseRegistry
import os
import platform
import logging

logger = logging.getLogger(__name__)

IS_WINDOWS = (platform.system() == 'Windows')

# Status badge mapping
_STATUS_BADGES = {
    "done":        "✅",
    "partial":     "⏳",
    "not_started": "❌",
    "failed":      "⚠️",
    "running":     "🔄",
}


def _build_phase_status_html(folder_path):
    """Build an HTML status strip showing per-phase completion for a folder."""
    if not folder_path:
        return ""

    wsl_folder = utils.convert_path_to_wsl(folder_path) if hasattr(utils, 'convert_path_to_wsl') else folder_path
    summary = db.get_folder_phase_summary(wsl_folder)

    if not summary:
        return "<div style='color: #888; padding: 4px;'>No phase data available.</div>"

    badges = []
    for ph in summary:
        icon = _STATUS_BADGES.get(ph["status"], "❓")
        count_text = f"{ph['done_count']}/{ph['total_count']}" if ph["total_count"] > 0 else "—"
        badges.append(
            f'<span style="display:inline-block; margin:2px 8px 2px 0; padding:3px 8px; '
            f'border-radius:6px; background:#1a1a2e; color:#e0e0e0; font-size:0.85em;">'
            f'{icon} <b>{ph["name"]}</b> <span style="color:#999;">({count_text})</span>'
            f'</span>'
        )

    return f'<div style="padding:4px 0;">{"".join(badges)}</div>'


def create_tab(app_config, scoring_runner=None, tagging_runner=None, selection_runner=None):
    """
    Creates the Folder Tree tab.

    Args:
        app_config: Application configuration.
        scoring_runner: ScoringRunner instance (for Run Scoring).
        tagging_runner: TaggingRunner instance (for Run Keywords).
        selection_runner: SelectionRunner instance (for Run Culling).

    Returns:
        dict: Components for wiring in main app.
    """
    PAGE_SIZE = app_config.get('ui', {}).get('gallery_page_size', 50)

    def update_tree_status(folder):
        if not folder:
            return "No folder selected.", ""

        wsl_folder = utils.convert_path_to_wsl(folder)
        rows = db.get_images_by_folder(wsl_folder)

        total_count = len(rows)

        status = f"{total_count} image{'s' if total_count != 1 else ''} in folder"
        if total_count > PAGE_SIZE:
            status += f" (showing first {PAGE_SIZE})"

        phase_html = _build_phase_status_html(folder)
        return status, phase_html

    def refresh_tree_wrapper():
        msg = db.rebuild_folder_cache()
        return ui_tree.get_tree_html(), msg

    # --- Direct job launch handlers ---

    def run_scoring_job(folder):
        """Start scoring job directly from Folder Tree."""
        if not folder:
            return "⚠️ No folder selected."
        if scoring_runner is None:
            return "⚠️ Scoring runner not available."

        # Check if already running
        status = scoring_runner.get_status()
        if status[0]:  # is_running
            return "⚠️ Scoring is already running."

        wsl_folder = utils.convert_path_to_wsl(folder)
        job_id = db.create_job(wsl_folder, phase_code=PhaseCode.SCORING, job_type="scoring")
        scoring_runner.start_batch(wsl_folder, job_id=job_id, skip_existing=True)
        return f"✅ Scoring started for {os.path.basename(folder)} (Job #{job_id})"

    def run_culling_job(folder):
        """Start culling/selection job directly from Folder Tree."""
        if not folder:
            return "⚠️ No folder selected."
        if selection_runner is None:
            return "⚠️ Selection runner not available."

        status = selection_runner.get_status()
        if status[0]:  # is_running
            return "⚠️ Selection is already running."

        wsl_folder = utils.convert_path_to_wsl(folder)
        job_id = db.create_job(wsl_folder, phase_code=PhaseCode.CULLING, job_type="selection")
        selection_runner.start_batch(wsl_folder, job_id=job_id)
        return f"✅ Culling started for {os.path.basename(folder)} (Job #{job_id})"

    def run_keywords_job(folder):
        """Start keywords/tagging job directly from Folder Tree."""
        if not folder:
            return "⚠️ No folder selected."
        if tagging_runner is None:
            return "⚠️ Tagging runner not available."

        status = tagging_runner.get_status()
        if status[0]:  # is_running
            return "⚠️ Keywords is already running."

        wsl_folder = utils.convert_path_to_wsl(folder)
        job_id = db.create_job(wsl_folder, phase_code=PhaseCode.KEYWORDS, job_type="tagging")
        tagging_runner.start_batch(wsl_folder, job_id=job_id)
        return f"✅ Keywords started for {os.path.basename(folder)} (Job #{job_id})"

    # --- UI Layout ---

    with gr.TabItem("Folder Tree", id="folder_tree"):
        # Row 1: Action Bar
        with gr.Row():
            t_refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0, min_width=100)
            _reg_scoring  = PhaseRegistry.get(PhaseCode.SCORING)
            _reg_culling  = PhaseRegistry.get(PhaseCode.CULLING)
            _reg_keywords = PhaseRegistry.get(PhaseCode.KEYWORDS)

            t_run_scoring_btn = gr.Button(
                "▶️ Run Scoring", variant="primary", size="sm", scale=1,
                interactive=(
                    scoring_runner is not None
                    and _reg_scoring is not None
                    and _reg_scoring.run_folder is not None
                )
            )
            t_run_culling_btn = gr.Button(
                "📚 Run Culling", variant="secondary", size="sm", scale=1,
                interactive=(
                    selection_runner is not None
                    and _reg_culling is not None
                    and _reg_culling.run_folder is not None
                )
            )
            t_run_keywords_btn = gr.Button(
                "🏷️ Run Keywords", variant="secondary", size="sm", scale=1,
                interactive=(
                    tagging_runner is not None
                    and _reg_keywords is not None
                    and _reg_keywords.run_folder is not None
                )
            )

        # Row 2: Phase Status Strip
        t_phase_status = gr.HTML(
            value="<div style='color:#666; padding:4px;'>Select a folder to view phase status.</div>",
            label="Pipeline Status",
            elem_classes=["phase-status-strip"]
        )

        # Row 3: Main Content — Tree
        with gr.Row():
            t_tree_view = gr.HTML(
                value=ui_tree.get_tree_html(),
                label="📁 Folder Tree",
                elem_classes=["folder-tree-container"]
            )

        # Divider
        gr.Markdown("---")

        # Row 4: Status Bar
        t_selected_path = gr.Textbox(
            elem_id="folder_tree_selection",
            label="Selected Folder",
            interactive=True
        )
        t_status = gr.Label(label="Status", elem_classes=["tree-status-label"])

        # --- Events ---

        t_refresh_btn.click(
            fn=refresh_tree_wrapper,
            inputs=[],
            outputs=[t_tree_view, t_status]
        )

        t_selected_path.change(
            fn=update_tree_status,
            inputs=[t_selected_path],
            outputs=[t_status, t_phase_status]
        )

        # Direct job launch buttons
        t_run_scoring_btn.click(
            fn=run_scoring_job,
            inputs=[t_selected_path],
            outputs=[t_status]
        )

        t_run_culling_btn.click(
            fn=run_culling_job,
            inputs=[t_selected_path],
            outputs=[t_status]
        )

        t_run_keywords_btn.click(
            fn=run_keywords_job,
            inputs=[t_selected_path],
            outputs=[t_status]
        )

    return {
        'refresh_btn': t_refresh_btn,
        'run_scoring_btn': t_run_scoring_btn,
        'run_culling_btn': t_run_culling_btn,
        'run_keywords_btn': t_run_keywords_btn,
        'selected_path': t_selected_path,
        'tree_view': t_tree_view,
        'status': t_status,
        'phase_status': t_phase_status,
    }
