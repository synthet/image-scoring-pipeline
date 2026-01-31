import sys
import os
import exifread


def test_exif_reading():
    TARGET_FILE = r"D:/Photos/Z8/180-600mm/2025/2025-11-01/DSC_3953.NEF"

    if not os.path.exists(TARGET_FILE):
        print("File not found")
        # For pytest, we skip instead of exit
        if "pytest" in sys.modules:
            import pytest
            pytest.skip("Test file not found")
        else:
            sys.exit(1)

    print(f"Testing {TARGET_FILE} with exifread")

    try:
        with open(TARGET_FILE, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            print(f"Found {len(tags)} tags")
            
            # Check standard EXIF tags for date
            keys_to_check = ['EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime']
            for k in keys_to_check:
                if k in tags:
                    print(f"{k}: {tags[k]}")
                    
    except Exception as e:
        print(f"Error: {e}")
        if "pytest" in sys.modules:
            pytest.fail(f"exifread processing failed: {e}")

if __name__ == "__main__":
    test_exif_reading()

