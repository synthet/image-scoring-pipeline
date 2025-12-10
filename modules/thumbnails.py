import os
from pathlib import Path
from PIL import Image
import hashlib

# Anchor to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
THUMB_DIR = str(PROJECT_ROOT / "thumbnails")
MAX_SIZE = (512, 512)

def ensure_thumb_dir():
    if not os.path.exists(THUMB_DIR):
        os.makedirs(THUMB_DIR)

def get_thumb_path(image_path):
    """
    Returns the expected path of the thumbnail for a given image.
    Uses MD5 of the path to avoid filename collisions/length issues.
    """
    ensure_thumb_dir()
    path_hash = hashlib.md5(str(image_path).encode('utf-8')).hexdigest()
    return os.path.join(THUMB_DIR, f"{path_hash}.jpg")

def generate_thumbnail(image_path):
    """
    Generates a thumbnail for the image if it doesn't exist.
    Returns the path to the thumbnail.
    """
    thumb_path = get_thumb_path(image_path)
    
    if os.path.exists(thumb_path):
        return thumb_path
        
    # Check if raw
    try:
        import rawpy
        import imageio
        HAS_RAWPY = True
    except ImportError:
        HAS_RAWPY = False

    try:
        # RAW handling
        is_raw = Path(image_path).suffix.lower() in ['.nef', '.cr2', '.dng', '.arw', '.orf']
        
        if is_raw and HAS_RAWPY:
            with rawpy.imread(str(image_path)) as raw:
                rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
                img = Image.fromarray(rgb)
        else:
            # Standard image handling
            img = Image.open(image_path)

        with img:
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            img.thumbnail(MAX_SIZE)
            img.save(thumb_path, "JPEG", quality=85)
            return thumb_path
            
    except Exception as e:
        print(f"Error generating thumbnail for {image_path}: {e}")
        return None
