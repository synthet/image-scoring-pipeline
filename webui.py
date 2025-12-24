import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging (1=INFO, 2=WARN, 3=ERROR)

import gradio as gr
import threading
import time
import math
import json
import platform
from modules import scoring, db, tagging, config, clustering, thumbnails, ui_tree, utils

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

# Pagination State
PAGE_SIZE = 50

def get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    """Fetch images for gallery with pagination."""
    date_range = (start_date, end_date) if (start_date or end_date) else None
    
    rows = db.get_images_paginated(
        page, PAGE_SIZE, sort_by, sort_order, 
        rating_filter, label_filter, keyword_filter, 
        min_score_general=min_gen, 
        min_score_aesthetic=min_aes, 
        min_score_technical=min_tech, 
        date_range=date_range,
        folder_path=folder
    )
    total_count = db.get_image_count(
        rating_filter, label_filter, keyword_filter,
        min_score_general=min_gen, 
        min_score_aesthetic=min_aes, 
        min_score_technical=min_tech, 
        date_range=date_range,
        folder_path=folder
    )
    total_pages = math.ceil(total_count / PAGE_SIZE) if total_count > 0 else 1
    
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
            
        # Ensure absolute path for Gradio
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
        results.append((image_path, label))
        
    return results, f"Page {page} of {total_pages}", total_pages, raw_paths

