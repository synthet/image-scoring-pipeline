import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging (1=INFO, 2=WARN, 3=ERROR)

import gradio as gr
import threading
import time
import math
import os
import json
from modules import scoring, db, tagging, config

# Initialize DB on load
# Initialize DB on load
db.init_db()

# Load Config
app_config = config.load_config()

runner = scoring.ScoringRunner()
tagging_runner = tagging.TaggingRunner()


def run_scoring_wrapper(input_path, force_rescore):
    """
    Wrapper to run scoring and update UI.
    """
    skip_existing = not force_rescore
    
    # Save Config
    config.save_config_value('scoring_input_path', input_path)
    
    # Disable Run/Fix, Enable Stop
    yield "", "Starting...", gr.update(interactive=False), gr.update(interactive=True), gr.update(interactive=False)
    
    job_id = db.create_job(input_path)
    db.update_job_status(job_id, "running")
    
    log_buffer = ""
    
    try:
        # Run the generator
        for line in runner.run_batch(input_path, job_id, skip_existing):
            log_buffer += line + "\n"
            yield log_buffer, "Running...", gr.update(interactive=False), gr.update(interactive=True), gr.update(interactive=False)
        
        # Finished
        db.update_job_status(job_id, "completed", log_buffer)
        yield log_buffer, "Done", gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=True)
        
    except Exception as e:
        log_buffer += f"\nError: {str(e)}"
        db.update_job_status(job_id, "failed", log_buffer)
        yield log_buffer, "Failed", gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=True)

def run_fix_db_wrapper():
    """
    Wrapper to run DB fix
    """
    # Disable Run/Fix, Enable Stop
    yield "", "Starting...", gr.update(interactive=False), gr.update(interactive=True), gr.update(interactive=False)

    job_id = db.create_job("DB_FIX_OPERATION")
    db.update_job_status(job_id, "running")
    
    log_buffer = ""
    try:
        runner.current_processor = None # Ensure clean state
        for line in runner.fix_db(job_id):
            log_buffer += line + "\n"
            yield log_buffer, "Fixing...", gr.update(interactive=False), gr.update(interactive=True), gr.update(interactive=False)
            
        db.update_job_status(job_id, "completed", log_buffer)
        yield log_buffer, "Done", gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=True)
    except Exception as e:
        log_buffer += f"\nError: {str(e)}"
        db.update_job_status(job_id, "failed", log_buffer)
        yield log_buffer, "Failed", gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=True)

def run_tagging_wrapper(input_path, custom_keywords, overwrite, generate_captions):
    """
    Wrapper to run tagging.
    """
    yield "", "Starting Tagging...", gr.update(interactive=False), gr.update(interactive=True)
    
    # Save Config
    config.save_config_value('tagging_input_path', input_path)
    
    # Simple keyword parsing
    keywords_list = None
    if custom_keywords:
        keywords_list = [k.strip() for k in custom_keywords.split(",") if k.strip()]
        
    log_buffer = ""
    try:
        for line in tagging_runner.run_batch(input_path, keywords_list, overwrite, generate_captions):
            log_buffer += line + "\n"
            yield log_buffer, "Tagging...", gr.update(interactive=False), gr.update(interactive=True)
            
        yield log_buffer, "Done", gr.update(interactive=True), gr.update(interactive=False)
    except Exception as e:
        log_buffer += f"\nError: {str(e)}"
        yield log_buffer, "Failed", gr.update(interactive=True), gr.update(interactive=False)

# Pagination State
PAGE_SIZE = 50

def get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    """Fetch images for gallery with pagination."""
    date_range = (start_date, end_date) if (start_date or end_date) else None
    
    rows = db.get_images_paginated(
        page, PAGE_SIZE, sort_by, sort_order, 
        rating_filter, label_filter, keyword_filter, 
        min_score_general=min_gen, 
        min_score_aesthetic=min_aes, 
        min_score_technical=min_tech, 
        date_range=date_range
    )
    total_count = db.get_image_count(
        rating_filter, label_filter, keyword_filter,
        min_score_general=min_gen, 
        min_score_aesthetic=min_aes, 
        min_score_technical=min_tech, 
        date_range=date_range
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

def update_gallery(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    images, label, _, raw_paths = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date)
    # Return: images, label, raw_paths, *details_cleared*
    # Details cleared must match detail_outputs list:
    # d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label
    return images, label, raw_paths, {}, {}, {}, {}, gr.update(visible=False), "", "", "", "0", "None"

def next_page(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    _, _, total_pages, _ = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date)
    new_page = min(page + 1, total_pages)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date)

def prev_page(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    new_page = max(page - 1, 1)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date)

