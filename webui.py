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
    job_id = db.create_job(input_path)
    db.update_job_status(job_id, "running")
    
    log_buffer = ""
    
    try:
        # Run the generator
        for line in runner.run_batch(input_path, job_id, skip_existing):
            log_buffer += line + "\n"
            yield log_buffer, "Running..."
        
        # Finished
        db.update_job_status(job_id, "completed", log_buffer)
        yield log_buffer, "Done"
        
    except Exception as e:
        log_buffer += f"\nError: {str(e)}"
        db.update_job_status(job_id, "failed", log_buffer)
        yield log_buffer, "Failed"

# Pagination State
PAGE_SIZE = 50

def get_gallery_data(page, sort_by, sort_order):
    """Fetch images for gallery with pagination."""
    rows = db.get_images_paginated(page, PAGE_SIZE, sort_by, sort_order)
    total_count = db.get_image_count()
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

def update_gallery(page, sort_by, sort_order):
    images, label, _, raw_paths = get_gallery_data(page, sort_by, sort_order)
    return images, label, raw_paths, {}

def next_page(page, sort_by, sort_order):
    _, _, total_pages, _ = get_gallery_data(page, sort_by, sort_order)
    new_page = min(page + 1, total_pages)
    return new_page, *update_gallery(new_page, sort_by, sort_order)

def prev_page(page, sort_by, sort_order):
    new_page = max(page - 1, 1)
    return new_page, *update_gallery(new_page, sort_by, sort_order)

def first_page(sort_by, sort_order):
     return 1, *update_gallery(1, sort_by, sort_order)

def display_details(evt: gr.SelectData, raw_paths):
    if evt is None:
        return {}
    index = evt.index
    if index is None or not raw_paths or index >= len(raw_paths):
        return {}
    
    file_path = raw_paths[index]
    details = db.get_image_details(file_path)
    
    # Parse scores_json for better display
    if 'scores_json' in details and isinstance(details['scores_json'], str):
        try:
            details['scores_json'] = json.loads(details['scores_json'])
        except:
            pass
            
    return details

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
with gr.Blocks(title="Image Scoring WebUI") as demo:
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
                        stop_btn = gr.Button("Stop Scoring", variant="stop")
                
                with gr.Column(scale=2):
                    status_label = gr.Label(value="Ready", label="Status")
                    log_output = gr.Textbox(label="Console Output", lines=20, interactive=False)
            
            run_btn.click(
                fn=run_scoring_wrapper,
                inputs=[input_dir, skip_checkbox],
                outputs=[log_output, status_label]
            )
            
            stop_btn.click(
                fn=lambda: runner.stop(),
                inputs=[],
                outputs=[]
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
            
            with gr.Row():
                prev_btn = gr.Button("Previous")
                page_label = gr.Button(value="Page 1", interactive=False)
                next_btn = gr.Button("Next")
            
            gallery = gr.Gallery(label="Scored Images", columns=5, height="auto", allow_preview=True)
            
            with gr.Row():
                image_details = gr.JSON(label="Image Details")

            # Events
            
            # Helper to link outputs
            gallery_outputs = [gallery, page_label, current_paths, image_details]
            
            refresh_btn.click(
                fn=first_page,
                inputs=[sort_dropdown, order_dropdown],
                outputs=[current_page, *gallery_outputs]
            )
            
            prev_btn.click(
                fn=prev_page,
                inputs=[current_page, sort_dropdown, order_dropdown],
                outputs=[current_page, *gallery_outputs]
            )
            
            next_btn.click(
                fn=next_page,
                inputs=[current_page, sort_dropdown, order_dropdown],
                outputs=[current_page, *gallery_outputs]
            )
            
            # Auto-refresh on sort change
            sort_dropdown.change(first_page, [sort_dropdown, order_dropdown], [current_page, *gallery_outputs])
            order_dropdown.change(first_page, [sort_dropdown, order_dropdown], [current_page, *gallery_outputs])
            
            # Selection -> Details
            gallery.select(fn=display_details, inputs=[current_paths], outputs=[image_details])
            


if __name__ == "__main__":
    allowed_paths = [os.path.abspath("."), os.path.abspath("thumbnails")]
    allowed_paths.append("D:/") 
    allowed_paths.append("/mnt/") 
    
    demo.queue().launch(inbrowser=True, allowed_paths=allowed_paths)
