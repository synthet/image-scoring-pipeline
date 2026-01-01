import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging (1=INFO, 2=WARN, 3=ERROR)

import warnings
# Suppress Gradio 6.0 deprecation warnings for css/head parameters (will migrate when 6.0 is released)
warnings.filterwarnings("ignore", message="The 'css' parameter in the Blocks constructor")
warnings.filterwarnings("ignore", message="The 'head' parameter in the Blocks constructor")

import gradio as gr
import threading
import time
import math
import json
import platform
from pathlib import Path
from modules import scoring, db, tagging, config, clustering, thumbnails, ui_tree, utils, culling

# Cache platform check at module load (not per-request)
IS_WINDOWS = platform.system() == "Windows"

# MCP Server Integration (optional - for Cursor debugging)
MCP_ENABLED = os.environ.get('ENABLE_MCP_SERVER', '0') == '1'
try:
    from modules import mcp_server
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Initialize DB on load
db.init_db()

# Load Config
app_config = config.load_config()

runner = scoring.ScoringRunner()
tagging_runner = tagging.TaggingRunner()
cluster_engine = clustering.ClusteringEngine()

# Initialize MCP server if enabled
if MCP_AVAILABLE and MCP_ENABLED:
    mcp_server.set_runners(runner, tagging_runner)
    print("MCP Server: Runners registered for debugging access")


def run_scoring_wrapper(input_path, force_rescore):
    """
    Wrapper to run scoring (Non-blocking).
    """
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
    """
    Wrapper to run DB fix (Non-blocking).
    """
    job_id = db.create_job("DB_FIX_OPERATION")
    msg = runner.start_fix_db(job_id)
    
    return msg, "Starting Fix...", gr.update(interactive=False), gr.update(interactive=True), gr.update(interactive=False)

def monitor_status():
    """
    Polls status from runners.
    Returns updates for:
    [s_log, s_status, s_run, s_stop, s_fix, k_log, k_status, k_run, k_stop]
    """
    # Scoring Status
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
    
    # Tagging Status
    t_running, t_log, t_status_msg, t_cur, t_tot = tagging_runner.get_status()
    
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
    
    return [
        s_log, s_status_html, s_run_up, s_stop_up, s_fix_up,
        t_log, t_status_html, t_run_up, t_stop_up
    ]

def run_tagging_wrapper(input_path, custom_keywords, overwrite, generate_captions):
    """
    Wrapper to run tagging (Non-blocking).
    """
    # Save Config
    config.save_config_value('tagging_input_path', input_path)
    
    # Simple keyword parsing
    keywords_list = None
    if custom_keywords:
        keywords_list = [k.strip() for k in custom_keywords.split(",") if k.strip()]
        
    msg = tagging_runner.start_batch(input_path, keywords_list, overwrite, generate_captions)
    
    return msg, "Starting...", gr.update(interactive=False), gr.update(interactive=True)

# Pagination State - Load from config
PAGE_SIZE = app_config.get('ui', {}).get('gallery_page_size', 50)

def get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    """Fetch images for gallery with pagination."""
    
    date_range = (start_date, end_date) if (start_date or end_date) else None
    
    try:
        rows = db.get_images_paginated(
            page, PAGE_SIZE, sort_by, sort_order, 
            rating_filter, label_filter, keyword_filter, 
            min_score_general=min_gen, 
            min_score_aesthetic=min_aes, 
            min_score_technical=min_tech, 
            date_range=date_range,
            folder_path=folder
        )
    except Exception as e:
        rows = []
    
    try:
        total_count = db.get_image_count(
            rating_filter, label_filter, keyword_filter,
            min_score_general=min_gen, 
            min_score_aesthetic=min_aes, 
            min_score_technical=min_tech, 
            date_range=date_range,
            folder_path=folder
        )
    except Exception as e:
        total_count = 0
    
    total_pages = math.ceil(total_count / PAGE_SIZE) if total_count > 0 else 1
    
    # Pre-fetch stack contexts for all images in batch (efficient single query)
    image_ids = [row['id'] for row in rows if 'id' in row.keys()]
    stack_contexts = db.get_stack_contexts_batch(image_ids) if image_ids else {}
    
    results = []
    raw_paths = []
    
    for row in rows:
        # sqlite3.Row access
        file_path = row['file_path']
        raw_paths.append(file_path)
        
        thumb_path = row['thumbnail_path'] if 'thumbnail_path' in row.keys() else None
        
        # OPTIMIZATION: Use thumbnail if available, skip expensive os.path.exists() check
        # Trust DB paths - they were validated when stored
        image_path = thumb_path if thumb_path else file_path
        
        # Convert WSL path to Windows path if needed (DB stores Windows-style paths, but may have WSL format)
        # Gradio needs Windows paths when running on Windows
        original_path = image_path
        if IS_WINDOWS and image_path.startswith("/mnt/"):
            image_path = utils.convert_path_to_local(image_path)
        elif not IS_WINDOWS and ":" in image_path and image_path[1] == ":":
            # Windows path on Linux/WSL - convert to WSL format
            image_path = utils.convert_path_to_wsl(image_path)
            
        # Ensure absolute path for Gradio
        before_abspath = image_path
        image_path = os.path.abspath(image_path)
        
        # Format path for display (showing parent directory)
        display_folder = os.path.dirname(file_path)
        
        # Dynamic Label Generation based on Sort Criteria
        if sort_by == "created_at":
             date_val = row['created_at']
             # Truncate microseconds if present
             if date_val and isinstance(date_val, str) and "." in date_val:
                 date_val = date_val.split('.')[0]
             label = f"{row['file_name']} ({date_val})"
             
        elif sort_by.startswith("score_"):
             # Specific Score
             val = row[sort_by]
             val = val if val is not None else 0.0
             
             # Pretty Label
             lbl_map = {
                 "score_general": "General",
                 "score_technical": "Technical", 
                 "score_aesthetic": "Aesthetic",
                 "score_spaq": "SPAQ",
                 "score_ava": "AVA",
                 "score_koniq": "KonIQ",
                 "score_paq2piq": "PaQ2PiQ",
                 "score_liqe": "LIQE"
             }
             metric_name = lbl_map.get(sort_by, sort_by.replace("score_", "").title())
             label = f"{row['file_name']} ({metric_name}: {val:.2f})"
             
        else:
             # Fallback (shouldn't happen with current dropdown)
             label = row['file_name']
        
        # Add stack badge if image is part of a stack
        image_id = row['id'] if 'id' in row.keys() else None
        if image_id and image_id in stack_contexts:
            ctx = stack_contexts[image_id]
            if ctx['is_best']:
                label = f"📚⭐ {label} (Best of {ctx['stack_size']})"
            else:
                label = f"📚 {label} ({ctx['stack_size']} in stack)"
        
        results.append((image_path, label))
    
        
    return results, f"Page {page} of {total_pages}", total_pages, raw_paths

def update_gallery(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    images, label, _, raw_paths = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    # Return: images, label, raw_paths, *details_cleared*
    # Details cleared must match detail_outputs list:
    return images, label, raw_paths, {}, {}, {}, {}, gr.update(visible=False), "", "", [], "0", "None", '<div style="display: none;"></div>', gr.update(visible=False), "", gr.update(visible=False), gr.update(visible=False)

def next_page(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    _, _, total_pages, _ = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    new_page = min(page + 1, total_pages)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)

def prev_page(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    new_page = max(page - 1, 1)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)

def first_page(sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
     return 1, *update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)

def last_page(sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    _, _, total_pages, _ = get_gallery_data(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    return total_pages, *update_gallery(total_pages, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)

def reset_folder_filter(sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    """Resets folder filter and goes to first page."""
    # Returns: folder_context_group, folder_display, current_folder_state, page, *gallery_outputs
    
    gal_outs = update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, None)
    
    # 1. Hide folder context group
    # 2. Clear folder display
    # 3. Set state to None
    # 4. Reset page to 1
    # 5. Gallery outputs
    
    return gr.update(visible=False), "", None, 1, *gal_outs

def open_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    """Switches to gallery tab and filters by folder.
       Returns: 
       [Tabs, current_folder_state, folder_context_group, folder_display, reset_btn_update] + [page, gallery, label, paths, details...]
    """
    if not folder:
        # If no folder provided, treat as "Reset / View All"
        print("DEBUG: No folder provided, resetting filter.")
        gal_outs = update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None)
        return gr.update(selected="gallery"), None, gr.update(visible=False), "", 1, *gal_outs
        
    print(f"DEBUG: open_folder_in_gallery called with folder='{folder}'")
    
    # Create a nice folder display HTML
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
    
    gal_outs = update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    
    # Return:
    # 1. Tabs Update (switch to "Gallery")
    # 2. current_folder state (set to folder)
    # 3. folder_context_group (visible=True)
    # 4. folder_display HTML
    # 5. page (1)
    # 6. *gal_outs
    
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

def open_stack_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    """Switches from Stacks to Gallery with folder filter."""
    return open_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date)

def open_stack_folder_in_tree(folder):
    """Switches from Stacks to Tree View and selects folder."""
    if not folder:
         return gr.update(selected="folder_tree"), gr.update(), gr.update()
         
    # We might need to refresh tree choices if the folder isn't there, but for now just try setting it.
    # The tree choices update happens on load or refresh click. 
    # If the folder exists in DB, it should be in the list if refreshed.
    
    html = ui_tree.get_tree_html(folder)
    return gr.update(selected="folder_tree"), folder, html

def open_stack_in_gallery(stack_id, sort_by, sort_order):
    """Switches to Gallery tab and displays only images from the selected stack."""
    if not stack_id:
        # Just switch to gallery without changing content if no stack selected
        return gr.update(selected="gallery"), None, gr.update(visible=False), "", 1, [], "", [], {}, {}, {}, {}, gr.update(visible=False), "", "", [], "0", "None", '<div style="display: none;"></div>', gr.update(visible=False), "", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)

    # Get images
    images = db.get_images_in_stack(stack_id)
    
    # Sort locally to match Stacks view
    if sort_by and sort_by != "created_at":
         try:
             reverse = (sort_order == "desc")
             images.sort(key=lambda x: x[sort_by] if x[sort_by] is not None else (0 if reverse else 999), reverse=reverse)
         except:
             pass
    
    # Format for gallery
    gallery_imgs = []
    raw_paths = []
    
    # Map sort_by to score column
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
        
    # Context HTML
    stack_html = f"""
    <div style="display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📚</span>
        <div>
            <div style="font-size: 1.1rem; font-weight: 600; color: #e6edf3;">Stack Viewer</div>
            <div style="font-size: 0.8rem; color: #8b949e;">stack #{stack_id} • {len(images)} images</div>
        </div>
    </div>
    """
    
    # Return matched to open_folder_in_gallery outputs:
    # [Tabs, current_folder_state, folder_context_group, folder_display, page, gallery, label, paths, *detail_outputs]
    return (
        gr.update(selected="gallery"), 
        None, 
        gr.update(visible=True), 
        stack_html, 
        1, 
        gallery_imgs, 
        f"Stack ({len(images)})", 
        raw_paths,
        {}, {}, {}, {}, gr.update(visible=False), "", "", [], "0", "None", '<div style="display: none;"></div>', gr.update(visible=False), "", gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
    )

def display_details(evt, raw_paths, forced_index=None):
    
    index = None
    if forced_index is not None:
        index = forced_index
    elif evt is not None:
        # Check if evt is a SelectData object (proper way)
        if isinstance(evt, gr.SelectData):
            index = evt.index
        elif isinstance(evt, dict) and 'index' in evt:
            index = evt['index']
        elif isinstance(evt, list):
            # FIX: If evt is a list (gallery value), this shouldn't happen
            # This means Gradio passed the gallery value instead of SelectData
            # We can't extract index from gallery value alone
            index = None
    
        
    # Ensure index is an integer before comparison
    if index is None or not raw_paths or not isinstance(index, int) or index >= len(raw_paths):
        return "", {}, {}, {}, {}, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
    
    file_path = raw_paths[index]
    details = db.get_image_details(file_path)
    
    # Parse scores_json for better display
    if 'scores_json' in details and isinstance(details['scores_json'], str):
        try:
            details['scores_json'] = json.loads(details['scores_json'])
        except:
            pass
            
    # Check for Delete Button Visibility
    # Criteria: 1. Is NEF file? 2. Rating <= 2 OR Label "Red"/"Yellow"
    
    show_delete = False
    
    # 1. Check if it's a NEF file
    is_nef = False
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.nef', '.nrw']:
        is_nef = True
        
    if is_nef:
        # 2. Check Logic based on Score/Rating
        
        # Parse scores_json safely
        data = details.get('scores_json', {})
        if isinstance(data, str): 
            try: data = json.loads(data) 
            except: data = {}
            
        # Locate nef_metadata (could be in multiple places depending on version)
        # 1. Top level
        nef_meta = data.get('nef_metadata')
        
        # 2. Inside summary (Legacy)
        if not nef_meta and 'summary' in data:
            nef_meta = data['summary'].get('nef_metadata')
            
        # 3. Inside full_results -> summary (New 3.0.0 structure)
        if not nef_meta and 'full_results' in data:
             full_res = data['full_results']
             if 'summary' in full_res:
                 nef_meta = full_res['summary'].get('nef_metadata')
        
        rating = 0
        label = ""
        
        if nef_meta:
            rating = nef_meta.get('rating', 0)
            label = nef_meta.get('label', '')
        else:
            # Fallback: Calculate from score_general in details
            sg = details.get('score_general')
            if sg is not None:
                try:
                    s = float(sg)
                    if s < 0.40: rating = 1
                    elif s < 0.55: rating = 2
                    elif s < 0.70: rating = 3
                    elif s < 0.85: rating = 4
                    else: rating = 5
                except:
                    pass
            
        rate_cond = False
        try:
            # Check rating <= 2
            if int(rating) > 0 and int(rating) <= 2:
                rate_cond = True
        except:
            pass
            
        label_cond = label in ["Red", "Yellow"]
        
        if rate_cond or label_cond:
            show_delete = True

    # Prepare Visual Outputs
    
    # 1. Summary Markdown
    filename = details.get('file_name', os.path.basename(file_path))
    created = details.get('created_at', 'Unknown')
    res_info = f"**File:** `{filename}`\n\n**Date:** {created}"
    
    # 2. General Score (Main)
    gen_score = details.get('score_general', details.get('score', 0))
    gen_label = {"General Score": gen_score}
    
    # 3. Weighted Scores
    tech = details.get('score_technical', 0)
    aes = details.get('score_aesthetic', 0)
    weighted_label = {
        "Technical": tech,
        "Aesthetic": aes
    }
    
    # 4. Model Scores (with timing if available)
    models_label = {}
    scores_data = details.get('scores_json', {})
    if isinstance(scores_data, str):
        try:
            scores_data = json.loads(scores_data)
        except:
            scores_data = {}
    
    # Extract model results and timing
    models_dict = scores_data.get('models', {}) if isinstance(scores_data, dict) else {}
    performance = scores_data.get('summary', {}).get('performance', {}) if isinstance(scores_data, dict) else {}
    model_times = performance.get('model_times', {}) if isinstance(performance, dict) else {}
    
    # Build models label with scores and timing
    # Build models label with scores and timing
    model_scores_map = {
        'spaq': ('SPAQ', details.get('score_spaq', 0)),
        'ava': ('AVA', details.get('score_ava', 0)),
        'koniq': ('KonIQ', details.get('score_koniq', 0)),
        'paq2piq': ('PaQ2PiQ', details.get('score_paq2piq', 0)),
        'liqe': ('LIQE', details.get('score_liqe', 0))
    }
    
    for model_key, (model_name, score) in model_scores_map.items():
        if score and score > 0:
            # Add timing if available
            if model_key in model_times:
                time_str = f"{model_times[model_key]:.3f}s"
                models_label[f"{model_name} ({time_str})"] = score
            else:
                models_label[model_name] = score
    
    # Show Fix button if we have a valid file path
    show_fix = bool(file_path and os.path.exists(file_path))
    
    return res_info, gen_label, weighted_label, models_label, details, gr.update(visible=show_delete), gr.update(visible=show_fix), gr.update(visible=show_fix), gr.update(visible=show_fix)


def fix_image_wrapper(details):
    """Wrapper for fix_image_metadata."""
    if not details or not isinstance(details, dict):
        return gr.update(visible=True), "❌ No image selected"
        
    file_path = details.get('file_path')
    if not file_path:
        return gr.update(visible=True), "❌ Invalid image data"
        
    success, msg = scoring_runner.fix_image_metadata(file_path)
    
    if success:
        return gr.update(visible=True), f"✅ {msg}"
    else:
        return gr.update(visible=True), f"❌ {msg}"

def rerun_scoring_wrapper(details):
    """Wrapper for run_single_image in scoring."""
    if not details or not isinstance(details, dict):
        return gr.update(visible=True), "❌ No image selected"
    file_path = details.get('file_path')
    if not file_path:
        return gr.update(visible=True), "❌ Invalid image data"
    
    success, msg = scoring_runner.run_single_image(file_path)
    if success:
        return gr.update(visible=True), f"✅ {msg}"
    else:
        return gr.update(visible=True), f"❌ {msg}"

def rerun_keywords_wrapper(details):
    """Wrapper for run_single_image in tagging."""
    if not details or not isinstance(details, dict):
        return gr.update(visible=True), "❌ No image selected"
    file_path = details.get('file_path')
    if not file_path:
        return gr.update(visible=True), "❌ Invalid image data"
        
    success, msg = tagging_runner.run_single_image(file_path)
    if success:
        return gr.update(visible=True), f"✅ {msg}"
    else:
        return gr.update(visible=True), f"❌ {msg}"
    


