import os
import sys

import pytest
from PIL import Image

pytestmark = [pytest.mark.wsl, pytest.mark.sample_data]

if sys.platform.startswith("win"):
    pytest.skip("WSL-only (pyiqa/torch environment expected in WSL)", allow_module_level=True)

pyiqa = pytest.importorskip("pyiqa")
torch = pytest.importorskip("torch")

# Load thumbnail (adjust path if needed for WSL)

def test_resolution_impact():
    thumb_path = os.environ.get(
        "IMAGE_SCORING_TEST_THUMBNAIL",
        "thumbnails/7904478152a1805d8e9bff7fa06ec600.jpg",
    )

    print(f"Testing with image: {thumb_path}")

    if not os.path.exists(thumb_path):
        pytest.skip(f"Thumbnail not found: {thumb_path}")

    try:
        metric = pyiqa.create_metric("liqe", device="cpu")
    except Exception as e:
        pytest.fail(f"Failed to load metric: {e}")

    # Score Original
    print("Scoring original thumbnail...")
    try:
        score_orig = metric(thumb_path).item()
        print(f"Original Score: {score_orig}")
    except Exception as e:
        pytest.fail(f"Error scoring original: {e}")

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
        if os.path.exists(large_path):
            os.remove(large_path)

    except Exception as e:
        pytest.fail(f"Error processing/scoring large image: {e}")

if __name__ == "__main__":
    test_resolution_impact()