def update_gallery(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    images, label, _, raw_paths = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    # Return: images, label, raw_paths, *details_cleared*
    # Details cleared must match detail_outputs list:
    # d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label
    return images, label, raw_paths, {}, {}, {}, {}, gr.update(visible=False), "", "", [], "0", "None"

def next_page(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    _, _, total_pages, _ = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    new_page = min(page + 1, total_pages)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)

def prev_page(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    new_page = max(page - 1, 1)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)

def first_page(sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
     return 1, *update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)

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

def display_details(evt: gr.SelectData, raw_paths):
    print(f"DEBUG: display_details called. Index: {evt.index if evt else 'None'}, Paths Len: {len(raw_paths) if raw_paths else 0}")
    if evt is None:
        return "", {}, {}, {}, {}, gr.update(visible=False)
    index = evt.index
    if index is None or not raw_paths or index >= len(raw_paths):
        print("DEBUG: Index out of bounds or no paths.")
        return "", {}, {}, {}, {}, gr.update(visible=False)
    
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
    
    # 4. Model Scores
    models_label = {
        "SPAQ": details.get('score_spaq', 0),
        "AVA": details.get('score_ava', 0),
        "KonIQ": details.get('score_koniq', 0),
        "PaQ2PiQ": details.get('score_paq2piq', 0),
        "LIQE": details.get('score_liqe', 0)
    }
    
    return res_info, gen_label, weighted_label, models_label, details, gr.update(visible=show_delete)

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
    if evt is None or not stack_ids_state:
        return [] # Return single list for gallery
        
    index = evt.index
    if index >= len(stack_ids_state):
        return []
        
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
    for row in images:
        p = row['file_path']
        if not p:
            continue
        
        # OPTIMIZATION: Use thumbnail if available, skip existence checks
        # Trust DB paths - they were validated when stored
        thumb = row['thumbnail_path']  # sqlite3.Row uses bracket notation, not .get()
        if thumb:
            p = utils.convert_path_to_local(thumb)
        else:
            p = utils.convert_path_to_local(p)
            
        s = row['score_general']
        label = f"Gen: {s:.2f}" if s is not None else "Gen: N/A"
        gallery_imgs.append((p, label))

    return gallery_imgs


def view_full_res_action(details):
    """
    Generates and returns the full resolution preview for the selected image.
    """
    if not details or not isinstance(details, dict):
         return None, gr.update(visible=False)
         
    file_path = details.get('file_path')
    if not file_path:
         return None, gr.update(visible=False)
         
    try:
        # returns path to preview
        preview_path = thumbnails.generate_preview(file_path)
        if preview_path and os.path.exists(preview_path):
             return preview_path, gr.update(visible=True)
        else:
             return None, gr.update(visible=False)
    except Exception as e:
        print(f"Error getting preview: {e}")
        return None, gr.update(visible=False)

def open_modal_view(details):
    """Opens the custom full-screen modal."""
    path, _ = view_full_res_action(details)
    if path:
        return gr.update(visible=True), path
    return gr.update(visible=False), None

def close_modal_view():
    """Closes the custom full-screen modal."""
    return gr.update(visible=False), None


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

# Tree View Start Script + Gallery Close Button
tree_js = """
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

/* ========== HEADER ========== */
h1 {
    font-size: 1.75rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.5px !important;
    color: var(--text-primary) !important;
    margin-bottom: 1rem !important;
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
}

.accordion > .label-wrap {
    background: var(--bg-tertiary) !important;
    padding: 14px 20px !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid var(--border-color) !important;
}

/* ========== PAGINATION ========== */
.pagination-container {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    padding: 16px !important;
}

.page-btn {
    min-width: 100px !important;
    padding: 10px 20px !important;
}

.page-indicator {
    background: var(--bg-tertiary) !important;
    padding: 10px 24px !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
    border: 1px solid var(--border-color) !important;
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
"""

with gr.Blocks(title="Image Scoring WebUI") as demo:
    gr.Markdown("# Image Scoring WebUI")
    
    # State
    current_page = gr.State(value=1)
    current_paths = gr.State(value=[])
    current_folder_state = gr.State(value=None)
    
    # Polling Timer for status updates
    status_timer = gr.Timer(value=1.0)
    
    # Custom Full Screen Modal
    with gr.Group(visible=False, elem_classes=["full-res-modal"]) as full_res_modal:
        modal_close_btn = gr.Button("❌ Close", variant="secondary", elem_classes=["modal-close-btn"])
        modal_image = gr.Image(show_label=False, interactive=False, type="filepath", elem_classes=["modal-image-container"])
        
        modal_close_btn.click(
            fn=close_modal_view,
            inputs=[],
            outputs=[full_res_modal, modal_image]
        )
    
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
                            value=False,
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
                        k_custom = gr.Textbox(
                            label="✨ Custom Keywords", 
                            placeholder="vintage, cinematic, rainy...",
                            info="Additional keywords to detect (comma separated)"
                        )
                    
                    with gr.Row():
                        k_overwrite = gr.Checkbox(label="🔄 Overwrite existing", value=False)
                        k_captions = gr.Checkbox(label="📝 Generate captions", value=False)
                    
                    with gr.Row():
                        k_run_btn = gr.Button("▶️ Generate Keywords", variant="primary", size="lg")
                        k_stop_btn = gr.Button("⏹️ Stop", variant="stop", interactive=False, size="lg")
                
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
                            value="score_general", 
                            label="Sort By",
                            container=False
                        )
                        order_dropdown = gr.Dropdown(
                            choices=[("↓ Highest First", "desc"), ("↑ Lowest First", "asc")], 
                            value="desc", 
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
                    f_min_gen = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min General", info="0.0 - 1.0")
                    f_min_aes = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Aesthetic", info="0.0 - 1.0")
                    f_min_tech = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Technical", info="0.0 - 1.0")
                
                with gr.Row():
                    f_date_start = gr.Textbox(label="From Date", placeholder="YYYY-MM-DD", scale=1)
                    f_date_end = gr.Textbox(label="To Date", placeholder="YYYY-MM-DD", scale=1)
                    filter_keyword = gr.Textbox(label="Keyword Search", placeholder="Search tags...", scale=2)

            # Pagination
            with gr.Row(elem_classes=["pagination-container"]):
                prev_btn = gr.Button("← Previous", size="sm", elem_classes=["page-btn"])
                page_label = gr.Button(value="Page 1 of 1", interactive=False, elem_classes=["page-indicator"])
                next_btn = gr.Button("Next →", size="sm", elem_classes=["page-btn"])
            
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
                    
                    # Metadata Editor
                    with gr.Accordion("✏️ Edit Metadata", open=True):
                        d_title = gr.Textbox(label="Title", placeholder="Enter title...", lines=1)
                        d_desc = gr.Textbox(label="Description", placeholder="Enter description...", lines=2)
                        d_keywords = gr.HighlightedText(
                            label="Keywords",
                            combine_adjacent=False,
                            show_legend=False,
                            interactive=True,
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
                        view_full_btn = gr.Button("🔍 View Full Resolution", variant="secondary", size="sm")
                        delete_btn = gr.Button("🗑️ Delete NEF File", variant="stop", visible=False, size="sm")
                        delete_status = gr.Textbox(label="Status", interactive=False, visible=False)
                    
                    # Raw Data (hidden by default)
                    with gr.Accordion("📋 Raw JSON Data", open=False):
                        image_details = gr.JSON(label="Full Details")
                    
                    full_res_image = gr.Image(label="Preview", visible=False, interactive=False, type="filepath")

            # Events
            
            # Events
            
            # Helper to link outputs
            gallery_outputs = [gallery, page_label, current_paths, image_details] # Note: image_details is still needed for pagination update if we want to clear it, but typically pagination just updates gallery. We might wanna clear details on page change? Let's leave as is for now, it's fine.
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
            detail_outputs = [d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label]
            
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
            
            # Full Res View Event
            view_full_btn.click(
                fn=open_modal_view,
                inputs=[image_details],
                outputs=[full_res_modal, modal_image]
            )
            f_min_tech.release(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            f_date_start.submit(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            f_date_end.submit(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            

            
            # Selection -> Details
            # Update: added delete_btn to outputs
            # Wrapper for display details to also return form values
            def display_details_wrapper(evt: gr.SelectData, raw_paths):
                 res, gen, weight, models, raw, del_upd = display_details(evt, raw_paths)
                 
                 # Extract form data from 'raw' (details dict)
                 t = raw.get('title', '')
                 d = raw.get('description', '')
                 # Convert keywords to HighlightedText format
                 k = keywords_to_highlighted(raw.get('keywords', ''))
                 r = str(raw.get('rating', 0))
                 l = raw.get('label', 'None')
                 if not l: l = "None"
                 
                 # Reset delete status
                 del_status_upd = gr.update(value="", visible=False)
                 
                 return res, gen, weight, models, raw, del_upd, t, d, k, r, l, del_status_upd
            
            gallery.select(
                fn=display_details_wrapper, 
                inputs=[current_paths], 
                outputs=[gr.Textbox(visible=False), d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label, delete_status]
            )
            
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


        # TAB: FOLDER TREE
        with gr.TabItem("Folder Tree", id="folder_tree"):
            with gr.Row():
                with gr.Column(scale=1):
                    t_refresh_btn = gr.Button("Refresh Tree Structure")
                    with gr.Row():
                        t_open_gallery_btn = gr.Button("Open in Gallery", variant="primary")
                        t_open_stacks_btn = gr.Button("Open in Stacks", variant="secondary")
                        t_open_keywords_btn = gr.Button("Open in Keywords", variant="secondary")
                    
                    # Tree View Replacement
                    t_tree_view = gr.HTML(label="Folder Tree Structure")
                    t_selected_path = gr.Textbox(elem_id="folder_tree_selection", label="Selected Folder", interactive=True)
                    
                    t_status = gr.Label(label="Status")
                
                with gr.Column(scale=3):
                    t_gallery = gr.Gallery(label="Folder Images", columns=6, height="auto", allow_preview=True)
            
            # Events



        # TAB 4: CLUSTERS

        with gr.TabItem("Stacks", id="stacks"):
            with gr.Row():
                with gr.Column(scale=1):
                    c_input_dir = gr.Textbox(
                        label="Input Folder Path", 
                        placeholder="D:\\Photos\\... (Leave empty for all)",
                        value=app_config.get('stacks_input_path', '')
                    )
                    c_threshold = gr.Slider(0.01, 1.0, value=0.15, label="Similarity Threshold")
                    c_gap = gr.Number(value=120, label="Time Split Gap (seconds)")
                    c_force_rescan = gr.Checkbox(label="Force Rescan", value=False)
                    
                    c_run_btn = gr.Button("Group into Stacks", variant="primary")
                    
                    gr.Markdown("---")
                    c_sort = gr.Dropdown(
                        choices=["created_at", "score_general", "score_technical", "score_aesthetic"], 
                        value="score_general", 
                        label="Sort Stacks By"
                    )
                    c_order = gr.Dropdown(choices=["desc", "asc"], value="desc", label="Order")
                    c_refresh_btn = gr.Button("Refresh Stacks", variant="secondary")
                    
                    with gr.Row():
                         c_open_gallery_btn = gr.Button("Open Folder in Gallery")
                         c_open_tree_btn = gr.Button("Open in Tree View")

                    # REQUEST: Remove Status, add Console Output
                    # c_status = gr.Label(label="Status") 
                    c_log = gr.Textbox(label="Console Output", lines=10, interactive=False)
                
                with gr.Column(scale=3):
                    # Stack Browser
                    gr.Markdown("### Stacks Gallery")
                    stack_gallery = gr.Gallery(label="Stacks", columns=5, height="auto", allow_preview=False)
                    stack_ids_state = gr.State([])

            gr.Markdown("---")
            
            # Stack Content Area
            gr.Markdown("### Stack Contents")
            c_all_gallery = gr.Gallery(label="Stack Images", columns=6, allow_preview=True)
            
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
            
            stack_gallery.select(
                fn=select_stack,
                inputs=[stack_ids_state, c_sort, c_order],
                outputs=[c_all_gallery]
            )
            
            c_open_gallery_btn.click(
                fn=open_stack_folder_in_gallery,
                inputs=[c_input_dir, *filter_inputs[:-1]],
                outputs=[main_tabs, current_folder_state, folder_context_group, folder_display, current_page, gallery, page_label, current_paths, *detail_outputs]
            )
            
            c_open_tree_btn.click(
                fn=open_stack_folder_in_tree,
                inputs=[c_input_dir],
                outputs=[main_tabs, t_selected_path, t_tree_view]
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
    
    demo.queue().launch(inbrowser=False, allowed_paths=allowed_paths, css=custom_css, head=tree_js)
