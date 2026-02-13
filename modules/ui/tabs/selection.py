"""
Selection tab module for unified stack + pick/reject workflow.

Automated batch mode: creates stacks, assigns top 33% pick / bottom 33% reject,
writes to metadata. No gallery or manual review UI.
"""

import gradio as gr
from modules import config


def create_tab(runner, app_config):
    """
    Creates the Selection tab.
    Contract matches Scoring/Keywords: input path, start, stop, status, console.
    """
    def run_selection_wrapper(input_path, force_rescan):
        config.save_config_value("selection_input_path", input_path)
        msg = runner.start_batch(input_path, force_rescan=force_rescan)
        return msg, "Starting...", gr.update(interactive=False), gr.update(interactive=True)

    def stop_selection():
        runner.stop()

    sel_config = app_config.get("selection", {})

    with gr.TabItem("Selection", id="selection") as tab_item:
        gr.Markdown("### Stack + Selection")
        gr.Markdown("Automated batch mode: creates stacks, assigns pick/reject by score. No gallery in this tab.")
        with gr.Row():
            with gr.Column(scale=1, min_width=350):
                with gr.Group():
                    input_dir = gr.Textbox(
                        label="Input Folder Path",
                        placeholder="D:/Photos/...",
                        value=app_config.get("selection_input_path", ""),
                        info="Folder with scored images",
                    )
                    force_checkbox = gr.Checkbox(
                        label="Force Re-run",
                        value=sel_config.get("force_rescan_default", False),
                        info="Re-cluster stacks and reassign pick/reject",
                    )
                with gr.Row():
                    run_btn = gr.Button("Start Selection", variant="primary", size="lg")
                    stop_btn = gr.Button("Stop", variant="stop", interactive=False, size="lg")
            with gr.Column(scale=2):
                status_html = gr.HTML(label="Status")
                with gr.Accordion("Console Output", open=True):
                    log_output = gr.Textbox(
                        label="",
                        lines=15,
                        interactive=False,
                        show_label=False,
                        placeholder="Waiting for job to start...",
                    )

        run_btn.click(
            fn=run_selection_wrapper,
            inputs=[input_dir, force_checkbox],
            outputs=[log_output, status_html, run_btn, stop_btn],
        )
        stop_btn.click(fn=stop_selection, inputs=[], outputs=[])

    return {
        "tab_item": tab_item,
        "input_dir": input_dir,
        "log_output": log_output,
        "status_html": status_html,
        "run_btn": run_btn,
        "stop_btn": stop_btn,
    }


def get_status_update(runner):
    """Returns [log, status_html, run_btn_update, stop_btn_update] for polling."""
    running, log_text, status_msg, cur, tot = runner.get_status()

    if running:
        status_icon = "⚡"
        status_color = "#58a6ff"
    elif "error" in status_msg.lower() or "failed" in status_msg.lower():
        status_icon = "❌"
        status_color = "#f85149"
    elif "completed" in status_msg.lower() or "done" in status_msg.lower():
        status_icon = "✅"
        status_color = "#3fb950"
    else:
        status_icon = "⏸️"
        status_color = "#8b949e"

    status_html = f"""
    <div style="padding: 20px; background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border-radius: 12px; border: 1px solid #30363d;">
        <div style="display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 1.5rem;">{status_icon}</span>
            <div>
                <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">{status_msg}</div>
                <div style="font-size: 0.8rem; color: #8b949e;">Selection (Stack + Pick/Reject)</div>
            </div>
        </div>
    """
    if tot > 0:
        pct = (cur / tot) * 100
        status_html += f"""
        <div style="margin-top: 12px; color: #8b949e; font-size: 0.9rem;">
            Progress: {cur}% | {status_msg}
        </div>
        <div style="width: 100%; background: #21262d; border-radius: 8px; height: 8px; margin-top: 8px;">
            <div style="width: {pct}%; background: {status_color}; height: 8px; border-radius: 8px; transition: width 0.3s;"></div>
        </div>
        """
    status_html += "</div>"

    return [
        log_text,
        status_html,
        gr.update(interactive=not running),
        gr.update(interactive=running),
    ]