def export_database(export_format, cols_basic, cols_scores, cols_metadata, cols_other,
                    filter_rating, filter_label, filter_keyword, filter_folder,
                    filter_min_gen, filter_min_aes, filter_min_tech,
                    filter_date_start, filter_date_end):
    """
    Exports the database to the specified format with optional column selection and filtering.
    Returns status message.
    """
    import datetime
    
    # Combine selected columns
    selected_columns = []
    if cols_basic:
        selected_columns.extend(cols_basic)
    if cols_scores:
        selected_columns.extend(cols_scores)
    if cols_metadata:
        selected_columns.extend(cols_metadata)
    if cols_other:
        selected_columns.extend(cols_other)
    
    # Use None if no columns selected (will use defaults)
    columns = selected_columns if selected_columns else None
    
    # Process filters
    rating_filter = None
    if filter_rating:
        # Convert "Unrated" to 0, others to int
        rating_filter = [0 if r == "Unrated" else int(r) for r in filter_rating]
    
    label_filter = filter_label if filter_label else None
    
    keyword_filter = filter_keyword.strip() if filter_keyword and filter_keyword.strip() else None
    
    folder_path = filter_folder.strip() if filter_folder and filter_folder.strip() else None
    
    date_range = None
    if filter_date_start or filter_date_end:
        date_range = (filter_date_start if filter_date_start else None,
                     filter_date_end if filter_date_end else None)
    
    # Generate output filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    if export_format == "json":
        # JSON export doesn't support filtering yet (could add later)
        output_path = os.path.join(output_dir, f"export_{timestamp}.json")
        success, msg = db.export_db_to_json(output_path)
    elif export_format == "csv":
        output_path = os.path.join(output_dir, f"export_{timestamp}.csv")
        success, msg = db.export_db_to_csv(
            output_path, columns=columns,
            rating_filter=rating_filter, label_filter=label_filter,
            keyword_filter=keyword_filter, folder_path=folder_path,
            min_score_general=filter_min_gen, min_score_aesthetic=filter_min_aes,
            min_score_technical=filter_min_tech, date_range=date_range
        )
    elif export_format == "xlsx":
        output_path = os.path.join(output_dir, f"export_{timestamp}.xlsx")
        success, msg = db.export_db_to_excel(
            output_path, columns=columns,
            rating_filter=rating_filter, label_filter=label_filter,
            keyword_filter=keyword_filter, folder_path=folder_path,
            min_score_general=filter_min_gen, min_score_aesthetic=filter_min_aes,
            min_score_technical=filter_min_tech, date_range=date_range
        )
    else:
        return gr.update(value=f"Unknown format: {export_format}", visible=True)
    
    if success:
        return gr.update(value=f"✅ {msg}", visible=True)
    else:
        return gr.update(value=f"❌ {msg}", visible=True)


def delete_nef(details):
    """
    Deletes the NEF file associated with the image.
    """
    if not details:
        return gr.update(value="No image selected", visible=True), gr.update(visible=False)
    
    try:
        # Resolve 'details' if it's a string (though it should be dict from State?)
        # Gradio might pass the dict as JSON object
        
        # Find NEF path
        # 1. Try nef_metadata['file_path']
        # 2. Try replacing extension of main file_path
        
        nef_path = None
        
        # Check nef_metadata
        scores_json = details.get('scores_json', {})
        if isinstance(scores_json, str):
             try: scores_json = json.loads(scores_json)
             except: scores_json = {}
             
        nef_meta = scores_json.get('nef_metadata', {})
        if nef_meta.get('file_path'):
            nef_path = nef_meta.get('file_path')
            
        # Fallback: Assume simple sidecar
        if not nef_path:
            base_path = details.get('file_path', '')
            if base_path:
                # Replace suffix with .NEF (try sensitive)
                p = os.path.splitext(base_path)[0]
                candidates = [p + ".NEF", p + ".nef"]
                for c in candidates:
                    if os.path.exists(c):
                        nef_path = c
                        break
        
        deleted_files = []
        if nef_path and os.path.exists(nef_path):
            os.remove(nef_path)
            deleted_files.append("NEF")
            
        # Delete Thumbnail
        thumb_path = details.get('thumbnail_path')
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
                deleted_files.append("Thumb")
            except:
                pass
                
        # Delete DB Record
        file_path = details.get('file_path')
        if file_path:
            db.delete_image(file_path)
            deleted_files.append("DB")
            
        if deleted_files:
            return gr.update(value=f"Deleted: {', '.join(deleted_files)}", visible=True), gr.update(visible=False)
        else:
            return gr.update(value=f"NEF file not found: {nef_path}", visible=True), gr.update(visible=False)
            
    except Exception as e:
        return gr.update(value=f"Error deleting: {e}", visible=True), gr.update(visible=True)



# Color palette for keyword tags - distinct, vibrant colors
KEYWORD_COLORS = [
    "#3b82f6",  # blue
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#ec4899",  # pink
    "#06b6d4",  # cyan
    "#84cc16",  # lime
    "#f97316",  # orange
    "#6366f1",  # indigo
    "#14b8a6",  # teal
    "#a855f7",  # purple
]

# Generate color_map for HighlightedText (category names map to background colors)
KEYWORD_COLOR_MAP = {f"c{i}": color for i, color in enumerate(KEYWORD_COLORS)}


def keywords_to_highlighted(keywords_str):
    """
    Converts a comma-separated keywords string to HighlightedText format.
    Returns list of (keyword, category) tuples with rotating color categories.
    """
    if not keywords_str:
        return []
    keywords_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
    # Assign rotating color categories for unique backgrounds
    return [(kw, f"c{i % len(KEYWORD_COLORS)}") for i, kw in enumerate(keywords_list)]


def highlighted_to_keywords(highlighted_data):
    """
    Converts HighlightedText format back to comma-separated string.
    Accepts list of (text, category) tuples.
    """
    if not highlighted_data:
        return ""
    if isinstance(highlighted_data, str):
        return highlighted_data  # Already a string (fallback)
    # Extract just the text from each tuple
    return ",".join([item[0].strip() for item in highlighted_data if item[0].strip()])


def save_metadata_action(details, title, desc, keywords, rating, label):
    """
    Saves metadata to DB and File.
    """
    if not details or not isinstance(details, dict):
         return "Error: No image selected.", gr.update(visible=True)
         
    file_path = details.get('file_path')
    if not file_path:
         return "Error: Invalid image record.", gr.update(visible=True)
         
    # Parse Keywords - handle both HighlightedText format and string
    keywords_str = highlighted_to_keywords(keywords) if isinstance(keywords, list) else keywords
    kw_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
    
    # 1. Update DB
    try:
        # Convert rating/label types if needed
        r_val = int(rating) if rating else 0
        l_val = label if label != "None" else ""
        
        success = db.update_image_metadata(file_path, keywords_str, title, desc, r_val, l_val)
        if not success:
             return "Failed to update database.", gr.update(visible=True)
             
        # 2. Write to File (Tagging Runner)
        # We run this synchronously here for simplicity, or we could spawn thread.
        # Given it's one file, sync is probably fine (~1-2s).
        
        if tagging_runner.write_metadata(file_path, kw_list, title, desc, r_val, l_val):
            return f"Saved metadata for {os.path.basename(file_path)}", gr.update(visible=False) # Hide error box
        else:
             return "Saved to DB, but failed to write to file (ExifTool error).", gr.update(visible=True)
             
    except Exception as e:
        return f"Error saving metadata: {e}", gr.update(visible=True)


def get_jobs_history():
    rows = db.get_jobs()
    data = []
    for row in rows:
        data.append([
            row['id'], 
            row['input_path'], 
            row['status'], 
            row['created_at'], 
            row['completed_at']
        ])
    return data

def get_stack_gallery_data():
    stacks = db.get_stacks()
    results = []
    stack_ids = []
    
    for row in stacks:
        # Gallery format: (path, label)
        # OPTIMIZATION: Skip existence checks - trust DB paths
        p = row['best_image_path']
        label = f"{row['name']} ({row['image_count']} imgs)"
        if p:
            local_p = utils.convert_path_to_local(p)
            results.append((local_p, label))
            stack_ids.append(row['id'])
            
    return results, stack_ids

def run_clustering_wrapper(input_path, threshold, gap, force, progress=gr.Progress()):
    log = ""
    try:
        # Save Config
        config.save_config_value('stacks_input_path', input_path)
        
        # Default gap 120s if None
        if gap is None: gap = 120
        
        target = input_path.strip() if input_path and input_path.strip() else None
        
        for msg_tuple in cluster_engine.cluster_images(distance_threshold=threshold, time_gap_seconds=gap, force_rescan=force, target_folder=target):
            if isinstance(msg_tuple, tuple):
                msg, cur, tot = msg_tuple
                if tot > 0:
                     val = cur / tot
                     progress(val, desc=msg)
                else:
                     progress(0, desc=msg)
                log = msg
            else:
                log = msg_tuple
                
            yield log, gr.update(interactive=False)
    except Exception as e:
        yield f"Error: {e}", gr.update(interactive=True)
        return

    # Refresh Stacks? No, let the UI handle it via .then() or user action.
    yield "Done", gr.update(interactive=True)



def refresh_stacks_wrapper(input_path, sort_by, sort_order):
    target = input_path.strip() if input_path and input_path.strip() else None
    
    rows = db.get_stacks_for_display(folder_path=target, sort_by=sort_by, order=sort_order)
    
    results = []
    stack_ids = []
    
    for row in rows:
        # Row: id, name, image_count, sort_val, cover_path
        s_id = row['id']
        name = row['name']
        count = row['image_count']
        cover = row['cover_path']
        
        label = f"{name} ({count} items)"
        
        # Convert path for WSL/Windows compatibility
        # Skip os.path.exists() check - it's slow and Gradio handles missing images gracefully
        if cover:
            local_cover = utils.convert_path_to_local(cover)
            results.append((local_cover, label))
            stack_ids.append(s_id)
            
    return results, stack_ids

def select_stack(evt: gr.SelectData, stack_ids_state, sort_by, sort_order):
    """Returns (gallery_images, content_paths, selected_stack_id)"""
    if evt is None or not stack_ids_state:
        return [], [], None  # Return gallery, paths, stack_id
        
    index = evt.index
    if index >= len(stack_ids_state):
        return [], [], None
        
    stack_id = stack_ids_state[index]
    
    # Get all images in stack
    images = db.get_images_in_stack(stack_id)
    
    # Sort locally if needed, though get_images_in_stack sorts by score_general
    # If we want to respect the main sort:
    if sort_by and sort_by != "created_at":
         # Try to sort
         try:
             reverse = (sort_order == "desc")
             images.sort(key=lambda x: x[sort_by] if x[sort_by] is not None else (0 if reverse else 999), reverse=reverse)
         except:
             pass

    # Prepare gallery format
    gallery_imgs = []
    content_paths = []  # Store original DB paths for selection tracking
    
    # Map sort_by to score column and display name
    score_map = {
        'score_general': ('score_general', 'Gen'),
        'score_technical': ('score_technical', 'Tech'),
        'score_aesthetic': ('score_aesthetic', 'Aes'),
        'created_at': ('score_general', 'Gen'),  # fallback to general for date sort
    }
    score_col, score_label = score_map.get(sort_by, ('score_general', 'Gen'))
    
    for row in images:
        file_path = row['file_path']
        if not file_path:
            continue
        
        content_paths.append(file_path)  # Track original DB path
        
        # Get file name from original path
        file_name = os.path.basename(file_path)
        
        # OPTIMIZATION: Use thumbnail if available, skip existence checks
        # Trust DB paths - they were validated when stored
        thumb = row['thumbnail_path']  # sqlite3.Row uses bracket notation, not .get()
        if thumb:
            p = utils.convert_path_to_local(thumb)
        else:
            p = utils.convert_path_to_local(file_path)
        
        # Get the selected score
        score = row[score_col] if score_col in row.keys() else None
        score_str = f"{score:.2f}" if score is not None else "N/A"
        
        # Label format: filename + selected score
        label = f"{file_name}\n{score_label}: {score_str}"
        gallery_imgs.append((p, label))

    return gallery_imgs, content_paths, stack_id


# --- Stack Management Handlers ---

def create_stack_from_selection(selected_indices, content_paths, input_path, sort_by, sort_order):
    """
    Creates a new stack from selected images in the content gallery.
    Returns updated (stacks_gallery, stack_ids, content_gallery, content_paths, status_msg).
    """
    if not selected_indices or not content_paths:
        return gr.update(), gr.update(), gr.update(), gr.update(), "No images selected"
    
    # Convert indices to paths, then to image IDs
    selected_paths = [content_paths[i] for i in selected_indices if i < len(content_paths)]
    if len(selected_paths) < 2:
        return gr.update(), gr.update(), gr.update(), gr.update(), "Select at least 2 images to create a stack"
    
    image_ids = db.get_image_ids_by_paths(selected_paths)
    if len(image_ids) < 2:
        return gr.update(), gr.update(), gr.update(), gr.update(), "Could not find selected images in database"
    
    success, result = db.create_stack_from_images(image_ids)
    if not success:
        return gr.update(), gr.update(), gr.update(), gr.update(), f"Error: {result}"
    
    # Refresh stacks gallery
    stacks, stack_ids = refresh_stacks_wrapper(input_path, sort_by, sort_order)
    
    return stacks, stack_ids, [], [], f"Created new stack with {len(image_ids)} images"


def remove_from_stack_handler(selected_indices, content_paths, current_stack_id, input_path, sort_by, sort_order):
    """
    Removes selected images from their current stack.
    Returns updated galleries and status.
    """
    if not selected_indices or not content_paths:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), "No images selected"
    
    selected_paths = [content_paths[i] for i in selected_indices if i < len(content_paths)]
    if not selected_paths:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), "No valid images selected"
    
    image_ids = db.get_image_ids_by_paths(selected_paths)
    if not image_ids:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), "Could not find selected images in database"
    
    success, msg = db.remove_images_from_stack(image_ids)
    if not success:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), f"Error: {msg}"
    
    # Refresh both galleries
    stacks, stack_ids = refresh_stacks_wrapper(input_path, sort_by, sort_order)
    
    # Refresh content gallery if current stack still exists
    content_gallery = []
    new_content_paths = []
    if current_stack_id:
        remaining_images = db.get_images_in_stack(current_stack_id)
        for row in remaining_images:
            file_path = row['file_path']
            if file_path:
                new_content_paths.append(file_path)
                thumb = row['thumbnail_path']
                p = utils.convert_path_to_local(thumb if thumb else file_path)
                file_name = os.path.basename(file_path)
                score = row['score_general']
                score_str = f"{score:.2f}" if score else "N/A"
                content_gallery.append((p, f"{file_name}\nGen: {score_str}"))
    
    return stacks, stack_ids, content_gallery, new_content_paths, None, msg


def dissolve_stack_handler(current_stack_id, input_path, sort_by, sort_order):
    """
    Dissolves the currently selected stack entirely.
    Returns updated stacks gallery and clears content.
    """
    if not current_stack_id:
        return gr.update(), gr.update(), [], [], None, "No stack selected"
    
    success, msg = db.dissolve_stack(current_stack_id)
    if not success:
        return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), f"Error: {msg}"
    
    # Refresh stacks gallery
    stacks, stack_ids = refresh_stacks_wrapper(input_path, sort_by, sort_order)
    
    return stacks, stack_ids, [], [], None, msg


def set_cover_image_handler(selected_indices, content_paths, current_stack_id, input_path, sort_by, sort_order):
    """
    Sets the selected image as the cover (best_image_id) for the current stack.
    Only works with a single selected image.
    """
    if not current_stack_id:
        return gr.update(), gr.update(), "No stack selected"
    
    if not selected_indices or len(selected_indices) != 1:
        return gr.update(), gr.update(), "Select exactly one image to set as cover"
    
    idx = selected_indices[0]
    if idx >= len(content_paths):
        return gr.update(), gr.update(), "Invalid selection"
    
    selected_path = content_paths[idx]
    image_ids = db.get_image_ids_by_paths([selected_path])
    
    if not image_ids:
        return gr.update(), gr.update(), "Could not find selected image in database"
    
    image_id = image_ids[0]
    success, msg = db.set_stack_cover_image(current_stack_id, image_id)
    
    if not success:
        return gr.update(), gr.update(), f"Error: {msg}"
    
    # Refresh stacks gallery to show new cover
    stacks, stack_ids = refresh_stacks_wrapper(input_path, sort_by, sort_order)
    
    return stacks, stack_ids, msg


# --- Culling Workflow Handlers ---

def run_culling_wrapper(input_path, threshold, time_gap, auto_export, force_rescan=False, progress=gr.Progress()):
    """
    Wrapper to run culling logic (Non-blocking).
    Now accepts force_rescan to allow non-destructive runs overlaying existing stacks.
    """
    if not input_path:
        return "⚠️ Please select a folder first.", gr.update(interactive=True), [], None, [], [], []
    
    # Disable button while running
    # This return is for immediate UI update, the actual processing happens in a background thread
    # and updates are sent via the progress object or other mechanisms if needed.
    # For now, we'll keep the original blocking structure but add the force_rescan parameter.
    
    config.save_config_value('culling_input_path', input_path)
    
    progress(0.1, desc="Creating culling session...")
    
    # Run full culling workflow
    result = culling.culling_engine.run_full_cull(
        folder_path=input_path,
        distance_threshold=threshold,
        time_gap_seconds=int(time_gap),
        score_field='score_general',
        auto_export=auto_export,
        force_rescan=force_rescan
    )
    
    if 'error' in result:
        return f"❌ Error: {result['error']}", gr.update(), [], None, [], [], []
    
    progress(0.9, desc="Preparing results...")
    
    # Format result message
    session_id = result.get('session_id')
    total = result.get('total', 0)
    picked = result.get('picked', 0)
    rejected = result.get('rejected', 0)
    pick_pct = (picked / total * 100) if total > 0 else 0
    reject_pct = (rejected / total * 100) if total > 0 else 0
    
    msg_lines = [
        f"✅ Culling complete for: {input_path}",
        f"📊 Total images: {total}",
        f"📚 Groups found: {result.get('groups', 0)}",
        f"✅ Picked: {picked} ({pick_pct:.0f}%)",
        f"❌ Rejected: {rejected} ({reject_pct:.0f}%)",
        f"🔑 Session ID: {session_id}"
    ]
    
    if result.get('exported'):
        msg_lines.append(f"💾 XMP Pick/Reject flags written: {result.get('xmp_count', 0)}")
        if result.get('xmp_errors', 0) > 0:
            msg_lines.append(f"⚠️ XMP errors: {result.get('xmp_errors', 0)}")
    
    progress(1.0, desc="Done!")
    
    # Get picks for gallery display
    picks_gallery = []
    picks_paths = []
    if session_id:
        picks = db.get_session_picks(session_id, decision_filter='pick')
        for pick in picks:
            file_path = pick.get('file_path')
            thumb = pick.get('thumbnail_path') or file_path
            if thumb:
                p = utils.convert_path_to_local(thumb)
                label = f"{pick.get('file_name', '?')}\nGen: {pick.get('score_general', 0):.2f}"
                picks_gallery.append((p, label))
                picks_paths.append(file_path)
    
    # Get rejects for gallery display
    rejects_gallery = []
    rejects_paths = []
    if session_id:
        rejects = db.get_session_picks(session_id, decision_filter='reject')
        for reject in rejects:
            file_path = reject.get('file_path')
            thumb = reject.get('thumbnail_path') or file_path
            if thumb:
                p = utils.convert_path_to_local(thumb)
                label = f"{reject.get('file_name', '?')}\nGen: {reject.get('score_general', 0):.2f}"
                rejects_gallery.append((p, label))
                rejects_paths.append(file_path)
    
    return "\n".join(msg_lines), gr.update(interactive=True), picks_gallery, session_id, picks_paths, rejects_gallery, rejects_paths


