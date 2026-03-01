import os
import platform
import re
from pathlib import Path
from PIL import Image
import hashlib
import subprocess
import shutil
import io
from typing import Optional

# Anchor to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
THUMB_DIR = str(PROJECT_ROOT / "thumbnails")
MAX_SIZE = (512, 512)

def ensure_thumb_dir():
    os.makedirs(THUMB_DIR, exist_ok=True)

def extract_embedded_jpeg(image_path: str, min_size: int = 100) -> Optional[Image.Image]:
    """
    Extract embedded JPEG preview from RAW file.
    Tries ExifTool first (robust for modern formats like Z8/Z9 HE*), then dcraw (fast).
    Returns PIL Image or None if extraction fails.
    
    Args:
        image_path: Path to RAW file
        min_size: Minimum file size in bytes to accept (default 100 bytes)
    
    Returns:
        PIL Image if successful, None otherwise
    """
    image_path_str = str(image_path)
    
    # Try ExifTool first (most robust for modern Nikon formats)
    if shutil.which("exiftool"):
        try:
            # Try -JpgFromRaw first (full-size embedded JPEG)
            cmd = ['exiftool', '-b', '-JpgFromRaw', image_path_str]
            result = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            
            if result.returncode == 0 and len(result.stdout) > min_size:
                if result.stdout.startswith(b'\xff\xd8'):  # JPEG header
                    try:
                        img = Image.open(io.BytesIO(result.stdout))
                        img.load()  # Verify validity
                        return img
                    except Exception:
                        pass
            
            # Try -PreviewImage if JpgFromRaw fails or is missing
            cmd = ['exiftool', '-b', '-PreviewImage', image_path_str]
            result = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            
            if result.returncode == 0 and len(result.stdout) > min_size:
                if result.stdout.startswith(b'\xff\xd8'):  # JPEG header
                    try:
                        img = Image.open(io.BytesIO(result.stdout))
                        img.load()  # Verify validity
                        return img
                    except Exception:
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
    
    # Fallback to dcraw -e (fast embedded thumbnail extraction)
    if shutil.which("dcraw"):
        try:
            cmd = ["dcraw", "-e", "-c", image_path_str]
            res = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            if res.returncode == 0 and len(res.stdout) > min_size:
                if res.stdout.startswith(b'\xff\xd8'):  # JPEG header
                    try:
                        img = Image.open(io.BytesIO(res.stdout))
                        img.load()  # Verify validity
                        return img
                    except Exception:
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass
    
    return None

def _thumb_hash(image_path):
    return hashlib.md5(str(image_path).encode('utf-8')).hexdigest()


def get_thumb_path(image_path):
    """
    Returns the expected path of the thumbnail for a given image.
    Uses MD5 of the path with a 2-char prefix subdirectory (git-style).
    Layout: thumbnails/{hash[:2]}/{hash}.jpg
    Falls back to legacy flat path if it exists and nested does not.
    """
    path_hash = _thumb_hash(image_path)
    prefix = path_hash[:2]

    nested = os.path.join(THUMB_DIR, prefix, f"{path_hash}.jpg")
    if os.path.exists(nested):
        return nested

    legacy = os.path.join(THUMB_DIR, f"{path_hash}.jpg")
    if os.path.exists(legacy):
        return legacy

    subdir = os.path.join(THUMB_DIR, prefix)
    os.makedirs(subdir, exist_ok=True)
    return nested


def thumb_path_to_win(wsl_path):
    """Deterministic WSL-to-Windows conversion for thumbnail paths."""
    if not wsl_path:
        return None
    p = wsl_path.replace('\\', '/')
    m = re.match(r'^/mnt/([a-zA-Z])/(.*)', p)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace('/', '\\')
        return f"{drive}:\\{rest}"
    return wsl_path.replace('/', '\\')


def thumb_path_to_wsl(win_path):
    """Deterministic Windows-to-WSL conversion for thumbnail paths."""
    if not win_path:
        return None
    m = re.match(r'^([a-zA-Z]):[\\\/](.*)', win_path)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace('\\', '/')
        return f"/mnt/{drive}/{rest}"
    return win_path.replace('\\', '/')


def get_thumb_wsl(row):
    """
    Return the WSL/Linux thumbnail path from a DB row.
    Use this in code that runs inside WSL (Gradio server, ML inference, scoring).
    Falls back to converting thumbnail_path_win if thumbnail_path is empty.
    """
    wsl = _row_val(row, 'thumbnail_path')
    if wsl:
        return wsl
    win = _row_val(row, 'thumbnail_path_win')
    return thumb_path_to_wsl(win) if win else None


def get_thumb_win(row):
    """
    Return the native Windows thumbnail path from a DB row.
    Use this in code that runs on native Windows (Windows-only scripts, native UI).
    Falls back to converting thumbnail_path if thumbnail_path_win is empty.
    """
    win = _row_val(row, 'thumbnail_path_win')
    if win:
        return win
    wsl = _row_val(row, 'thumbnail_path')
    return thumb_path_to_win(wsl) if wsl else None


