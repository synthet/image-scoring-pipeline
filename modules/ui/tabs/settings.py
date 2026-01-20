"""
Settings/Configuration tab module for application settings.

This module provides UI for configuring:
- Scoring defaults (force re-score, default sort)
- Processing options (thread counts, batch sizes)
- Clustering parameters (threshold, time gap)
- Culling workflow settings
- UI preferences (page size, default sort)

All changes are saved to config.json and persist across sessions.
"""
import gradio as gr
from modules import config

def create_tab(app_config):
    """
    Creates the Settings/Configuration tab.
    
    Args:
        app_config (dict): The loaded application configuration.
        
    Returns:
        dict: A dictionary of components (currently empty/minimal as other tabs don't depend on these inputs directly).
    """
    
    # Load current config values with defaults
    scoring_config = app_config.get('scoring', {})
    processing_config = app_config.get('processing', {})
    clustering_config = app_config.get('clustering', {})
    culling_config = app_config.get('culling', {})
    ui_config = app_config.get('ui', {})
    tagging_config = app_config.get('tagging', {})
    
    with gr.TabItem("Configurations", id="configurations"):
        gr.Markdown("### ⚙️ Experimental & Advanced Configuration")
        gr.Markdown("*Configure experimental options and advanced settings. Changes are saved to config.json.*")
        
        # Scoring Configuration
        with gr.Accordion("🎯 Scoring Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_force_rescore = gr.Checkbox(
                        label="Force Re-score (Default)",
                        value=scoring_config.get('force_rescore_default', False),
                        info="Default value for 'Force Re-score' checkbox in Scoring tab"
                    )
                    cfg_default_sort_by = gr.Dropdown(
                        choices=[
                            ("📅 Date Added", "created_at"),
                            ("🆔 ID", "id"),
                            ("⭐ General Score", "score_general"),
                            ("🔧 Technical Score", "score_technical"),
                            ("🎨 Aesthetic Score", "score_aesthetic"),
                            ("⬤ SPAQ", "score_spaq"),
                            ("⬤ AVA", "score_ava"),
                            ("⬤ KonIQ", "score_koniq"),
                            ("⬤ PaQ2PiQ", "score_paq2piq"),
                            ("⬤ LIQE", "score_liqe")
                        ],
                        value=scoring_config.get('default_sort_by', 'score_general'),
                        label="Default Sort Field"
                    )
                    cfg_default_sort_order = gr.Radio(
                        choices=[("↓ Descending (Highest First)", "desc"), ("↑ Ascending (Lowest First)", "asc")],
                        value=scoring_config.get('default_sort_order', 'desc'),
                        label="Default Sort Order"
                    )
        
        # Processing Configuration
        with gr.Accordion("⚙️ Processing Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Queue Sizes** (for threaded pipeline)")
                    cfg_prep_queue_size = gr.Number(
                        value=processing_config.get('prep_queue_size', 50),
                        label="Prep Queue Max Size",
                        info="Maximum items in preparation queue (default: 50)"
                    )
                    cfg_scoring_queue_size = gr.Number(
                        value=processing_config.get('scoring_queue_size', 10),
                        label="Scoring Queue Max Size",
                        info="Maximum items in scoring queue - keep small to avoid VRAM overload (default: 10)"
                    )
                    cfg_result_queue_size = gr.Number(
                        value=processing_config.get('result_queue_size', 50),
                        label="Result Queue Max Size",
                        info="Maximum items in result queue (default: 50)"
                    )
                with gr.Column():
                    gr.Markdown("**Batch Processing**")
                    cfg_clustering_batch_size = gr.Number(
                        value=processing_config.get('clustering_batch_size', 32),
                        label="Clustering Batch Size",
                        info="Number of images processed per batch for clustering (default: 32)"
                    )
                    cfg_enable_gpu = gr.Checkbox(
                        label="Enable GPU for Scoring",
                        value=processing_config.get('enable_gpu', True),
                        info="Use GPU acceleration for model inference (if available)"
                    )
        
        # Clustering/Stacks Configuration
        with gr.Accordion("📚 Clustering/Stacks Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_clustering_threshold = gr.Slider(
                        0.01, 1.0,
                        value=clustering_config.get('default_threshold', 0.15),
                        step=0.01,
                        label="Default Similarity Threshold",
                        info="Default threshold for grouping similar images (0.01-1.0)"
                    )
                    cfg_clustering_time_gap = gr.Number(
                        value=clustering_config.get('default_time_gap', 120),
                        label="Default Time Gap (seconds)",
                        info="Default time gap for splitting groups (default: 120)"
                    )
                    cfg_clustering_force_rescan = gr.Checkbox(
                        label="Force Rescan (Default)",
                        value=clustering_config.get('force_rescan_default', False),
                        info="Default value for 'Force Rescan' checkbox in Stacks tab"
                    )
        
        # Culling Configuration
        with gr.Accordion("✂️ Culling Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_culling_threshold = gr.Slider(
                        0.05, 0.5,
                        value=culling_config.get('default_threshold', 0.15),
                        step=0.05,
                        label="Default Similarity Threshold",
                        info="Default threshold for culling groups (0.05-0.5)"
                    )
                    cfg_culling_time_gap = gr.Number(
                        value=culling_config.get('default_time_gap', 120),
                        label="Default Time Gap (seconds)",
                        info="Default time gap for splitting culling groups (default: 120)"
                    )
                    cfg_culling_auto_export = gr.Checkbox(
                        label="Auto Export (Default)",
                        value=culling_config.get('auto_export_default', False),
                        info="Default value for 'Auto-export to XMP' checkbox in Culling tab"
                    )
                with gr.Column():
                    gr.Markdown("**Rating Thresholds**")
                    cfg_culling_pick_rating = gr.Slider(
                        1, 5,
                        value=culling_config.get('pick_rating_threshold', 4),
                        step=1,
                        label="Pick Rating Threshold (stars)",
                        info="Minimum rating for 'picks' (default: 4)"
                    )
                    cfg_culling_reject_rating = gr.Slider(
                        0, 2,
                        value=culling_config.get('reject_rating_threshold', 1),
                        step=1,
                        label="Reject Rating Threshold (stars)",
                        info="Maximum rating for 'rejects' (default: 1)"
                    )
        
        # UI Configuration
        with gr.Accordion("🖼️ UI Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_gallery_page_size = gr.Number(
                        value=ui_config.get('gallery_page_size', 50),
                        label="Gallery Page Size",
                        info="Number of images per page in gallery (default: 50)"
                    )
                    cfg_default_export_format = gr.Dropdown(
                        choices=[
                            ("📄 JSON (Full Data)", "json"),
                            ("📊 CSV (Spreadsheet)", "csv"),
                            ("📗 Excel (.xlsx)", "xlsx")
                        ],
                        value=ui_config.get('default_export_format', 'json'),
                        label="Default Export Format"
                    )
                with gr.Column():
                    gr.Markdown("**Default Filter Minimum Scores**")
                    cfg_default_min_general = gr.Slider(
                        0.0, 1.0,
                        value=ui_config.get('default_min_general', 0.0),
                        step=0.05,
                        label="Min General Score",
                        info="Default minimum general score filter"
                    )
                    cfg_default_min_aesthetic = gr.Slider(
                        0.0, 1.0,
                        value=ui_config.get('default_min_aesthetic', 0.0),
                        step=0.05,
                        label="Min Aesthetic Score",
                        info="Default minimum aesthetic score filter"
                    )
                    cfg_default_min_technical = gr.Slider(
                        0.0, 1.0,
                        value=ui_config.get('default_min_technical', 0.0),
                        step=0.05,
                        label="Min Technical Score",
                        info="Default minimum technical score filter"
                    )
        
        # Tagging Configuration
        with gr.Accordion("🏷️ Tagging Configuration", open=False):
            with gr.Row():
                with gr.Column():
                    cfg_tagging_overwrite = gr.Checkbox(
                        label="Overwrite Existing Tags (Default)",
                        value=tagging_config.get('overwrite_default', False),
                        info="Default value for 'Overwrite' checkbox in Tagging tab"
                    )
                    cfg_tagging_captions = gr.Checkbox(
                        label="Generate Captions (Default)",
                        value=tagging_config.get('captions_default', False),
                        info="Default value for 'Captions' checkbox in Tagging tab"
                    )
                    cfg_tagging_max_tokens = gr.Number(
                        value=tagging_config.get('max_new_tokens', 50),
                        label="Max New Tokens (BLIP)",
                        info="Maximum tokens for BLIP caption generation (default: 50)"
                    )
                with gr.Column():
                    cfg_tagging_clip_model = gr.Dropdown(
                        choices=[
                            ("CLIP Base (ViT-B/32)", "openai/clip-vit-base-patch32"),
                            ("CLIP Large (ViT-L/14)", "openai/clip-vit-large-patch14")
                        ],
                        value=tagging_config.get('clip_model', 'openai/clip-vit-base-patch32'),
                        label="CLIP Model Selection",
                        info="CLIP model for keyword extraction"
                    )
        
        # Save and Reset buttons
        with gr.Row():
            cfg_save_btn = gr.Button("💾 Save All Configuration", variant="primary", size="lg")
            cfg_reset_btn = gr.Button("🔄 Reset to Defaults", variant="secondary", size="lg")
        
        cfg_status = gr.Textbox(label="Status", interactive=False, visible=False)
        
        # Configuration save handler
        def save_all_config(
            force_rescore, sort_by, sort_order,
            prep_queue, scoring_queue, result_queue, clustering_batch, enable_gpu,
            clust_threshold, clust_gap, clust_force,
            cull_threshold, cull_gap, cull_auto, cull_pick, cull_reject,
            page_size, export_format, min_gen, min_aes, min_tech,
            tag_overwrite, tag_captions, tag_tokens, tag_clip_model
        ):
            try:
                # Save each section
                config.save_config_value('scoring', {
                    'force_rescore_default': force_rescore,
                    'default_sort_by': sort_by,
                    'default_sort_order': sort_order
                })
                config.save_config_value('processing', {
                    'prep_queue_size': int(prep_queue) if prep_queue else 50,
                    'scoring_queue_size': int(scoring_queue) if scoring_queue else 10,
                    'result_queue_size': int(result_queue) if result_queue else 50,
                    'clustering_batch_size': int(clustering_batch) if clustering_batch else 32,
                    'enable_gpu': enable_gpu
                })
                config.save_config_value('clustering', {
                    'default_threshold': float(clust_threshold) if clust_threshold else 0.15,
                    'default_time_gap': int(clust_gap) if clust_gap else 120,
                    'force_rescan_default': clust_force
                })
                config.save_config_value('culling', {
                    'default_threshold': float(cull_threshold) if cull_threshold else 0.15,
                    'default_time_gap': int(cull_gap) if cull_gap else 120,
                    'auto_export_default': cull_auto,
                    'pick_rating_threshold': int(cull_pick) if cull_pick else 4,
                    'reject_rating_threshold': int(cull_reject) if cull_reject else 1
                })
                config.save_config_value('ui', {
                    'gallery_page_size': int(page_size) if page_size else 50,
                    'default_export_format': export_format,
                    'default_min_general': float(min_gen) if min_gen else 0.0,
                    'default_min_aesthetic': float(min_aes) if min_aes else 0.0,
                    'default_min_technical': float(min_tech) if min_tech else 0.0
                })
                config.save_config_value('tagging', {
                    'overwrite_default': tag_overwrite,
                    'captions_default': tag_captions,
                    'max_new_tokens': int(tag_tokens) if tag_tokens else 50,
                    'clip_model': tag_clip_model
                })
                return gr.update(value="✅ Configuration saved successfully! Restart the application for some changes to take effect.", visible=True)
            except Exception as e:
                return gr.update(value=f"❌ Error saving configuration: {str(e)}", visible=True)
        
        # Reset to defaults handler
        def reset_config_defaults():
            defaults = {
                'force_rescore': False,
                'sort_by': 'score_general',
                'sort_order': 'desc',
                'prep_queue': 50,
                'scoring_queue': 10,
                'result_queue': 50,
                'clustering_batch': 32,
                'enable_gpu': True,
                'clust_threshold': 0.15,
                'clust_gap': 120,
                'clust_force': False,
                'cull_threshold': 0.15,
                'cull_gap': 120,
                'cull_auto': False,
                'cull_pick': 4,
                'cull_reject': 1,
                'page_size': 50,
                'export_format': 'json',
                'min_gen': 0.0,
                'min_aes': 0.0,
                'min_tech': 0.0,
                'tag_overwrite': False,
                'tag_captions': False,
                'tag_tokens': 50,
                'tag_clip_model': 'openai/clip-vit-base-patch32'
            }
            return (
                defaults['force_rescore'], defaults['sort_by'], defaults['sort_order'],
                defaults['prep_queue'], defaults['scoring_queue'], defaults['result_queue'],
                defaults['clustering_batch'], defaults['enable_gpu'],
                defaults['clust_threshold'], defaults['clust_gap'], defaults['clust_force'],
                defaults['cull_threshold'], defaults['cull_gap'], defaults['cull_auto'],
                defaults['cull_pick'], defaults['cull_reject'],
                defaults['page_size'], defaults['export_format'],
                defaults['min_gen'], defaults['min_aes'], defaults['min_tech'],
                defaults['tag_overwrite'], defaults['tag_captions'],
                defaults['tag_tokens'], defaults['tag_clip_model']
            )
        
        # Wire up events
        cfg_inputs = [
            cfg_force_rescore, cfg_default_sort_by, cfg_default_sort_order,
            cfg_prep_queue_size, cfg_scoring_queue_size, cfg_result_queue_size,
            cfg_clustering_batch_size, cfg_enable_gpu,
            cfg_clustering_threshold, cfg_clustering_time_gap, cfg_clustering_force_rescan,
            cfg_culling_threshold, cfg_culling_time_gap, cfg_culling_auto_export,
            cfg_culling_pick_rating, cfg_culling_reject_rating,
            cfg_gallery_page_size, cfg_default_export_format,
            cfg_default_min_general, cfg_default_min_aesthetic, cfg_default_min_technical,
            cfg_tagging_overwrite, cfg_tagging_captions, cfg_tagging_max_tokens, cfg_tagging_clip_model
        ]
        
        cfg_save_btn.click(
            fn=save_all_config,
            inputs=cfg_inputs,
            outputs=[cfg_status]
        )
        
        cfg_reset_btn.click(
            fn=reset_config_defaults,
            inputs=[],
            outputs=cfg_inputs
        )
        
    return {}
