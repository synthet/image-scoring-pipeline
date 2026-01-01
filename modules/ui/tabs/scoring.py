"""
Scoring tab module for batch image quality assessment.

This module provides the UI for running MUSIQ model scoring jobs:
- Input folder selection with force re-score option
- Real-time status updates via polling
- Console log output
- Database fix operation for missing scores

The create_tab() function accepts a ScoringRunner instance and returns components
needed for status monitoring (log_output, status_html, buttons).
"""
import gradio as gr
from modules import db, config

def create_tab(runner, app_config):
    """
    Creates the Scoring tab.
    
    Args:
        runner: The ScoringRunner instance.
        app_config: Application configuration.
        
    Returns:
        dict: Components needed for external status updates (log_output, status_html, buttons).
    """
    
    def run_scoring_wrapper(input_path, force_rescore):
        """Wrapper to run scoring (Non-blocking)."""
        # Save Config
        config.save_config_value('scoring_input_path', input_path)
        
        # Create Job ID
        job_id = db.create_job(input_path)
        
        # Start Runner
        msg = runner.start_batch(input_path, job_id, not force_rescore)
        
        # Return initial state
        # Log, Status, RunBtn, StopBtn, FixBtn
        return msg, "Starting...", gr.update(interactive=False), gr.update(interactive=True), gr.update(interactive=False)

    def run_fix_db_wrapper():
        """Wrapper to run DB fix (Non-blocking)."""
        job_id = db.create_job("DB_FIX_OPERATION")
        msg = runner.start_fix_db(job_id)
        
        return msg, "Starting Fix...", gr.update(interactive=False), gr.update(interactive=True), gr.update(interactive=False)

    def stop_scoring():
         runner.stop()

    with gr.TabItem("Run Scoring", id="scoring") as tab_item:
        gr.Markdown("### 🎯 Image Quality Scoring")
        with gr.Row():
            with gr.Column(scale=1, min_width=350):
                with gr.Group():
                    input_dir = gr.Textbox(
                        label="📁 Input Folder Path", 
                        placeholder="D:\\Photos\\2024\\...",
                        value=app_config.get('scoring_input_path', ''),
                        info="Select folder containing images to score"
                    )
                    force_checkbox = gr.Checkbox(
                        label="🔄 Force Re-score", 
                        value=app_config.get('scoring', {}).get('force_rescore_default', False),
                        info="Overwrite existing scores in database"
                    )
                
                with gr.Row():
                    run_btn = gr.Button("▶️ Start Scoring", variant="primary", size="lg")
                    stop_btn = gr.Button("⏹️ Stop", variant="stop", interactive=False, size="lg")
                
                fix_btn = gr.Button("🔧 Fix Database (Re-run missing)", variant="secondary", size="sm")
            
            with gr.Column(scale=2):
                # Status Card
                s_status_html = gr.HTML(label="Status")
                
                # Console Output
                with gr.Accordion("📋 Console Output", open=True):
                    log_output = gr.Textbox(
                        label="", 
                        lines=15, 
                        interactive=False,
                        show_label=False,
                        placeholder="Waiting for scoring job to start..."
                    )
        
        # Events
        run_btn.click(
            fn=run_scoring_wrapper,
            inputs=[input_dir, force_checkbox],
            outputs=[log_output, s_status_html, run_btn, stop_btn, fix_btn]
        )
        
        stop_btn.click(
            fn=stop_scoring,
            inputs=[],
            outputs=[]
        )
        
        fix_btn.click(
            fn=run_fix_db_wrapper,
            inputs=[],
            outputs=[log_output, s_status_html, run_btn, stop_btn, fix_btn]
        )
        
    return {
        'tab_item': tab_item,
        'input_dir': input_dir,
        'log_output': log_output,
        'status_html': s_status_html,
        'run_btn': run_btn,
        'stop_btn': stop_btn,
        'fix_btn': fix_btn
    }

def get_status_update(runner):
    """
    Called by the main loop to get status updates for the Scoring tab.
    Returns: [log, status_html, run_btn_update, stop_btn_update, fix_btn_update]
    """
    s_running, s_log, s_status_msg, s_cur, s_tot = runner.get_status()
    
    # Determine status icon and color
    if s_running:
        status_icon = "⚡"
        status_color = "#58a6ff"
        badge_bg = "rgba(88, 166, 255, 0.15)"
    elif "Error" in s_status_msg or "Failed" in s_status_msg:
        status_icon = "❌"
        status_color = "#f85149"
        badge_bg = "rgba(248, 81, 73, 0.15)"
    elif "Done" in s_status_msg or "Complete" in s_status_msg:
        status_icon = "✅"
        status_color = "#3fb950"
        badge_bg = "rgba(63, 185, 80, 0.15)"
    else:
        status_icon = "⏸️"
        status_color = "#8b949e"
        badge_bg = "rgba(139, 148, 158, 0.15)"
    
    # Build modern status HTML
    s_status_html = f"""
    <div style="padding: 20px; background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border-radius: 12px; border: 1px solid #30363d;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
            <span style="font-size: 1.5rem;">{status_icon}</span>
            <div>
                <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">{s_status_msg}</div>
                <div style="font-size: 0.8rem; color: #8b949e;">Image Scoring Engine</div>
            </div>
        </div>
    """
    
    if s_tot > 0:
        pct = (s_cur / s_tot) * 100
        s_status_html += f"""
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px; color: #8b949e; font-size: 0.9rem;">
            <span>Progress: {s_cur} / {s_tot} images</span>
            <span style="color: {status_color}; font-weight: 600;">{pct:.1f}%</span>
        </div>
        <div style="width: 100%; background-color: #21262d; border-radius: 8px; height: 10px; overflow: hidden;">
            <div style="width: {pct}%; background: linear-gradient(90deg, #58a6ff 0%, #a371f7 100%); height: 10px; border-radius: 8px; transition: width 0.3s ease;"></div>
        </div>
        """
    elif s_running:
        s_status_html += f"""
        <div style="display: flex; align-items: center; gap: 8px; color: #8b949e;">
            <div style="width: 8px; height: 8px; background: {status_color}; border-radius: 50%; animation: pulse 1.5s infinite;"></div>
            <span>Initializing...</span>
        </div>
        <style>@keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}</style>
        """
    
    s_status_html += "</div>"
    
    s_run_up = gr.update(interactive=not s_running)
    s_stop_up = gr.update(interactive=s_running)
    s_fix_up = gr.update(interactive=not s_running)
    
    return s_log, s_status_html, s_run_up, s_stop_up, s_fix_up
