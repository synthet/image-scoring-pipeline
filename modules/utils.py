import hashlib
import os
import platform

def convert_path_to_local(path):
    """
    Converts a path to the local OS format.
    Specifically handles WSL paths (/mnt/c/...) when running on Windows.
    """
    system = platform.system()
    
    if system == "Windows":
        # Handle WSL paths
        if path.startswith("/mnt/"):
            # /mnt/d/Description -> D:/Description
            parts = path.split('/')
            if len(parts) > 2 and len(parts[2]) == 1:
                drive = parts[2].upper()
                rest = "/".join(parts[3:])
                return f"{drive}:/{rest}"
    
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
