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
        gal_outs = update_gallery_fn(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None)
        return gr.update(selected="gallery"), None, gr.update(visible=False), "", 1, *gal_outs
        
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
    
    gal_outs = update_gallery_fn(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    
    return gr.update(selected="gallery"), folder, gr.update(visible=True), folder_html, 1, *gal_outs

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

def open_stack_in_gallery(stack_id, sort_by, sort_order):
    """Switches to Gallery tab and displays only images from the selected stack."""
    if not stack_id:
        # Return empty/reset
        return (gr.update(selected="gallery"), None, gr.update(visible=False), "", 1, [], "", []) + tuple(common.get_empty_details())

    # Get images
    images = db.get_images_in_stack(stack_id)
    
    # Sort locally
    if sort_by and sort_by != "created_at":
         try:
             reverse = (sort_order == "desc")
             images.sort(key=lambda x: x[sort_by] if x[sort_by] is not None else (0 if reverse else 999), reverse=reverse)
         except:
             pass
    
    # Format for gallery
    gallery_imgs = []
    raw_paths = []
    
    score_map = {
        'score_general': ('score_general', 'Gen'),
        'score_technical': ('score_technical', 'Tech'),
        'score_aesthetic': ('score_aesthetic', 'Aes'),
        'created_at': ('score_general', 'Gen'), 
    }
    score_col, score_label = score_map.get(sort_by, ('score_general', 'Gen'))

    for row in images:
        file_path = row['file_path']
        if not file_path: continue
        
        raw_paths.append(file_path)
        file_name = os.path.basename(file_path)
        
        thumb = row['thumbnail_path']
        if thumb:
            p = utils.convert_path_to_local(thumb)
        else:
            p = utils.convert_path_to_local(file_path)
            
        score = row[score_col] if score_col in row.keys() else None
        score_str = f"{score:.2f}" if score is not None else "N/A"
        label = f"{file_name}\n{score_label}: {score_str}"
        gallery_imgs.append((p, label))
        
    stack_html = f"""
    <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📚</span>
        <div>
            <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">Stack Viewer</div>
            <div style="font-size: 0.8rem; color: #8b949e;">stack #{stack_id} • {len(images)} images</div>
        </div>
    </div>
    """
    
    # Return matched to open_folder_in_gallery outputs
    return (
        gr.update(selected="gallery"), 
        None, 
        gr.update(visible=True), 
        stack_html, 
        1, 
        gallery_imgs, 
        f"Stack ({len(images)})", 
        raw_paths
    ) + tuple(common.get_empty_details())
