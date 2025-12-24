
import os
import sys
import platform

def check_rawpy():
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.platform()}")
    
    try:
        import rawpy
        print(f"rawpy version: {rawpy.__version__}")
        try:
            import libraw
            # rawpy doesn't expose libraw version directly usually, but let's check
            pass
        except:
            pass
    except ImportError:
        print("rawpy not installed!")
        return

    # Target file from logs
    # /mnt/d/Photos/Z8/180-600mm/2025/2025-11-16/DSC_5986.NEF
    # Windows: D:\Photos\Z8\180-600mm\2025\2025-11-16\DSC_5986.NEF
    
    candidates = [
        "/mnt/d/Photos/Z8/180-600mm/2025/2025-11-16/DSC_5986.NEF",
        "D:/Photos/Z8/180-600mm/2025/2025-11-16/DSC_5986.NEF",
        r"D:\Photos\Z8\180-600mm\2025\2025-11-16\DSC_5986.NEF"
    ]
    
    target_file = None
    for c in candidates:
        if os.path.exists(c):
            target_file = c
            break
            
    if not target_file:
        print("Could not find test file DSC_5986.NEF at expected locations.")
        # Try to search recursively in recent dirs? No, unsafe.
        return

    print(f"Testing file: {target_file}")
    
    try:
        with rawpy.imread(target_file) as raw:
            print("Successfully opened file!")
            print(f"Sizes: raw_pattern={raw.raw_pattern.shape} sizes={raw.sizes}")
            # Try minimal processing
            rgb = raw.postprocess(half_size=True)
            print("Successfully postprocessed (half size).")
    except Exception as e:
        print(f"FAILED to open/process: {type(e).__name__}: {e}")

if __name__ == "__main__":
    check_rawpy()