def get_culling_groups(session_id):
    """Returns grouped images for review."""
    if not session_id:
        return [], []
    
    groups = db.get_session_groups(session_id)
    
    gallery_imgs = []
    group_ids = []
    
    for group in groups:
        # Show best image (first in sorted list) as group cover
        if group['images']:
            best = group['images'][0]
            thumb = best.get('thumbnail_path') or best.get('file_path')
            if thumb:
                p = utils.convert_path_to_local(thumb)
                count = len(group['images'])
                picked = 1 if group.get('has_pick') else 0
                label = f"Group {group['group_id']}\n{count} imgs, {picked} picked"
                gallery_imgs.append((p, label))
                group_ids.append(group['group_id'])
    
    return gallery_imgs, group_ids


def export_culling_xmp(session_id):
    """Exports culling decisions to XMP sidecars using Lightroom Pick/Reject flags."""
    if not session_id:
        return "No active session to export"
    
    result = culling.culling_engine.export_to_xmp(session_id)
    
    exported = result.get('exported', 0)
    errors = result.get('errors', 0)
    failed_files = result.get('failed_files', [])
    
    msg = f"✅ Exported {exported} Pick/Reject flags"
    if errors > 0:
        msg += f"\n⚠️ {errors} errors"
        if failed_files:
            msg += "\n\nFailed files:"
            for file_path, error_msg in failed_files[:5]:  # Show first 5
                file_name = os.path.basename(file_path)
                msg += f"\n  • {file_name}: {error_msg[:50]}"
            if len(failed_files) > 5:
                msg += f"\n  ... and {len(failed_files) - 5} more"
    
    return msg


def refresh_culling_groups(session_id, threshold, time_gap):
    """
    Re-imports group assignments for an existing session.
    Useful after manual stack modifications in the Stacks tab.
    """
    if not session_id:
        return "❌ No active session. Run AI Culling first.", [], []
    
    # Get session info
    session = db.get_culling_session(session_id)
    if not session:
        return "❌ Session not found.", [], []
    
    folder_path = session['folder_path']
    
    # Clear existing picks for this session (so we can re-import)
    db.clear_culling_picks(session_id)
    
    # Re-run import with current stack assignments
    import_stats = culling.culling_engine.import_images(
        session_id,
        distance_threshold=threshold,
        time_gap_seconds=int(time_gap)
    )
    
    if 'error' in import_stats:
        return f"❌ {import_stats['error']}", [], []
    
    msg = f"✅ Refreshed groups from: {folder_path}\n"
    msg += f"📊 Total: {import_stats.get('total', 0)} images\n"
    msg += f"📚 Groups: {import_stats.get('groups', 0)}\n"
    msg += f"ℹ️ Use 'Re-Pick Best' to auto-select best images"
    
    return msg, [], []


def repick_culling_best(session_id, score_field='score_general'):
    """
    Re-runs auto-pick on an existing session.
    Useful after refreshing groups or changing preferences.
    """
    if not session_id:
        return "❌ No active session.", [], []
    
    # Clear existing decisions
    db.reset_culling_decisions(session_id)
    
    # Re-run auto-pick
    pick_stats = culling.culling_engine.auto_pick_all(session_id, score_field=score_field)
    
    # Get updated picks for gallery
    picks_gallery = []
    picks_paths = []
    picks = db.get_session_picks(session_id, decision_filter='pick')
    for pick in picks:
        file_path = pick.get('file_path')
        thumb = pick.get('thumbnail_path') or file_path
        if thumb:
            p = utils.convert_path_to_local(thumb)
            label = f"{pick.get('file_name', '?')}\nGen: {pick.get('score_general', 0):.2f}"
            picks_gallery.append((p, label))
            picks_paths.append(file_path)
    
    msg = f"✅ Re-picked best images\n"
    msg += f"📸 Picked: {pick_stats.get('picked', 0)}\n"
    msg += f"❌ Rejected: {pick_stats.get('rejected', 0)}"
    
    return msg, picks_gallery, picks_paths


def get_active_sessions():
    """Returns active culling sessions for dropdown."""
    sessions = db.get_active_culling_sessions()
    choices = []
    for s in sessions:
        folder = os.path.basename(s['folder_path'])
        # Include stats in label
        picked = s.get('picked_count', 0)
        rejected = s.get('rejected_count', 0)
        total = s.get('total_groups', 0)
        reviewed = s.get('reviewed_groups', 0)
        label = f"Session {s['id']}: {folder} ({picked} picks, {rejected} rejects, {reviewed}/{total} groups)"
        choices.append((label, s['id']))
    return choices


def resume_culling_session(session_id):
    """
    Resumes a culling session by loading its picks and rejects into the galleries.
    Returns: (status_msg, picks_gallery, session_id, picks_paths, rejects_gallery, rejects_paths)
    """
    if not session_id:
        return "❌ Please select a session to resume", [], None, [], [], []
    
    # Get session details
    session = db.get_culling_session(session_id)
    if not session:
        return f"❌ Session {session_id} not found", [], None, [], [], []
    
    folder_path = session.get('folder_path', '')
    
    # Get picks for gallery display
    picks_gallery = []
    picks_paths = []
    picks = db.get_session_picks(session_id, decision_filter='pick')
    
    for pick in picks:
        file_path = pick.get('file_path')
        thumb = pick.get('thumbnail_path') or file_path
        if thumb:
            p = utils.convert_path_to_local(thumb)
            label = f"{pick.get('file_name', '?')}\nGen: {pick.get('score_general', 0):.2f}"
            picks_gallery.append((p, label))
            picks_paths.append(file_path)
    
    # Get rejects for gallery display
    rejects_gallery = []
    rejects_paths = []
    rejects = db.get_session_picks(session_id, decision_filter='reject')
    
    for reject in rejects:
        file_path = reject.get('file_path')
        thumb = reject.get('thumbnail_path') or file_path
        if thumb:
            p = utils.convert_path_to_local(thumb)
            label = f"{reject.get('file_name', '?')}\nGen: {reject.get('score_general', 0):.2f}"
            rejects_gallery.append((p, label))
            rejects_paths.append(file_path)
    
    # Format status message
    total = session.get('total_images', 0)
    groups = session.get('total_groups', 0)
    picked = session.get('picked_count', len(picks))
    rejected = session.get('rejected_count', len(rejects))
    reviewed = session.get('reviewed_groups', 0)
    
    msg_lines = [
        f"✅ Resumed Session {session_id}: {os.path.basename(folder_path)}",
        f"📊 Total images: {total}",
        f"📚 Groups: {groups}",
        f"✅ Picked: {picked}",
        f"❌ Rejected: {rejected}",
        f"📝 Reviewed: {reviewed}/{groups} groups"
    ]
    
    return "\n".join(msg_lines), picks_gallery, session_id, picks_paths, rejects_gallery, rejects_paths


def get_rejects_gallery(session_id):
    """
    Returns rejected images for gallery display.
    Returns: (rejects_gallery, rejects_paths)
    """
    if not session_id:
        return [], []
    
    rejects_gallery = []
    rejects_paths = []
    rejects = db.get_session_picks(session_id, decision_filter='reject')
    
    for reject in rejects:
        file_path = reject.get('file_path')
        thumb = reject.get('thumbnail_path') or file_path
        if thumb:
            p = utils.convert_path_to_local(thumb)
            label = f"{reject.get('file_name', '?')}\nGen: {reject.get('score_general', 0):.2f}"
            rejects_gallery.append((p, label))
            rejects_paths.append(file_path)
    
    return rejects_gallery, rejects_paths


def delete_rejected_files(session_id, confirmed):
    """
    Permanently deletes rejected files from disk and database.
    
    WARNING: This is destructive and cannot be undone!
    
    Returns: (status_message, updated_rejects_gallery, updated_rejects_paths)
    """
    from modules import xmp as xmp_module
    
    if not confirmed:
        return "⚠️ Please check the confirmation box to delete files", [], []
    
    if not session_id:
        return "❌ No active session", [], []
    
    rejects = db.get_session_picks(session_id, decision_filter='reject')
    
    if not rejects:
        return "ℹ️ No rejected files to delete", [], []
    
    deleted_count = 0
    error_count = 0
    errors = []
    
    for reject in rejects:
        file_path = reject.get('file_path')
        if not file_path:
            continue
        
        try:
            local_path = utils.convert_path_to_local(file_path)
            
            # Delete the image file
            if os.path.exists(local_path):
                os.remove(local_path)
            
            # Delete XMP sidecar if exists
            xmp_module.delete_xmp(file_path)
            
            # Delete thumbnail if exists
            thumb_path = reject.get('thumbnail_path')
            if thumb_path:
                local_thumb = utils.convert_path_to_local(thumb_path)
                if os.path.exists(local_thumb):
                    os.remove(local_thumb)
            
            # Remove from database
            db.delete_image(file_path)
            
            deleted_count += 1
            
        except Exception as e:
            error_count += 1
            errors.append(f"{os.path.basename(file_path)}: {str(e)}")
    
    # Build status message
    status = f"🗑️ Deleted {deleted_count} rejected files"
    if error_count > 0:
        status += f"\n⚠️ {error_count} errors"
        if errors[:3]:  # Show first 3 errors
            status += "\n" + "\n".join(errors[:3])
    
    # Return empty galleries since files are deleted
    return status, [], []




def get_tree_choices():
    # 1. Get real folders from DB
    raw_folders = db.get_all_folders() 
    if not raw_folders: return []
    

    # Normalize paths
    real_folders = [os.path.normpath(f) for f in raw_folders]
    
    # 2. Sort (folders table query is already sorted, but explicit sort is safer)
    sorted_nodes = sorted(real_folders)
    
    # 3. Create Choices
    choices = []
    for node in sorted_nodes:
        # Determine depth
        
        # Calculate indentation
        parts = node.split(os.sep)
        # Handle drive letter split
        if node.endswith(os.sep): 
            parts = [p for p in parts if p]
            
        depth = len(parts) - 1
        # Use spaces for visual indentation
        indent = "    " * max(0, depth)
        
        base = os.path.basename(node)
        if not base: base = node # Root like D:\
        
        label = f"{indent}📁 {base}"
        choices.append((label, node))

        
    return choices

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
    
    results = []
    for row in rows:
        p = row['file_path']
        label = row['file_name']
        
        # OPTIMIZATION: Prioritize thumbnails, skip expensive existence checks
        # Trust DB paths - they were valid when stored
        thumb_path = row.get('thumbnail_path')
        
        if thumb_path:
            # Use thumbnail (fast path - no existence check)
            if IS_WINDOWS and thumb_path.startswith("/mnt/"):
                # Convert WSL path to Windows
                parts = thumb_path.split('/')
                if len(parts) > 2 and len(parts[2]) == 1:
                    drive = parts[2].upper()
                    rest = "/".join(parts[3:])
                    p = f"{drive}:/{rest}"
                else:
                    p = thumb_path
            else:
                p = thumb_path
        else:
            # No thumbnail - convert original path
            if IS_WINDOWS and p.startswith("/mnt/"):
                parts = p.split('/')
                if len(parts) > 2 and len(parts[2]) == 1:
                    drive = parts[2].upper()
                    rest = "/".join(parts[3:])
                    p = f"{drive}:/{rest}"
        
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


# --- UI Definition ---

