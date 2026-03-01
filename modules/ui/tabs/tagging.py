"""
Tagging (Keywords) tab module for AI-powered keyword extraction.

This module provides the UI for running keyword extraction jobs:
- Input folder selection
- Options for overwriting existing keywords and generating captions
- Real-time status updates via polling
- Console log output

The create_tab() function accepts a TaggingRunner instance and returns components
needed for status monitoring (log_output, status_html, buttons).
"""
import gradio as gr
from modules import db, config

def create_tab(runner, app_config):
    """
    Creates the Tagging (Keywords) tab.
    
    Args:
        runner: The TaggingRunner instance.
        app_config: Application configuration.
        
    Returns:
        dict: Components needed for external status updates (log_output, status_html, buttons).
    """

    def run_tagging_wrapper(input_path, custom_keywords, overwrite, generate_captions):
        """Wrapper to run tagging (Non-blocking)."""
        # Save Config
        config.save_config_value('tagging_input_path', input_path)
        
        # Simple keyword parsing
        keywords_list = None
        if custom_keywords:
            keywords_list = [k.strip() for k in custom_keywords.split(",") if k.strip()]
            
        # Create Job
        job_id = db.create_job(input_path)
            
        msg = runner.start_batch(input_path, job_id=job_id, custom_keywords=keywords_list, overwrite=overwrite, generate_captions=generate_captions)
        
        return f"Job {job_id}: {msg}", "Starting...", gr.update(interactive=False), gr.update(interactive=True)

    def stop_tagging():
        runner.stop()

    with gr.TabItem("Keywords", id="keywords") as tab_item:
        gr.Markdown("### 🏷️ AI Keyword Extraction")
        with gr.Row():
            with gr.Column(scale=1, min_width=350):
                with gr.Group():
                    k_input_dir = gr.Textbox(
                        label="📁 Input Folder Path", 
                        placeholder="D:\\Photos\\... (Leave empty for all)",
                        value=app_config.get('tagging_input_path', ''),
                        info="Process images from this folder"
                    )
                    # Hidden state - Custom Keywords removed from UI
                    k_custom = gr.State(value="")
                
                with gr.Row():
                    k_overwrite = gr.Checkbox(
                        label="Overwrite",
                        value=app_config.get('tagging', {}).get('overwrite_default', False)
                    )
                    k_captions = gr.Checkbox(
                        label="Captions",
                        value=app_config.get('tagging', {}).get('captions_default', False)
                    )
                    k_run_btn = gr.Button("▶ Generate", variant="primary")
                    k_stop_btn = gr.Button("⏹ Stop", variant="stop", interactive=False)
            
            with gr.Column(scale=2):
                # Status Card
                k_status_html = gr.HTML(label="Status")
                
                # Console Output
                with gr.Accordion("📋 Console Output", open=True):
                    k_log_output = gr.Textbox(
                        label="", 
                        lines=15, 
                        interactive=False,
                        show_label=False,
                        placeholder="Waiting for keyword extraction to start..."
                    )
        # Events
        k_run_btn.click(
            fn=run_tagging_wrapper,
            inputs=[k_input_dir, k_custom, k_overwrite, k_captions],
            outputs=[k_log_output, k_status_html, k_run_btn, k_stop_btn]
        )
        
        k_stop_btn.click(
            fn=stop_tagging,
            inputs=[],
            outputs=[]
        )
            
    return {
        'tab_item': tab_item,
        'input_dir': k_input_dir,
        'log_output': k_log_output,
        'status_html': k_status_html,
        'run_btn': k_run_btn,
        'stop_btn': k_stop_btn
    }

def get_status_update(runner):
    """
    Called by the main loop to get status updates for the Tagging tab.
    Returns: [log, status_html, run_btn_update, stop_btn_update]
    """
    t_running, t_log, t_status_msg, t_cur, t_tot = runner.get_status()
    
    # Determine tagging status icon and color
    if t_running:
        t_status_icon = "🏷️"
        t_status_color = "#a371f7"
    elif "Error" in t_status_msg or "Failed" in t_status_msg:
        t_status_icon = "❌"
        t_status_color = "#f85149"
    elif "Done" in t_status_msg or "Complete" in t_status_msg:
        t_status_icon = "✅"
        t_status_color = "#3fb950"
    else:
        t_status_icon = "⏸️"
        t_status_color = "#8b949e"
    
    # Build modern tagging status HTML
    t_status_html = f"""
    <div style="padding: 20px; background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border-radius: 12px; border: 1px solid #30363d;">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
            <span style="font-size: 1.5rem;">{t_status_icon}</span>
            <div>
                <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">{t_status_msg}</div>
                <div style="font-size: 0.8rem; color: #8b949e;">Keyword Extraction Engine</div>
            </div>
        </div>
    """
    
    if t_tot > 0:
        pct = (t_cur / t_tot) * 100
        t_status_html += f"""
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px; color: #8b949e; font-size: 0.9rem;">
            <span>Progress: {t_cur} / {t_tot} images</span>
            <span style="color: {t_status_color}; font-weight: 600;">{pct:.1f}%</span>
        </div>
        <div style="width: 100%; background-color: #21262d; border-radius: 8px; height: 10px; overflow: hidden;">
            <div style="width: {pct}%; background: linear-gradient(90deg, #a371f7 0%, #f778ba 100%); height: 10px; border-radius: 8px; transition: width 0.3s ease;"></div>
        </div>
        """
    elif t_running:
        t_status_html += f"""
        <div style="display: flex; align-items: center; gap: 8px; color: #8b949e;">
            <div style="width: 8px; height: 8px; background: {t_status_color}; border-radius: 50%; animation: pulse 1.5s infinite;"></div>
            <span>Scanning images...</span>
        </div>
        """
        
    t_status_html += "</div>"
    
    t_run_up = gr.update(interactive=not t_running)
    t_stop_up = gr.update(interactive=t_running)
    
    return t_log, t_status_html, t_run_up, t_stop_up
