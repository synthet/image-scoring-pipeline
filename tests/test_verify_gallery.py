
import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the gallery generator module directly to test its functions if possible, 
# or use subprocess to run it.
from scripts.python.gallery_generator import generate_html_with_embedded_data

def test_gallery_thumbnail():
    print("Testing gallery thumbnail support...")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    print(f"Created temp directory: {temp_dir}")
    
    try:
        # Create dummy image data with thumbnail
        dummy_data = [
            {
                "image_path": "test_image.jpg",
                "image_name": "test_image",
                "thumbnail": "data:image/jpeg;base64,TEST_THUMBNAIL_DATA",
                "summary": {
                    "average_normalized_score": 0.85,
                    "advanced_scoring": {
                        "final_robust_score": 0.85
                    }
                },
                "models": {
                    "spaq": {"normalized_score": 0.9},
                    "ava": {"normalized_score": 0.8}
                }
            }
        ]
        
        output_path = os.path.join(temp_dir, "test_gallery.html")
        generate_html_with_embedded_data(dummy_data, output_path)
        
        if not os.path.exists(output_path):
            print("FAILED: Gallery HTML not created")
            return
            
        print("Gallery HTML created successfully")
        
        # Check content
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if "data:image/jpeg;base64,TEST_THUMBNAIL_DATA" in content:
            print("SUCCESS: Base64 thumbnail found in HTML")
        else:
            print("FAILED: Base64 thumbnail NOT found in HTML")
            # print(content[:500]) # Debug
            
        # Check fallback logic existence (string check)
        if "this.src = 'test_image.jpg'" in content or "this.src = '${imagePath}'" in content or "this.src = imagePath" not in content: 
             # The template logic is: const imageSrc = image.thumbnail ? image.thumbnail : imagePath;
             # And onerror="if (this.src !== '${imagePath}') this.src = '${imagePath}'; ...
             
             if "if (this.src !== 'test_image.jpg') this.src = 'test_image.jpg'" in content:
                 print("SUCCESS: Fallback logic found in HTML")
             else:
                 print("WARNING: Exact fallback logic string not found, check implementation")
                 
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print("Cleaned up temp directory")

if __name__ == "__main__":
    test_gallery_thumbnail()