# Tree View Start Script + Gallery Close Button + NEF Viewer
tree_js = r"""
<script src="/file=static/js/libraw-viewer.js"></script>
<script>
window.selectFolder = function(e, path) {
    e.preventDefault();
    e.stopPropagation();
    
    // Clear selection style
    var all = document.querySelectorAll('.tree-content');
    for (var i=0; i<all.length; i++) {
        all[i].style.backgroundColor = '';
        all[i].style.color = '';
    }
    
    // Set new style
    e.target.style.backgroundColor = '#2196f3';
    e.target.style.color = 'white';
    
    // Update hidden input
    var ta = document.querySelector('#folder_tree_selection textarea');
    if (ta) {
        var descriptor = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value");
        descriptor.set.call(ta, path);
        ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

// Gallery lightbox close button handler
function initGalleryCloseButton() {
    let closeBtn = null;
    
    function createCloseButton() {
        if (closeBtn && document.body.contains(closeBtn)) return closeBtn;
        
        closeBtn = document.createElement('button');
        closeBtn.id = 'gallery-close-btn';
        closeBtn.innerHTML = '✕ Back to Grid';
        closeBtn.style.cssText = `
            position: fixed;
            top: 15px;
            right: 15px;
            z-index: 99999;
            background: linear-gradient(135deg, #f85149 0%, #da3633 100%);
            color: white;
            padding: 14px 28px;
            border-radius: 10px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(248, 81, 73, 0.5);
            border: 2px solid rgba(255,255,255,0.2);
            transition: all 0.2s ease;
            font-family: system-ui, -apple-system, sans-serif;
            letter-spacing: 0.5px;
        `;
        closeBtn.onmouseenter = function() {
            this.style.transform = 'scale(1.08)';
            this.style.boxShadow = '0 6px 25px rgba(248, 81, 73, 0.7)';
        };
        closeBtn.onmouseleave = function() {
            this.style.transform = 'scale(1)';
            this.style.boxShadow = '0 4px 20px rgba(248, 81, 73, 0.5)';
        };
        closeBtn.onclick = function(e) {
            e.preventDefault();
            e.stopPropagation();
            closePreview();
        };
        return closeBtn;
    }
    
    function closePreview() {
        // Method 1: Find and click the grid/thumbnail view
        const gridButtons = document.querySelectorAll('.gallery button, .gallery .thumbnail, .gallery [class*="grid"]');
        
        // Method 2: Simulate Escape key
        document.dispatchEvent(new KeyboardEvent('keydown', { 
            key: 'Escape', 
            code: 'Escape', 
            keyCode: 27, 
            which: 27, 
            bubbles: true,
            cancelable: true
        }));
        
        // Method 3: Find preview container and trigger close
        const previewBtn = document.querySelector('.gallery button.preview');
        if (previewBtn) {
            // Try to find a close mechanism
            const svgIcons = previewBtn.querySelectorAll('svg');
            svgIcons.forEach(svg => {
                if (svg.closest('button')) {
                    svg.closest('button').click();
                }
            });
        }
        
        // Method 4: Click on the preview backdrop area
        setTimeout(() => {
            const preview = document.querySelector('.gallery .preview, .gallery button.preview');
            if (preview) {
                // Dispatch escape again
                preview.dispatchEvent(new KeyboardEvent('keydown', { 
                    key: 'Escape', 
                    bubbles: true 
                }));
            }
            removeCloseButton();
        }, 100);
    }
    
    function removeCloseButton() {
        const btn = document.getElementById('gallery-close-btn');
        if (btn) btn.remove();
        closeBtn = null;
    }
    
    function checkForPreviewMode() {
        // Check if gallery is in preview/lightbox mode
        const previewActive = document.querySelector('.gallery button.preview');
        const hasLargeImage = document.querySelector('.gallery .preview img, .gallery button.preview img');
        const thumbnailStrip = document.querySelector('.gallery .thumbnails, .gallery [class*="thumbnail"]');
        
        // If preview mode detected (large image with thumbnail strip)
        if (previewActive || (hasLargeImage && thumbnailStrip)) {
            if (!document.getElementById('gallery-close-btn')) {
                const btn = createCloseButton();
                document.body.appendChild(btn);
            }
        } else {
            removeCloseButton();
        }
    }
    
    // Watch for DOM changes
    const observer = new MutationObserver(function(mutations) {
        checkForPreviewMode();
    });
    
    observer.observe(document.body, { 
        childList: true, 
        subtree: true, 
        attributes: true,
        attributeFilter: ['class', 'style']
    });
    
    // Also check periodically for edge cases
    setInterval(checkForPreviewMode, 500);
    
    // Initial check
    setTimeout(checkForPreviewMode, 1000);
}

// Handle Escape key globally
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const btn = document.getElementById('gallery-close-btn');
        if (btn) btn.remove();
    }
});

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGalleryCloseButton);
} else {
    initGalleryCloseButton();
}

// ========== STACK BADGE OVERLAY ==========
function initStackBadges() {
    function addBadgesToStackGallery() {
        // Find the Stacks tab gallery (first gallery in the Stacks tab)
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find all gallery items in the stacks section
        const galleries = document.querySelectorAll('.gallery');
        
        galleries.forEach(gallery => {
            // Look for stack gallery items (they have captions with "X imgs")
            const items = gallery.querySelectorAll('.thumbnail-item, .gallery-item, [class*="thumbnail"]');
            
            items.forEach(item => {
                // Skip if already has badge
                if (item.querySelector('.stack-badge')) return;
                
                // Get the caption/label
                const caption = item.querySelector('.caption, .label, [class*="caption"]');
                if (!caption) return;
                
                const text = caption.textContent || '';
                // Match pattern like "(5 imgs)" or "(12 imgs)"
                const match = text.match(/\((\d+)\s*imgs?\)/i);
                
                if (match) {
                    const count = parseInt(match[1], 10);
                    if (count >= 2) {
                        // Make item position relative if not already
                        const computed = window.getComputedStyle(item);
                        if (computed.position === 'static') {
                            item.style.position = 'relative';
                        }
                        
                        // Create and add badge
                        const badge = document.createElement('span');
                        badge.className = 'stack-badge' + (count >= 10 ? ' large' : '');
                        badge.textContent = count;
                        item.appendChild(badge);
                    }
                }
            });
        });
    }
    
    // Watch for DOM changes (galleries update dynamically)
    const badgeObserver = new MutationObserver(function(mutations) {
        // Debounce
        clearTimeout(window._stackBadgeTimeout);
        window._stackBadgeTimeout = setTimeout(addBadgesToStackGallery, 200);
    });
    
    badgeObserver.observe(document.body, { 
        childList: true, 
        subtree: true 
    });
    
    // Initial run
    setTimeout(addBadgesToStackGallery, 1000);
    
    // Also run on tab changes
    document.addEventListener('click', function(e) {
        if (e.target.closest('[role="tab"]')) {
            setTimeout(addBadgesToStackGallery, 300);
        }
    });
}

// Initialize stack badges
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackBadges);
} else {
    initStackBadges();
}

// ========== KEYBOARD SHORTCUTS FOR STACK OPERATIONS ==========
function initStackKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Only trigger if no input/textarea is focused
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')) {
            return;
        }
        
        // Ctrl+G -> Group Selected
        if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'g') {
            e.preventDefault();
            const groupBtn = document.getElementById('stack-group-btn');
            if (groupBtn) {
                groupBtn.click();
                console.log('Keyboard: Ctrl+G -> Group Selected');
            }
        }
        
        // Ctrl+Shift+G -> Ungroup All
        if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'g') {
            e.preventDefault();
            const ungroupBtn = document.getElementById('stack-ungroup-btn');
            if (ungroupBtn) {
                ungroupBtn.click();
                console.log('Keyboard: Ctrl+Shift+G -> Ungroup All');
            }
        }
        
        // Ctrl+R -> Remove from Stack
        if (e.ctrlKey && !e.shiftKey && e.key.toLowerCase() === 'r') {
            // Check if we're on stacks tab to avoid conflicts
            const stacksTab = document.querySelector('[id*="stacks"].tabitem--selected, [id*="stacks"][aria-selected="true"]');
            if (stacksTab) {
                e.preventDefault();
                const removeBtn = document.getElementById('stack-remove-btn');
                if (removeBtn) {
                    removeBtn.click();
                    console.log('Keyboard: Ctrl+R -> Remove from Stack');
                }
            }
        }
    });
    
    console.log('Stack keyboard shortcuts initialized: Ctrl+G (Group), Ctrl+Shift+G (Ungroup), Ctrl+R (Remove)');
}

// Initialize keyboard shortcuts
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackKeyboardShortcuts);
} else {
    initStackKeyboardShortcuts();
}

// ========== STACK INLINE EXPAND/COLLAPSE ==========
function initStackExpandCollapse() {
    let currentExpandedStack = null;
    
    // Add visual feedback for expand/collapse state
    function updateExpandState() {
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find the content gallery section
        const contentSection = stacksTab.querySelector('[id*="stack"][class*="gallery"]');
        const stackItems = stacksTab.querySelectorAll('.gallery .thumbnail-item, .gallery .gallery-item, .gallery [class*="thumbnail"]');
        
        // Add expand indicator to stack items
        stackItems.forEach((item, index) => {
            if (item.querySelector('.expand-indicator')) return;
            
            const indicator = document.createElement('span');
            indicator.className = 'expand-indicator';
            indicator.style.cssText = `
                position: absolute;
                bottom: 6px;
                left: 6px;
                font-size: 14px;
                opacity: 0.7;
                pointer-events: none;
                transition: transform 0.2s ease;
            `;
            indicator.textContent = '▼';
            
            const computed = window.getComputedStyle(item);
            if (computed.position === 'static') {
                item.style.position = 'relative';
            }
            item.appendChild(indicator);
        });
    }
    
    // Create collapse button for content gallery
    function addCollapseButton() {
        const stacksTab = document.querySelector('[id*="stacks"]');
        if (!stacksTab) return;
        
        // Find the content gallery header
        const contentHeaders = stacksTab.querySelectorAll('h3, .markdown');
        contentHeaders.forEach(header => {
            if (header.textContent.includes('Stack Contents') && !header.querySelector('.collapse-btn')) {
                const btn = document.createElement('button');
                btn.className = 'collapse-btn';
                btn.innerHTML = '▲ Collapse';
                btn.style.cssText = `
                    margin-left: 10px;
                    padding: 4px 12px;
                    font-size: 11px;
                    background: var(--bg-tertiary, #21262d);
                    border: 1px solid var(--border-color, #30363d);
                    border-radius: 6px;
                    color: var(--text-secondary, #8b949e);
                    cursor: pointer;
                    vertical-align: middle;
                `;
                btn.onclick = function(e) {
                    e.preventDefault();
                    const gallery = this.closest('[id*="stacks"]').querySelector('.gallery:not(:first-child)');
                    if (gallery) {
                        const isCollapsed = gallery.style.display === 'none';
                        gallery.style.display = isCollapsed ? '' : 'none';
                        this.innerHTML = isCollapsed ? '▲ Collapse' : '▼ Expand';
                    }
                };
                header.appendChild(btn);
            }
        });
    }
    
    // Observe DOM changes
    const expandObserver = new MutationObserver(function() {
        clearTimeout(window._expandTimeout);
        window._expandTimeout = setTimeout(() => {
            updateExpandState();
            addCollapseButton();
        }, 300);
    });
    
    expandObserver.observe(document.body, { childList: true, subtree: true });
    
    // Initial setup
    setTimeout(() => {
        updateExpandState();
        addCollapseButton();
    }, 1500);
}

// Initialize expand/collapse
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStackExpandCollapse);
} else {
    initStackExpandCollapse();
}

// ========== IMAGE COMPARISON VIEW ==========
window.compareImages = [];
window.maxCompareImages = 4;

function initCompareMode() {
    // Add compare button to image details
    const addBtn = document.getElementById('compare-add-btn');
    if (addBtn && !addBtn.hasAttribute('data-compare-init')) {
        addBtn.setAttribute('data-compare-init', 'true');
        addBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // Get current image path from JSON details
            let imagePath = null;
            const jsonElements = document.querySelectorAll('.json-holder pre, [data-testid="json"] pre');
            jsonElements.forEach(el => {
                try {
                    const data = JSON.parse(el.textContent);
                    if (data && data.file_path) {
                        imagePath = data.file_path;
                    }
                } catch (ex) {}
            });
            
            if (!imagePath) {
                alert('Select an image first');
                return;
            }
            
            // Add to compare list (max 4)
            if (window.compareImages.length >= window.maxCompareImages) {
                window.compareImages.shift(); // Remove oldest
            }
            
            if (!window.compareImages.includes(imagePath)) {
                window.compareImages.push(imagePath);
            }
            
            // Show visual feedback
            const count = window.compareImages.length;
            this.textContent = `📊 Compare (${count}/${window.maxCompareImages})`;
            
            if (count >= 2) {
                showCompareView();
            }
        });
    }
}

function showCompareView() {
    if (window.compareImages.length < 2) {
        alert('Add at least 2 images to compare');
        return;
    }
    
    // Create modal
    const modal = document.createElement('div');
    modal.className = 'compare-modal';
    modal.innerHTML = `
        <div class="compare-header">
            <span class="compare-title">📊 Image Comparison (${window.compareImages.length} images)</span>
            <button onclick="closeCompareView()" style="background: #f85149; border: none; color: white; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600;">✕ Close</button>
        </div>
        <div class="compare-grid cols-${Math.min(window.compareImages.length, 4)}">
            ${window.compareImages.map((path, i) => `
                <div class="compare-item">
                    <img src="/file=${path.replace(/\\\\/g, '/')}" alt="Image ${i+1}">
                    <div class="compare-item-info">
                        <strong>${path.split(/[/\\\\]/).pop()}</strong>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeCompareView() {
    const modal = document.querySelector('.compare-modal');
    if (modal) {
        modal.remove();
    }
    window.compareImages = [];
    
    // Reset button text
    const addBtn = document.getElementById('compare-add-btn');
    if (addBtn) {
        addBtn.textContent = '📊 Add to Compare';
    }
}

// Initialize compare mode
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCompareMode);
} else {
    initCompareMode();
}

// Re-init on DOM changes (Gradio rerenders)
const compareObserver = new MutationObserver(() => {
    clearTimeout(window._compareInitTimeout);
    window._compareInitTimeout = setTimeout(initCompareMode, 500);
});
compareObserver.observe(document.body, { childList: true, subtree: true });

// ========== LAZY LOAD FULL RESOLUTION ==========
function initLazyFullResolution() {
    console.log("Initializing Lazy Full Resolution Loader");
    let currentPreviewId = 0;
    let loadTimeout = null;
    let abortController = null;
    let previousObjectURL = null;  // Track ObjectURL for cleanup
    const LOAD_DELAY_MS = 600;  // Wait 600ms before loading full res (debounce)
    
    // Find the preview image element
    function getCurrentPreviewImg() {
        // Gradio 3/4 structure vary, check multiple selectors
        return document.querySelector('.gallery .preview img, .gallery button.preview img, img.preview-image');
    }
    
    // Show a subtle loading indicator
    function showLoadingIndicator(img) {
        if (!img || img.parentNode.querySelector('.full-res-loader')) return;
        
        const loader = document.createElement('div');
        loader.className = 'full-res-loader';
        loader.innerHTML = `
            <div style="
                position: absolute; 
                top: 50%; 
                left: 50%; 
                transform: translate(-50%, -50%);
                background: rgba(0,0,0,0.6);
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 13px;
                pointer-events: none;
                z-index: 10;
                backdrop-filter: blur(4px);
                border: 1px solid rgba(255,255,255,0.1);
                display: flex;
                align-items: center;
                gap: 8px;
            ">
                <div class="spinner" style="
                    width: 14px; 
                    height: 14px; 
                    border: 2px solid rgba(255,255,255,0.3); 
                    border-top: 2px solid white; 
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                "></div>
                <span>Loading Full Res...</span>
            </div>
            <style>@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
        `;
        
        // Position relative to parent if needed
        if (getComputedStyle(img.parentNode).position === 'static') {
            img.parentNode.style.position = 'relative';
        }
        
        img.parentNode.appendChild(loader);
    }
    
    function hideLoadingIndicator(img) {
        if (!img) return;
        const loader = img.parentNode.querySelector('.full-res-loader');
        if (loader) loader.remove();
    }
    
    // BETTER APPROACH: Use the selected gallery item data
    function getSelectedImagePath() {
        // Try to find the file path from the details panel (which updates instantly on click)
        // This is robust because it comes from the server metadata
        const jsonElements = document.querySelectorAll('.json-holder pre, [data-testid="json"] pre');
        for (const el of jsonElements) {
            try {
                const data = JSON.parse(el.textContent);
                if (data && data.file_path) {
                    return data.file_path;
                }
            } catch (e) {}
        }
        
        // Fallback: visible path textbox?
        // In webui.py we have 'stacks_selected_path' or similar components
        const pathInputs = document.querySelectorAll('textarea[label="Selected Image"], input[label="Selected Image"]');
        for (const input of pathInputs) {
            if (input.value && input.value.trim().length > 1) {
                return input.value;
            }
        }
        
        return null;
    }
    
    function loadFullResolution(imgPath, previewId, imgElement) {
        // Cancel previous load
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
        
        // Cleanup previous ObjectURL to prevent memory leak
        if (previousObjectURL) {
            URL.revokeObjectURL(previousObjectURL);
            previousObjectURL = null;
        }
        
        // If previewId changed, don't load (stale)
        if (previewId !== currentPreviewId) return;
        
        abortController = new AbortController();
        
        // Determine URL
        // If it's a RAW file, use our API. Else use /file=
        const ext = imgPath.split('.').pop().toLowerCase();
        const isRaw = ['nef', 'cr2', 'arw', 'dng', 'orf', 'nrw', 'cr3', 'rw2'].includes(ext);
        
        let url = '';
        if (isRaw) {
             url = `/api/raw-preview?path=${encodeURIComponent(imgPath)}`;
        } else {
             // For standard images, append a distinct param to bypass cache or ensure full load
             url = `/file=${imgPath}`;
        }
        
        showLoadingIndicator(imgElement);
        
        fetch(url, { signal: abortController.signal })
            .then(response => {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.blob();
            })
            .then(blob => {
                if (previewId !== currentPreviewId) {
                    // Changed, discard blob (no need to create ObjectURL just to revoke)
                    return;
                }
                
                const objectURL = URL.createObjectURL(blob);
                previousObjectURL = objectURL;  // Track for cleanup
                imgElement.onload = () => {
                   hideLoadingIndicator(imgElement);
                };
                imgElement.src = objectURL;
                
                // Cleanup controller
                abortController = null;
            })
            .catch(err => {
                if (err.name !== 'AbortError') {
                    console.error('Full res load error:', err);
                }
                hideLoadingIndicator(imgElement);
            });
    }
    
    function handlePreviewChange() {
        const img = getCurrentPreviewImg();
        
        // If no preview image, we might be in grid mode.
        if (!img) {
            // Cancel any pending
            if (loadTimeout) clearTimeout(loadTimeout);
            if (abortController) abortController.abort();
            
            // Cleanup previous ObjectURL
            if (previousObjectURL) {
                URL.revokeObjectURL(previousObjectURL);
                previousObjectURL = null;
            }
            
            currentPreviewId++; 
            return;
        }
        
        // Retrieve path
        const path = getSelectedImagePath();
        if (!path) return; // Wait until details populate
        
        // Check if we already loaded this path for this session?
        if (img.dataset.fullResPath === path) {
             return; // Already initiated or loaded
        }
        
        // New image detected!
        currentPreviewId++;
        const myPreviewId = currentPreviewId;
        
        img.dataset.fullResPath = path; // Mark as handled
        
        // Cancel previous
        if (loadTimeout) clearTimeout(loadTimeout);
        if (abortController) abortController.abort();
        
        // Cleanup previous ObjectURL (if we are switching faster than load completes)
        if (previousObjectURL) {
            URL.revokeObjectURL(previousObjectURL);
            previousObjectURL = null;
        }
        
        // Set delay
        loadTimeout = setTimeout(() => {
            loadFullResolution(path, myPreviewId, img);
        }, LOAD_DELAY_MS);
    }
    
    // Watch for DOM changes to detect when preview opens or changes
    // The gallery preview creates a new <img> or changes src
    const observer = new MutationObserver((mutations) => {
        // Quick check if preview exists
        if (document.querySelector('.gallery .preview')) {
             handlePreviewChange();
        }
    });
    
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'style'] });
}

// Initialize Lazy Loader
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLazyFullResolution);
} else {
    initLazyFullResolution();
}

</script>
"""

