"""
Stacks tab module for image grouping and clustering.

This module provides UI for:
- Automatic image clustering based on visual similarity and time gaps
- Manual stack creation from selected images
- Stack management (view, expand, set cover image, remove images, dissolve)
- Navigation to view stack contents in Gallery

The create_stacks_tab() function returns components needed for cross-tab
navigation and stack operations.
"""
import gradio as gr
import os
from modules import db, utils, clustering, config

cluster_engine = clustering.ClusteringEngine()

def run_clustering_wrapper(input_path, threshold, gap, force, progress=gr.Progress()):
    """Regular (non-generator) fn so .then(refresh) runs reliably after it completes."""
    try:
        config.save_config_value('stacks_input_path', input_path)
        if gap is None:
            gap = 120
        target = input_path.strip() if input_path and input_path.strip() else None
        for msg_tuple in cluster_engine.cluster_images(distance_threshold=threshold, time_gap_seconds=gap, force_rescan=force, target_folder=target):
            if isinstance(msg_tuple, tuple):
                msg, cur, tot = msg_tuple
                if tot > 0:
                    progress(cur / tot, desc=msg)
                else:
                    progress(0, desc=msg)
    except Exception as e:
        return f"Error: {e}", gr.update(interactive=True)
    return "Done", gr.update(interactive=True)


def run_clustering_and_refresh(input_path, threshold, gap, force, sort_by, sort_order, progress=gr.Progress()):
    """Run clustering then refresh in one handler. Updates gallery directly (no .then()) to avoid loading spinner stuck."""
    try:
        log_msg, _ = run_clustering_wrapper(input_path, threshold, gap, force, progress)
    except Exception as e:
        return f"Error: {e}", gr.update(interactive=True), [], []
    if log_msg.startswith("Error:"):
        return log_msg, gr.update(interactive=True), [], []
    results, stack_ids = refresh_stacks_wrapper(input_path, sort_by, sort_order)
    return log_msg, gr.update(interactive=True), results, stack_ids


def refresh_stacks_wrapper(input_path, sort_by, sort_order, progress=gr.Progress()):
    try:
        target = input_path.strip() if input_path and input_path.strip() else None
        progress(0, desc="Loading stacks from database...")
        
        # Execute database query with error handling
        try:
            rows = db.get_stacks_for_display(folder_path=target, sort_by=sort_by, order=sort_order)
        except Exception as db_error:
            import traceback
            error_msg = f"Database error: {str(db_error)}\n{traceback.format_exc()}"
            print(f"Error loading stacks: {error_msg}")
            progress(1.0, desc=f"Error: {str(db_error)}")
            return [], []

        results = []
        stack_ids = []
        total_rows = len(rows) if rows else 0
        
        if total_rows == 0:
            progress(1.0, desc="No stacks found")
            return [], []
        
        # OPTIMIZATION: Batch resolve cover images
        cover_image_ids = []
        for row in rows:
            try:
                if row['cover_path']:
                    iid = row.get('best_image_id')
                    if iid: cover_image_ids.append(iid)
            except: pass
            
        resolved_map = {}
        if cover_image_ids:
             try:
                 resolved_map = db.get_resolved_paths_batch(cover_image_ids)
             except: pass

        for i, row in enumerate(rows):
            if total_rows > 0:
                progress((i + 1) / total_rows, desc=f"Loading stacks... {i + 1}/{total_rows}")
            
            try:
                s_id = row['id']
                name = row['name']
                count = row['image_count']
                cover = row['cover_path']
                label = f"{name} ({count} items)"

                if cover:
                    image_id = row.get('best_image_id') if hasattr(row, 'get') else None
                    
                    # Optimized Resolution Logic
                    local_cover = None
                    if image_id and image_id in resolved_map:
                        cached_path = resolved_map[image_id]
                        if cached_path:
                            is_malformed = '\\' in cached_path and '/' in cached_path
                            if not is_malformed:
                                local_cover = cached_path
                                
                    if not local_cover:
                         local_cover = utils.resolve_file_path(cover, image_id) or utils.convert_path_to_local(cover) or cover
                         
                    if local_cover and os.path.exists(local_cover):
                        results.append((local_cover, label))
                        stack_ids.append(s_id)
            except Exception as row_error:
                # Skip problematic rows but continue processing
                print(f"Error processing stack row {i}: {str(row_error)}")
                continue
        
        progress(1.0, desc=f"Loaded {len(results)} stacks")
        return results, stack_ids
    except Exception as e:
        import traceback
        error_msg = f"Unexpected error: {str(e)}\n{traceback.format_exc()}"
        print(f"Error in refresh_stacks_wrapper: {error_msg}")
        return [], []

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
    
    # OPTIMIZATION: Batch resolve stack content images
    stack_image_ids = [row['id'] for row in images if row['file_path']]
    resolved_map = {}
    if stack_image_ids:
        try:
            resolved_map = db.get_resolved_paths_batch(stack_image_ids)
        except: pass
    
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
            # Resolve thumb or file path
            image_id = row['id']
            if thumb:
                p = utils.resolve_file_path(thumb, image_id) or utils.convert_path_to_local(thumb)
            else:
                p = utils.resolve_file_path(file_path, image_id) or utils.convert_path_to_local(file_path)

            # Optimized Resolution Logic
            if image_id and image_id in resolved_map:
                cached_path = resolved_map[image_id]
                if cached_path:
                    is_malformed = '\\' in cached_path and '/' in cached_path
                    if not is_malformed:
                        p = cached_path
        
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
                image_id = row['id']
                if thumb:
                    p = utils.resolve_file_path(thumb, image_id) or utils.convert_path_to_local(thumb)
                else:
                    p = utils.resolve_file_path(file_path, image_id) or utils.convert_path_to_local(file_path)
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


