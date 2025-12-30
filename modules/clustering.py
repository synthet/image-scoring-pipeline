
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

# Default cache directory for persisted feature vectors
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'thumbnails', 'feature_cache')


class ClusteringEngine:
    def __init__(self, cache_dir=None):
        self.model = None
        self.feature_cache = {}  # In-memory cache (hash -> feature vector)
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._ensure_cache_dir()
        self._load_cache()

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            logging.info(f"Created feature cache directory: {self.cache_dir}")

    def _get_cache_file(self):
        """Returns path to the cache file."""
        return os.path.join(self.cache_dir, 'feature_cache.npz')

    def _load_cache(self):
        """Load persisted feature cache from disk."""
        cache_file = self._get_cache_file()
        if os.path.exists(cache_file):
            try:
                data = np.load(cache_file, allow_pickle=True)
                # Load the cache dict from the npz file
                if 'cache' in data:
                    self.feature_cache = data['cache'].item()
                    logging.info(f"Loaded {len(self.feature_cache)} cached feature vectors from disk.")
                data.close()
            except Exception as e:
                logging.warning(f"Failed to load feature cache: {e}")
                self.feature_cache = {}

    def _save_cache(self):
        """Persist feature cache to disk."""
        cache_file = self._get_cache_file()
        try:
            np.savez_compressed(cache_file, cache=self.feature_cache)
            logging.debug(f"Saved {len(self.feature_cache)} feature vectors to cache.")
        except Exception as e:
            logging.error(f"Failed to save feature cache: {e}")

    def _get_image_hash(self, file_path):
        """Get image hash from database for cache key."""
        details = db.get_image_details(file_path)
        if details and details.get('image_hash'):
            return details['image_hash']
        return None

    def load_model(self):
        if self.model is None:
            # Load MobileNetV2, exclude top layer, use global average pooling
            self.model = MobileNetV2(weights='imagenet', include_top=False, pooling='avg')
            logging.info("Clustering Model (MobileNetV2) loaded.")

    def extract_features(self, image_paths):
        """
        Extract features for a list of image paths.
        Uses persisted cache when available.
        Returns numpy array of features.
        """
        self.load_model()
        
        features_list = []
        valid_indices = []  # Track which images were successfully processed
        
        # Separate cached vs uncached images
        uncached_paths = []
        uncached_indices = []
        path_to_hash = {}
        
        for i, path in enumerate(image_paths):
            if not os.path.exists(path):
                continue
            
            # Get hash for cache lookup
            img_hash = self._get_image_hash(path)
            path_to_hash[path] = img_hash
            
            if img_hash and img_hash in self.feature_cache:
                # Use cached feature
                features_list.append(self.feature_cache[img_hash])
                valid_indices.append(i)
            else:
                # Need to extract
                uncached_paths.append(path)
                uncached_indices.append(i)
        
        # Process uncached images in batches
        if uncached_paths:
            batch_images = []
            batch_paths = []
            batch_indices = []
            # Load batch size from config
            from modules import config
            processing_config = config.get_config_section('processing')
            batch_size = processing_config.get('clustering_batch_size', 32)
            new_features = []
            
            for idx, path in zip(uncached_indices, uncached_paths):
                try:
                    # Load image, resize to 224x224
                    img = keras_image.load_img(path, target_size=(224, 224))
                    x = keras_image.img_to_array(img)
                    x = preprocess_input(x)
                    batch_images.append(x)
                    batch_paths.append(path)
                    batch_indices.append(idx)
                    
                    if len(batch_images) >= batch_size:
                        batch_arr = np.array(batch_images)
                        preds = self.model.predict(batch_arr, verbose=0)
                        
                        # Cache and collect results
                        for j, (p, feat) in enumerate(zip(batch_paths, preds)):
                            h = path_to_hash.get(p)
                            if h:
                                self.feature_cache[h] = feat
                            new_features.append((batch_indices[j], feat))
                        
                        batch_images = []
                        batch_paths = []
                        batch_indices = []
                        
                except Exception as e:
                    logging.error(f"Error extracting features for {path}: {e}")
            
            # Process remaining batch
            if batch_images:
                batch_arr = np.array(batch_images)
                preds = self.model.predict(batch_arr, verbose=0)
                
                for j, (p, feat) in enumerate(zip(batch_paths, preds)):
                    h = path_to_hash.get(p)
                    if h:
                        self.feature_cache[h] = feat
                    new_features.append((batch_indices[j], feat))
            
            # Add new features to results in original index order
            for orig_idx, feat in new_features:
                features_list.append(feat)
                valid_indices.append(orig_idx)
            
            # Persist cache to disk after extraction
            if new_features:
                self._save_cache()
                logging.info(f"Cached {len(new_features)} new feature vectors. Total cache size: {len(self.feature_cache)}")
        
        # Sort by original index to maintain order consistency
        if features_list:
            sorted_pairs = sorted(zip(valid_indices, features_list), key=lambda x: x[0])
            valid_indices = [p[0] for p in sorted_pairs]
            features_list = [p[1] for p in sorted_pairs]
        
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

    def cluster_images(self, distance_threshold=None, time_gap_seconds=None, force_rescan=None, target_folder=None):
        """
        Main function to load images from DB, cluster them, and update DB.
        Enforces: 1. Folder Isolation 2. Time Gap Splitting 3. Persistence
        """
        import datetime
        import json
        from itertools import groupby
        from modules import config
        
        # Load defaults from config if not provided
        if distance_threshold is None:
            clustering_config = config.get_config_section('clustering')
            distance_threshold = clustering_config.get('default_threshold', 0.15)
        if time_gap_seconds is None:
            clustering_config = config.get_config_section('clustering')
            time_gap_seconds = clustering_config.get('default_time_gap', 120)
        if force_rescan is None:
            clustering_config = config.get_config_section('clustering')
            force_rescan = clustering_config.get('force_rescan_default', False)
        
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
            if target_folder:
                # Clear stacks only for the target folder (targeted re-clustering)
                success, msg = db.clear_stacks_in_folder(target_folder)
                if success:
                    processed_folders.discard(os.path.normpath(target_folder))
                    yield f"Force Rescan: {msg}", 0, len(images_rows)
                else:
                    yield f"Warning: {msg}", 0, len(images_rows)
            else:
                # Global force rescan - clear everything
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
                # Calculate overall progress for this folder
                folder_progress = processed_count + (len(rows) * (b_idx / len(time_batches)))
                yield f"Processing folder: {folder} - Batch {b_idx+1}/{len(time_batches)}", folder_progress, len(images_rows)

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

