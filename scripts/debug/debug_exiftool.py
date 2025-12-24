
import subprocess
import shutil
import os

def debug_exiftool():
    # File from logs
    target_file = "/mnt/d/Photos/Z8/180-600mm/2025/2025-11-16/DSC_6007.NEF"
    
    print(f"Checking for exiftool in path: {shutil.which('exiftool')}")
    
    if not os.path.exists(target_file):
        # Try windows path mapping if run from windows python
        if target_file.startswith("/mnt/d/"):
             target_file = target_file.replace("/mnt/d/", "D:/")
             
    if not os.path.exists(target_file):
        print(f"File not found: {target_file}")
        # Try to find any Z8 file nearby
        # assuming d:\Photos\Z8\180-600mm\2025\2025-11-16 exists
        dir_path = os.path.dirname(target_file)
        if os.path.exists(dir_path):
             print(f"Directory exists: {dir_path}")
             files = os.listdir(dir_path)
             z8_files = [f for f in files if f.upper().endswith('.NEF')]
             if z8_files:
                 target_file = os.path.join(dir_path, z8_files[0])
                 print(f"Using alternative file: {target_file}")

    print(f"Target File: {target_file}")
    
    cmd = ['exiftool', '-Compression', '-s', '-S', target_file]
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
        print(f"Return Code: {result.returncode}")
        print(f"Stdout: '{result.stdout}'")
        print(f"Stderr: '{result.stderr}'")
        
        compression = result.stdout.strip()
        print(f"Parsed Compression: '{compression}'")
        
        if "Nikon HE" in compression:
            print("MATCH: Nikon HE detected!")
        else:
            print("NO MATCH: Nikon HE not found in string.")
            
    except Exception as e:
        print(f"Execution failed: {e}")

if __name__ == "__main__":
    debug_exiftool()
