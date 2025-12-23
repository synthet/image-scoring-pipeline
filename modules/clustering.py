
import os
import logging
import numpy as np
import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing import image as keras_image
from sklearn.cluster import AgglomerativeClustering
from modules import db
from PIL import Image

# Suppress TF logging
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

class ClusteringEngine:
    def __init__(self):
        self.model = None
        self.feature_cache = {} # Simple in-memory cache for now. TODO: Persist?

    def load_model(self):
        if self.model is None:
            # Load MobileNetV2, exclude top layer, use global average pooling
            self.model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg')
            logging.info("Clustering Model (MobileNetV2) loaded.")

    def extract_features(self, image_paths):
        """
        Extract features for a list of image paths.
        Returns numpy array of features.
        """
        self.load_model()
        
        features_list = []
        valid_indices = [] # Track which images were successfully processed
        
        batch_images = []
        batch_paths = []
        batch_size = 32
        
        for i, path in enumerate(image_paths):
            if not os.path.exists(path):
                continue
                
            try:
                # Load image, resize to 224x224
                # Use PIL to handle potential issues before Keras
                img = keras_image.load_img(path, target_size=(224, 224))
                x = keras_image.img_to_array(img)
                x = preprocess_input(x)
                batch_images.append(x)
                batch_paths.append(path)
                valid_indices.append(i)
                
                if len(batch_images) >= batch_size:
                    batch_arr = np.array(batch_images)
                    preds = self.model.predict(batch_arr, verbose=0)
                    features_list.extend(preds)
                    batch_images = []
                    batch_paths = []
                    
            except Exception as e:
                logging.error(f"Error extracting features for {path}: {e}")
                
        # Process remaining
        if batch_images:
            batch_arr = np.array(batch_images)
            preds = self.model.predict(batch_arr, verbose=0)
            features_list.extend(preds)
            
        return np.array(features_list), valid_indices

    def _get_image_time(self, row):
        """
        Returns timestamp for image. Tries metadata, falls back to file mtime.
        """
        # Try metadata
        if row['metadata']:
            try:
                meta = json.loads(row['metadata'])
                # Look for common EXIF date keys
                # "DateTimeOriginal", "CreateDate"
                # formats: "YYYY:MM:DD HH:MM:SS"
                date_str = meta.get('DateTimeOriginal') or meta.get('CreateDate')
                if date_str:
                    # Parse
                    return datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S").timestamp()
            except:
                pass
                
        # Fallback: Filesystem mtime
        try:
            p = row['file_path']
            if os.path.exists(p):
                return os.path.getmtime(p)
        except:
            pass
            
        return 0.0

    def cluster_images(self, distance_threshold=0.3, time_gap_seconds=120, force_rescan=False, target_folder=None):
        """
        Main function to load images from DB, cluster them, and update DB.
        Enforces: 1. Folder Isolation 2. Time Gap Splitting 3. Persistence
        """
        import datetime
        import json
        from itertools import groupby
        
        logging.info("Fetching images for clustering...")
        
        images_rows = []
        if target_folder:
             images_rows = db.get_images_by_folder(target_folder)
             if not images_rows:
                 yield f"No images found in folder: {target_folder}", 0, 0
                 return
        else:
            # Fallback to all (limit 50k)
            images_rows = db.get_all_images(sort_by="created_at", order="desc", limit=50000)
        
        if not images_rows:
            yield "No images found in database.", 0, 0
            return

        yield f"Found {len(images_rows)} images. Checking progress...", 0, len(images_rows)

        # 1. Group by Folder
        by_folder = {}
        for row in images_rows:
            p = row['file_path']
            if not p: continue
            folder = os.path.dirname(p)
            # Normalize?
            folder = os.path.normpath(folder)
            
            if folder not in by_folder:
                by_folder[folder] = []
            by_folder[folder].append(row)
            
        # Get processed folders
        processed_folders = db.get_clustered_folders()
        if force_rescan:
             # If target folder, only clear for that folder?
             # db.clear_cluster_progress() clears EVERYTHING.
             # We might need a targeted clear.
             # For now, if targeting one folder, maybe we just re-process it and overwrite?
             # The db.create_stacks_batch inserts new stacks. It doesn't delete old ones for the images.
             # We should probably clear stacks for the target folder if forcing.
             if target_folder:
                 # TODO: Add db.clear_stacks_in_folder?
                 # For now, let's just warn or handle it.
                 # Actually, db.clear_cluster_progress() is too aggressive for single folder.
                 # Let's rely on logic or just clear all if user really wants 'Force Rescan' (which implies global usually).
                 # But for single folder flow, 'Force' might mean 'Re-cluster THIS folder'.
                 pass
             else:
                 db.clear_cluster_progress()
                 processed_folders = set()
                 yield "Force Rescan: Cleared previous progress.", 0, len(images_rows)
        
        total_clusters = db.get_stack_count() 
        processed_count = 0
        
        # Filter folders to process
        folders_to_process = []
        if target_folder:
            target_norm = os.path.normpath(target_folder)
            # Only process if it is in by_folder (which it should be)
            if target_norm in by_folder:
                folders_to_process = [target_norm]
            else:
                 # Logic to handle subfolders? Request says "create stacks only inside a single folder", implies recursion?
                 # "recursively scans and processes images located within sub-folders" was a previous topic.
                 # Current request: "create stacks only inside a single folder".
                 # If input path is D:\Photos, do we do D:\Photos\Sub? 
                 # Usually users want recursive.
                 # My by_folder keys are from image paths.
                 # So if I gathered images from subfolders (db.get_images_by_folder is non-recursive strictly speaking? Let's check db.py)
                 # db.get_images_by_folder uses folder_id which is strict 1:1.
                 # So if target_folder is strict, we only have one folder.
                 folders_to_process = [f for f in by_folder.keys()]
        else:
            folders_to_process = [f for f in by_folder.keys() if f not in processed_folders]
        
        if not folders_to_process:
            yield "All folders already processed or no images in target folder.", len(images_rows), len(images_rows)
            return

        yield f"Processing {len(folders_to_process)} new folders...", processed_count, len(images_rows)

        for folder in folders_to_process:
            rows = by_folder[folder]
            yield f"Processing folder: {folder} ({len(rows)} images)...", processed_count, len(images_rows)
            
            # Sort by Time
            rows_with_time = []
            for r in rows:
                t = self._get_image_time(r)
                rows_with_time.append((r, t))
            
            rows_with_time.sort(key=lambda x: x[1])
            
            # Split by Time Gap
            time_batches = []
            if not rows_with_time: continue
            
            current_batch = [rows_with_time[0]]
            
            for i in range(1, len(rows_with_time)):
                prev_row, prev_time = rows_with_time[i-1]
                curr_row, curr_time = rows_with_time[i]
                
                if (curr_time - prev_time) > time_gap_seconds:
                    time_batches.append(current_batch)
                    current_batch = []
                
                current_batch.append((curr_row, curr_time))
            
            if current_batch:
                time_batches.append(current_batch)
                
            folder_stacks = 0
            
            for b_idx, batch in enumerate(time_batches):
                if len(batch) < 2:
                    continue
                    
                # Extract features for this batch
                batch_paths = []
                batch_ids = []
                for r, t in batch:
                    thumb = r['thumbnail_path']
                    p = thumb if (thumb and os.path.exists(thumb)) else r['file_path']
                    
                    if p and os.path.exists(p):
                        batch_paths.append(p)
                        batch_ids.append(r['id'])
                
                if len(batch_paths) < 2:
                    continue
                    
                features, valid_indices = self.extract_features(batch_paths)
                
                if len(features) < 2:
                    continue
                
                # Cluster
                clustering = AgglomerativeClustering(
                    n_clusters=None,
                    distance_threshold=distance_threshold,
                    metric='cosine',
                    linkage='average'
                )
                labels = clustering.fit_predict(features)
                
                local_clusters = {}
                for i, lbl in enumerate(labels):
                    orig_idx = valid_indices[i] 
                    img_id = batch_ids[orig_idx]
                    
                    if lbl not in local_clusters:
                        local_clusters[lbl] = []
                    local_clusters[lbl].append(img_id)
                    
                # Collect stacks for this batch
                batch_stacks_data = [] # List of dicts
                
                for lbl, img_ids in local_clusters.items():
                    if len(img_ids) < 2:
                        continue
                        
                    # Find best image
                    # Use provided scores OR fetch? Rows have score_general
                    id_to_score = {}
                    for r, t in batch:
                         id_to_score[r['id']] = r['score_general'] if r['score_general'] else 0
                    
                    best_id = img_ids[0]
                    max_score = -1.0
                    for mid in img_ids:
                        s = id_to_score.get(mid, 0)
                        if s > max_score:
                            max_score = s
                            best_id = mid
                            
                    # Name based on Time? or Folder?
                    # Stack (Time)
                    timestamp = datetime.datetime.fromtimestamp(batch[0][1]).strftime("%H:%M")
                    s_name = f"Stack {os.path.basename(folder)} {timestamp} #{lbl}"
                    
                    batch_stacks_data.append({
                        'name': s_name,
                        'best_image_id': best_id,
                        'image_ids': img_ids
                    })
                    
                    folder_stacks += 1
                    total_clusters += 1
                
                # Execute batch for this time-group
                if batch_stacks_data:
                    db.create_stacks_batch(batch_stacks_data)
                    
            # Mark as processed
            db.mark_folder_clustered(folder)
            processed_count += len(rows)
            yield f"Finished {folder}. Created {folder_stacks} stacks.", processed_count, len(images_rows)
            
        yield f"Done! Processed {processed_count} images. Total Stacks: {db.get_stack_count()}", len(images_rows), len(images_rows)

