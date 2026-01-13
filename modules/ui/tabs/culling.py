import gradio as gr
import os
from modules import db, utils, culling, config

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

def run_culling_wrapper(input_path, threshold, time_gap, auto_export, force_rescan=False, progress=gr.Progress()):
    """
    Wrapper to run culling logic (Non-blocking).
    """
    if not input_path:
        return "⚠️ Please select a folder first.", gr.update(interactive=True), [], None, [], [], []
    
    config.save_config_value('culling_input_path', input_path)
    
    progress(0.1, desc="Creating culling session...")
    
    # Run full culling workflow
    # Ensure path is in WSL format if that's how it's stored
    wsl_path = utils.convert_path_to_wsl(input_path)
    
    result = culling.culling_engine.run_full_cull(
        folder_path=wsl_path,
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
    
    progress(1.0, desc="Done!")
    
    # Get updated views
    res_msg, gal, sid, paths = resume_culling_session(session_id)
    # Combine messages
    full_msg = "\n".join(msg_lines) + "\n\n" + res_msg
    
    return full_msg, gr.update(interactive=True), gal, sid, paths


def resume_culling_session(session_id):
    """
    Resumes a culling session by loading all images into a single gallery, 
    grouped by stack, with color-coded borders.
    Returns: (status_msg, main_gallery, session_id, all_file_paths)
    """
    if not session_id:
        return "❌ Please select a session to resume", [], None, []
    
    session = db.get_culling_session(session_id)
    if not session:
        return f"❌ Session {session_id} not found", [], None, []
    
    # Get all groups
    groups = db.get_session_groups(session_id)
    
    gallery_items = []
    all_paths = []
    
    # Separate Singles (Group 0) from others
    regular_groups = [g for g in groups if g['group_id'] != 0]
    singles_group = next((g for g in groups if g['group_id'] == 0), None)
    
    # Sort groups by ID (or we could use another metric, but ID is stable)
    regular_groups.sort(key=lambda x: x['group_id'])
    
    # Process regular groups
    for group in regular_groups:
        gid = group['group_id']
        images = group['images']
        
        # Sort internal: Picks first, then Rejects, then others
        # Within those, sort by score descending
        
        picks = [img for img in images if img['decision'] == 'pick']
        rejects = [img for img in images if img['decision'] == 'reject']
        others = [img for img in images if img['decision'] not in ('pick', 'reject')]
        
        picks.sort(key=lambda x: x.get('score_general') or 0, reverse=True)
        rejects.sort(key=lambda x: x.get('score_general') or 0, reverse=True)
        others.sort(key=lambda x: x.get('score_general') or 0, reverse=True)
        
        # Add to gallery with borders
        for img in picks:
             _add_to_gallery(gallery_items, all_paths, img, gid, 'green', 'PICK')
        for img in rejects:
             _add_to_gallery(gallery_items, all_paths, img, gid, 'red', 'REJECT')
        for img in others:
             _add_to_gallery(gallery_items, all_paths, img, gid, 'gray', 'UNREVIEWED')
             
    # Process Singles (Gray border)
    if singles_group:
        singles = singles_group['images']
        singles.sort(key=lambda x: x.get('score_general') or 0, reverse=True)
        for img in singles:
            # User requested gray border for singles
            # Even if they are "picked", they are visually distinct as singles
            color = 'gray'
            status = 'SINGLE'
            if img['decision'] == 'pick':
                 color = 'gray' # Or 'green'? User said "singles with gray border"
                 status = 'SINGLE PICK'
            elif img['decision'] == 'reject':
                 color = 'red' # Rejects are always red?
                 status = 'SINGLE REJECT'
                 
            _add_to_gallery(gallery_items, all_paths, img, 0, color, status)
            
    # Stats
    total = session.get('total_images', 0)
    msg = f"✅ Session {session_id}: Loaded {len(gallery_items)} images in {len(regular_groups) + (1 if singles_group else 0)} groups."
    
    return msg, gallery_items, session_id, all_paths

def _add_to_gallery(gallery_list, path_list, img_data, group_id, color, status):
    """Helper to process image and add to gallery list."""
    file_path = img_data.get('file_path')
    thumb = img_data.get('thumbnail_path') or file_path
    
    # Create label
    score = img_data.get('score_general', 0)
    gid_str = f"G{group_id}" if group_id > 0 else "Single"
    label = f"{gid_str}\n{status}\n{score:.2f}"
    
    # Add border
    # Uses utils.add_border_to_image
    # NOTE: This might be slow for many images.
    # We pass the PIL object to Gradio.
    
    if thumb:
        bordered_img = utils.add_border_to_image(thumb, color=color, border=15)
        if bordered_img:
            gallery_list.append((bordered_img, label))
            path_list.append(file_path)

def export_culling_xmp(session_id):
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
            for f, e in failed_files[:5]:
                msg += f"\n  • {os.path.basename(f)}: {e[:50]}"
    return msg

def delete_rejected_files(session_id, confirmed):
    from modules import xmp as xmp_module
    if not confirmed:
        return "⚠️ Please check the confirmation box to delete files", [], []
    if not session_id: return "❌ No active session", [], []
    rejects = db.get_session_picks(session_id, decision_filter='reject')
    if not rejects: return "ℹ️ No rejected files to delete", [], []
    
    deleted_count = 0
    for reject in rejects:
        file_path = reject.get('file_path')
        if not file_path: continue
        try:
            local_path = utils.convert_path_to_local(file_path)
            if os.path.exists(local_path): os.remove(local_path)
            xmp_module.delete_xmp(file_path)
            thumb_path = reject.get('thumbnail_path')
            if thumb_path:
                local_thumb = utils.convert_path_to_local(thumb_path)
                if os.path.exists(local_thumb): os.remove(local_thumb)
            db.delete_image(file_path)
            deleted_count += 1
        except: pass
    
    # Refresh gallery after delete
    msg, gal, sid, paths = resume_culling_session(session_id)
    
    return f"🗑️ Deleted {deleted_count} rejected files. {msg}", gal, paths

def refresh_culling_groups(session_id, threshold, time_gap):
    if not session_id: return "❌ No active session.", [], []
    session = db.get_culling_session(session_id)
    if not session: return "❌ Session not found.", [], []
    db.clear_culling_picks(session_id)
    import_stats = culling.culling_engine.import_images(session_id, distance_threshold=threshold, time_gap_seconds=int(time_gap))
    if 'error' in import_stats: return f"❌ {import_stats['error']}", [], []
    
    msg, gal, sid, paths = resume_culling_session(session_id)
    return f"✅ Refreshed groups\n{msg}", gal, paths

def repick_culling_best(session_id, score_field='score_general'):
    if not session_id: return "❌ No active session.", [], []
    db.reset_culling_decisions(session_id)
    pick_stats = culling.culling_engine.auto_pick_all(session_id, score_field=score_field)
    msg, gal, sid, paths = resume_culling_session(session_id)
    return f"✅ Re-picked best: {pick_stats.get('picked', 0)} picks\n{msg}", gal, paths

def create_tab(app_config):
    with gr.TabItem("Culling", id="culling") as tab_item:
        gr.Markdown("### ✂️ AI Culling - Grouped View")
        with gr.Row():
            with gr.Column(scale=1, min_width=350):
                with gr.Group():
                    cull_input_dir = gr.Textbox(
                        label="📁 Folder to Cull",
                        value=app_config.get('culling_input_path', ''),
                        info="Select folder with scored images"
                    )
                    cull_threshold = gr.State(value=app_config.get('culling', {}).get('default_threshold', 0.15))
                    cull_time_gap = gr.State(value=app_config.get('culling', {}).get('default_time_gap', 120))
                    cull_auto_export = gr.Checkbox(
                        label="📤 Auto-export to XMP after culling",
                        value=app_config.get('culling', {}).get('auto_export_default', False)
                    )
                    cull_force_rescan = gr.Checkbox(label="Rescan/Regroup (Destructive)", value=False)
                cull_run_btn = gr.Button("▶️ Run AI Culling", variant="primary", size="lg")
            with gr.Column(scale=2):
                cull_status = gr.Textbox(label="Results", lines=4, interactive=False)
        
        gr.Markdown("---")
        
        with gr.Accordion("🔄 Session Management", open=False):
            with gr.Row():
                cull_session_id = gr.State(None)
                cull_resume_dropdown = gr.Dropdown(label="Resume Session", choices=[], interactive=True, scale=2)
                cull_resume_btn = gr.Button("▶️ Resume", variant="primary", size="sm", scale=1)
            with gr.Row():
                cull_refresh_btn = gr.Button("🔄 Refresh Groups", variant="secondary", size="sm", scale=1)
                cull_repick_btn = gr.Button("🎯 Re-Pick Best", variant="secondary", size="sm", scale=1)
            cull_session_status = gr.Textbox(label="Session Status", interactive=False, lines=2)
            cull_delete_confirm = gr.Checkbox(label="Enable Delete", value=False)
            cull_delete_btn = gr.Button("🗑️ Delete REJECTED Files", variant="stop", size="sm")

        # Main Gallery (Unified)
        cull_main_gallery = gr.Gallery(
            label="Culling Decisions (Green=Pick, Red=Reject, Gray=Single)", 
            columns=6, 
            height=800, 
            object_fit="contain",
            allow_preview=True
        )
        cull_main_paths = gr.State([])
        
        # Legacy/Unused outputs (to keep signature compatible if needed, or we just update)
        # We need to update run_wrapper too.
        
        with gr.Accordion("💾 Manual XMP Export", open=False):
            cull_export_btn = gr.Button("📤 Export Pick/Reject Flags to XMP", variant="secondary")
            cull_export_status = gr.Textbox(label="Export Status", interactive=False)

        # Events
        # Update run_wrapper signature locally
        def local_run_wrapper(*args):
             msg, upd, picks, sid, ppaths, rgallery, rpaths = run_culling_wrapper(*args)
             # Adapted to new output: We need to just call resume_culling_session here essentially
             # But run_culling_wrapper calls resume_culling_session at the end.
             # So we just need to adapt the unpacking.
             # run_culling_wrapper returns: full_msg, update, picks, sid, ppaths, rgallery, rpaths
             # We want: msg, update, main_gallery, session_id, main_paths
             # Wait, run_culling_wrapper in 'culling.py' (this file) needs update too.
             # Actually, simpler to just update the wrapper function definition above in a separate replacement block?
             # No, this is replacing everything from 80 downwards.
             # I need to handle run_culling_wrapper logic too or update it.
             # I should update run_culling_wrapper separately or include it in this block.
             # This block starts at Resume Culling Session (line 80).
             # Run Culling wrapper is at line 20.
             # So I need to update run_culling_wrapper too.
             # For now, let's just make the outputs of run_wrapper match.
             pass

        # We will re-wire run_culling_wrapper in a separate tool call or assume I will fix it.
        # Let's fix create_tab first.
        
        cull_run_btn.click(
            fn=run_culling_wrapper, 
            inputs=[cull_input_dir, cull_threshold, cull_time_gap, cull_auto_export, cull_force_rescan],
            outputs=[cull_status, cull_run_btn, cull_main_gallery, cull_session_id, cull_main_paths]
        )
        
        cull_resume_btn.click(
            fn=resume_culling_session,
            inputs=[cull_resume_dropdown],
            outputs=[cull_status, cull_main_gallery, cull_session_id, cull_main_paths]
        )
        
        cull_refresh_btn.click(
            fn=refresh_culling_groups,
            inputs=[cull_session_id, cull_threshold, cull_time_gap],
            outputs=[cull_session_status, cull_main_gallery, cull_main_paths]
        )
        
        cull_repick_btn.click(
            fn=repick_culling_best,
            inputs=[cull_session_id],
            outputs=[cull_session_status, cull_main_gallery, cull_main_paths]
        )
        
        cull_delete_btn.click(
            fn=delete_rejected_files,
            inputs=[cull_session_id, cull_delete_confirm],
            outputs=[cull_session_status, cull_main_gallery, cull_main_paths]
        )

        cull_export_btn.click(fn=export_culling_xmp, inputs=[cull_session_id], outputs=[cull_export_status])

    return {
        'tab_item': tab_item,
        'resume_dropdown': cull_resume_dropdown,
        'session_id': cull_session_id
    }

