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
        
        if is_raw:
            # Try rawpy first
            if HAS_RAWPY:
                try:
                    with rawpy.imread(str(image_path)) as raw:
                        rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
                        img = Image.fromarray(rgb)
                except Exception as e:
                    # Fallback for Z8/HE* files
                    # print(f"Rawpy failed for {image_path}, trying dcraw: {e}")
                    img = None
            else:
                img = None

            # Fallback to dcraw if rawpy failed or missing
            if img is None:
                import subprocess
                import shutil
                import io
                
                if shutil.which("dcraw"):
                    # dcraw -e -c > stdout (Extract embedded thumbnail)
                    # This is much faster and avoids decoding issues with Z8 HE* files
                    cmd = ["dcraw", "-e", "-c", str(image_path)]
                    res = subprocess.run(cmd, capture_output=True, text=False) # Binary output
                    if res.returncode == 0 and len(res.stdout) > 0:
                        try:
                            # It is usually a JPEG
                            img = Image.open(io.BytesIO(res.stdout))
                            img.load() # Verify validity
                        except Exception as e:
                            # If extraction failed, maybe try full decode?
                            # But if -e failed, likely file is really weird.
                            # We can try fallback to Magick below.
                            img = None
                            pass
            
            if img is None:
                # Last resort: Magick?
                 if shutil.which("magick"):
                     # magick input -resize 512x512 output
                     # We can write directly to thumb_path
                     cmd = ["magick", str(image_path), "-resize", "512x512", "-quality", "85", thumb_path]
                     res = subprocess.run(cmd, capture_output=True)
                     if res.returncode == 0:
                         return thumb_path
                     # If failed, raise error
                     raise Exception("All RAW conversion methods failed")
                 else:
                     raise Exception("All RAW conversion methods failed")
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

PREVIEW_DIR = str(PROJECT_ROOT / "thumbnails" / "previews")

def ensure_preview_dir():
    if not os.path.exists(PREVIEW_DIR):
        try:
            os.makedirs(PREVIEW_DIR)
        except OSError:
            pass

def get_preview_filename(image_path):
    path_hash = hashlib.md5(str(image_path).encode('utf-8')).hexdigest()
    return os.path.join(PREVIEW_DIR, f"{path_hash}.jpg")

def generate_preview(image_path):
    """
    Generates or extracts a high-resolution preview for the image.
    Returns the path to the preview image (JPEG).
    """
    ensure_preview_dir()
    
    # If not raw, return original (assuming browser compatible)
    ext = Path(image_path).suffix.lower()
    if ext not in ['.nef', '.cr2', '.dng', '.arw', '.orf']:
        return image_path
        
    preview_path = get_preview_filename(image_path)
    if os.path.exists(preview_path):
        return preview_path
        
    print(f"Generating preview for {image_path}...")
    
    # Try extracting embedded JPEG via dcraw first (fastest, high res)
    import subprocess
    import shutil
    import io
    
    img = None
    
    if shutil.which("dcraw"):
        try:
            # -e extracts embedded thumb/preview
            cmd = ["dcraw", "-e", "-c", str(image_path)]
            res = subprocess.run(cmd, capture_output=True)
            if res.returncode == 0 and len(res.stdout) > 0:
                try:
                    # Check if valid image
                    img = Image.open(io.BytesIO(res.stdout))
                    img.load()
                    # If it's very small, discard it? 
                    # Some RAWs have tiny embedded thumbs. 
                    # Full HD is usually > 1600 width. 
                    # Let's say if width > 1000, we accept it.
                    if img.width > 1000:
                        img.save(preview_path, "JPEG", quality=90)
                        return preview_path
                    else:
                        print(f"Embedded preview too small: {img.size}")
                        img = None
                except Exception as e:
                    print(f"Failed to read embedded preview: {e}")
                    img = None
        except Exception as e:
            print(f"dcraw extraction failed: {e}")
            
    # Fallback to Rawpy (Full decode)
    try:
        import rawpy
        with rawpy.imread(str(image_path)) as raw:
            # postprocess gives full size numpy array
            rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
            img = Image.fromarray(rgb)
            img.save(preview_path, "JPEG", quality=90)
            return preview_path
    except Exception as e:
        print(f"rawpy decode failed: {e}")
        
    return None
