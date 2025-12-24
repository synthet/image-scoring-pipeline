
import os
import sys
import subprocess
from PIL import Image
import numpy as np

def test_liqe_script():
    print("Testing LIQE script...")
    
    # Create dummy image
    img_name = "test_liqe.jpg"
    img = Image.fromarray(np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8))
    img.save(img_name)
    
    script_path = os.path.join("scripts", "python", "score_liqe.py")
    if not os.path.exists(script_path):
        script_path = os.path.join(os.getcwd(), "scripts", "python", "score_liqe.py")
        
    cmd = [sys.executable, script_path, img_name, "--json"]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("SUCCESS: LIQE script ran successfully")
        else:
            print("FAILED: LIQE script returned error code")
            
    except Exception as e:
        print(f"FAILED: Exception running script: {e}")
    finally:
        if os.path.exists(img_name):
            os.remove(img_name)

if __name__ == "__main__":
    test_liqe_script()
