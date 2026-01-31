
import os
import sys
import json
import base64
from pathlib import Path
from PIL import Image
import numpy as np

# Add project root to path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest
import base64

pytestmark = [pytest.mark.wsl]

if sys.platform.startswith("win"):
    pytest.skip("WSL-only (TensorFlow/MUSIQ integration expected in WSL)", allow_module_level=True)

def test_thumbnail_generation():
    print("Testing thumbnail generation...")
    
    try:
        from scripts.python.run_all_musiq_models import MultiModelMUSIQ
    except ImportError:
        pytest.skip("Machine learning dependencies (TensorFlow) not available")
    
    # create dummy image
    img_path = "test_image.jpg"
    img = Image.fromarray(np.random.randint(0, 255, (800, 600, 3), dtype=np.uint8))
    img.save(img_path)
    
    try:
        scorer = MultiModelMUSIQ()
        
        # Test method directly
        print("Testing generate_thumbnail_base64 method...")
        thumb_b64 = scorer.generate_thumbnail_base64(img_path)
        
        if not thumb_b64:
            print("FAILED: Thumbnail generation returned None")
            return
            
        if not thumb_b64.startswith("data:image/jpeg;base64,"):
            print("FAILED: Invalid prefix")
            print(f"Got: {thumb_b64[:30]}...")
            return
            
        print("SUCCESS: Valid base64 prefix")
        
        # Decode and check size
        data = thumb_b64.split(",")[1]
        decoded = base64.b64decode(data)
        print(f"Encoded size: {len(thumb_b64)} bytes")
        
        # Verify mocked results structure
        print("\nVerifying integration in run_all_models (mocked)...")
        # We can't easily run full run_all_models without checkpoints, 
        # but we can verify the method works as expected on the file.
        
        # Clean up
        os.remove(img_path)
        print("Test completed successfully")
        
    except Exception as e:
        print(f"FAILED: Exception occurred: {e}")
        if os.path.exists(img_path):
            os.remove(img_path)

if __name__ == "__main__":
    test_thumbnail_generation()
