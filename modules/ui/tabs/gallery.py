import gradio as gr
import os
import json
import datetime
import platform
from modules import db, config, utils
from modules.ui import common

IS_WINDOWS = (platform.system() == 'Windows')

# --- Helper Functions ---

def get_gallery_data(page, page_size, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
    """Fetch images for gallery with pagination."""
    date_range = (start_date, end_date) if (start_date or end_date) else None
    
    try:
        wsl_folder = utils.convert_path_to_wsl(folder) if folder else None
        
        rows = db.get_images_paginated(
            page, page_size, sort_by, sort_order, 
            rating_filter, label_filter, keyword_filter, 
            min_score_general=min_gen, 
            min_score_aesthetic=min_aes, 
            min_score_technical=min_tech, 
            date_range=date_range,
            folder_path=wsl_folder
        )
        
        total_count = db.get_image_count(
            rating_filter=rating_filter,
            label_filter=label_filter,
            keyword_filter=keyword_filter,
            min_score_general=min_gen, 
            min_score_aesthetic=min_aes, 
            min_score_technical=min_tech, 
            date_range=date_range,
            folder_path=wsl_folder
        )
        
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
        
        images = []
        raw_paths = []
        
        for row in rows:
            file_path = row['file_path']
            raw_paths.append(file_path)
            
            # Use thumbnail if available
            thumb_path = row['thumbnail_path']
            if thumb_path:
                p = utils.convert_path_to_local(thumb_path)
            else:
                p = utils.convert_path_to_local(file_path)
                
            # Create label with score
            score = row['score_general']
            score_str = f"{score:.2f}" if score is not None else "N/A"
            label = f"{row['file_name']}\nGen: {score_str}"
            
            images.append((p, label))
            
        page_label = f"Page {page} of {total_pages} ({total_count} images)"
        
        return images, page_label, total_pages, raw_paths
        
    except Exception as e:
        print(f"Error fetching gallery data: {e}")
        import traceback
        traceback.print_exc()
        return [], f"Error: {e}", 1, []

def export_database(export_format, cols_basic, cols_scores, cols_metadata, cols_other,
                    filter_rating, filter_label, filter_keyword, filter_folder,
                    filter_min_gen, filter_min_aes, filter_min_tech,
                    filter_date_start, filter_date_end):
    """
    Exports the database to the specified format with optional column selection and filtering.
    Returns status message.
    """
    
    # Combine selected columns
    selected_columns = []
    if cols_basic: selected_columns.extend(cols_basic)
    if cols_scores: selected_columns.extend(cols_scores)
    if cols_metadata: selected_columns.extend(cols_metadata)
    if cols_other: selected_columns.extend(cols_other)
    
    columns = selected_columns if selected_columns else None
    
    # Process filters
    rating_filter_processed = None
    if filter_rating:
        rating_filter_processed = [0 if r == "Unrated" else int(r) for r in filter_rating]
    
    keyword_filter_processed = filter_keyword.strip() if filter_keyword and filter_keyword.strip() else None
    folder_path = filter_folder.strip() if filter_folder and filter_folder.strip() else None
    
    date_range = None
    if filter_date_start or filter_date_end:
        date_range = (filter_date_start if filter_date_start else None,
                     filter_date_end if filter_date_end else None)
    
    # Generate output filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "output") # ../../../output from modules/ui/tabs/gallery.py? No, assume app root level logic.
    # webui.py used os.path.dirname(__file__), "output". 
    # Since we are deep in structure, we should just use absolute path or relative to CWD.
    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    success = False
    msg = ""
    
    if export_format == "json":
        output_path = os.path.join(output_dir, f"export_{timestamp}.json")
        success, msg = db.export_db_to_json(output_path)
    elif export_format == "csv":
        output_path = os.path.join(output_dir, f"export_{timestamp}.csv")
        success, msg = db.export_db_to_csv(
            output_path, columns=columns,
            rating_filter=rating_filter_processed, label_filter=filter_label,
            keyword_filter=keyword_filter_processed, folder_path=folder_path,
            min_score_general=filter_min_gen, min_score_aesthetic=filter_min_aes,
            min_score_technical=filter_min_tech, date_range=date_range
        )
    elif export_format == "xlsx":
        output_path = os.path.join(output_dir, f"export_{timestamp}.xlsx")
        success, msg = db.export_db_to_excel(
            output_path, columns=columns,
            rating_filter=rating_filter_processed, label_filter=filter_label,
            keyword_filter=keyword_filter_processed, folder_path=folder_path,
            min_score_general=filter_min_gen, min_score_aesthetic=filter_min_aes,
            min_score_technical=filter_min_tech, date_range=date_range
        )
    else:
        return gr.update(value=f"Unknown format: {export_format}", visible=True)
    
    if success:
        return gr.update(value=f"✅ {msg}", visible=True)
    else:
        return gr.update(value=f"❌ {msg}", visible=True)

# Helper Actions Wrappers - defined in common, but wrappers for click events here
def save_metadata_action(details, title, desc, keywords, rating, label, tagging_runner):
    if not details or not isinstance(details, dict):
         return "Error: No image selected.", gr.update(visible=True)
         
    file_path = details.get('file_path')
    if not file_path:
         return "Error: Invalid image record.", gr.update(visible=True)
         
    # Parse Keywords
    if isinstance(keywords, list):
        # HighlightedText returns list of (token, class)
        keywords_str = common.highlighted_to_keywords(keywords)
    else:
        keywords_str = keywords
        
    kw_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
    
    try:
        r_val = int(rating) if rating else 0
        l_val = label if label != "None" else ""
        
        success = db.update_image_metadata(file_path, keywords_str, title, desc, r_val, l_val)
        if not success:
             return "Failed to update database.", gr.update(visible=True)
             
        if tagging_runner.write_metadata(file_path, kw_list, title, desc, r_val, l_val):
            return f"Saved metadata for {os.path.basename(file_path)}", gr.update(visible=False)
        else:
             return "Saved to DB, but failed to write to file.", gr.update(visible=True)
             
    except Exception as e:
        return f"Error saving metadata: {e}", gr.update(visible=True)

def display_details(evt, raw_paths, forced_index=None):
    """Fetches and formats image details for the side panel."""
    index = None
    if forced_index is not None:
        index = forced_index
    elif evt is not None:
        if isinstance(evt, gr.SelectData):
            index = evt.index
        elif isinstance(evt, dict) and 'index' in evt:
            index = evt['index']
            
    if index is None or not raw_paths or not isinstance(index, int) or index >= len(raw_paths):
        # Return empty/invisible updates matching detail_outputs order
        return common.get_empty_details()
    
    file_path = raw_paths[index]
    details = db.get_image_details(file_path)
    if not details:
        return common.get_empty_details()

    # Parse scores_json safely
    scores_data = details.get('scores_json', {})
    if isinstance(scores_data, str):
        try: scores_data = json.loads(scores_data)
        except: scores_data = {}
    
    # Logic for Delete Button (NEF only + specific ratings/labels)
    show_delete = False
    is_nef = os.path.splitext(file_path)[1].lower() in ['.nef', '.nrw']
    if is_nef:
        nef_meta = scores_data.get('nef_metadata')
        if not nef_meta and 'summary' in scores_data:
            nef_meta = scores_data['summary'].get('nef_metadata')
        if not nef_meta and 'full_results' in scores_data:
             # Use safe get
             full_res = scores_data.get('full_results', {})
             summary = full_res.get('summary', {}) if isinstance(full_res, dict) else {}
             nef_meta = summary.get('nef_metadata') if isinstance(summary, dict) else None
        
        rating = int(nef_meta.get('rating', 0)) if nef_meta and isinstance(nef_meta, dict) else 0
        label = nef_meta.get('label', '') if nef_meta and isinstance(nef_meta, dict) else ""
        
        if (rating > 0 and rating <= 2) or label in ["Red", "Yellow"]:
            show_delete = True

    # Prepare Visual Outputs
    filename = details.get('file_name', os.path.basename(file_path))
    created = details.get('created_at', 'Unknown')
    res_info = f"**File:** `{filename}`\n\n**Date:** {created}"
    
    gen_score = details.get('score_general', 0)
    gen_label = {"General Score": gen_score}
    
    tech = details.get('score_technical', 0)
    aes = details.get('score_aesthetic', 0)
    weighted_label = {"Technical": tech, "Aesthetic": aes}
    
    models_label = {}
    perform_data = scores_data.get('summary', {}) if isinstance(scores_data, dict) else {}
    performance = perform_data.get('performance', {}) if isinstance(perform_data, dict) else {}
    model_times = performance.get('model_times', {}) if isinstance(performance, dict) else {}
    
    model_scores_map = {
        'spaq': ('SPAQ', details.get('score_spaq', 0)),
        'ava': ('AVA', details.get('score_ava', 0)),
        'koniq': ('KonIQ', details.get('score_koniq', 0)),
        'paq2piq': ('PaQ2PiQ', details.get('score_paq2piq', 0)),
        'liqe': ('LIQE', details.get('score_liqe', 0))
    }
    
    for model_key, (model_name, score) in model_scores_map.items():
        if score and score > 0:
            if model_key in model_times:
                models_label[f"{model_name} ({model_times[model_key]:.3f}s)"] = score
            else:
                models_label[model_name] = score

    # Metadata fields
    title = details.get('title', '')
    desc = details.get('description', '')
    keywords_str = details.get('keywords', '')
    keywords_highlighted = common.keywords_to_highlighted(keywords_str)
    rating_val = str(details.get('rating', 0))
    label_val = details.get('label', 'None') or 'None'
    
    # Culling Status HTML (Optional DB sidecar)
    try:
        culling_status = db.get_image_culling_status(file_path) if hasattr(db, 'get_image_culling_status') else None
    except:
        culling_status = None
        
    culling_html = '<div style="display: none;"></div>'
    if culling_status:
        color = "#3fb950" if culling_status == "pick" else "#f85149" if culling_status == "reject" else "#d29922"
        text = "Pick" if culling_status == "pick" else "Reject" if culling_status == "reject" else "Maybe"
        culling_html = f'<div style="margin-top: 10px; padding: 5px 10px; border-radius: 5px; background: {color}22; border: 1px solid {color}44; color: {color}; font-weight: bold; text-align: center;">AI Status: {text}</div>'

    # Fix button visibility logic
    local_p = utils.convert_path_to_local(file_path)
    show_fix = os.path.exists(local_p)

    return [
        res_info, gen_label, weighted_label, models_label, details,
        gr.update(visible=show_delete), title, desc, keywords_highlighted,
        rating_val, label_val, gr.update(visible=False), 
        file_path, culling_html, gr.update(visible=show_fix), 
        gr.update(visible=False), gr.update(visible=show_fix), gr.update(visible=show_fix), index
    ]

# --- Component Creation ---

def create_tab(shared_state, current_folder_state, runner, tagging_runner, app_config):
    PAGE_SIZE = app_config.get('ui', {}).get('gallery_page_size', 50)
    current_page, current_paths, image_details = shared_state
    
    # Internal wrappers that close over variables
    def update_gallery(page, sort_by, sort_order, rating_filter, label_filter, keyword_filter, min_gen, min_aes, min_tech, start_date, end_date, folder=None):
        images, label, total_pages, raw_paths = get_gallery_data(
            page, PAGE_SIZE, sort_by, sort_order, rating_filter, label_filter, keyword_filter, 
            min_gen, min_aes, min_tech, start_date, end_date, folder
        )
        
        # Details cleared must match detail_outputs list
        # We need a predictable list of default values for all detail outputs
        # List order: [res_info, gen_label, weighted_label, models_label, details_state, delete_btn, title, desc, keywords, rating, label, save_status, current_path, culling_html, fix_btn, fix_status, rerun_score_btn, rerun_tags_btn, selected_index]
        return [images, label, raw_paths] + common.get_empty_details()

    def next_page(page, *args):
        # args match filter_inputs below, minus folder_context_group?
        # args will be [sort_by, sort_order, ...]
        # We need to extract folder from args if present.
        # But filter_inputs includes folder_context_group which is just a Group. 
        # Actually in webui.py `current_folder_state` was passed.
        folder = args[-1]
        other_args = args[:-1]
        _, _, total, _ = get_gallery_data(page, PAGE_SIZE, *other_args, folder=folder)
        new = min(page + 1, total)
        return [new] + update_gallery(new, *other_args, folder=folder)

    def prev_page(page, *args):
        folder = args[-1]
        other_args = args[:-1]
        new = max(page - 1, 1)
        return [new] + update_gallery(new, *other_args, folder=folder)
    
    def first_page(*args):
        folder = args[-1]
        other_args = args[:-1]
        return [1] + update_gallery(1, *other_args, folder=folder)
    
    def last_page(*args):
        folder = args[-1]
        other_args = args[:-1]
        _, _, total, _ = get_gallery_data(1, PAGE_SIZE, *other_args, folder=folder)
        return [total] + update_gallery(total, *other_args, folder=folder)
        
    def reset_folder_filter(*args):
         # Returns: folder_context_group, folder_display, current_folder_state, page, *gallery_outputs
         folder = None 
         # args are filters but we reset folder to None
         gal_outs = update_gallery(1, *args, folder=None)
         return gr.update(visible=False), "", None, 1, *gal_outs

    def display_details_wrapper(evt, raw_paths):
        return display_details(evt, raw_paths)

    # Re-declare display_details locally or import? 
    # I already defined `display_details` at module level.
    
    with gr.TabItem("Gallery", id="gallery"):
        # Folder Context Bar
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
                        choices=[("📅 Date Added", "created_at"), ("🆔 ID", "id"), ("⭐ General Score", "score_general"), ("🔧 Technical Score", "score_technical"), ("🎨 Aesthetic Score", "score_aesthetic")], 
                        value=app_config.get('scoring', {}).get('default_sort_by', 'score_general'), 
                        label="Sort By", container=False)
                    order_dropdown = gr.Dropdown(
                        choices=[("↓ Highest First", "desc"), ("↑ Lowest First", "asc")], 
                        value=app_config.get('scoring', {}).get('default_sort_order', 'desc'), 
                        label="Order", container=False)

        # Filters Section
        with gr.Accordion("🔍 Filters & Search", open=False):
            with gr.Row():
                filter_rating = gr.CheckboxGroup(choices=["1", "2", "3", "4", "5"], label="Rating Filter")
                filter_label = gr.CheckboxGroup(choices=["Red", "Yellow", "Green", "Blue", "Purple", "None"], label="Color Label")
            with gr.Row():
                f_min_gen = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min General")
                f_min_aes = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Aesthetic")
                f_min_tech = gr.Slider(0.0, 1.0, value=0.0, step=0.05, label="Min Technical")
            with gr.Row():
                f_date_start = gr.Textbox(label="From Date", placeholder="YYYY-MM-DD", scale=1)
                f_date_end = gr.Textbox(label="To Date", placeholder="YYYY-MM-DD", scale=1)
                filter_keyword = gr.Textbox(label="Keyword Search", placeholder="Search tags...", scale=2)
        
        # Export Section
        with gr.Accordion("📤 Export Data", open=False, elem_classes=["accordion"]):
            with gr.Row():
                 export_format = gr.Dropdown(
                    choices=[("📄 JSON", "json"), ("📊 CSV", "csv"), ("📗 Excel", "xlsx")],
                    value=app_config.get('ui', {}).get('default_export_format', 'json'),
                    label="Export Format", scale=1)
                 export_btn = gr.Button("⬇️ Export All Images", variant="primary", size="sm", scale=1)
                 export_status = gr.Textbox(label="Status", visible=False) # Helper output
            
            with gr.Accordion("⚙️ Advanced Options", open=False):
                 available_columns = db.get_available_columns()
                 basic_cols = ['id', 'file_path', 'file_name', 'file_type', 'created_at']
                 score_cols = ['score_general', 'score_technical', 'score_aesthetic', 'score_spaq', 'score_ava', 'score_koniq', 'score_paq2piq', 'score_liqe']
                 metadata_cols = ['rating', 'label', 'keywords', 'title', 'description']
                 other_cols = [c for c in available_columns if c not in basic_cols + score_cols + metadata_cols]
                 
                 with gr.Row():
                     with gr.Column(scale=1): 
                         gr.Markdown("**Basic**")
                         export_cols_basic = gr.CheckboxGroup(choices=basic_cols, value=basic_cols, show_label=False)
                     with gr.Column(scale=1): 
                         gr.Markdown("**Scores**")
                         export_cols_scores = gr.CheckboxGroup(choices=score_cols, value=score_cols, show_label=False)
                     with gr.Column(scale=1): 
                         gr.Markdown("**Metadata**")
                         export_cols_metadata = gr.CheckboxGroup(choices=metadata_cols, value=metadata_cols, show_label=False)
                     with gr.Column(scale=1): 
                         gr.Markdown("**Other**")
                         export_cols_other = gr.CheckboxGroup(choices=other_cols, value=[], show_label=False)

        # Pagination
        with gr.Row(elem_classes=["pagination-container"]):
             first_btn = gr.Button("⏮", size="sm", elem_classes=["page-btn"], scale=0)
             prev_btn = gr.Button("◀", size="sm", elem_classes=["page-btn"], scale=0)
             page_label = gr.Button(value="Page 1 of 1", interactive=False, elem_classes=["page-indicator"], scale=1)
             next_btn = gr.Button("▶", size="sm", elem_classes=["page-btn"], scale=0)
             last_btn = gr.Button("⏭", size="sm", elem_classes=["page-btn"], scale=0)

        # Main Content
        with gr.Row():
            with gr.Column(scale=3):
                gallery = gr.Gallery(label="📸 Image Gallery", columns=5, height=600, object_fit="cover", allow_preview=True)
            
            with gr.Column(scale=1, min_width=320, elem_classes=["details-panel"]):
                res_info = gr.Markdown()
                d_score_gen = gr.Label(label="General", num_top_classes=1)
                d_score_weighted = gr.Label(label="Weighted")
                d_score_models = gr.Label(label="Models")
                d_culling_status = gr.HTML(value='<div style="display: none;"></div>')
                
                with gr.Accordion("✏️ Edit Metadata", open=False):
                    d_title = gr.Textbox(label="Title")
                    d_desc = gr.Textbox(label="Description")
                    d_keywords = gr.HighlightedText(label="Keywords", combine_adjacent=False)
                    with gr.Row():
                        d_rating = gr.Dropdown(choices=["0", "1", "2", "3", "4", "5"], label="Rating")
                        d_label = gr.Dropdown(choices=["None", "Red", "Yellow", "Green", "Blue", "Purple"], label="Label")
                    save_btn = gr.Button("💾 Save")
                    save_status = gr.Label(visible=False)

                with gr.Row():
                    fix_btn = gr.Button("🔧 Fix Data", variant="secondary", size="sm", visible=False)
                    rerun_score_btn = gr.Button("🔄 Re-Run Scoring", variant="secondary", size="sm", visible=False)
                    rerun_tags_btn = gr.Button("🏷️ Re-Run Keywords", variant="secondary", size="sm", visible=False)
                    delete_btn = gr.Button("🗑️ Delete NEF", variant="stop", visible=False, size="sm")
                
                fix_status = gr.Textbox(label="Status", visible=False)
                # delete_status defined implicitly in return of delete_nef if separate, 
                # but we usually reuse a label or separate one.
                # In display_details, we just used gr.update.
                # Let's add delete_status
                # In webui.py it wasn't explicit component? 
                # Wait, delete_nef returned (status, visible_update).
                # We can reuse fix_status or make new one.
                delete_status = gr.Textbox(label="Status", visible=False) # Separate one
                
                gallery_selected_path = gr.Textbox(visible=False)
                current_selection_index = gr.State(None)

        # Component validation function
        def validate_components():
            """Ensure all components are initialized before wiring."""
            components = [
                res_info, d_score_gen, d_score_weighted, d_score_models, image_details,
                delete_btn, d_title, d_desc, d_keywords, d_rating, d_label, save_status,
                gallery_selected_path, d_culling_status, fix_btn, fix_status,
                rerun_score_btn, rerun_tags_btn, current_selection_index
            ]
            for i, comp in enumerate(components):
                if comp is None:
                    raise ValueError(f"Component at index {i} in detail_outputs is None! "
                                   f"Component names: res_info, d_score_gen, d_score_weighted, "
                                   f"d_score_models, image_details, delete_btn, d_title, d_desc, "
                                   f"d_keywords, d_rating, d_label, save_status, gallery_selected_path, "
                                   f"d_culling_status, fix_btn, fix_status, rerun_score_btn, "
                                   f"rerun_tags_btn, current_selection_index")
            return components

        # Definition of detail_outputs for wiring
        # Order MUST match update_gallery return and display_details return
        detail_outputs = validate_components()
        
        # Wiring Logic
        filter_inputs_base = [sort_dropdown, order_dropdown, filter_rating, filter_label, filter_keyword, f_min_gen, f_min_aes, f_min_tech, f_date_start, f_date_end, current_folder_state]
        
        refresh_btn.click(fn=first_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        
        # Pagination Events
        next_btn.click(fn=next_page, inputs=[current_page] + filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        prev_btn.click(fn=prev_page, inputs=[current_page] + filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        first_btn.click(fn=first_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        last_btn.click(fn=last_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
        
        # Filter Changes
        for inp in filter_inputs_base[:-1]: # exclude folder_state
            # When filter changes, go to first page
             inp.change(fn=first_page, inputs=filter_inputs_base, outputs=[current_page, gallery, page_label, current_paths] + detail_outputs)
             
        # Reset Folder
        reset_folder_btn.click(
            fn=reset_folder_filter, 
            inputs=filter_inputs_base[:-1], # filters
            outputs=[folder_context_group, folder_display, current_folder_state, current_page, gallery, page_label, current_paths] + detail_outputs
        )
        
        # Gallery Select
        gallery.select(
            fn=display_details,
            inputs=[gallery, current_paths], 
            outputs=detail_outputs
        )
        
        # Actions
        fix_btn.click(
            fn=lambda d: common.fix_image_wrapper(d, runner),
            inputs=[image_details],
            outputs=[fix_btn, fix_status]
        )
        
        rerun_score_btn.click(
            fn=lambda d: common.rerun_scoring_wrapper(d, runner),
            inputs=[image_details],
            outputs=[fix_btn, fix_status] # reuse fix_status for message
        )
        
        rerun_tags_btn.click(
            fn=lambda d: common.rerun_keywords_wrapper(d, tagging_runner),
            inputs=[image_details],
            outputs=[fix_btn, fix_status]
        )
        
        save_btn.click(
            fn=lambda d, t, desc, k, r, l: save_metadata_action(d, t, desc, k, r, l, tagging_runner),
            inputs=[image_details, d_title, d_desc, d_keywords, d_rating, d_label],
            outputs=[save_status, save_status] # msg, visibility
        )
        
        delete_btn.click(
            fn=common.delete_nef, 
            inputs=[image_details],
            outputs=[delete_status, delete_btn] # msg, visibility
        )
        
        # Export
        export_btn.click(
            fn=export_database,
            inputs=[export_format, export_cols_basic, export_cols_scores, export_cols_metadata, export_cols_other, 
                    filter_rating, filter_label, filter_keyword, current_folder_state, 
                    f_min_gen, f_min_aes, f_min_tech, f_date_start, f_date_end],
            outputs=[export_status]
        )

    return {
        'gallery': gallery,
        'folder_context_group': folder_context_group,
        'folder_display': folder_display,
        'page_label': page_label,
        'detail_outputs': detail_outputs,
        'filter_inputs': filter_inputs_base,
        'update_gallery_fn': update_gallery, # For external use
        # Components needed for external wiring if any
    }