# Custom CSS for modern dark UI
custom_css = """
/* ========== ROOT THEME VARIABLES ========== */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --bg-elevated: #30363d;
    --border-color: #30363d;
    --border-subtle: #21262d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --accent-primary: #58a6ff;
    --accent-success: #3fb950;
    --accent-warning: #d29922;
    --accent-danger: #f85149;
    --accent-purple: #a371f7;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.5);
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
    --transition-fast: 150ms ease;
    --transition-normal: 250ms ease;
}

/* ========== GLOBAL STYLES ========== */
.gradio-container {
    background: linear-gradient(135deg, var(--bg-primary) 0%, #0a0d12 100%) !important;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.dark {
    --block-background-fill: var(--bg-secondary) !important;
    --block-border-color: var(--border-color) !important;
    --body-background-fill: var(--bg-primary) !important;
    --button-primary-background-fill: var(--accent-primary) !important;
    --button-primary-background-fill-hover: #4895ef !important;
    --input-background-fill: var(--bg-tertiary) !important;
}

/* ========== COMPACT LAYOUT ========== */
/* Reduce vertical gaps between rows and blocks */
.contain > .column > .row,
.contain > .column > .block,
.contain > .column > .form {
    margin-bottom: 8px !important;
}

.contain > .column > .accordion {
    margin-bottom: 8px !important;
}

/* Reduce padding on blocks */
.block {
    padding-top: 8px !important;
    padding-bottom: 8px !important;
}

/* Compact rows */
.row {
    gap: 8px !important;
}

/* ========== HEADER ========== */
h1 {
    font-size: 1.75rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.5px !important;
    color: var(--text-primary) !important;
    margin-bottom: 0.5rem !important;
}

/* ========== TABS ========== */
.tab-nav {
    background: var(--bg-secondary) !important;
    border-radius: var(--radius-lg) !important;
    padding: 4px !important;
    gap: 4px !important;
    border: 1px solid var(--border-color) !important;
}

.tab-nav button {
    background: transparent !important;
    border: none !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    transition: all var(--transition-fast) !important;
}

.tab-nav button:hover {
    background: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
}

.tab-nav button.selected {
    background: var(--accent-primary) !important;
    color: white !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ========== TREE VIEW ========== */
.tree-content { 
    cursor: pointer; 
    padding: 6px 12px; 
    border-radius: var(--radius-sm); 
    display: inline-block; 
    user-select: none; 
    color: var(--text-secondary);
    transition: all var(--transition-fast);
}

.tree-content:hover { 
    background-color: var(--bg-tertiary); 
    color: var(--text-primary);
}

summary { outline: none; cursor: pointer; }
#folder_tree_selection { display: none; } 

/* ========== GALLERY HEADER ========== */
.gallery-header {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    padding: 16px 20px !important;
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    margin-bottom: 16px !important;
}

.folder-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 8px 16px !important;
    background: linear-gradient(135deg, var(--accent-primary) 0%, var(--accent-purple) 100%) !important;
    border-radius: 20px !important;
    color: white !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    box-shadow: var(--shadow-sm) !important;
}

.folder-badge::before {
    content: "📁";
    font-size: 1rem;
}

/* ========== BUTTONS ========== */
.primary-btn {
    background: linear-gradient(135deg, var(--accent-primary) 0%, #4895ef 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
    padding: 10px 24px !important;
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-sm) !important;
    transition: all var(--transition-fast) !important;
}

.primary-btn:hover {
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-md) !important;
}

.secondary-btn {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    border-radius: var(--radius-md) !important;
    transition: all var(--transition-fast) !important;
}

.secondary-btn:hover {
    background: var(--bg-elevated) !important;
    border-color: var(--accent-primary) !important;
}

.danger-btn {
    background: linear-gradient(135deg, var(--accent-danger) 0%, #da3633 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 600 !important;
}

/* ========== GALLERY GRID ========== */
.gallery-container {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px !important;
}

/* Reset Gradio gallery wrapper positioning in preview mode */
.gallery-container .wrap,
.gallery-container > div {
    padding: 0 !important;
    margin: 0 !important;
}

/* Ensure the gallery block fills properly */
.block.gallery-container {
    padding: 0 !important;
}

.gallery .gallery-item {
    border-radius: var(--radius-md) !important;
    overflow: hidden !important;
    transition: all var(--transition-normal) !important;
    border: 2px solid transparent !important;
}

.gallery .gallery-item:hover {
    transform: scale(1.02) !important;
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-md) !important;
}

.gallery .gallery-item.selected {
    border-color: var(--accent-success) !important;
    box-shadow: 0 0 0 3px rgba(63, 185, 80, 0.3) !important;
}

/* ========== DETAILS PANEL ========== */
.details-panel {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 20px !important;
}

.score-card {
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-secondary) 100%) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 16px !important;
    text-align: center !important;
}

.score-value {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: var(--accent-primary) !important;
}

.score-label {
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}

/* ========== INPUTS ========== */
.input-container input,
.input-container textarea {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    padding: 12px 16px !important;
    transition: all var(--transition-fast) !important;
}

.input-container input:focus,
.input-container textarea:focus {
    border-color: var(--accent-primary) !important;
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2) !important;
    outline: none !important;
}

/* ========== DROPDOWNS ========== */
.dropdown-container {
    position: relative !important;
}

select, .svelte-dropdown {
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    padding: 10px 14px !important;
}

/* ========== ACCORDION ========== */
.accordion {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    overflow: hidden !important;
    margin-bottom: 4px !important;
}

.accordion > .label-wrap {
    background: var(--bg-tertiary) !important;
    padding: 10px 16px !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid var(--border-color) !important;
}

/* ========== PAGINATION ========== */
.pagination-container {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 4px !important;
    padding: 6px 12px !important;
    margin: 0 !important;
}

.page-btn {
    min-width: 40px !important;
    padding: 8px 12px !important;
    font-size: 1rem !important;
}

.page-btn:hover {
    background: var(--accent-primary) !important;
    color: white !important;
}

.page-indicator {
    background: var(--bg-tertiary) !important;
    padding: 8px 20px !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
    border: 1px solid var(--border-color) !important;
    min-width: 120px !important;
    text-align: center !important;
}

/* ========== MODAL & LIGHTBOX ========== */
/* Only target the main preview image, not thumbnails */
.preview .media-button img, 
.lightbox img, 
.modal img {
    object-fit: contain !important;
    width: auto !important;
    height: auto !important;
    max-width: 100% !important;
    max-height: calc(100% - 80px) !important;
    margin: auto;
}

/* Ensure thumbnail images display properly */
.gallery .thumbnails img,
.gallery .thumbnail-item img,
.thumbnails img,
.thumbnail-item img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    opacity: 1 !important;
    visibility: visible !important;
}

/* Gradio Gallery Lightbox/Preview Mode Styling */
.gallery .preview,
.gallery button.preview {
    position: relative !important;
    width: 100% !important;
    display: block !important;
    padding: 0 !important;
    margin: 0 !important;
    left: 0 !important;
    right: 0 !important;
    box-sizing: border-box !important;
}

/* Gallery container should clip images but not buttons (buttons are fixed positioned) */
.gallery-container {
    overflow: hidden !important;
    padding: 0 !important;
}

/* The media-button contains the preview image - make it fill the container */
.gallery button.preview .media-button,
.gallery .preview .media-button {
    overflow: hidden !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    left: 0 !important;
    right: 0 !important;
    position: relative !important;
    box-sizing: border-box !important;
}

.gallery button.preview .media-button img,
.gallery .preview .media-button img {
    object-fit: contain !important;
    max-width: 100% !important;
    max-height: 100% !important;
    width: auto !important;
    height: auto !important;
    display: block !important;
    margin: 0 auto !important;
}

/* Override hide-top-corner to show controls - be more specific */
/* Since icon-button-wrapper is position:fixed, parent overflow doesn't affect it */
.gallery .hide-top-corner,
.gallery .top-panel,
.gallery .top-panel.hide-top-corner,
.gallery .icon-button-wrapper.hide-top-corner,
.gallery .icon-button-wrapper.top-panel.hide-top-corner {
    opacity: 1 !important;
    visibility: visible !important;
    display: flex !important;
    clip: auto !important;
    clip-path: none !important;
}

/* Style the built-in gallery controls (download, fullscreen, close) */
/* position:fixed removes element from document flow - parent overflow doesn't affect it */
.gallery .icon-buttons,
.gallery .icon-button-wrapper,
.gallery .icon-button-wrapper.top-panel {
    position: fixed !important;
    top: 15px !important;
    right: 180px !important;
    z-index: 99998 !important;
    display: flex !important;
    flex-direction: row !important;
    gap: 8px !important;
    opacity: 1 !important;
    visibility: visible !important;
    width: auto !important;
    max-width: none !important;
    transform: none !important;
}

.gallery .icon-buttons button,
.gallery .icon-button-wrapper button {
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 14px !important;
    color: var(--text-primary) !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
    opacity: 1 !important;
    visibility: visible !important;
    display: inline-flex !important;
    min-width: auto !important;
    flex-shrink: 0 !important;
}

.gallery .icon-buttons button:hover,
.gallery .icon-button-wrapper button:hover {
    background: var(--accent-primary) !important;
    border-color: var(--accent-primary) !important;
}

/* Navigation hint text at bottom of preview */
.gallery button.preview::after {
    content: "Press ESC or click '✕ Back to Grid' to return" !important;
    position: fixed !important;
    bottom: 80px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    z-index: 99990 !important;
    background: rgba(0, 0, 0, 0.85) !important;
    color: #a0a0a0 !important;
    padding: 12px 24px !important;
    border-radius: 25px !important;
    font-size: 13px !important;
    pointer-events: none !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
}

/* Thumbnail strip styling */
.gallery .thumbnails {
    background: rgba(0, 0, 0, 0.9) !important;
    padding: 12px !important;
    border-radius: var(--radius-lg) !important;
    margin: 16px auto 0 auto !important;
    width: 100% !important;
    max-width: 100% !important;
    display: flex !important;
    justify-content: center !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
}

.gallery .thumbnails button,
.gallery .thumbnail-item {
    border-radius: var(--radius-sm) !important;
    border: 2px solid transparent !important;
    transition: all 0.2s ease !important;
    overflow: visible !important;
    background-size: cover !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
}

.gallery .thumbnails button:hover,
.gallery .thumbnail-item:hover {
    border-color: var(--accent-primary) !important;
}

.gallery .thumbnails button.selected,
.gallery .thumbnail-item.selected {
    border-color: var(--accent-warning) !important;
    box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.3) !important;
}

/* Ensure thumbnail images are visible */
.gallery .thumbnails button img,
.gallery .thumbnail-item img {
    width: 100% !important;
    height: 100% !important;
    object-fit: cover !important;
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}

/* Ensure the preview backdrop is clickable to close */
.gallery .preview > div:first-child {
    cursor: pointer !important;
}

/* Preview content divs should contain images properly and be centered */
/* Exclude icon-button-wrapper and thumbnails from these styles */
.gallery button.preview > div:not(.icon-button-wrapper):not(.thumbnails),
.gallery .preview > div:not(.icon-button-wrapper):not(.thumbnails) {
    overflow: hidden !important;
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin: 0 !important;
    padding: 0 !important;
    left: 0 !important;
    right: 0 !important;
    box-sizing: border-box !important;
}

/* Svelte gallery specific overrides */
.svelte-ao1xvt.preview,
button.preview.svelte-ao1xvt {
    padding: 0 !important;
    margin: 0 !important;
    width: 100% !important;
    left: 0 !important;
}

.svelte-ao1xvt.media-button,
button.media-button.svelte-ao1xvt {
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
    left: 0 !important;
}

/* Specifically target the close button in gallery preview */
.gallery button.preview .icon-button-wrapper button,
.gallery .preview .icon-button-wrapper button,
.gallery [class*="close"],
.gallery button[aria-label*="close"],
.gallery button[aria-label*="Close"] {
    opacity: 1 !important;
    visibility: visible !important;
    display: inline-flex !important;
    pointer-events: auto !important;
}

.full-res-modal {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    background-color: rgba(0, 0, 0, 0.95) !important;
    z-index: 9999 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    backdrop-filter: blur(10px) !important;
}

.modal-close-btn {
    position: absolute !important;
    top: 20px !important;
    right: 30px !important;
    z-index: 10000 !important;
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 10px 20px !important;
}

.modal-image-container {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 95% !important;
    height: 90% !important;
    border: none !important;
    background-color: transparent !important;
}

.modal-image-container img {
    max-height: 90vh !important;
    max-width: 95vw !important;
    object-fit: contain !important;
    border-radius: var(--radius-lg) !important;
}

/* ========== STATUS INDICATORS ========== */
.status-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    padding: 6px 12px !important;
    border-radius: 20px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

.status-badge.success {
    background: rgba(63, 185, 80, 0.15) !important;
    color: var(--accent-success) !important;
    border: 1px solid rgba(63, 185, 80, 0.3) !important;
}

.status-badge.warning {
    background: rgba(210, 153, 34, 0.15) !important;
    color: var(--accent-warning) !important;
    border: 1px solid rgba(210, 153, 34, 0.3) !important;
}

/* ========== PROGRESS BAR ========== */
.progress-container {
    background: var(--bg-tertiary) !important;
    border-radius: var(--radius-md) !important;
    height: 8px !important;
    overflow: hidden !important;
}

.progress-bar {
    height: 100% !important;
    background: linear-gradient(90deg, var(--accent-primary) 0%, var(--accent-purple) 100%) !important;
    border-radius: var(--radius-md) !important;
    transition: width var(--transition-normal) !important;
}

/* ========== LABELS ========== */
.label {
    color: var(--text-secondary) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 6px !important;
}

/* ========== CARDS ========== */
.card {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    padding: 20px !important;
    transition: all var(--transition-fast) !important;
}

.card:hover {
    border-color: var(--accent-primary) !important;
    box-shadow: var(--shadow-md) !important;
}

/* ========== EMPTY STATE ========== */
.empty-state {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 60px 20px !important;
    color: var(--text-muted) !important;
}

.empty-state-icon {
    font-size: 3rem !important;
    margin-bottom: 16px !important;
    opacity: 0.5 !important;
}

/* ========== SCROLLBAR ========== */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
    background: var(--bg-elevated);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
}

/* ========== ANIMATION ========== */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.animate-in {
    animation: fadeIn var(--transition-normal) ease-out !important;
}

/* ========== FILTER CHIPS ========== */
.filter-chip {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    padding: 6px 14px !important;
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 20px !important;
    font-size: 0.85rem !important;
    color: var(--text-secondary) !important;
    transition: all var(--transition-fast) !important;
}

.filter-chip:hover {
    border-color: var(--accent-primary) !important;
    color: var(--text-primary) !important;
}

.filter-chip.active {
    background: var(--accent-primary) !important;
    border-color: var(--accent-primary) !important;
    color: white !important;
}

/* ========== FOLDER CONTEXT BAR ========== */
.folder-context-bar {
    background: linear-gradient(135deg, rgba(88, 166, 255, 0.1) 0%, rgba(163, 113, 247, 0.1) 100%) !important;
    border: 1px solid rgba(88, 166, 255, 0.3) !important;
    border-radius: var(--radius-lg) !important;
    padding: 16px 24px !important;
    margin-bottom: 16px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
}

.folder-path-display {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
}

.folder-icon {
    font-size: 1.5rem !important;
}

/* ========== FOLDER TREE CONTAINER ========== */
.folder-tree-container {
    max-height: 550px !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-md) !important;
    padding: 12px !important;
}

/* Folder Tree Status Label - smaller font */
.tree-status-label .output-class {
    font-size: 0.9rem !important;
    font-weight: 400 !important;
    color: var(--text-secondary) !important;
    padding: 8px 12px !important;
}

.folder-tree-container::-webkit-scrollbar {
    width: 8px;
}

.folder-tree-container::-webkit-scrollbar-track {
    background: var(--bg-tertiary);
    border-radius: 4px;
}

.folder-tree-container::-webkit-scrollbar-thumb {
    background: var(--bg-elevated);
    border-radius: 4px;
}

.folder-tree-container::-webkit-scrollbar-thumb:hover {
    background: var(--accent-primary);
}

/* ========== HIGHLIGHTED TEXT (KEYWORDS) ========== */
/* Hide category labels (C0, C1, etc.) */
[data-testid="highlighted-text"] .label {
    display: none !important;
}

/* Hide close/cross button */
[data-testid="highlighted-text"] .label-clear-button {
    display: none !important;
}

/* White text for keyword tags */
[data-testid="highlighted-text"] .textspan {
    color: white !important;
    font-weight: 500 !important;
    padding: 4px 12px !important;
    border-radius: 6px !important;
    margin: 2px !important;
}

[data-testid="highlighted-text"] .text {
    color: white !important;
}

/* ========== STACK BADGE OVERLAY ========== */
.stack-badge {
    position: absolute;
    top: 6px;
    right: 6px;
    background: linear-gradient(135deg, #58a6ff 0%, #a371f7 100%);
    color: white;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 10px;
    min-width: 20px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    z-index: 10;
    pointer-events: none;
    font-family: system-ui, -apple-system, sans-serif;
}

.stack-badge.large {
    background: linear-gradient(135deg, #3fb950 0%, #238636 100%);
}

/* ========== STACK INLINE PREVIEW (Hover Expand) ========== */
.stack-preview-popup {
    position: fixed;
    background: var(--bg-secondary, #161b22);
    border: 1px solid var(--border-color, #30363d);
    border-radius: 12px;
    padding: 12px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    z-index: 9999;
    max-width: 400px;
    display: none;
}

.stack-preview-popup.visible {
    display: block;
    animation: fadeInScale 0.15s ease-out;
}

@keyframes fadeInScale {
    from {
        opacity: 0;
        transform: scale(0.95);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}

.stack-preview-header {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary, #e6edf3);
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border-subtle, #21262d);
}

.stack-preview-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
}

.stack-preview-thumb {
    width: 80px;
    height: 80px;
    object-fit: cover;
    border-radius: 6px;
    border: 2px solid transparent;
    transition: border-color 0.15s ease;
}

.stack-preview-thumb:hover {
    border-color: var(--accent-primary, #58a6ff);
}

.stack-preview-thumb.best {
    border-color: var(--accent-success, #3fb950);
}

.stack-preview-more {
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary, #21262d);
    border-radius: 6px;
    color: var(--text-secondary, #8b949e);
    font-size: 12px;
    font-weight: 500;
}

/* ========== IMAGE COMPARISON VIEW ========== */
.compare-modal {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100% !important;
    height: 100% !important;
    background: rgba(0, 0, 0, 0.95) !important;
    z-index: 10000 !important;
    display: flex !important;
    flex-direction: column !important;
    padding: 20px !important;
    box-sizing: border-box !important;
}

.compare-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 20px;
    background: var(--bg-secondary, #161b22);
    border-radius: 10px;
    margin-bottom: 15px;
}

.compare-title {
    font-size: 1.2rem;
    font-weight: 600;
    color: var(--text-primary, #e6edf3);
}

.compare-grid {
    display: grid;
    gap: 15px;
    flex: 1;
    overflow: hidden;
}

.compare-grid.cols-2 {
    grid-template-columns: repeat(2, 1fr);
}

.compare-grid.cols-3 {
    grid-template-columns: repeat(3, 1fr);
}

.compare-grid.cols-4 {
    grid-template-columns: repeat(2, 1fr);
    grid-template-rows: repeat(2, 1fr);
}

.compare-item {
    background: var(--bg-secondary, #161b22);
    border: 1px solid var(--border-color, #30363d);
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.compare-item img {
    width: 100%;
    height: calc(100% - 60px);
    object-fit: contain;
    background: var(--bg-primary, #0d1117);
}

.compare-item-info {
    padding: 10px 15px;
    background: var(--bg-tertiary, #21262d);
    color: var(--text-primary, #e6edf3);
    font-size: 0.9rem;
}

.compare-item-score {
    display: flex;
    gap: 15px;
    margin-top: 5px;
}

.compare-item-score span {
    color: var(--accent-primary, #58a6ff);
    font-weight: 600;
}
"""

