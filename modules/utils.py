import hashlib
import os
import platform
import re
from PIL import Image, ImageOps

def add_border_to_image(image_path, color='gray', border=10):
    """
    Loads an image (or path) and adds a colored border.
    Returns a PIL Image object.
    """
    try:
        if isinstance(image_path, str):
            # Resolve path if needed
            local_path = convert_path_to_local(image_path)
            if not os.path.exists(local_path):
                # Placeholder or error
                return None
            img = Image.open(local_path)
        else:
            img = image_path
            
        # Add border
        # ImageOps.expand adds border, but we want it inside or outside?
        # Outside is safer to preserve content.
        img_with_border = ImageOps.expand(img, border=border, fill=color)
        return img_with_border
    except Exception as e:
        print(f"Error adding border to {image_path}: {e}")
        return None

def convert_path_to_local(path):
    """
    Converts a path to the local OS format.
    Specifically handles WSL paths (/mnt/c/...) when running on Windows.
    """
    system = platform.system()
    
    if system == "Windows":
        # Handle WSL paths (forward and backslashes)
        # Normalize to forward slashes for checking
        p_str = path.replace('\\', '/')
        if p_str.startswith("/mnt/"):
            # /mnt/d/Description -> D:/Description
            parts = p_str.split('/')
            if len(parts) > 2 and len(parts[2]) == 1:
                drive = parts[2].upper()
                rest = "/".join(parts[3:])
                return f"{drive}:/{rest}"
    elif system == "Linux":
         # Handle Windows paths on WSL
         # D:\Foo -> /mnt/d/Foo
         # Check for D:\ or D:/
         match = re.match(r'^([a-zA-Z]):[\\\/](.*)', path)
         if match:
             drive = match.group(1).lower()
             rest = match.group(2).replace('\\', '/')
             return f"/mnt/{drive}/{rest}"
         
         # Fallback: maintain forward slashes for Linux
         if '\\' in path:
             path = path.replace('\\', '/')
    
    return path

def convert_path_to_wsl(path):
    """
    Converts a Windows path to WSL format.
    D:/Photos/... -> /mnt/d/Photos/...
    """
    # Check for D:\ or D:/
    match = re.match(r'^([a-zA-Z]):[\\\/](.*)', path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace('\\', '/')
        return f"/mnt/{drive}/{rest}"
    return path

def compute_file_hash(file_path, algorithm='sha256', chunk_size=8192):
    """
    Computes the hash of a file using the specified algorithm (default: sha256).
    Reads the file in chunks to handle large files efficiently.
    """
    # Try resolving path
    if not os.path.exists(file_path):
        resolved_path = convert_path_to_local(file_path)
        if os.path.exists(resolved_path):
            file_path = resolved_path
        else:
            return None # Still not found

    try:
        if algorithm == 'sha256':
            hasher = hashlib.sha256()
        elif algorithm == 'md5':
            hasher = hashlib.md5()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error computing hash for {file_path}: {e}")
        return None
