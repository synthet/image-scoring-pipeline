import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging (1=INFO, 2=WARN, 3=ERROR)

import gradio as gr
import threading
import time
import math
import os
import json
from modules import scoring, db, tagging, config, clustering, thumbnails, ui_tree

# Initialize DB on load
# Initialize DB on load
db.init_db()

# Load Config
app_config = config.load_config()

runner = scoring.ScoringRunner()
tagging_runner = tagging.TaggingRunner()
cluster_engine = clustering.ClusteringEngine()


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
    
    s_prog_html = ""
    if s_tot > 0:
        pct = (s_cur / s_tot) * 100
        s_prog_html = f"""
        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
            <span>Processing: {s_cur}/{s_tot}</span>
            <span>{pct:.1f}%</span>
        </div>
        <div style="width: 100%; background-color: #e0e0e0; border-radius: 4px; height: 20px;">
            <div style="width: {pct}%; background-color: #4caf50; height: 20px; border-radius: 4px; transition: width 0.5s;"></div>
        </div>
        """
    elif s_running:
         s_prog_html = "Scanning..."
    
    s_run_up = gr.update(interactive=not s_running)
    s_stop_up = gr.update(interactive=s_running)
    s_fix_up = gr.update(interactive=not s_running)
    
    # Tagging Status
    t_running, t_log, t_status_msg, t_cur, t_tot = tagging_runner.get_status()
    
    t_prog_html = ""
    if t_tot > 0:
        pct = (t_cur / t_tot) * 100
        t_prog_html = f"""
        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
            <span>Processing: {t_cur}/{t_tot}</span>
            <span>{pct:.1f}%</span>
        </div>
        <div style="width: 100%; background-color: #e0e0e0; border-radius: 4px; height: 20px;">
            <div style="width: {pct}%; background-color: #2196f3; height: 20px; border-radius: 4px; transition: width 0.5s;"></div>
        </div>
        """
    elif t_running:
        t_prog_html = "Scanning..."
    
    t_run_up = gr.update(interactive=not t_running)
    t_stop_up = gr.update(interactive=t_running)
    
    return [
        s_log, s_status_msg, s_run_up, s_stop_up, s_fix_up, s_prog_html,
        t_log, t_status_msg, t_run_up, t_stop_up, t_prog_html
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
    
    
    if folder and os.path.exists(folder):
        # Only fetch images from this specific folder (recursive? current requirement seems flat or specific folder from tree)
        # DB `get_images_by_folder` is flat. `get_images_paginated` now supports folder path.
        pass

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
        
        image_path = file_path
        if thumb_path and os.path.exists(thumb_path):
            image_path = thumb_path
            
        # Ensure absolute path for Gradio
        image_path = os.path.abspath(image_path)
        
        # Format path for display (showing parent directory)
        folder = os.path.dirname(file_path)
        
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
    return images, label, raw_paths, {}, {}, {}, {}, gr.update(visible=False), "", "", "", "0", "None"

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
    # Return (update_button_visibility), (current_folder_state=None), *update_gallery outputs
    
    # 1. Hide reset button
    # 2. Set state to None
    # 3. Refresh gallery
    
    gal_outs = update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, None)
    
    return gr.update(visible=False), None, 1, *gal_outs

def open_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    """Switches to gallery tab and filters by folder.
       Returns: 
       [Tabs, current_folder_state, reset_btn_update] + [page, gallery, label, paths, details...]
    """
    if not folder:
        # If no folder provided, treat as "Reset / View All"
        print("DEBUG: No folder provided, resetting filter.")
        gal_outs = update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None)
        return gr.Tabs(selected="Gallery"), None, gr.update(visible=False), 1, *gal_outs
        
    print(f"DEBUG: open_folder_in_gallery called with folder='{folder}'")
    
    # Switch to Gallery Tab
    # Update folder state
    # Show Reset Button
    # Refresh Gallery with new folder
    
    gal_outs = update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder)
    
    # Return:
    # 1. Tabs Update (switch to "Gallery")
    # 2. current_folder state (set to folder)
    # 3. reset_btn (visible=True, value=f"Reset Folder: {os.path.basename(folder)}")
    # 4. page (1)
    # 5. *gal_outs
    
    return gr.Tabs(selected="Gallery"), folder, gr.update(visible=True, value=f"Reset Folder ({os.path.basename(folder)})"), 1, *gal_outs