with gr.Blocks(title="Image Scoring WebUI", css=custom_css, head=tree_js) as demo:
    gr.Markdown("# Image Scoring WebUI")
    
    # State
    current_page = gr.State(value=1)
    current_paths = gr.State(value=[])
    current_folder_state = gr.State(value=None)
    
    # Polling Timer for status updates
    status_timer = gr.Timer(value=1.0)
    

    
    with gr.Tabs() as main_tabs:
        # TAB 1: RUN SCORING
        with gr.TabItem("Scoring", id="scoring"):
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
            
            run_btn.click(
                fn=run_scoring_wrapper,
                inputs=[input_dir, force_checkbox],
                outputs=[log_output, s_status_html, run_btn, stop_btn, fix_btn]
            )
            
            stop_btn.click(
                fn=lambda: runner.stop(),
                inputs=[],
                outputs=[]
            )
            
            fix_btn.click(
                fn=run_fix_db_wrapper,
                inputs=[],
                outputs=[log_output, s_status_html, run_btn, stop_btn, fix_btn]
            )

        # TAB 2: KEYWORDS
        with gr.TabItem("Keywords", id="keywords"):
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
            
            k_run_btn.click(
                fn=run_tagging_wrapper,
                inputs=[k_input_dir, k_custom, k_overwrite, k_captions],
                outputs=[k_log_output, k_status_html, k_run_btn, k_stop_btn]
            )
            
            k_stop_btn.click(
                fn=lambda: tagging_runner.stop(),
                inputs=[],
                outputs=[]
            )

        # TAB 3: GALLERY
        with gr.TabItem("Gallery", id="gallery"):
            # Folder Context Bar (visible when folder is selected)
            with gr.Group(visible=False, elem_classes=["folder-context-bar"]) as folder_context_group:
                with gr.Row():
                    with gr.Column(scale=4):
                        folder_display = gr.HTML(value="")
                    with gr.Column(scale=1, min_width=150):
                        reset_folder_btn = gr.Button("✕ Clear Filter", variant="secondary", size="sm")
            
            # Main Controls Row
            with gr.Row(elem_classes=["gallery-header"]):
                with gr.Column(scale=1, min_width=200):
                    refresh_btn = gr.Button("🔄 Refresh", variant="primary", size="lg")
                with gr.Column(scale=2):
                    with gr.Row():
                        sort_dropdown = gr.Dropdown(
                            choices=[
                                ("📅 Date Added", "created_at"),
                                ("🆔 ID", "id"),
                                ("⭐ General Score", "score_general"),
                                ("🔧 Technical Score", "score_technical"),
                                ("🎨 Aesthetic Score", "score_aesthetic"),
                                ("📊 SPAQ", "score_spaq"),
                                ("🏆 AVA", "score_ava"),
                                ("📈 KonIQ", "score_koniq"),
                                ("📉 PaQ2PiQ", "score_paq2piq"),
                                ("🎯 LIQE", "score_liqe")
                            ], 
                            value=app_config.get('scoring', {}).get('default_sort_by', 'score_general'), 
                            label="Sort By",
                            container=False
                        )
                        order_dropdown = gr.Dropdown(
                            choices=[("↓ Highest First", "desc"), ("↑ Lowest First", "asc")], 
                            value=app_config.get('scoring', {}).get('default_sort_order', 'desc'), 
                            label="Order",
                            container=False
                        )
            
            # Filters Section
            with gr.Accordion("🔍 Filters & Search", open=False, elem_classes=["accordion"]):
                with gr.Row():
                    with gr.Column(scale=1):
                        filter_rating = gr.CheckboxGroup(
                            choices=[
                                ("⭐", "1"), ("⭐⭐", "2"), ("⭐⭐⭐", "3"), 
                                ("⭐⭐⭐⭐", "4"), ("⭐⭐⭐⭐⭐", "5")
                            ], 
                            label="Rating Filter"
                        )
                    with gr.Column(scale=1):
                        filter_label = gr.CheckboxGroup(
                            choices=[
                                ("🔴 Red", "Red"), ("🟡 Yellow", "Yellow"), ("🟢 Green", "Green"), 
                                ("🔵 Blue", "Blue"), ("🟣 Purple", "Purple"), ("⚪ None", "None")
                            ], 
                            label="Color Label"
                        )
                
                with gr.Row():
                    f_min_gen = gr.Slider(
                        0.0, 1.0,
                        value=app_config.get('ui', {}).get('default_min_general', 0.0),
                        step=0.05, label="Min General", info="0.0 - 1.0"
                    )
                    f_min_aes = gr.Slider(
                        0.0, 1.0,
                        value=app_config.get('ui', {}).get('default_min_aesthetic', 0.0),
                        step=0.05, label="Min Aesthetic", info="0.0 - 1.0"
                    )
                    f_min_tech = gr.Slider(
                        0.0, 1.0,
                        value=app_config.get('ui', {}).get('default_min_technical', 0.0),
                        step=0.05, label="Min Technical", info="0.0 - 1.0"
                    )
                
                with gr.Row():
                    f_date_start = gr.Textbox(label="From Date", placeholder="YYYY-MM-DD", scale=1)
                    f_date_end = gr.Textbox(label="To Date", placeholder="YYYY-MM-DD", scale=1)
                    filter_keyword = gr.Textbox(label="Keyword Search", placeholder="Search tags...", scale=2)
            
            # Export Section
            with gr.Accordion("📤 Export Data", open=False, elem_classes=["accordion"]):
                with gr.Row():
                    export_format = gr.Dropdown(
                        choices=[
                            ("📄 JSON (Full Data)", "json"),
                            ("📊 CSV (Spreadsheet)", "csv"),
                            ("📗 Excel (.xlsx)", "xlsx")
                        ],
                        value=app_config.get('ui', {}).get('default_export_format', 'json'),
                        label="Export Format",
                        scale=1
                    )
                    export_btn = gr.Button("⬇️ Export All Images", variant="primary", size="sm", scale=1)
                
                # Export Templates - DISABLED: Feature hidden from UI
                # with gr.Accordion("📋 Export Templates", open=False):
                #     gr.Markdown("Save and load preset export configurations for quick reuse.")
                #     with gr.Row():
                #         export_template_dropdown = gr.Dropdown(
                #             choices=[],
                #             value=None,
                #             label="Template",
                #             scale=2,
                #             info="Select a saved template to load"
                #         )
                #         export_template_load_btn = gr.Button("📥 Load Template", variant="secondary", size="sm", scale=1)
                #         export_template_delete_btn = gr.Button("🗑️ Delete", variant="stop", size="sm", scale=1, visible=False)
                #     with gr.Row():
                #         export_template_name = gr.Textbox(
                #             label="Template Name",
                #             placeholder="e.g., 'Scores Only', 'High Quality Filter'",
                #             scale=2
                #         )
                #         export_template_save_btn = gr.Button("💾 Save Template", variant="secondary", size="sm", scale=1)
                #     export_template_status = gr.Textbox(label="Template Status", interactive=False, visible=False)
                #     export_template_state = gr.State(None)  # Track currently loaded template name
                export_template_dropdown = gr.State(None)  # Hidden placeholder for removed feature
                
                # Advanced Export Options
                with gr.Accordion("⚙️ Advanced Options", open=False):
                    # Column Selection
                    available_columns = db.get_available_columns()
                    # Group columns by category for better UX
                    basic_cols = ['id', 'file_path', 'file_name', 'file_type', 'created_at']
                    score_cols = ['score_general', 'score_technical', 'score_aesthetic', 
                                 'score_spaq', 'score_ava', 'score_koniq', 'score_paq2piq', 'score_liqe']
                    metadata_cols = ['rating', 'label', 'keywords', 'title', 'description']
                    other_cols = [c for c in available_columns if c not in basic_cols + score_cols + metadata_cols]
                    
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("**Basic Info**")
                            export_cols_basic = gr.CheckboxGroup(
                                choices=basic_cols,
                                value=basic_cols,
                                label="",
                                show_label=False
                            )
                        with gr.Column(scale=1):
                            gr.Markdown("**Scores**")
                            export_cols_scores = gr.CheckboxGroup(
                                choices=score_cols,
                                value=score_cols,
                                label="",
                                show_label=False
                            )
                        with gr.Column(scale=1):
                            gr.Markdown("**Metadata**")
                            export_cols_metadata = gr.CheckboxGroup(
                                choices=metadata_cols,
                                value=metadata_cols,
                                label="",
                                show_label=False
                            )
                    # Always create other_cols component (empty if no other columns)
                    export_cols_other = gr.CheckboxGroup(
                        choices=other_cols if other_cols else [],
                        value=[],
                        label="Other Columns",
                        visible=bool(other_cols)
                    )
                    
                    # Filtering Options
                    gr.Markdown("**Filtering (optional)**")
                    with gr.Row():
                        export_filter_rating = gr.CheckboxGroup(
                            choices=["1", "2", "3", "4", "5", "Unrated"],
                            value=[],
                            label="Rating Filter",
                            scale=1
                        )
                        export_filter_label = gr.CheckboxGroup(
                            choices=["Red", "Yellow", "Green", "Blue", "Purple", "None"],
                            value=[],
                            label="Label Filter",
                            scale=1
                        )
                    with gr.Row():
                        export_filter_keyword = gr.Textbox(
                            label="Keyword Search",
                            placeholder="Search in keywords...",
                            scale=2
                        )
                        export_filter_folder = gr.Textbox(
                            label="Folder Path",
                            placeholder="D:\\Photos\\...",
                            scale=2
                        )
                    with gr.Row():
                        export_filter_min_gen = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min General Score")
                        export_filter_min_aes = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Aesthetic Score")
                        export_filter_min_tech = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Technical Score")
                    with gr.Row():
                        export_filter_date_start = gr.Textbox(label="From Date (YYYY-MM-DD)", placeholder="2024-01-01", scale=1)
                        export_filter_date_end = gr.Textbox(label="To Date (YYYY-MM-DD)", placeholder="2024-12-31", scale=1)
                
                export_status = gr.Textbox(label="Status", interactive=False, visible=False)

            # Pagination
            with gr.Row(elem_classes=["pagination-container"]):
                first_btn = gr.Button("⏮", size="sm", elem_classes=["page-btn"], scale=0, min_width=45)
                prev_btn = gr.Button("◀", size="sm", elem_classes=["page-btn"], scale=0, min_width=45)
                page_label = gr.Button(value="Page 1 of 1", interactive=False, elem_classes=["page-indicator"], scale=1)
                next_btn = gr.Button("▶", size="sm", elem_classes=["page-btn"], scale=0, min_width=45)
                last_btn = gr.Button("⏭", size="sm", elem_classes=["page-btn"], scale=0, min_width=45)
            
            # Main Content Area - Gallery + Details Side Panel
            with gr.Row():
                # Gallery Section (wider)
                with gr.Column(scale=3):
                    gallery = gr.Gallery(
                        label="📸 Image Gallery", 
                        columns=5, 
                        height=600,
                        object_fit="cover",
                        allow_preview=True,
                        show_share_button=False,
                        elem_classes=["gallery-container"]
                    )
                
                # Details Side Panel (narrower)
                with gr.Column(scale=1, min_width=320, elem_classes=["details-panel"]):
                    # Score Overview
                    with gr.Group():
                        gr.Markdown("### 📊 Quality Scores")
                        d_score_gen = gr.Label(label="General", num_top_classes=1, elem_classes=["score-card"])
                        with gr.Row():
                            d_score_weighted = gr.Label(label="Weighted", num_top_classes=2, scale=1)
                        d_score_models = gr.Label(label="Models", num_top_classes=5)
                    
                    # Culling Status (from AI Culling workflow)
                    d_culling_status = gr.HTML(
                        value='<div style="display: none;"></div>',
                        elem_id="culling-status-display"
                    )
                    
                    # Metadata Editor
                    with gr.Accordion("✏️ Edit Metadata", open=False):
                        d_title = gr.Textbox(label="Title", placeholder="Enter title...", lines=1)
                        d_desc = gr.Textbox(label="Description", placeholder="Enter description...", lines=2)
                        d_keywords = gr.HighlightedText(
                            label="Keywords",
                            combine_adjacent=False,
                            show_legend=False,
                            interactive=False,
                            color_map=KEYWORD_COLOR_MAP
                        )
                        with gr.Row():
                            d_rating = gr.Dropdown(
                                choices=[("Not Rated", "0"), ("★", "1"), ("★★", "2"), ("★★★", "3"), ("★★★★", "4"), ("★★★★★", "5")], 
                                label="Rating",
                                value="0"
                            )
                            d_label = gr.Dropdown(
                                choices=[("None", "None"), ("🔴 Red", "Red"), ("🟡 Yellow", "Yellow"), ("🟢 Green", "Green"), ("🔵 Blue", "Blue"), ("🟣 Purple", "Purple")], 
                                label="Label",
                                value="None"
                            )
                        save_btn = gr.Button("💾 Save Changes", variant="primary", size="lg")
                        save_status = gr.Label(label="Status", visible=False)
                    
                    # Actions
                    with gr.Group():
                        # Buttons removed

                        
                        with gr.Row():
                            fix_btn = gr.Button("🔧 Fix Data (Fast)", variant="secondary", size="sm", visible=False)
                            rerun_score_btn = gr.Button("🔄 Re-Run Scoring (Slow)", variant="secondary", size="sm", visible=False)
                            rerun_tags_btn = gr.Button("🏷️ Re-Run Keywords", variant="secondary", size="sm", visible=False)
                            delete_btn = gr.Button("🗑️ Delete NEF File", variant="stop", visible=False, size="sm")
                        
                        fix_status = gr.Textbox(label="Status", visible=False)
                        delete_status = gr.Textbox(label="Status", interactive=False, visible=False)
                    

                    
                    # Selected file path for RAW preview (hidden, used by JavaScript)
                    gallery_selected_path = gr.Textbox(visible=False, elem_id="gallery-selected-path")
                    
                    # In-Browser RAW Preview (LibRaw-WASM) - DISABLED: Feature not working
                    # with gr.Accordion("🎞️ In-Browser RAW Preview", open=False):
                    #     gr.Markdown("""
                    #     **Client-side NEF preview** - Extracts embedded JPEG directly in your browser.
                    #     No server processing required. Works for Nikon NEF files.
                    #     """)
                    #     raw_preview_btn = gr.Button("🖼️ Extract Preview", variant="secondary", size="sm", elem_id="raw-preview-btn")
                    #     raw_preview_status = gr.HTML(value='<div id="raw-preview-status" style="color: #8b949e; font-size: 0.9em;">Click button to extract preview</div>')
                    #     raw_preview_canvas = gr.HTML(value='<canvas id="raw-preview-canvas" style="max-width: 100%; border-radius: 8px; display: none;"></canvas>')
                    
                    # Raw Data (hidden by default)
                    with gr.Accordion("📋 Raw JSON Data", open=False):
                        image_details = gr.JSON(label="Full Details")
                    
                    full_res_image = gr.Image(label="Preview", visible=False, interactive=False, type="filepath")

            # Events
            
            # Events
            
            # Helper to link outputs
            gallery_outputs = [gallery, page_label, current_paths, image_details] # Note: image_details is still needed for pagination update if we want to clear it, but typically pagination just updates gallery. We might wanna clear details on page? Let's leave as is for now, it's fine.
            # Actually, `get_gallery_data` returns just gallery list + label.
            # `update_gallery` wrapper returns images, label, paths, {}.
            # The last {} was `image_details`. We need to match the new outputs if we want to clear them.
            # But wait, `update_gallery` returns 4 items.
            # The outputs below are [current_page, gallery, page_label, current_paths, image_details].
            
            # We need to update `update_gallery` to return empty values for new components too to clear them?
            # Or just leave them stale? Stale is bad.
            # Let's update `update_gallery` to return 8 outputs to match (page is separate).
            
            # Let's patch `update_gallery` separately. For now, let's fix the select event.
            
            
            # Legacy filter list + new ones
            filter_inputs = [
                sort_dropdown, order_dropdown, 
                filter_rating, filter_label, filter_keyword,
                f_min_gen, f_min_aes, f_min_tech, f_date_start, f_date_end,
                current_folder_state
            ]
            
            # Helper list for all detail outputs that need clearing
            # Must match return order of update_gallery (excluding first 3: images, label, paths)
            # Helper list for all detail outputs that need clearing
            # Must match return order of update_gallery (excluding first 3: images, label, paths)
            detail_outputs = [d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label, d_culling_status, fix_btn, fix_status, rerun_score_btn, rerun_tags_btn]
            
            # Combined outputs for gallery update: [current_page, gallery, page_label, current_paths, *detail_outputs]
            
            refresh_btn.click(
                fn=first_page,
                inputs=filter_inputs,
                outputs=[current_page, gallery, page_label, current_paths, *detail_outputs]
            )
            
            reset_folder_btn.click(
                fn=reset_folder_filter,
                inputs=[*filter_inputs[:-1]], # Exclude current_folder_state from inputs, we force plain None
                outputs=[folder_context_group, folder_display, current_folder_state, current_page, gallery, page_label, current_paths, *detail_outputs]
            )
            
            first_btn.click(
                fn=first_page,
                inputs=filter_inputs,
                outputs=[current_page, gallery, page_label, current_paths, *detail_outputs]
            )
            
            prev_btn.click(
                fn=prev_page,
                inputs=[current_page, *filter_inputs],
                outputs=[current_page, gallery, page_label, current_paths, *detail_outputs]
            )
            
            next_btn.click(
                fn=next_page,
                inputs=[current_page, *filter_inputs],
                outputs=[current_page, gallery, page_label, current_paths, *detail_outputs]
            )
            
            last_btn.click(
                fn=last_page,
                inputs=filter_inputs,
                outputs=[current_page, gallery, page_label, current_paths, *detail_outputs]
            )
            
            # Auto-refresh on sort change
            sort_dropdown.change(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            order_dropdown.change(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            
            # Auto-refresh on filter change
            filter_rating.change(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            filter_label.change(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            filter_keyword.submit(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            
            # Advanced Filter Events
            f_min_gen.release(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            f_min_aes.release(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            

            f_min_tech.release(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            f_date_start.submit(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            f_date_end.submit(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            

            
            # Selection -> Details
            # Update: added delete_btn to outputs
            # State for tracking the currently selected index in the main gallery
            current_selection_index = gr.State(None)

            # Wrapper for display details to also return form values
            def process_details_display(evt, raw_paths, forced_index=None):
                 # display_details now returns fix_btn updated too (used for all 3 buttons for now)
                 try:
                     res, gen, weight, models, raw, del_upd, fix_upd, rerun_score_upd, rerun_tags_upd = display_details(evt, raw_paths, forced_index)
                 except Exception as e:
                     # Return empty values on error
                     res, gen, weight, models, raw, del_upd, fix_upd, rerun_score_upd, rerun_tags_upd = "", {}, {}, {}, {}, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
                 
                 # Extract form data from 'raw' (details dict)
                 t = raw.get('title', '')
                 d = raw.get('description', '')
                 # Convert keywords to HighlightedText format
                 k = keywords_to_highlighted(raw.get('keywords', ''))
                 r = str(raw.get('rating', 0))
                 l = raw.get('label', 'None')
                 if not l: l = "None"
                 
                 # Reset delete/fix status
                 del_status_upd = gr.update(value="", visible=False)
                 fix_status_upd = gr.update(value="", visible=False)
                 
                 # Extract file path for RAW preview
                 selected_file_path = ""
                 
                 # Safe index extraction
                 index = None
                 if forced_index is not None:
                     index = forced_index
                 elif evt is not None:
                     # Check if evt is a SelectData object (has .index attribute that's an int)
                     if hasattr(evt, 'index') and not callable(getattr(evt, 'index', None)):
                         # It's a SelectData object with .index attribute
                         index = evt.index
                     elif isinstance(evt, dict) and 'index' in evt:
                         index = evt['index']
                     elif isinstance(evt, (list, tuple)) and len(evt) > 0:
                         # FIX: If evt is a list (gallery value), this shouldn't happen, but handle it
                         # This means Gradio passed the gallery value instead of SelectData
                         # We can't extract index from gallery value alone
                         index = None
                 
                 
                 # Ensure index is an integer before comparison
                 if index is not None and isinstance(index, int) and raw_paths and index < len(raw_paths):
                     selected_file_path = raw_paths[index]
                 
                 # Get culling status for this image
                 culling_html = '<div style="display: none;"></div>'  # Hidden by default
                 if selected_file_path:
                     culling_status = db.get_image_culling_status(selected_file_path)
                     if culling_status and culling_status.get('decision'):
                         decision = culling_status['decision']
                         if decision == 'pick':
                             culling_html = '''
                             <div style="background: linear-gradient(135deg, #10b981, #059669); color: white; 
                                         padding: 8px 16px; border-radius: 8px; text-align: center; 
                                         font-weight: 600; font-size: 14px; margin: 8px 0;">
                                 ✅ Accepted
                             </div>'''
                         elif decision == 'reject':
                             culling_html = '''
                             <div style="background: linear-gradient(135deg, #ef4444, #dc2626); color: white; 
                                         padding: 8px 16px; border-radius: 8px; text-align: center; 
                                         font-weight: 600; font-size: 14px; margin: 8px 0;">
                                 ❌ Rejected
                             </div>'''
                         elif decision == 'maybe':
                             culling_html = '''
                             <div style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; 
                                         padding: 8px 16px; border-radius: 8px; text-align: center; 
                                         font-weight: 600; font-size: 14px; margin: 8px 0;">
                                 ❓ Maybe
                             </div>'''
                 
                 # Return index as well so it can be saved to current_selection_index
                 return res, gen, weight, models, raw, del_upd, t, d, k, r, l, del_status_upd, selected_file_path, culling_html, fix_upd, fix_status_upd, rerun_score_upd, rerun_tags_upd, index
            
            # Handler for Gallery Select
            # FIX: If raw_paths is empty, query DB to get paths for current page
            def on_gallery_select(evt: gr.SelectData, raw_paths=None):
                # Debug logging to help diagnose event handling
                print(f"Event Type: {type(evt)}")
                print(f"Event Data: {evt.__dict__ if hasattr(evt, '__dict__') else evt}")
                
                # Handle case where raw_paths might be None or empty
                if raw_paths is None or (isinstance(raw_paths, list) and len(raw_paths) == 0):
                    # FALLBACK: If current_paths State is empty, query DB to get paths for current page
                    # This is a workaround for the State not being updated by .load()
                    try:
                        # Get current page from state (we'll need to pass it or get it from config)
                        # For now, query first page with default sort
                        default_sort = app_config.get('ui', {}).get('default_sort', 'score_general')
                        default_order = app_config.get('ui', {}).get('default_order', 'desc')
                        rows = db.get_images_paginated(
                            page=1, page_size=PAGE_SIZE, sort_by=default_sort, order=default_order,
                            rating_filter=None, label_filter=None, keyword_filter=None,
                            min_score_general=0.0, min_score_aesthetic=0.0, min_score_technical=0.0,
                            date_range=None, folder_path=None
                        )
                        raw_paths = [row['file_path'] for row in rows]
                    except Exception as e:
                        raw_paths = []
                
                # Pass the SelectData event directly - it contains the index
                result = process_details_display(evt, raw_paths, None)
                return result

            # Handler for Manual Refresh (No event)
            def on_manual_refresh(raw_paths, forced_index):
                return process_details_display(None, raw_paths, forced_index)

            # Gallery select event - evt is SelectData, raw_paths comes from current_paths state
            # Note: process_details_display now returns index as the last value
            # FIX: Pass gallery value as input to allow fallback DB query if current_paths is empty
            gallery.select(
                fn=on_gallery_select, 
                inputs=[current_paths], # Only pass current_paths, not gallery (evt is SelectData event)
                outputs=[gr.Textbox(visible=False), d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label, delete_status, gallery_selected_path, d_culling_status, fix_btn, fix_status, rerun_score_btn, rerun_tags_btn, current_selection_index]
            )
            
            # Fix Action
            fix_btn.click(
                fn=fix_image_wrapper,
                inputs=[image_details],
                outputs=[fix_btn, fix_status]
            ).success(fn=on_manual_refresh, inputs=[current_paths, current_selection_index], outputs=None)
            
            # Re-Run Scoring Action
            rerun_score_btn.click(
                fn=rerun_scoring_wrapper,
                inputs=[image_details],
                outputs=[rerun_score_btn, fix_status]
            ).success(fn=on_manual_refresh, inputs=[current_paths, current_selection_index], outputs=None)
            
            # Re-Run Tags Action
            rerun_tags_btn.click(
                fn=rerun_keywords_wrapper,
                inputs=[image_details],
                outputs=[rerun_tags_btn, fix_status]
            ).success(fn=on_manual_refresh, inputs=[current_paths, current_selection_index], outputs=None)
            
            # Save Action
            save_btn.click(
                fn=save_metadata_action,
                inputs=[image_details, d_title, d_desc, d_keywords, d_rating, d_label],
                outputs=[save_status, save_status] # Update label and visibility
            )
            
            # Delete Action
            delete_btn.click(
                fn=delete_nef,
                inputs=[image_details],
                outputs=[delete_status, delete_btn]
            )
            
            # Export template functions
            def load_export_templates():
                """Returns list of template names for dropdown."""
                templates = config.get_export_templates()
                return list(templates.keys()) if templates else []
            
            def save_export_template_handler(template_name, export_format, cols_basic, cols_scores, 
                                            cols_metadata, cols_other, filter_rating, filter_label,
                                            filter_keyword, filter_folder, filter_min_gen, filter_min_aes,
                                            filter_min_tech, filter_date_start, filter_date_end):
                """Save current export settings as a template."""
                if not template_name or not template_name.strip():
                    return gr.update(value="❌ Template name is required", visible=True), gr.update()
                
                template_config = {
                    'format': export_format,
                    'columns_basic': cols_basic or [],
                    'columns_scores': cols_scores or [],
                    'columns_metadata': cols_metadata or [],
                    'columns_other': cols_other or [],
                    'filter_rating': filter_rating or [],
                    'filter_label': filter_label or [],
                    'filter_keyword': filter_keyword or '',
                    'filter_folder': filter_folder or '',
                    'filter_min_gen': float(filter_min_gen) if filter_min_gen else 0.0,
                    'filter_min_aes': float(filter_min_aes) if filter_min_aes else 0.0,
                    'filter_min_tech': float(filter_min_tech) if filter_min_tech else 0.0,
                    'filter_date_start': filter_date_start or '',
                    'filter_date_end': filter_date_end or ''
                }
                
                success = config.save_export_template(template_name.strip(), template_config)
                if success:
                    return gr.update(value=f"✅ Template '{template_name}' saved successfully", visible=True), gr.update(choices=load_export_templates())
                else:
                    return gr.update(value="❌ Failed to save template", visible=True), gr.update()
            
            def load_export_template_handler(template_name):
                """Load a template and return all export settings."""
                if not template_name:
                    return (
                        export_format, export_cols_basic, export_cols_scores, export_cols_metadata,
                        export_cols_other, export_filter_rating, export_filter_label,
                        export_filter_keyword, export_filter_folder, export_filter_min_gen,
                        export_filter_min_aes, export_filter_min_tech, export_filter_date_start,
                        export_filter_date_end, export_template_state, export_template_delete_btn,
                        gr.update(value="", visible=False)
                    )
                
                template = config.get_export_template(template_name)
                if not template:
                    return (
                        export_format, export_cols_basic, export_cols_scores, export_cols_metadata,
                        export_cols_other, export_filter_rating, export_filter_label,
                        export_filter_keyword, export_filter_folder, export_filter_min_gen,
                        export_filter_min_aes, export_filter_min_tech, export_filter_date_start,
                        export_filter_date_end, export_template_state, export_template_delete_btn,
                        gr.update(value=f"❌ Template '{template_name}' not found", visible=True)
                    )
                
                # Return template values
                return (
                    template.get('format', 'csv'),
                    template.get('columns_basic', []),
                    template.get('columns_scores', []),
                    template.get('columns_metadata', []),
                    template.get('columns_other', []),
                    template.get('filter_rating', []),
                    template.get('filter_label', []),
                    template.get('filter_keyword', ''),
                    template.get('filter_folder', ''),
                    template.get('filter_min_gen', 0.0),
                    template.get('filter_min_aes', 0.0),
                    template.get('filter_min_tech', 0.0),
                    template.get('filter_date_start', ''),
                    template.get('filter_date_end', ''),
                    template_name,  # Update state
                    gr.update(visible=True),  # Show delete button
                    gr.update(value=f"✅ Template '{template_name}' loaded", visible=True)
                )
            
            def delete_export_template_handler(template_name):
                """Delete an export template."""
                if not template_name:
                    return gr.update(choices=load_export_templates()), gr.update(value="❌ No template selected", visible=True), gr.update(visible=False), None
                
                success = config.delete_export_template(template_name)
                if success:
                    new_choices = load_export_templates()
                    return (
                        gr.update(choices=new_choices, value=None),
                        gr.update(value=f"✅ Template '{template_name}' deleted", visible=True),
                        gr.update(visible=False),
                        None  # Clear state
                    )
                else:
                    return gr.update(), gr.update(value="❌ Failed to delete template", visible=True), gr.update(), export_template_state
            
            # Template management events
            # Template management events - DISABLED (Feature removed)
            # export_template_save_btn.click(
            #     fn=save_export_template_handler,
            #     inputs=[
            #         export_template_name, export_format, export_cols_basic, export_cols_scores,
            #         export_cols_metadata, export_cols_other, export_filter_rating, export_filter_label,
            #         export_filter_keyword, export_filter_folder, export_filter_min_gen,
            #         export_filter_min_aes, export_filter_min_tech, export_filter_date_start, export_filter_date_end
            #     ],
            #     outputs=[export_template_status, export_template_dropdown]
            # )
            
            # export_template_load_btn.click(
            #     fn=load_export_template_handler,
            #     inputs=[export_template_dropdown],
            #     outputs=[
            #         export_format, export_cols_basic, export_cols_scores, export_cols_metadata,
            #         export_cols_other, export_filter_rating, export_filter_label,
            #         export_filter_keyword, export_filter_folder, export_filter_min_gen,
            #         export_filter_min_aes, export_filter_min_tech, export_filter_date_start,
            #         export_filter_date_end, export_template_state, export_template_delete_btn,
            #         export_template_status
            #     ]
            # )
            
            # export_template_delete_btn.click(
            #     fn=delete_export_template_handler,
            #     inputs=[export_template_state],
            #     outputs=[export_template_dropdown, export_template_status, export_template_delete_btn, export_template_state]
            # )
            
            # Export Action
            export_btn.click(
                fn=export_database,
                inputs=[
                    export_format,
                    export_cols_basic, export_cols_scores, export_cols_metadata, export_cols_other,
                    export_filter_rating, export_filter_label, export_filter_keyword, export_filter_folder,
                    export_filter_min_gen, export_filter_min_aes, export_filter_min_tech,
                    export_filter_date_start, export_filter_date_end
                ],
                outputs=[export_status]
            )


        # TAB: FOLDER TREE
        with gr.TabItem("Folder Tree", id="folder_tree"):
            # Row 1: Action Bar
            with gr.Row():
                t_refresh_btn = gr.Button("🔄 Refresh", size="sm", scale=0, min_width=100)
                t_open_gallery_btn = gr.Button("📸 Open in Gallery", variant="primary", size="sm", scale=1)
                t_open_stacks_btn = gr.Button("📚 Open in Stacks", variant="secondary", size="sm", scale=1)
                t_open_keywords_btn = gr.Button("🏷️ Open in Keywords", variant="secondary", size="sm", scale=1)
            
            # Row 2: Main Content - Tree | Gallery (equal width)
            with gr.Row(equal_height=True):
                # Left: Tree View
                with gr.Column(scale=1):
                    t_tree_view = gr.HTML(
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



        # TAB 4: CLUSTERS

        with gr.TabItem("Stacks", id="stacks"):
            # Row 1: Controls split into two columns
            with gr.Row():
                # Left column: Input controls
                with gr.Column(scale=1, min_width=300):
                    c_input_dir = gr.Textbox(
                        label="Input Folder Path", 
                        placeholder="D:\\Photos\\... (Leave empty for all)",
                        value=app_config.get('stacks_input_path', '')
                    )
                    # Hidden state components - values from Configurations tab
                    c_threshold = gr.State(value=app_config.get('clustering', {}).get('default_threshold', 0.15))
                    c_gap = gr.State(value=app_config.get('clustering', {}).get('default_time_gap', 120))
                    with gr.Row():
                        c_force_rescan = gr.Checkbox(
                            label="Force Rescan",
                            value=app_config.get('clustering', {}).get('force_rescan_default', False),
                            scale=1
                        )
                        c_run_btn = gr.Button("▶ Group", variant="primary", scale=1)
                        c_refresh_btn = gr.Button("🔄", variant="secondary", scale=0, min_width=50)
                
                # Right column: Sort controls + Console output
                with gr.Column(scale=1, min_width=300):
                    with gr.Row():
                        c_sort = gr.Dropdown(
                            choices=["created_at", "score_general", "score_technical", "score_aesthetic"], 
                            value="score_general", 
                            label="Sort By",
                            scale=2
                        )
                        c_order = gr.Dropdown(choices=["desc", "asc"], value="desc", label="Order", scale=1)
                    with gr.Accordion("📋 Console Output", open=False):
                        c_log = gr.Textbox(label="", lines=6, interactive=False, show_copy_button=True)
            
            # Divider
            gr.Markdown("---")
            
            # Row 2: Stacks Gallery (full width)
            gr.Markdown("### 📚 Stacks Gallery")
            stack_gallery = gr.Gallery(
                label="Stacks", 
                columns=8, 
                height=180,
                object_fit="cover",
                allow_preview=False,
                show_share_button=False
            )
            stack_ids_state = gr.State([])

            # Row 3: Stack Contents (full width)
            gr.Markdown("### 🖼️ Stack Contents")
            c_all_gallery = gr.Gallery(
                label="Stack Images", 
                columns=6, 
                height=400,
                object_fit="cover",
                allow_preview=True,
                show_share_button=False
            )
            
            # State for tracking content and selection
            stack_content_paths = gr.State([])  # Paths for selection tracking
            current_stack_id = gr.State(None)   # Currently selected stack
            
            # Stack Management Buttons
            with gr.Row():
                c_create_stack_btn = gr.Button("📚 Group Selected", variant="primary", size="sm", scale=1, elem_id="stack-group-btn")
                c_open_gallery_btn = gr.Button("📖 Open in Gallery", variant="secondary", size="sm", scale=1, elem_id="stack-open-gallery-btn")
                c_remove_btn = gr.Button("➖ Remove from Stack", variant="secondary", size="sm", scale=1, elem_id="stack-remove-btn")
                c_set_cover_btn = gr.Button("🖼️ Set as Cover", variant="secondary", size="sm", scale=1, elem_id="stack-cover-btn")
                c_dissolve_btn = gr.Button("🔓 Ungroup All", variant="stop", size="sm", scale=1, elem_id="stack-ungroup-btn")
            
            c_stack_status = gr.Textbox(label="Status", interactive=False, visible=True, lines=1)
            
            # In-Browser RAW Preview for Stacks - DISABLED: Feature not working
            # with gr.Accordion("🎞️ In-Browser RAW Preview", open=False):
            #     gr.Markdown("**Client-side NEF preview** - Select an image, then click Extract to view.")
            #     with gr.Row():
            #         stacks_selected_path = gr.Textbox(label="Selected Image", interactive=False, scale=3)
            #         stacks_preview_btn = gr.Button("🖼️ Extract Preview", variant="secondary", size="sm", elem_id="stacks-raw-preview-btn", scale=1)
            #     stacks_preview_status = gr.HTML(value='<div id="stacks-raw-preview-status" style="color: #8b949e; font-size: 0.9em;">Select an image from Stack Contents above</div>')
            #     stacks_preview_canvas = gr.HTML(value='<canvas id="stacks-raw-preview-canvas" style="max-width: 100%; border-radius: 8px; display: none;"></canvas>')
            #
            # # Handle content gallery selection to update selected path for RAW preview
            # def update_stacks_selected_path(evt: gr.SelectData, paths):
            #     if evt is None or not paths or evt.index >= len(paths):
            #         return ""
            #     return paths[evt.index]
            #
            # c_all_gallery.select(
            #     fn=update_stacks_selected_path,
            #     inputs=[stack_content_paths],
            #     outputs=[stacks_selected_path]
            # )
            
            # Events
            c_run_btn.click(
                fn=run_clustering_wrapper,
                inputs=[c_input_dir, c_threshold, c_gap, c_force_rescan],
                outputs=[c_log, c_run_btn]
            ).then( 
                fn=refresh_stacks_wrapper,
                inputs=[c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state]
            )
            
            c_refresh_btn.click(
                fn=refresh_stacks_wrapper,
                inputs=[c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state]
            )
            
            # Auto-refresh on sort change
            c_sort.change(
                fn=refresh_stacks_wrapper,
                inputs=[c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state]
            )
            c_order.change(
                fn=refresh_stacks_wrapper,
                inputs=[c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state]
            )
            
            # State for tracking selected indices in content gallery (must be defined before event wiring)
            selected_indices_state = gr.State([])
            
            # Content gallery selection handler for tracking selected indices (toggle behavior)
            def get_selected_indices(evt: gr.SelectData, current_indices):
                """Accumulates selections via toggle. Click to add/remove from selection."""
                if evt is None:
                    return current_indices or []
                idx = evt.index
                current = current_indices or []
                # Toggle behavior: click to add, click again to remove
                if idx in current:
                    return [i for i in current if i != idx]  # Deselect
                return current + [idx]  # Add to selection
            
            # Stack selection - returns gallery, paths, stack_id, and clears selection
            stack_gallery.select(
                fn=select_stack,
                inputs=[stack_ids_state, c_sort, c_order],
                outputs=[c_all_gallery, stack_content_paths, current_stack_id]
            ).then(
                fn=lambda: [],  # Clear selection when switching stacks
                inputs=[],
                outputs=[selected_indices_state]
            )
            
            c_all_gallery.select(
                fn=get_selected_indices,
                inputs=[selected_indices_state],
                outputs=[selected_indices_state]
            )
            
            # Manual Stack Creation from selection
            c_create_stack_btn.click(
                fn=create_stack_from_selection,
                inputs=[selected_indices_state, stack_content_paths, c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state, c_all_gallery, stack_content_paths, c_stack_status]
            )
            
            # Remove from Stack
            c_remove_btn.click(
                fn=remove_from_stack_handler,
                inputs=[selected_indices_state, stack_content_paths, current_stack_id, c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state, c_all_gallery, stack_content_paths, current_stack_id, c_stack_status]
            )
            
            # Dissolve Stack (Ungroup All)
            c_dissolve_btn.click(
                fn=dissolve_stack_handler,
                inputs=[current_stack_id, c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state, c_all_gallery, stack_content_paths, current_stack_id, c_stack_status]
            )
            
            # Set Cover Image
            c_set_cover_btn.click(
                fn=set_cover_image_handler,
                inputs=[selected_indices_state, stack_content_paths, current_stack_id, c_input_dir, c_sort, c_order],
                outputs=[stack_gallery, stack_ids_state, c_stack_status]
            )
            
            # Open Stack in Gallery
            c_open_gallery_btn.click(
                fn=open_stack_in_gallery,
                inputs=[current_stack_id, c_sort, c_order],
                outputs=[main_tabs, current_folder_state, folder_context_group, folder_display, current_page, gallery, page_label, current_paths, *detail_outputs]
            )

        # TAB: CULLING (AI-Automated)
        with gr.TabItem("Culling", id="culling"):
            gr.Markdown("### ✂️ AI Culling - Pick/Reject Best Shots")
            gr.Markdown("*Import a folder, let AI group similar shots, and mark top 38% as Picked (rest as Rejected). Export Pick/Reject flags to XMP for Lightroom.*")
            
            # Row 1: Controls
            with gr.Row():
                with gr.Column(scale=1, min_width=350):
                    with gr.Group():
                        cull_input_dir = gr.Textbox(
                            label="📁 Folder to Cull",
                            placeholder="D:\\Photos\\...",
                            value=app_config.get('culling_input_path', ''),
                            info="Select folder with scored images"
                        )
                        
                        # Hidden state components - values from Configurations tab
                        cull_threshold = gr.State(value=app_config.get('culling', {}).get('default_threshold', 0.15))
                        cull_time_gap = gr.State(value=app_config.get('culling', {}).get('default_time_gap', 120))
                        
                        cull_auto_export = gr.Checkbox(
                            label="📤 Auto-export to XMP after culling",
                            value=app_config.get('culling', {}).get('auto_export_default', False),
                            info="Write Pick/Reject flags to XMP for Lightroom"
                        )
                        
                        cull_force_rescan = gr.Checkbox(
                            label="Rescan/Regroup (Destructive)",
                            value=False,
                            info="⚠️ If checked, WILL DESTROY existing stacks and re-group all images. Leave unchecked to preserve manual stacks."
                        )
                    
                    cull_run_btn = gr.Button("▶️ Run AI Culling", variant="primary", size="lg")
                
                with gr.Column(scale=2):
                    # Results display
                    cull_status = gr.Textbox(
                        label="Results",
                        lines=6,
                        interactive=False,
                        placeholder="Click 'Run AI Culling' to start..."
                    )
            
            # Divider
            gr.Markdown("---")
            
            # Row 2: Picks Gallery
            gr.Markdown("### ✅ AI Picks (Top 38% of Each Group)")
            cull_picks_gallery = gr.Gallery(
                label="Picked Images",
                columns=6,
                height=400,
                object_fit="cover",
                allow_preview=True,
                show_share_button=False
            )
            
            # State for tracking culling picks paths
            cull_picks_paths = gr.State([])
            
            # In-Browser RAW Preview for Culling - DISABLED: Feature not working
            # with gr.Accordion("🎞️ In-Browser RAW Preview", open=False):
            #     gr.Markdown("**Client-side NEF preview** - Select a picked image, then click Extract to view.")
            #     with gr.Row():
            #         cull_selected_path = gr.Textbox(label="Selected Image", interactive=False, scale=3)
            #         cull_preview_btn = gr.Button("🖼️ Extract Preview", variant="secondary", size="sm", elem_id="cull-raw-preview-btn", scale=1)
            #     cull_preview_status = gr.HTML(value='<div id="cull-raw-preview-status" style="color: #8b949e; font-size: 0.9em;">Select an image from AI Picks above</div>')
            #     cull_preview_canvas = gr.HTML(value='<canvas id="cull-raw-preview-canvas" style="max-width: 100%; border-radius: 8px; display: none;"></canvas>')
            
            # Session management (refresh groups after manual stack changes)
            with gr.Accordion("🔄 Session Management", open=False):
                gr.Markdown("""
                **Resume Previous Session**: Load a previous culling session to review or continue working.
                
                **Refresh Groups**: If you've manually modified stacks in the Stacks tab, use this to re-import 
                the updated stack assignments into the current culling session.
                
                **Re-Pick Best**: Re-run the auto-pick logic to update picks based on current scores.
                """)
                with gr.Row():
                    cull_session_id = gr.State(None)
                    cull_resume_dropdown = gr.Dropdown(
                        label="Resume Session",
                        choices=get_active_sessions(),
                        value=None,
                        interactive=True,
                        scale=2,
                        info="Select a previous session to resume"
                    )
                    cull_resume_btn = gr.Button("▶️ Resume Session", variant="primary", size="sm", scale=1)
                with gr.Row():
                    cull_refresh_btn = gr.Button("🔄 Refresh Groups", variant="secondary", size="sm", scale=1)
                    cull_repick_btn = gr.Button("🎯 Re-Pick Best", variant="secondary", size="sm", scale=1)
                cull_session_status = gr.Textbox(label="Session Status", interactive=False, lines=3)
            
            # Export controls (for manual export if not auto)
            with gr.Accordion("💾 Manual XMP Export", open=False):
                gr.Markdown("Export Pick/Reject flags to XMP sidecar files for Lightroom. Uses `xmpDM:pick` (1=Picked, -1=Rejected).")
                with gr.Row():
                    cull_export_btn = gr.Button("📤 Export Pick/Reject Flags to XMP", variant="secondary")
                cull_export_status = gr.Textbox(label="Export Status", interactive=False)
            
            # Divider
            gr.Markdown("---")
            
            # Row 3: Rejected Gallery
            gr.Markdown("### ❌ Rejected Images (62%)")
            cull_rejects_gallery = gr.Gallery(
                label="Rejected Images",
                columns=6,
                height=300,
                object_fit="cover",
                allow_preview=True,
                show_share_button=False
            )
            
            # State for tracking rejects paths
            cull_rejects_paths = gr.State([])
            
            # Delete rejected files
            with gr.Accordion("🗑️ Delete Rejected Files", open=False):
                gr.Markdown("⚠️ **WARNING**: This will permanently delete rejected image files from disk. This cannot be undone!")
                with gr.Row():
                    cull_delete_confirm = gr.Checkbox(
                        label="I confirm I want to permanently delete these files",
                        value=False
                    )
                    cull_delete_btn = gr.Button("🗑️ Delete All Rejected", variant="stop", size="sm")
                cull_delete_status = gr.Textbox(label="Delete Status", interactive=False)
            
            # Events
            # Handle culling picks gallery selection for RAW preview
            def update_cull_selected_path(evt: gr.SelectData, paths):
                if evt is None or not paths or evt.index >= len(paths):
                    return ""
                return paths[evt.index]
            
            # cull_picks_gallery.select(
            #     fn=update_cull_selected_path,
            #     inputs=[cull_picks_paths],
            #     outputs=[cull_selected_path]
            # )
            
            cull_run_btn.click(
                fn=run_culling_wrapper,
                inputs=[cull_input_dir, cull_threshold, cull_time_gap, cull_auto_export, cull_force_rescan],
                outputs=[cull_status, cull_run_btn, cull_picks_gallery, cull_session_id, cull_picks_paths, cull_rejects_gallery, cull_rejects_paths]
            )
            
            # Session resume: Load existing session
            cull_resume_btn.click(
                fn=resume_culling_session,
                inputs=[cull_resume_dropdown],
                outputs=[cull_status, cull_picks_gallery, cull_session_id, cull_picks_paths, cull_rejects_gallery, cull_rejects_paths]
            )
            
            cull_export_btn.click(
                fn=export_culling_xmp,
                inputs=[cull_session_id],
                outputs=[cull_export_status]
            )
            
            # Delete rejected files event
            cull_delete_btn.click(
                fn=delete_rejected_files,
                inputs=[cull_session_id, cull_delete_confirm],
                outputs=[cull_delete_status, cull_rejects_gallery, cull_rejects_paths]
            )
            
            # Session management: Refresh groups after manual stack changes
            cull_refresh_btn.click(
                fn=refresh_culling_groups,
                inputs=[cull_session_id, cull_threshold, cull_time_gap],
                outputs=[cull_session_status, cull_picks_gallery, cull_picks_paths]
            )
            
            # Session management: Re-pick best images in groups
            cull_repick_btn.click(
                fn=repick_culling_best,
                inputs=[cull_session_id],
                outputs=[cull_session_status, cull_picks_gallery, cull_picks_paths]
            )

        # TAB: SETTINGS - HIDDEN (weights are now hard-coded and stable)
        # Hard-coded model weights (do not modify - stable values for consistency):
        # paq2piq: 0.25, liqe: 0.25, ava: 0.20, koniq: 0.20, spaq: 0.10, vila: 0.00

        # TAB: CONFIGURATIONS
        with gr.TabItem("Configurations", id="configurations"):
            gr.Markdown("### ⚙️ Experimental & Advanced Configuration")
            gr.Markdown("*Configure experimental options and advanced settings. Changes are saved to config.json.*")
            
            # Load current config values with defaults
            scoring_config = app_config.get('scoring', {})
            processing_config = app_config.get('processing', {})
            clustering_config = app_config.get('clustering', {})
            culling_config = app_config.get('culling', {})
            ui_config = app_config.get('ui', {})
            tagging_config = app_config.get('tagging', {})
            
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
                                ("📊 SPAQ", "score_spaq"),
                                ("🏆 AVA", "score_ava"),
                                ("📈 KonIQ", "score_koniq"),
                                ("📉 PaQ2PiQ", "score_paq2piq"),
                                ("🎯 LIQE", "score_liqe")
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

    # Folder Tree Events (Moved here to ensure all referenced components like c_input_dir are defined)
    t_refresh_btn.click(
        fn=refresh_tree_wrapper,
        inputs=[],
        outputs=[t_tree_view, t_status]
    )

    t_open_gallery_btn.click(
        fn=open_folder_in_gallery,
        inputs=[t_selected_path, *filter_inputs[:-1]],
        outputs=[main_tabs, current_folder_state, folder_context_group, folder_display, current_page, gallery, page_label, current_paths, *detail_outputs]
    )

    t_open_stacks_btn.click(
        fn=open_folder_in_stacks,
        inputs=[t_selected_path],
        outputs=[main_tabs, c_input_dir]
    )
    
    t_open_keywords_btn.click(
        fn=open_folder_in_keywords,
        inputs=[t_selected_path],
        outputs=[main_tabs, k_input_dir]
    )

    
    t_selected_path.change(
        fn=update_tree_gallery,
        inputs=[t_selected_path],
        outputs=[t_gallery, t_status]
    )
    
    # Load tree initially
    demo.load(
        fn=ui_tree.get_tree_html,
        inputs=[],
        outputs=[t_tree_view]
    )
    
    # Load gallery initially with first page of images
    def load_initial_gallery():
        """Load the first page of images when the app starts."""
        
        # Get default filter values from config or use defaults
        default_sort = app_config.get('ui', {}).get('default_sort', 'score_general')
        default_order = app_config.get('ui', {}).get('default_order', 'desc')
        
        
        # Call update_gallery with default values and return page number first (like first_page does)
        # This ensures correct mapping: (current_page, gallery, page_label, current_paths, ...)
        result = (1, *update_gallery(
            page=1,
            sort_by=default_sort,
            sort_order=default_order,
            rating_filter=None,
            label_filter=None,
            keyword_filter=None,
            min_gen=0.0,
            min_aes=0.0,
            min_tech=0.0,
            start_date=None,
            end_date=None,
            folder=None
        ))
        
        
        return result
    
    # Note: detail_outputs is defined in the Gallery tab, so we reference components directly
    # The outputs must match update_gallery return: images, label, paths, then detail_outputs
    # IMPORTANT: We need to ensure current_paths State is updated, so we use a wrapper that explicitly extracts and returns it
    def load_initial_gallery_with_paths():
        result = load_initial_gallery()
        # Extract raw_paths (4th element: page, images, label, paths, ...)
        if result and len(result) >= 4:
            raw_paths = result[3]
        return result
    
    demo.load(
        fn=load_initial_gallery_with_paths,
        inputs=[],
        outputs=[current_page, gallery, page_label, current_paths, d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label, d_culling_status, fix_btn, fix_status, rerun_score_btn, rerun_tags_btn]
    )
    
            # Load active culling sessions for resume dropdown
    demo.load(
        fn=get_active_sessions,
        inputs=[],
        outputs=[cull_resume_dropdown]
    )
    
    # Load export templates on page load - DISABLED: Feature hidden from UI
    # def load_export_templates_for_dropdown():
    #     templates = config.get_export_templates()
    #     return list(templates.keys()) if templates else []
    # 
    # demo.load(
    #     fn=load_export_templates_for_dropdown,
    #     inputs=[],
    #     outputs=[export_template_dropdown]
    # )

    # Monitor Loop
    status_timer.tick(
        fn=monitor_status,
        inputs=[],
        outputs=[log_output, s_status_html, run_btn, stop_btn, fix_btn, k_log_output, k_status_html, k_run_btn, k_stop_btn]
    )


if __name__ == "__main__":
    allowed_paths = [os.path.abspath("."), os.path.abspath("thumbnails")]
    allowed_paths.append("D:/") 
    allowed_paths.append("/mnt/") 
    
    # Start MCP server in background if enabled
    if MCP_AVAILABLE and MCP_ENABLED:
        print("Starting MCP debugging server in background...")
        mcp_server.start_mcp_server_background()
    elif MCP_ENABLED and not MCP_AVAILABLE:
        print("Warning: MCP server requested but 'mcp' package not installed. Run: pip install mcp")
    
    # Add server-side RAW preview endpoint for optimized in-browser preview
    @demo.app.get("/api/raw-preview")
    async def raw_preview_endpoint(path: str):
        """
        Server-side endpoint to extract embedded JPEG preview from RAW files.
        Returns JPEG blob directly (~2-5MB vs 20-60MB NEF), much faster than client-side extraction.
        
        Args:
            path: File path (URL encoded, Windows or WSL format)
        
        Returns:
            JPEG image bytes with appropriate content-type header
        """
        import urllib.parse
        from fastapi.responses import Response
        from fastapi import HTTPException
        
        try:
            # Decode URL-encoded path
            file_path = urllib.parse.unquote(path)
            
            # Convert WSL path to Windows if needed (for file access)
            if IS_WINDOWS and file_path.startswith("/mnt/"):
                file_path = utils.convert_path_to_local(file_path)
            elif not IS_WINDOWS and ":" in file_path and file_path[1] == ":":
                # Windows path on Linux/WSL - convert to WSL format
                file_path = utils.convert_path_to_wsl(file_path)
            
            # Validate file exists
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
            
            # Check if RAW file
            ext = Path(file_path).suffix.lower()
            if ext not in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']:
                raise HTTPException(status_code=400, detail=f"Not a supported RAW format: {ext}")
            
            # Extract embedded JPEG using optimized method
            img = thumbnails.extract_embedded_jpeg(file_path, min_size=1000)
            
            if img is None:
                raise HTTPException(status_code=500, detail="Failed to extract embedded JPEG preview")
            
            # Convert PIL Image to JPEG bytes
            import io
            jpeg_bytes = io.BytesIO()
            img.save(jpeg_bytes, format='JPEG', quality=90)
            jpeg_bytes.seek(0)
            
            # Return JPEG response
            return Response(
                content=jpeg_bytes.read(),
                media_type="image/jpeg",
                headers={
                    "Content-Disposition": f"inline; filename=preview.jpg",
                    "Cache-Control": "public, max-age=3600"  # Cache for 1 hour
                }
            )
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error extracting preview: {str(e)}")
    
    demo.queue().launch(inbrowser=False, allowed_paths=allowed_paths)
