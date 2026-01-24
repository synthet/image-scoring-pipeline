"""
Culling Engine Module

Provides Aftershoot-style AI culling workflow:
1. Import images from a folder into a culling session
2. Group similar images using existing clustering infrastructure
3. Auto-pick best images in each group based on scores
4. Export decisions to XMP sidecars for Lightroom Cloud

Mode: AI-Automated (AI picks best, user reviews)
"""

import os
import logging
from datetime import datetime
from modules import db, clustering, xmp

logger = logging.getLogger(__name__)


class CullingEngine:
    """
    Main culling workflow engine.
    Manages sessions, grouping, and auto-picking.
    """
    
    def __init__(self):
        self.cluster_engine = clustering.ClusteringEngine()
        self.current_session_id = None
    
    def create_session(self, folder_path: str, mode: str = 'automated') -> int:
        """
        Creates a new culling session for a folder.
        
        Args:
            folder_path: Path to the folder to cull
            mode: 'automated' (AI picks) or 'assisted' (user picks with AI help)
        
        Returns:
            session_id or None on error
        """
        folder_path = os.path.normpath(folder_path)
        
        # Create session in DB
        session_id = db.create_culling_session(folder_path, mode)
        if not session_id:
            logger.error("Failed to create culling session in database")
            return None
        
        self.current_session_id = session_id
        logger.info(f"Created culling session {session_id} for {folder_path}")
        
        return session_id
    
    def import_images(self, session_id: int, 
                      distance_threshold: float = None,
                      time_gap_seconds: int = None,
                      force_rescan: bool = False) -> dict:
        """
        Imports images from session folder, groups similar ones.
        
        Args:
            session_id: Culling session ID
            distance_threshold: Similarity threshold for grouping (lower = more similar)
            time_gap_seconds: Time gap to split groups (even if similar)
        
        Returns:
            Dict with import stats: {total, groups, singles}
        """
        # Load defaults from config if not provided
        from modules import config
        if distance_threshold is None:
            culling_config = config.get_config_section('culling')
            distance_threshold = culling_config.get('default_threshold', 0.15)
        if time_gap_seconds is None:
            culling_config = config.get_config_section('culling')
            time_gap_seconds = culling_config.get('default_time_gap', 120)
        
        session = db.get_culling_session(session_id)
        if not session:
            return {'error': 'Session not found'}
        
        folder_path = session['folder_path']
        
        # Get images from DB that are in this folder
        # (assumes they've already been scored)
        images = db.get_images_by_folder(folder_path)
        
        if not images:
            return {'error': f'No scored images found in {folder_path}', 'total': 0}
        
        image_ids = [img['id'] for img in images]
        
        # Check if stacks already exist for this folder
        should_cluster = True
        if not force_rescan:
            try:
                stack_count = db.get_stack_count_for_folder(folder_path)
                if stack_count > 0:
                    logger.info(f"Found {stack_count} existing stacks. Skipping re-clustering (use Rescan to force).")
                    should_cluster = False
            except Exception as e:
                logger.warning(f"Error checking stacks: {e}. Proceeding with clustering.")
        
        if should_cluster:
            # Run clustering to find similar groups
            logger.info(f"Clustering {len(images)} images...")
            
            # Use the existing clustering engine
            # This will create/update stack assignments in the DB
            # cluster_images() is a generator - must consume it to execute
            for progress_msg in self.cluster_engine.cluster_images(
                distance_threshold=distance_threshold,
                time_gap_seconds=time_gap_seconds,
                force_rescan=force_rescan,
                target_folder=folder_path
            ):
                # Log progress from the clustering generator
                if isinstance(progress_msg, tuple):
                    msg, current, total = progress_msg
                    logger.info(f"Clustering: {msg}")
                else:
                    logger.info(f"Clustering: {progress_msg}")
        
        # Now read the stack assignments back
        # Map image_id -> stack_id (group_id)
        group_assignments = {}
        for img in images:
            # Re-fetch to get updated stack_id
            details = db.get_image_details(img['file_path'])
            if details and details.get('stack_id'):
                group_assignments[img['id']] = details['stack_id']
        
        # Add images to culling session
        db.add_images_to_culling_session(session_id, image_ids, group_assignments)
        
        # Count unique groups
        unique_groups = set(group_assignments.values())
        singles_count = len(image_ids) - len(group_assignments)
        
        # Update session stats
        db.update_culling_session(
            session_id,
            total_images=len(image_ids),
            total_groups=len(unique_groups) + (1 if singles_count > 0 else 0)
        )
        
        stats = {
            'total': len(image_ids),
            'groups': len(unique_groups),
            'singles': singles_count,
            'session_id': session_id
        }
        
        logger.info(f"Imported {stats['total']} images into {stats['groups']} groups")
        return stats
    
    def auto_pick_all(self, session_id: int, 
                      score_field: str = 'score_general',
                      pick_percentage: float = 0.38) -> dict:
        """
        AI-Automated mode: Automatically picks the top images in each group.
        
        Args:
            session_id: Culling session ID
            score_field: Which score to use for ranking (score_general, score_technical, score_aesthetic)
            pick_percentage: Percentage of top images to pick (default: 0.38 = 38%)
        
        Returns:
            Dict with pick stats: {picked, rejected, groups_processed}
        """
        import math
        
        groups = db.get_session_groups(session_id)
        
        picked_count = 0
        rejected_count = 0
        
        for group in groups:
            images = group['images']
            
            if len(images) == 0:
                continue
            
            # Sort by score (highest first)
            images_sorted = sorted(
                images, 
                key=lambda x: x.get(score_field) or 0, 
                reverse=True
            )
            
            # Calculate pick count: ceil(38% of stack size)
            # Special handling for Singles (group_id=0): Pick ALL because they are unique moments
            if group.get('group_id') == 0:
                pick_count = len(images)
            else:
                pick_count = math.ceil(len(images_sorted) * pick_percentage)
            
            # Mark top percentage as picked, rest as rejected
            for i, img in enumerate(images_sorted):
                if i < pick_count:
                    # Pick this image
                    db.set_pick_decision(session_id, img['image_id'], 'pick', auto_suggested=True)
                    # Mark the first one as best in group
                    if i == 0:
                        db.set_best_in_group(session_id, img['image_id'], group['group_id'])
                    picked_count += 1
                else:
                    # Reject this image
                    db.set_pick_decision(session_id, img['image_id'], 'reject', auto_suggested=True)
                    rejected_count += 1
        
        # Update session stats
        stats = db.get_session_stats(session_id)
        db.update_culling_session(
            session_id,
            picked_count=stats['picked_count'],
            rejected_count=stats['rejected_count'],
            reviewed_groups=stats['total_groups']
        )
        
        result = {
            'picked': picked_count,
            'rejected': rejected_count,
            'groups_processed': len(groups)
        }
        
        logger.info(f"Auto-picked {picked_count} images (38%), rejected {rejected_count} (62%)")
        return result
    
    def get_picks(self, session_id: int) -> list:
        """Returns all picked images for a session."""
        return db.get_session_picks(session_id, decision_filter='pick')
    
    def get_rejects(self, session_id: int) -> list:
        """Returns all rejected images for a session."""
        return db.get_session_picks(session_id, decision_filter='reject')
    
    def export_to_xmp(self, session_id: int) -> dict:
        """
        Exports culling decisions to XMP sidecar files using Lightroom Pick/Reject flags.
        
        Uses xmpDM:pick values:
            - Picked images: pick=1, good=true
            - Rejected images: pick=-1, good=false
        
        Args:
            session_id: Culling session ID
        
        Returns:
            Dict with export stats: {exported, errors, failed_files}
                - exported: Number of successfully exported files
                - errors: Number of failed exports
                - failed_files: List of tuples (file_path, error_message) for failed exports
        """
        picks = db.get_session_picks(session_id)
        
        exported = 0
        errors = 0
        failed_files = []
        
        for pick in picks:
            file_path = pick.get('file_path')
            decision = pick.get('decision')
            
            if not file_path or not decision:
                continue
            
            try:
                if decision == 'pick':
                    # Write Lightroom Pick flag (xmpDM:pick=1)
                    success = xmp.write_pick_reject_flag(file_path, pick_status=1)
                elif decision == 'reject':
                    # Write Lightroom Reject flag (xmpDM:pick=-1)
                    success = xmp.write_pick_reject_flag(file_path, pick_status=-1)
                else:
                    # Maybe / unreviewed - skip
                    continue
                
                if success:
                    exported += 1
                else:
                    errors += 1
                    failed_files.append((file_path, "XMP write returned False"))
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to export XMP for {file_path}: {error_msg}")
                errors += 1
                failed_files.append((file_path, error_msg))
        
        # Mark session as exported
        db.update_culling_session(session_id, status='exported')
        
        result = {
            'exported': exported,
            'errors': errors,
            'failed_files': failed_files[:10],  # Limit to first 10 for UI display
            'session_id': session_id
        }
        
        if errors > 0:
            logger.warning(f"Exported {exported} XMP Pick/Reject flags ({errors} errors)")
            if len(failed_files) > 10:
                logger.warning(f"First 10 failed files logged, {len(failed_files) - 10} more failures")
        else:
            logger.info(f"Exported {exported} XMP Pick/Reject flags successfully")
        
        return result
    
    def run_full_cull(self, folder_path: str,
                      distance_threshold: float = None,
                      time_gap_seconds: int = None,
                      score_field: str = 'score_general',
                      auto_export: bool = None,
                      force_rescan: bool = False) -> dict:
        """
        One-shot full culling workflow:
        1. Create session
        2. Import and group images
        3. Auto-pick best in each group
        4. Optionally export to XMP
        
        Returns combined stats from all steps.
        """
        # Load defaults from config if not provided
        from modules import config
        if distance_threshold is None:
            culling_config = config.get_config_section('culling')
            distance_threshold = culling_config.get('default_threshold', 0.15)
        if time_gap_seconds is None:
            culling_config = config.get_config_section('culling')
            time_gap_seconds = culling_config.get('default_time_gap', 120)
        if auto_export is None:
            culling_config = config.get_config_section('culling')
            auto_export = culling_config.get('auto_export_default', False)
        
        # Create session
        session_id = self.create_session(folder_path, mode='automated')
        if not session_id:
            return {'error': 'Failed to create session'}
        
        # Import and group
        import_stats = self.import_images(
            session_id, 
            distance_threshold=distance_threshold,
            time_gap_seconds=time_gap_seconds,
            force_rescan=force_rescan
        )
        
        if 'error' in import_stats:
            return import_stats
        
        # Auto-pick
        pick_stats = self.auto_pick_all(session_id, score_field=score_field)
        
        result = {
            'session_id': session_id,
            'folder': folder_path,
            **import_stats,
            **pick_stats,
            'exported': False
        }
        
        # Export if requested
        if auto_export:
            export_stats = self.export_to_xmp(session_id)
            result['exported'] = True
            result['xmp_count'] = export_stats['exported']
            result['xmp_errors'] = export_stats['errors']
        
        return result


# Singleton instance for WebUI
culling_engine = CullingEngine()