def open_folder_in_stacks(folder):
    """Switches to Stacks tab and sets input folder."""
    if not folder:
        return gr.Tabs(selected="Stacks"), gr.update()
    
    return gr.Tabs(selected="Stacks"), folder

def open_folder_in_keywords(folder):
    """Switches to Keywords tab and sets input folder."""
    if not folder:
        return gr.Tabs(selected="Keywords"), gr.update()
    
    return gr.Tabs(selected="Keywords"), folder

def open_stack_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    """Switches from Stacks to Gallery with folder filter."""
    return open_folder_in_gallery(folder, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date)

def open_stack_folder_in_tree(folder):
    """Switches from Stacks to Tree View and selects folder."""
    if not folder:
         return gr.Tabs(selected="Folder Tree"), gr.update(), gr.update()
         
    # We might need to refresh tree choices if the folder isn't there, but for now just try setting it.
    # The tree choices update happens on load or refresh click. 
    # If the folder exists in DB, it should be in the list if refreshed.
    
    html = ui_tree.get_tree_html(folder)
    return gr.Tabs(selected="Folder Tree"), folder, html

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



def save_metadata_action(details, title, desc, keywords, rating, label):
    """
    Saves metadata to DB and File.
    """
    if not details or not isinstance(details, dict):
         return "Error: No image selected.", gr.update(visible=True)
         
    file_path = details.get('file_path')
    if not file_path:
         return "Error: Invalid image record.", gr.update(visible=True)
         
    # Parse Keywords
    kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
    
    # 1. Update DB
    try:
        # Convert rating/label types if needed
        r_val = int(rating) if rating else 0
        l_val = label if label != "None" else ""
        
        success = db.update_image_metadata(file_path, keywords, title, desc, r_val, l_val)
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
        # Handle path
        p = row['best_image_path']
        label = f"{row['name']} ({row['image_count']} imgs)"
        if p and os.path.exists(p):
            results.append((p, label))
            stack_ids.append(row['id'])
            
    return results, stack_ids

def run_clustering_wrapper(input_path, threshold, gap, force, progress=gr.Progress()):
    log = ""
    try:
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
        
        # Ensure absolute path
        if cover and os.path.exists(cover):
            results.append((cover, label))
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
        s = row['score_general']
        l = f"Gen: {s:.2f}"
        gallery_imgs.append((p, l))
        

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
    
    rows = db.get_images_by_folder(folder)
    results = []
    for row in rows:
        p = row['file_path']
        label = row['file_name']
        results.append((p, label))
        

    return results, f"Found {len(results)} images in {os.path.basename(folder)}"

def refresh_tree_wrapper():
    msg = db.rebuild_folder_cache()
    return ui_tree.get_tree_html(), msg


# --- UI Definition ---

# Custom CSS to prevent upscaling of images in preview/gallery
custom_css = """
.preview img, .lightbox img, .modal img {
    object-fit: scale-down !important;
    width: auto !important;
    height: auto !important;
    max-width: 100% !important;
    max-height: 90vh !important;
    margin: auto;
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
}
.modal-close-btn {
    position: absolute !important;
    top: 20px !important;
    right: 30px !important;
    z-index: 10000 !important;
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
}
"""

