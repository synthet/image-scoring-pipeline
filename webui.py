import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logging (1=INFO, 2=WARN, 3=ERROR)

import gradio as gr
import threading
import time
import math
import os
import json
from modules import scoring, db

# Initialize DB on load
db.init_db()

runner = scoring.ScoringRunner()


def run_scoring_wrapper(input_path, skip_existing):
    """
    Wrapper to run scoring and update UI.
    """
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

# Pagination State
PAGE_SIZE = 50

def get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter):
    """Fetch images for gallery with pagination."""
    rows = db.get_images_paginated(page, PAGE_SIZE, sort_by, sort_order, rating_filter, label_filter)
    total_count = db.get_image_count(rating_filter, label_filter)
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

def update_gallery(page, sort_by, sort_order, rating_filter, label_filter):
    images, label, _, raw_paths = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter)
    return images, label, raw_paths, {}

def next_page(page, sort_by, sort_order, rating_filter, label_filter):
    _, _, total_pages, _ = get_gallery_data(page, sort_by, sort_order, rating_filter, label_filter)
    new_page = min(page + 1, total_pages)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter)

def prev_page(page, sort_by, sort_order, rating_filter, label_filter):
    new_page = max(page - 1, 1)
    return new_page, *update_gallery(new_page, sort_by, sort_order, rating_filter, label_filter)

def first_page(sort_by, sort_order, rating_filter, label_filter):
     return 1, *update_gallery(1, sort_by, sort_order, rating_filter, label_filter)

def display_details(evt: gr.SelectData, raw_paths):
    if evt is None:
        return {}, gr.update(visible=False)
    index = evt.index
    if index is None or not raw_paths or index >= len(raw_paths):
        return {}, gr.update(visible=False)
    
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

    return details, gr.update(visible=show_delete)

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
                    input_dir = gr.Textbox(label="Input Folder Path", placeholder="D:\\Photos\\...")
                    skip_checkbox = gr.Checkbox(label="Skip already scored images", value=True)
                    with gr.Row():
                        run_btn = gr.Button("Start Scoring", variant="primary")
                        stop_btn = gr.Button("Stop Scoring", variant="stop", interactive=False)
                    fix_btn = gr.Button("Fix DB (Re-run missing)", variant="secondary")
                
                with gr.Column(scale=2):
                    status_label = gr.Label(value="Ready", label="Status")
                    log_output = gr.Textbox(label="Console Output", lines=20, interactive=False)
            
            run_btn.click(
                fn=run_scoring_wrapper,
                inputs=[input_dir, skip_checkbox],
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

        # TAB 2: GALLERY
        with gr.TabItem("Gallery"):
            with gr.Row():
                refresh_btn = gr.Button("Refresh / First Page")
                sort_dropdown = gr.Dropdown(
                    choices=["created_at", "score_general", "score_technical", "score_aesthetic", "score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe"], 
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
            
            with gr.Row():
                prev_btn = gr.Button("Previous")
                page_label = gr.Button(value="Page 1", interactive=False)
                next_btn = gr.Button("Next")
            
            gallery = gr.Gallery(label="Scored Images", columns=5, height="auto", allow_preview=True)
            
            with gr.Row():
                with gr.Column():
                    image_details = gr.JSON(label="Image Details")
                    delete_btn = gr.Button("Delete Original NEF", variant="stop", visible=False)
                    delete_status = gr.Textbox(label="Deletion Status", interactive=False, visible=True)

            # Events
            
            # Events
            
            # Helper to link outputs
            gallery_outputs = [gallery, page_label, current_paths, image_details]
            filter_inputs = [sort_dropdown, order_dropdown, filter_rating, filter_label]
            
            refresh_btn.click(
                fn=first_page,
                inputs=filter_inputs,
                outputs=[current_page, *gallery_outputs]
            )
            
            prev_btn.click(
                fn=prev_page,
                inputs=[current_page, *filter_inputs],
                outputs=[current_page, *gallery_outputs]
            )
            
            next_btn.click(
                fn=next_page,
                inputs=[current_page, *filter_inputs],
                outputs=[current_page, *gallery_outputs]
            )
            
            # Auto-refresh on sort change
            sort_dropdown.change(first_page, filter_inputs, [current_page, *gallery_outputs])
            order_dropdown.change(first_page, filter_inputs, [current_page, *gallery_outputs])
            
            # Auto-refresh on filter change
            filter_rating.change(first_page, filter_inputs, [current_page, *gallery_outputs])
            filter_label.change(first_page, filter_inputs, [current_page, *gallery_outputs])
            
            # Selection -> Details
            # Update: added delete_btn to outputs
            gallery.select(fn=display_details, inputs=[current_paths], outputs=[image_details, delete_btn])
            
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
