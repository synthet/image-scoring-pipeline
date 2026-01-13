"""
Navigation functions for cross-tab interactions in the WebUI.

This module provides functions to switch between tabs while preserving filter state
and context. All functions return Gradio component updates for seamless UI transitions.

Key functions:
- open_folder_in_gallery: Opens a folder in the Gallery tab with filters applied
- open_folder_in_stacks: Opens a folder in the Stacks tab
- open_folder_in_keywords: Opens a folder in the Keywords tab
- open_stack_in_gallery: Displays a stack's images in the Gallery tab

All navigation functions maintain consistency with the Gallery's sorting and filtering
logic to ensure a smooth user experience.
"""
import os
import gradio as gr
from modules import db, utils, ui_tree
from modules.ui import common

def open_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, update_gallery_fn):
    """
    Switches to gallery tab and filters by folder.
    
    Args:
        folder (str): The folder path to open.
        ...filters...
        update_gallery_fn (callable): The function to call to get gallery data.
    
    Returns:
        tuple: (Tabs update, folder state, context visible, folder html, page, *gallery_outputs)
    """
    if not folder:
        # If no folder provided, treat as "Reset / View All"
        print("DEBUG: No folder provided, resetting filter.")
        # Call update_gallery with None folder
        gal_outs = update_gallery_fn(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None, stack_id=None)
        # Returns: tabs, folder_state, stack_state, context_visible, folder_html, page, *gallery_outputs
        return gr.update(selected="gallery"), None, None, gr.update(visible=False), "", 1, *gal_outs
        
    print(f"DEBUG: open_folder_in_gallery called with folder='{folder}'")
    
    # Create HTML display
    folder_name = os.path.basename(folder)
    parent_path = os.path.dirname(folder)
    folder_html = f"""
    <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📁</span>
        <div>
            <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">{folder_name}</div>
            <div style="font-size: 0.8rem; color: #8b949e;">{parent_path}</div>
        </div>
    </div>
    """
    
    gal_outs = update_gallery_fn(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder, stack_id=None)
    
    return gr.update(selected="gallery"), folder, None, gr.update(visible=True), folder_html, 1, *gal_outs

def open_folder_in_stacks(folder):
    """Switches to Stacks tab and sets input folder."""
    if not folder:
        return gr.update(selected="stacks"), gr.update()
    return gr.update(selected="stacks"), folder

def open_folder_in_keywords(folder):
    """Switches to Keywords tab and sets input folder."""
    if not folder:
        return gr.update(selected="keywords"), gr.update()
    return gr.update(selected="keywords"), folder

def open_stack_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, update_gallery_fn):
    """Switches from Stacks to Gallery with folder filter."""
    return open_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, update_gallery_fn)

def open_stack_folder_in_tree(folder):
    """Switches from Stacks to Tree View and selects folder."""
    if not folder:
         return gr.update(selected="folder_tree"), gr.update(), gr.update()
         
    html = ui_tree.get_tree_html(folder)
    return gr.update(selected="folder_tree"), folder, html

def open_stack_in_gallery(stack_id, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, update_gallery_fn):
    """Switches to Gallery tab and displays only images from the selected stack."""
    # Get content via main gallery update function to ensure consistency (and filtering support)
    # Note: open_stack bypasses folder filter (folder=None) but sets stack_id
    
    gal_outs = update_gallery_fn(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None, stack_id=stack_id)
    
    # We need to get the image count for the label
    # The gal_outs[0] is images list, gal_outs[2] is total_pages, gal_outs[3] is raw_paths
    # Wait, gallery outputs from update_gallery in gallery.py: [images, label, raw_paths] + details
    # So gal_outs[0] is images (list of tuples), gal_outs[1] is page_label
    
    # Extract info from gal_outs if possible or just use the return
    page_label = gal_outs[1]
    
    stack_html = f"""
    <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📚</span>
        <div>
            <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">Stack Viewer</div>
            <div style="font-size: 0.8rem; color: #8b949e;">stack #{stack_id} • {page_label}</div>
        </div>
    </div>
    """
    
    # Returns: tabs, folder_state, stack_state, context_visible, folder_html, page, *gallery_outputs
    return (
        gr.update(selected="gallery"), 
        None,        # folder_state
        stack_id,    # stack_state
        gr.update(visible=True), 
        stack_html, 
        1,           # page
        *gal_outs
    )
