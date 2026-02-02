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

    def update_tree_gallery(folder):
        if not folder: 
            return [], "No folder selected."
        
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
            
            results.append((p, label))

        # Show count with note if truncated
        folder_name = os.path.basename(folder)
        if total_count > PAGE_SIZE:
            status = f"Showing {len(results)} of {total_count} images in {folder_name} (use 'Open in Gallery' for full view)"
        else:
            status = f"Found {total_count} images in {folder_name}"
        
        return results, status

    def refresh_tree_wrapper():
        msg = db.rebuild_folder_cache()
        return ui_tree.get_tree_html(), msg

    def delete_folder_cache_wrapper(folder, confirmed):
        if not confirmed:
            return ui_tree.get_tree_html(), "⚠️ Check confirmation to delete the selected folder from DB cache.", "", []
        if not folder:
            return ui_tree.get_tree_html(), "⚠️ No folder selected.", "", []

        result = db.delete_folder_cache_entry(folder_path=folder, delete_descendants=True)
        if not result.get("success"):
            return ui_tree.get_tree_html(), f"❌ {result.get('message', 'Delete failed')}", folder, []

        # Clear selection + gallery preview after successful delete
        return ui_tree.get_tree_html(), f"🗑️ {result.get('message', 'Deleted')}", "", []

    with gr.TabItem("Folder Tree", id="folder_tree"):
        # Row 1: Action Bar
        with gr.Row():
            t_refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0, min_width=100)
            t_open_gallery_btn = gr.Button("📸 Open in Gallery", variant="primary", size="sm", scale=1)
            t_open_stacks_btn = gr.Button("📚 Open in Stacks", variant="secondary", size="sm", scale=1)
            t_open_keywords_btn = gr.Button("🏷️ Open in Keywords", variant="secondary", size="sm", scale=1)
            t_delete_confirm = gr.Checkbox(label="Confirm", value=False, scale=0, min_width=90)
            t_delete_btn = gr.Button("🗑️ Remove from DB", variant="stop", size="sm", scale=0, min_width=160)
        
        # Row 2: Main Content - Tree | Gallery (equal width)
        with gr.Row(equal_height=True):
            # Left: Tree View
            with gr.Column(scale=1):
                # Init with empty tree, will be loaded on app start or via loop
                t_tree_view = gr.HTML(
                    value=ui_tree.get_tree_html(), # Initialize immediately if possible
                    label="📁 Folder Tree",
                    elem_classes=["folder-tree-container"]
                )
            
            # Right: Gallery Preview
            with gr.Column(scale=1):
                t_gallery = gr.Gallery(
                    label="Folder Images", 
                    columns=4, 
                    height=500,
                    object_fit="cover",
                    allow_preview=True,
                    show_share_button=False
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

        t_delete_btn.click(
            fn=delete_folder_cache_wrapper,
            inputs=[t_selected_path, t_delete_confirm],
            outputs=[t_tree_view, t_status, t_selected_path, t_gallery]
        )
        
        t_selected_path.change(
            fn=update_tree_gallery,
            inputs=[t_selected_path],
            outputs=[t_gallery, t_status]
        )
        
    return {
        'refresh_btn': t_refresh_btn,
        'open_gallery_btn': t_open_gallery_btn,
        'open_stacks_btn': t_open_stacks_btn,
        'open_keywords_btn': t_open_keywords_btn,
        'selected_path': t_selected_path,
        'tree_view': t_tree_view,
        'gallery': t_gallery,
        'status': t_status # if needed
    }
