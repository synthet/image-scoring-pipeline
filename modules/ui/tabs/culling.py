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
    
    # Get updated views
    res_msg, picks, sid, ppaths, rgallery, rpaths = resume_culling_session(session_id)
    # Combine messages
    full_msg = "\n".join(msg_lines) + "\n\n" + res_msg
    
    return full_msg, gr.update(interactive=True), picks, sid, ppaths, rgallery, rpaths

def resume_culling_session(session_id):
    """
    Resumes a culling session by loading its picks and rejects into the galleries.
    Returns: (status_msg, picks_gallery, session_id, picks_paths, rejects_gallery, rejects_paths)
    """
    if not session_id:
        return "❌ Please select a session to resume", [], None, [], [], []
    
    session = db.get_culling_session(session_id)
    if not session:
        return f"❌ Session {session_id} not found", [], None, [], [], []
    
    folder_path = session.get('folder_path', '')
    
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
    
    total = session.get('total_images', 0)
    groups = session.get('total_groups', 0)
    picked = session.get('picked_count', len(picks))
    rejected = session.get('rejected_count', len(rejects))
    reviewed = session.get('reviewed_groups', 0)
    
    msg_lines = [
        f"✅ Session {session_id}: {os.path.basename(folder_path)}",
        f"📊 Total: {total} | Groups: {groups}",
        f"✅ Picked: {picked} | ❌ Rejected: {rejected}",
        f"📝 Reviewed: {reviewed}/{groups} groups"
    ]
    
    return "\n".join(msg_lines), picks_gallery, session_id, picks_paths, rejects_gallery, rejects_paths

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
    return f"🗑️ Deleted {deleted_count} rejected files", [], []

def refresh_culling_groups(session_id, threshold, time_gap):
    if not session_id: return "❌ No active session.", [], []
    session = db.get_culling_session(session_id)
    if not session: return "❌ Session not found.", [], []
    db.clear_culling_picks(session_id)
    import_stats = culling.culling_engine.import_images(session_id, distance_threshold=threshold, time_gap_seconds=int(time_gap))
    if 'error' in import_stats: return f"❌ {import_stats['error']}", [], []
    msg = f"✅ Refreshed groups\n📊 Total: {import_stats.get('total', 0)} | 📚 Groups: {import_stats.get('groups', 0)}"
    return msg, [], []

def repick_culling_best(session_id, score_field='score_general'):
    if not session_id: return "❌ No active session.", [], []
    db.reset_culling_decisions(session_id)
    pick_stats = culling.culling_engine.auto_pick_all(session_id, score_field=score_field)
    _, picks_gal, _, picks_paths, _, _ = resume_culling_session(session_id)
    msg = f"✅ Re-picked best: {pick_stats.get('picked', 0)} picks, {pick_stats.get('rejected', 0)} rejects"
    return msg, picks_gal, picks_paths

"""
Culling tab module for AI-assisted photo culling workflow.

This module provides an Aftershoot-style culling interface:
- Automatic grouping of similar images (bursts, duplicates)
- AI-powered best shot selection based on quality scores
- Manual override and fine-tuning
- Export to XMP sidecar files for Lightroom Cloud integration
- Session management (save/resume culling sessions)

The create_tab() function returns components needed for session management
and cross-tab integration.
"""
def create_tab(app_config):
    with gr.TabItem("Culling", id="culling") as tab_item:
        gr.Markdown("### ✂️ AI Culling - Pick/Reject Best Shots")
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
                cull_status = gr.Textbox(label="Results", lines=6, interactive=False)
        
        gr.Markdown("---")
        gr.Markdown("### ✅ AI Picks")
        cull_picks_gallery = gr.Gallery(label="Picked Images", columns=6, height=400, object_fit="cover")
        cull_picks_paths = gr.State([])
        
        with gr.Accordion("🔄 Session Management", open=False):
            with gr.Row():
                cull_session_id = gr.State(None)
                # We need to refresh choices on open or via button.
                # For now init empty, wire in app.
                cull_resume_dropdown = gr.Dropdown(label="Resume Session", choices=[], interactive=True, scale=2)
                cull_resume_btn = gr.Button("▶️ Resume", variant="primary", size="sm", scale=1)
            with gr.Row():
                cull_refresh_btn = gr.Button("🔄 Refresh Groups", variant="secondary", size="sm", scale=1)
                cull_repick_btn = gr.Button("🎯 Re-Pick Best", variant="secondary", size="sm", scale=1)
            cull_session_status = gr.Textbox(label="Session Status", interactive=False, lines=3)
        
        with gr.Accordion("💾 Manual XMP Export", open=False):
            cull_export_btn = gr.Button("📤 Export Pick/Reject Flags to XMP", variant="secondary")
            cull_export_status = gr.Textbox(label="Export Status", interactive=False)
        
        gr.Markdown("---")
        gr.Markdown("### ❌ Rejected Images")
        cull_rejects_gallery = gr.Gallery(label="Rejected Images", columns=6, height=300, object_fit="cover")
        cull_rejects_paths = gr.State([])
        
        with gr.Accordion("🗑️ Delete Rejected Files", open=False):
            with gr.Row():
                cull_delete_confirm = gr.Checkbox(label="I confirm I want to permanently delete these files", value=False)
                cull_delete_btn = gr.Button("🗑️ Delete All Rejected", variant="stop", size="sm")
            cull_delete_status = gr.Textbox(label="Delete Status", interactive=False)

        # Events
        cull_run_btn.click(
            fn=run_culling_wrapper,
            inputs=[cull_input_dir, cull_threshold, cull_time_gap, cull_auto_export, cull_force_rescan],
            outputs=[cull_status, cull_run_btn, cull_picks_gallery, cull_session_id, cull_picks_paths, cull_rejects_gallery, cull_rejects_paths]
        )
        cull_resume_btn.click(
            fn=resume_culling_session,
            inputs=[cull_resume_dropdown],
            outputs=[cull_status, cull_picks_gallery, cull_session_id, cull_picks_paths, cull_rejects_gallery, cull_rejects_paths]
        )
        cull_export_btn.click(fn=export_culling_xmp, inputs=[cull_session_id], outputs=[cull_export_status])
        cull_delete_btn.click(
            fn=delete_rejected_files,
            inputs=[cull_session_id, cull_delete_confirm],
            outputs=[cull_delete_status, cull_rejects_gallery, cull_rejects_paths]
        )
        cull_refresh_btn.click(
            fn=refresh_culling_groups,
            inputs=[cull_session_id, cull_threshold, cull_time_gap],
            outputs=[cull_session_status, cull_picks_gallery, cull_picks_paths]
        )
        cull_repick_btn.click(fn=repick_culling_best, inputs=[cull_session_id], outputs=[cull_session_status, cull_picks_gallery, cull_picks_paths])

    return {
        'tab_item': tab_item,
        'resume_dropdown': cull_resume_dropdown,
        'session_id': cull_session_id
    }