def create_stacks_tab():
    app_config = config.load_config()
    
    with gr.TabItem("Stacks", id="stacks") as tab_item:
        # Row 1: Controls split into two columns
        with gr.Row():
            # Left column: Input controls
            with gr.Column(scale=1, min_width=300):
                c_input_dir = gr.Textbox(
                    label="Folder", 
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
                # Sort controls - moved below action buttons
                with gr.Row():
                    c_sort = gr.Dropdown(
                        choices=["created_at", "score_general", "score_technical", "score_aesthetic"], 
                        value="score_general", 
                        label="Sort By",
                        scale=2
                    )
                    c_order = gr.Dropdown(choices=["desc", "asc"], value="desc", label="Order", scale=1)
            
            # Right column: Status display
            with gr.Column(scale=1, min_width=300):
                # Status Card
                c_status_html = gr.HTML(label="Status")
                with gr.Accordion("📋 Console Output", open=False, visible=False):
                    c_log = gr.Textbox(label="", lines=6, interactive=False, show_copy_button=True)
        
        # Divider
        gr.Markdown("---")
        
        # Row 2: Stacks Gallery (full width)
        gr.Markdown("### 📚 Stacks Gallery")
        stack_gallery = gr.Gallery(
            label="Stacks", 
            columns=8, 
            height=350,
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
        
        # Events: single handler (clustering + refresh) — no .then() to avoid gallery loading spinner stuck
        c_run_btn.click(
            fn=run_clustering_and_refresh,
            inputs=[c_input_dir, c_threshold, c_gap, c_force_rescan, c_sort, c_order],
            outputs=[c_log, c_run_btn, stack_gallery, stack_ids_state]
        )
        
        c_refresh_btn.click(
            fn=refresh_stacks_wrapper,
            inputs=[c_input_dir, c_sort, c_order],
            outputs=[stack_gallery, stack_ids_state]
        )
        
        # State to track if stacks have been loaded initially
        stacks_loaded_state = gr.State(value=False)

        # Auto-refresh on sort change, and trigger initial load
        def refresh_stacks_with_initial_check(input_path, sort_by, sort_order, loaded_state):
            """Refresh stacks, and load initially if not yet loaded."""
            result = refresh_stacks_wrapper(input_path, sort_by, sort_order)
            return result[0], result[1], True  # Mark as loaded
        
        c_sort.change(
            fn=refresh_stacks_with_initial_check,
            inputs=[c_input_dir, c_sort, c_order, stacks_loaded_state],
            outputs=[stack_gallery, stack_ids_state, stacks_loaded_state]
        )
        c_order.change(
            fn=refresh_stacks_with_initial_check,
            inputs=[c_input_dir, c_sort, c_order, stacks_loaded_state],
            outputs=[stack_gallery, stack_ids_state, stacks_loaded_state]
        )
        
        # Initial load when tab is first accessed - trigger via input_dir focus
        def load_stacks_on_tab_open(input_path, sort_by, sort_order):
            """Load stacks when tab is first opened."""
            return refresh_stacks_wrapper(input_path, sort_by, sort_order)
        
        # Trigger initial load when input_dir gets focus (happens when tab is accessed)
        c_input_dir.focus(
            fn=load_stacks_on_tab_open,
            inputs=[c_input_dir, c_sort, c_order],
            outputs=[stack_gallery, stack_ids_state],
            show_progress=True
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

        return {
            'tab_item': tab_item,
            'input_dir': c_input_dir,
            'open_gallery_btn': c_open_gallery_btn,
            'current_stack_id': current_stack_id,
            'sort_by': c_sort,
            'order': c_order,
            'run_btn': c_run_btn,
            'refresh_btn': c_refresh_btn,
            'log_output': c_log,
            'status_html': c_status_html,
            'stack_gallery': stack_gallery,
            'stack_ids_state': stack_ids_state
        }


def get_status_update():
    """
    Called by the main timer loop to get status updates for the Stacks tab.
    Returns: [status_html, run_btn_update, refresh_btn_update]
    """
    is_running, status_msg, cur, tot = cluster_engine.get_status()
    
    # Determine status icon and color
    if is_running:
        status_icon = "⚡"
        status_color = "#58a6ff"
        badge_bg = "rgba(88, 166, 255, 0.15)"
    elif "Error" in status_msg or "Failed" in status_msg:
        status_icon = "❌"
        status_color = "#f85149"
        badge_bg = "rgba(248, 81, 73, 0.15)"
    elif "Done" in status_msg or "Complete" in status_msg:
        status_icon = "✅"
        status_color = "#3fb950"
        badge_bg = "rgba(63, 185, 80, 0.15)"
    else:
        status_icon = "⏸️"
        status_color = "#8b949e"
        badge_bg = "rgba(139, 148, 158, 0.15)"
    
    # Build modern status HTML
    status_html = f"""
    <div style="padding: 16px; background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border-radius: 10px; border: 1px solid #30363d;">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
            <span style="font-size: 1.3rem;">{status_icon}</span>
            <div>
                <div style="font-size: 1rem; font-weight: 600; color: #e6edf3;">{status_msg}</div>
                <div style="font-size: 0.75rem; color: #8b949e;">Image Clustering Engine</div>
            </div>
        </div>
    """
    
    if tot > 0 and is_running:
        pct = (cur / tot) * 100
        status_html += f"""
        <div style="display: flex; justify-content: space-between; margin-bottom: 6px; color: #8b949e; font-size: 0.85rem;">
            <span>Progress: {int(cur)} / {tot} images</span>
            <span style="color: {status_color}; font-weight: 600;">{pct:.1f}%</span>
        </div>
        <div style="width: 100%; background-color: #21262d; border-radius: 6px; height: 8px; overflow: hidden;">
            <div style="width: {pct}%; background: linear-gradient(90deg, #58a6ff 0%, #a371f7 100%); height: 8px; border-radius: 6px; transition: width 0.3s ease;"></div>
        </div>
        """
    elif is_running:
        status_html += f"""
        <div style="display: flex; align-items: center; gap: 8px; color: #8b949e;">
            <div style="width: 8px; height: 8px; background: {status_color}; border-radius: 50%; animation: pulse 1.5s infinite;"></div>
            <span>Processing...</span>
        </div>
        <style>@keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}</style>
        """
    
    status_html += "</div>"
    
    # Disable buttons while running
    run_btn_update = gr.update(interactive=not is_running)
    refresh_btn_update = gr.update(interactive=not is_running)
    
    return status_html, run_btn_update, refresh_btn_update