def first_page(sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
     return 1, *update_gallery(1, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date)

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
        return "No image selected", gr.update(visible=False)
    
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
            return f"Deleted: {', '.join(deleted_files)}", gr.update(visible=False)
        else:
            return f"NEF file not found: {nef_path}", gr.update(visible=False)
            
    except Exception as e:
        return f"Error deleting: {e}", gr.update(visible=True)

def export_filtered_images(export_path, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date):
    """
    Exports images matching current filters to `export_path`.
    """
    import shutil
    
    if not export_path or not export_path.strip():
        return "Error: Export path cannot be empty."
        
    if not os.path.exists(export_path):
        try:
            os.makedirs(export_path)
        except Exception as e:
            return f"Error creating directory: {e}"
            
    # Get paths
    date_range = (start_date, end_date) if (start_date or end_date) else None
    
    paths = db.get_filtered_paths(
        rating_filter, label_filter, keyword_filter, 
        min_score_general=min_gen, 
        min_score_aesthetic=min_aes, 
        min_score_technical=min_tech, 
        date_range=date_range
    )
    
    if not paths:
        return "No images match current filters."
        
    count = 0
    try:
        for src in paths:
             if not os.path.exists(src): continue
             
             name = os.path.basename(src)
             dst = os.path.join(export_path, name)
             
             # Avoid overwrite if same folder (which is silly but possible)
             if os.path.abspath(src) == os.path.abspath(dst):
                 continue
                 
             shutil.copy2(src, dst)
             count += 1
             
        return f"Successfully exported {count} images to {export_path}"
    except Exception as e:
        return f"Export partial/failed: {e}"

def export_all_db(export_path):
    """
    Exports full DB to JSON.
    """
    if not export_path or not export_path.strip():
        return "Error: Export path cannot be empty."
        
    if not os.path.exists(export_path):
        try:
            os.makedirs(export_path)
        except Exception as e:
            return f"Error creating directory: {e}"
            
    # Define filename
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"db_export_{timestamp}.json"
    full_path = os.path.join(export_path, filename)
    
    success, msg = db.export_db_to_json(full_path)
    return msg

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
/* Ensure grid thumbnails still look okay if needed, though scale-down is usually fine */
"""

with gr.Blocks(title="Image Scoring WebUI", css=custom_css) as demo:
    gr.Markdown("# Image Scoring WebUI")
    
    # State
    current_page = gr.State(value=1)
    current_paths = gr.State(value=[])
    
    with gr.Tabs():
        # TAB 1: RUN SCORING
        with gr.TabItem("Run Scoring"):
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
                
            with gr.Accordion("Export", open=False):
                with gr.Row():
                    export_dir = gr.Textbox(label="Export Path", placeholder="D:\\Photos\\BestOf...")
                    export_btn = gr.Button("Export Filtered Images")
                    export_db_btn = gr.Button("Export DB to JSON", variant="secondary")
                export_status = gr.Label(label="Export Status")
            
            with gr.Row():
                prev_btn = gr.Button("Previous")
                page_label = gr.Button(value="Page 1", interactive=False)
                next_btn = gr.Button("Next")
            
            gallery = gr.Gallery(label="Scored Images", columns=5, height="auto", allow_preview=True)
            
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
                    delete_status = gr.Textbox(label="Deletion Status", interactive=False, visible=True)

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
                f_min_gen, f_min_aes, f_min_tech, f_date_start, f_date_end
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
            f_min_tech.release(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            f_date_start.submit(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            f_date_end.submit(first_page, filter_inputs, [current_page, gallery, page_label, current_paths, *detail_outputs])
            
            # Export Action
            # Reuse filter_inputs but exclude sort/order which aren't needed for filtering, 
            # though get_filtered_paths doesn't take sort.
            # Inputs: export_dir, rating, label, keyword, min_gen, ... 
            # Slice filter_inputs[2:] to skip sort/order
            
            export_inputs = [export_dir] + filter_inputs[2:]
            
            export_btn.click(
                fn=export_filtered_images,
                inputs=export_inputs,
                outputs=[export_status]
            )
            
            export_db_btn.click(
                fn=export_all_db,
                inputs=[export_dir],
                outputs=[export_status]
            )
            
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
                 
                 return res, gen, weight, models, raw, del_upd, t, d, k, r, l
            
            gallery.select(
                fn=display_details_wrapper, 
                inputs=[current_paths], 
                outputs=[gr.Textbox(visible=False), d_score_gen, d_score_weighted, d_score_models, image_details, delete_btn, d_title, d_desc, d_keywords, d_rating, d_label]
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
            


if __name__ == "__main__":
    allowed_paths = [os.path.abspath("."), os.path.abspath("thumbnails")]
    allowed_paths.append("D:/") 
    allowed_paths.append("/mnt/") 
    
    demo.queue().launch(inbrowser=True, allowed_paths=allowed_paths)
