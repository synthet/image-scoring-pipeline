
import os
import sys
import json
import shutil
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np

# Add project root to path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scripts.python.run_all_musiq_models import MultiModelMUSIQ

def test_smart_patching():
    print("Testing smart patching...")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Created temp directory: {temp_dir}")
    
    try:
        # Create a dummy image
        img_name = "test_patch_image.jpg"
        img_path = os.path.join(temp_dir, img_name)
        img = Image.fromarray(np.random.randint(0, 255, (800, 600, 3), dtype=np.uint8))
        img.save(img_path)
        
        # Create a "legacy" v2.3.2 JSON file without thumbnail
        json_name = "test_patch_image.json"
        json_path = os.path.join(temp_dir, json_name)
        legacy_data = {
            "version": "2.3.2",
            "image_path": img_path,
            "image_name": img_name,
            "models": {},
            "summary": {}
        }
        
        with open(json_path, 'w') as f:
            json.dump(legacy_data, f)
            
        print("Created legacy v2.3.2 JSON without thumbnail")
        
        # Initialize scorer
        scorer = MultiModelMUSIQ()
        
        # Run is_already_processed check - this should trigger the patch
        # Note: We need to pass the directory containing the JSON
        print("Running is_already_processed check...")
        is_processed = scorer.is_already_processed(img_path, temp_dir)
        
        if is_processed:
            print("SUCCESS: Returned True (processed/patched)")
        else:
            print("FAILED: Returned False (re-process required)")
            
        # Verify JSON was updated
        with open(json_path, 'r') as f:
            updated_data = json.load(f)
            
        if updated_data.get("version") == "2.5.0":
            print("SUCCESS: Version updated to 2.5.0")
        else:
            print(f"FAILED: Version not updated, got {updated_data.get('version')}")
            
        if "thumbnail" in updated_data and updated_data["thumbnail"].startswith("data:image/jpeg;base64,"):
            print("SUCCESS: Thumbnail added to JSON")
        else:
            print("FAILED: Thumbnail not added to JSON")
            
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print("Cleaned up temp directory")

if __name__ == "__main__":
    test_smart_patching()