with gr.Blocks(title="Image Scoring WebUI", css=custom_css) as demo:
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
        with gr.TabItem("Scoring"):
            with gr.Row():
                with gr.Column(scale=1):
                    input_dir = gr.Textbox(
                        label="Input Folder Path", 
                        placeholder="D:\\Photos\\...",
                        value=app_config.get('scoring_input_path', '')
                    )
                    force_checkbox = gr.Checkbox(label="Force Re-score (Overwrite existing)", value=False)
                    with gr.Row():
                        run_btn = gr.Button("Start Scoring", variant="primary")
                        stop_btn = gr.Button("Stop Scoring", variant="stop", interactive=False)
                    fix_btn = gr.Button("Fix DB (Re-run missing)", variant="secondary")
                
                with gr.Column(scale=2):
                    status_label = gr.Label(value="Ready", label="Status")
                    s_progress = gr.HTML(label="Progress")
                    log_output = gr.Textbox(label="Console Output", lines=20, interactive=False)
            
            run_btn.click(
                fn=run_scoring_wrapper,
                inputs=[input_dir, force_checkbox],
                outputs=[log_output, status_label, run_btn, stop_btn, fix_btn]
            )
            
            stop_btn.click(
                fn=lambda: runner.stop(),
                inputs=[],
                outputs=[]
            )
            
            fix_btn.click(
                fn=run_fix_db_wrapper,
                inputs=[],
                outputs=[log_output, status_label, run_btn, stop_btn, fix_btn]
            )

        # TAB 2: KEYWORDS
        with gr.TabItem("Keywords"):
            with gr.Row():
                with gr.Column(scale=1):
                    k_input_dir = gr.Textbox(
                        label="Input Folder Path", 
                        placeholder="D:\\Photos\\... (Leave empty to process all DB images matching folder)",
                        value=app_config.get('tagging_input_path', '')
                    )
                    k_custom = gr.Textbox(label="Custom Keywords (comma separated)", placeholder="e.g. vintage, cinematic, rainy")
                    with gr.Row():
                        k_overwrite = gr.Checkbox(label="Overwrite existing keywords", value=False)
                        k_captions = gr.Checkbox(label="Generate Title & Description (Attributes)", value=False)
                    with gr.Row():
                        k_run_btn = gr.Button("Generate Keywords", variant="primary")
                        k_stop_btn = gr.Button("Stop", variant="stop", interactive=False)
                
                with gr.Column(scale=2):
                    k_status_label = gr.Label(value="Ready", label="Status")
                    k_progress = gr.HTML(label="Progress")
                    k_log_output = gr.Textbox(label="Console Output", lines=20, interactive=False)
            
            k_run_btn.click(
                fn=run_tagging_wrapper,
                inputs=[k_input_dir, k_custom, k_overwrite, k_captions],
                outputs=[k_log_output, k_status_label, k_run_btn, k_stop_btn]
            )
            
            k_stop_btn.click(
                fn=lambda: tagging_runner.stop(),
                inputs=[],
                outputs=[]
            )

        # TAB 3: GALLERY
        with gr.TabItem("Gallery"):
            with gr.Row():
                refresh_btn = gr.Button("Refresh / First Page")
                reset_folder_btn = gr.Button("Reset Folder", visible=False, variant="secondary")
                sort_dropdown = gr.Dropdown(
                    choices=["created_at", "id", "score_general", "score_technical", "score_aesthetic", "score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe"], 
                    value="created_at", 
                    label="Sort By"
                )
                order_dropdown = gr.Dropdown(choices=["desc", "asc"], value="desc", label="Order")
            
            with gr.Accordion("Filters", open=False):
                with gr.Row():
                    filter_rating = gr.CheckboxGroup(
                        choices=["1", "2", "3", "4", "5"], 
                        label="Filter by Rating"
                    )
                    filter_label = gr.CheckboxGroup(
                        choices=["Red", "Yellow", "Green", "Blue", "Purple", "None"], 
                        label="Filter by Color Label"
                    )
                
                with gr.Group():
                    gr.Markdown("### Advanced Filters")
                    with gr.Row():
                        f_min_gen = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min General Score")
                        f_min_aes = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Aesthetic Score")
                        f_min_tech = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Technical Score")
                    with gr.Row():
                        f_date_start = gr.Textbox(label="Start Date (YYYY-MM-DD)", placeholder="2024-01-01")
                        f_date_end = gr.Textbox(label="End Date (YYYY-MM-DD)", placeholder="2025-12-31")
                        
                filter_keyword = gr.Textbox(label="Filter by Keyword", placeholder="Search tags...")
                

            
            with gr.Row():
                prev_btn = gr.Button("Previous")
                page_label = gr.Button(value="Page 1", interactive=False)
                next_btn = gr.Button("Next")
            
            gallery = gr.Gallery(label="Scored Images", columns=5, height="auto", allow_preview=False)
            
            with gr.Row():
                with gr.Column():
                    with gr.Group():
                        # selected_info = gr.Markdown("Select an image to view details.")
                        with gr.Row():
                             d_score_gen = gr.Label(label="General Score", num_top_classes=1)
                             d_score_weighted = gr.Label(label="Weighted Scores", num_top_classes=2)
                        d_score_models = gr.Label(label="Model Scores", num_top_classes=5)
                        
                    with gr.Group():
                        gr.Markdown("### Metadata Editor")
                        d_title = gr.Textbox(label="Title", interactive=True)
                        d_desc = gr.Textbox(label="Description", interactive=True)
                        d_keywords = gr.Textbox(label="Keywords (comma separated)", interactive=True)
                        with gr.Row():
                             d_rating = gr.Dropdown(choices=["0", "1", "2", "3", "4", "5"], label="Rating", interactive=True)
                             d_label = gr.Dropdown(choices=["None", "Red", "Yellow", "Green", "Blue", "Purple"], label="Color Label", interactive=True)
                        
                        save_btn = gr.Button("Save Metadata", variant="primary")
                        save_status = gr.Label(label="Save Status", visible=False)
                    
                    with gr.Accordion("Raw Data", open=False):
                        image_details = gr.JSON(label="Image Details")
                        
                    delete_btn = gr.Button("Delete Original NEF", variant="stop", visible=False)
                    delete_status = gr.Textbox(label="Deletion Status", interactive=False, visible=False)
                    
                    with gr.Row():
                        view_full_btn = gr.Button("View Full Resolution", variant="secondary")
                    
                    full_res_image = gr.Image(label="Full Resolution Preview", visible=False, interactive=False, type="filepath")

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
                outputs=[reset_folder_btn, current_folder_state, current_page, gallery, page_label, current_paths, *detail_outputs]
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
                 k = raw.get('keywords', '')
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
            ).then(
                fn=open_modal_view,
                inputs=[image_details],
                outputs=[full_res_modal, modal_image]
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
        with gr.TabItem("Folder Tree"):
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

        with gr.TabItem("Stacks"):
            with gr.Row():
                with gr.Column(scale=1):
                    c_input_dir = gr.Textbox(
                        label="Input Folder Path", 
                        placeholder="D:\\Photos\\... (Leave empty for all)",
                        value=""
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
                    c_refresh_btn = gr.Button("Refresh Stacks (View Only)", variant="secondary")
                    
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
                outputs=[main_tabs, current_folder_state, reset_folder_btn, current_page, gallery, page_label, current_paths, *detail_outputs]
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
        outputs=[main_tabs, current_folder_state, reset_folder_btn, current_page, gallery, page_label, current_paths, *detail_outputs]
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
        outputs=[log_output, status_label, run_btn, stop_btn, fix_btn, s_progress, k_log_output, k_status_label, k_run_btn, k_stop_btn, k_progress]
    )


if __name__ == "__main__":
    allowed_paths = [os.path.abspath("."), os.path.abspath("thumbnails")]
    allowed_paths.append("D:/") 
    allowed_paths.append("/mnt/") 
    
    demo.queue().launch(inbrowser=True, allowed_paths=allowed_paths)
