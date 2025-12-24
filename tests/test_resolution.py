import pyiqa
import torch
from PIL import Image
import sys
import os

# Load thumbnail (adjust path if needed for WSL)
# thumb_path = "/mnt/d/Projects/image-scoring/thumbnails/7904478152a1805d8e9bff7fa06ec600.jpg"
# Using arguments or hardcoded for now
thumb_path = sys.argv[1] if len(sys.argv) > 1 else "thumbnails/7904478152a1805d8e9bff7fa06ec600.jpg"

print(f"Testing with image: {thumb_path}")

try:
    metric = pyiqa.create_metric('liqe', device='cpu')
except Exception as e:
    print(f"Failed to load metric: {e}")
    sys.exit(1)

# Score Original
print("Scoring original thumbnail...")
try:
    score_orig = metric(thumb_path).item()
    print(f"Original Score: {score_orig}")
except Exception as e:
    print(f"Error scoring original: {e}")

# Upscale
try:
    img = Image.open(thumb_path)
    # Target size similar to 24MP RAW
    img_large = img.resize((4000, 3000), Image.BICUBIC)
    large_path = "temp_large_liqe_test.jpg"
    img_large.save(large_path, quality=95)

    # Score Large
    print(f"Scoring large image ({large_path})...")
    score_large = metric(large_path).item()
    print(f"Large Score: {score_large}")

    # Cleanup
    # if os.path.exists(large_path):
    #     os.remove(large_path)

except Exception as e:
    print(f"Error processing/scoring large image: {e}")
