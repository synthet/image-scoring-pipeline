"""
Folder Tree tab module for hierarchical folder navigation.

This module provides a tree view of folders containing scored images:
- Interactive folder tree with selection
- Quick preview of images in selected folder
- Navigation buttons to open folder in Gallery, Stacks, or Keywords tabs

The create_tab() function returns navigation buttons that are wired in app.py
for cross-tab navigation.
"""
import gradio as gr
from modules import ui_tree, utils, db, config
import os
import platform

IS_WINDOWS = (platform.system() == 'Windows')

def create_tab(app_config):
    """
    Creates the Folder Tree tab.
    
    Args:
        app_config: Application configuration.
        
    Returns:
        dict: Components (buttons, selection, etc.) for wiring in main app.
    """
    PAGE_SIZE = app_config.get('ui', {}).get('gallery_page_size', 50)

    def update_tree_status(folder):
        if not folder: 
            return "No folder selected."
        
        # Convert Windows path to WSL format for DB query
        # DB stores paths in WSL format (/mnt/d/...)
        wsl_folder = utils.convert_path_to_wsl(folder)
        rows = db.get_images_by_folder(wsl_folder)
        
        total_count = len(rows)
        
        # OPTIMIZATION: Limit to PAGE_SIZE to avoid slow Gradio rendering
        # Folder Tree is for quick preview; use "Open in Gallery" for full browsing
        rows = rows[:PAGE_SIZE]
        
        
        # OPTIMIZATION: Batch resolve paths
        image_ids = [row.get('id') for row in rows if row.get('id')]
        resolved_map = {}
        if image_ids:
            try:
                resolved_map = db.get_resolved_paths_batch(image_ids)
            except:
                pass

        results = []
        for row in rows:
            p = row['file_path']
            label = row['file_name']
            
            # OPTIMIZATION: Prioritize thumbnails, skip expensive existence checks
            # Trust DB paths - they were valid when stored
            thumb_path = row.get('thumbnail_path')
            
            image_id = row.get('id')
            
            # Optimized Resolution Logic
            resolved_p = None
            if image_id and image_id in resolved_map:
                cached_path = resolved_map[image_id]
                # Validate path (allow /mnt for WSL, reject mixed separators)
                if cached_path:
                    is_malformed = '\\' in cached_path and '/' in cached_path
                    if not is_malformed:
                        resolved_p = cached_path
            
            if resolved_p:
                p = resolved_p
            elif thumb_path:
                p = utils.resolve_file_path(thumb_path, image_id) or utils.convert_path_to_local(thumb_path)
            else:
                p = utils.resolve_file_path(p, image_id) or utils.convert_path_to_local(p)
            
        status = f"{total_count} image{'s' if total_count != 1 else ''} in folder"
        if total_count > PAGE_SIZE:
            status += f" (showing first {PAGE_SIZE})"
        return status

    def refresh_tree_wrapper():
        msg = db.rebuild_folder_cache()
        return ui_tree.get_tree_html(), msg



    with gr.TabItem("Folder Tree", id="folder_tree"):
        # Row 1: Action Bar
        with gr.Row():
            t_refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0, min_width=100)
            t_open_scoring_btn = gr.Button("▶️ Open in Scoring", variant="primary", size="sm", scale=1)
            t_open_selection_btn = gr.Button("📋 Open in Selection", variant="secondary", size="sm", scale=1)
            t_open_culling_btn = gr.Button("✂️ Open in Culling", variant="secondary", size="sm", scale=1)
            t_open_stacks_btn = gr.Button("📚 Open in Stacks", variant="secondary", size="sm", scale=1)
            t_open_keywords_btn = gr.Button("🏷️ Open in Keywords", variant="secondary", size="sm", scale=1)
        
        # Row 2: Main Content - Tree 
        with gr.Row():
            # Tree View
            t_tree_view = gr.HTML(
                value=ui_tree.get_tree_html(), # Initialize immediately if possible
                label="📁 Folder Tree",
                elem_classes=["folder-tree-container"]
            )
        
        # Divider
        gr.Markdown("---")
        
        # Row 3: Status Bar (full width)
        t_selected_path = gr.Textbox(
            elem_id="folder_tree_selection", 
            label="Selected Folder", 
            interactive=True
        )
        t_status = gr.Label(label="Status", elem_classes=["tree-status-label"])
        
        # Events
        t_refresh_btn.click(
            fn=refresh_tree_wrapper,
            inputs=[],
            outputs=[t_tree_view, t_status]
        )

        t_selected_path.change(
            fn=update_tree_status,
            inputs=[t_selected_path],
            outputs=[t_status]
        )
        
    return {
        'refresh_btn': t_refresh_btn,
        'open_scoring_btn': t_open_scoring_btn,
        'open_selection_btn': t_open_selection_btn,
        'open_culling_btn': t_open_culling_btn,
        'open_stacks_btn': t_open_stacks_btn,
        'open_keywords_btn': t_open_keywords_btn,
        'selected_path': t_selected_path,
        'tree_view': t_tree_view,
        'status': t_status # if needed
    }