def get_local_thumb(row):
    """
    Auto-detect platform and return the appropriate thumbnail path.
    Prefer get_thumb_wsl() or get_thumb_win() for explicit intent.
    """
    if platform.system() == 'Windows':
        return get_thumb_win(row)
    return get_thumb_wsl(row)


def _row_val(row, col_name):
    """Read a column from a DB row (dict, Row, or keys()-supporting object)."""
    try:
        if hasattr(row, 'get'):
            return row.get(col_name)
        if hasattr(row, 'keys') and col_name in row.keys():
            return row[col_name]
    except Exception:
        pass
    return None

def generate_thumbnail(image_path):
    """
    Generates a thumbnail for the image if it doesn't exist.
    Returns the path to the thumbnail.
    
    For RAW files, prioritizes fast embedded JPEG extraction:
    ExifTool → dcraw (embedded) → rawpy (full decode) → ImageMagick
    """
    thumb_path = get_thumb_path(image_path)
    
    if os.path.exists(thumb_path):
        return thumb_path

    try:
        # Check if RAW file
        is_raw = Path(image_path).suffix.lower() in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']
        
        if is_raw:
            img = None
            
            # Priority 1: Extract embedded JPEG (fast - ExifTool or dcraw)
            img = extract_embedded_jpeg(image_path, min_size=1000)
            
            # Priority 2: Full RAW decode with rawpy (slow but high quality)
            if img is None:
                try:
                    import rawpy
                    with rawpy.imread(str(image_path)) as raw:
                        rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
                        img = Image.fromarray(rgb)
                except ImportError:
                    pass  # rawpy not available
                except Exception:
                    pass  # rawpy failed (e.g., Z8 HE* files)
            
            # Priority 3: ImageMagick as last resort
            if img is None:
                if shutil.which("magick"):
                    # ImageMagick can write directly to output path
                    cmd = ["magick", str(image_path), "-resize", "512x512", "-quality", "85", thumb_path]
                    res = subprocess.run(cmd, capture_output=True, timeout=30)
                    if res.returncode == 0 and os.path.exists(thumb_path):
                        return thumb_path
                
                # All methods failed
                raise Exception("All RAW conversion methods failed for thumbnail generation")
        else:
            # Standard image handling (non-RAW)
            img = Image.open(image_path)

        # Process and save thumbnail
        with img:
            # Convert to RGB if needed
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            img.thumbnail(MAX_SIZE)
            img.save(thumb_path, "JPEG", quality=85)
            
            # Copy EXIF orientation from original
            if is_raw and shutil.which("exiftool"):
                cmd = ["exiftool", "-TagsFromFile", str(image_path), "-Orientation", "-overwrite_original", thumb_path]
                subprocess.run(cmd, capture_output=True, timeout=10)
                
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
    
    For RAW files, prioritizes embedded JPEG extraction (ExifTool → dcraw),
    then falls back to full RAW decode if needed.
    """
    ensure_preview_dir()
    
    # If not raw, return original (assuming browser compatible)
    ext = Path(image_path).suffix.lower()
    if ext not in ['.nef', '.cr2', '.dng', '.arw', '.orf', '.nrw', '.cr3', '.rw2']:
        return image_path
        
    preview_path = get_preview_filename(image_path)
    if os.path.exists(preview_path):
        return preview_path
        
    print(f"Generating preview for {image_path}...")
    
    img = None
    
    # Priority 1: Extract embedded JPEG via ExifTool or dcraw (fast, high quality)
    img = extract_embedded_jpeg(image_path, min_size=1000)
    
    if img:
        # Check if preview is large enough (reject tiny thumbnails)
        # Full HD is usually > 1600 width, but we accept > 1000 for previews
        if img.width > 1000:
            try:
                img.save(preview_path, "JPEG", quality=90)
                
                # Copy EXIF orientation from original
                if shutil.which("exiftool"):
                    cmd = ["exiftool", "-TagsFromFile", str(image_path), "-Orientation", "-overwrite_original", preview_path]
                    subprocess.run(cmd, capture_output=True, timeout=10)
                
                return preview_path
            except Exception as e:
                print(f"Failed to save extracted preview: {e}")
                img = None
        else:
            print(f"Embedded preview too small: {img.size}, trying full decode...")
            img = None
    
    # Priority 2: Fallback to rawpy full decode (slow but best quality)
    if img is None:
        try:
            import rawpy
            with rawpy.imread(str(image_path)) as raw:
                # postprocess gives full size numpy array
                rgb = raw.postprocess(use_camera_wb=True, bright=1.0, user_sat=None)
                img = Image.fromarray(rgb)
                img.save(preview_path, "JPEG", quality=90)
                
                # Copy EXIF orientation from original
                if shutil.which("exiftool"):
                    cmd = ["exiftool", "-TagsFromFile", str(image_path), "-Orientation", "-overwrite_original", preview_path]
                    subprocess.run(cmd, capture_output=True, timeout=10)
                
                return preview_path
        except ImportError:
            print("rawpy not available for full decode")
        except Exception as e:
            print(f"rawpy decode failed: {e}")
        
    return None
