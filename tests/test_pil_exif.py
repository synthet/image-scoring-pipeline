import os
import datetime

import pytest
from PIL import Image

pytestmark = [pytest.mark.sample_data]


def _get_test_path() -> str | None:
    # Prefer existing env vars used by other sample-data tests in this repo.
    return (
        os.environ.get("IMAGE_SCORING_TEST_RAW_FILE")
        or os.environ.get("IMAGE_SCORING_TEST_PIL_EXIF_FILE")
    )


def test_pil_exif_smoke():
    """
    Smoke-test that Pillow can open the sample file and that EXIF accessors don't crash.

    This test is intentionally gated on a user-provided sample file path via env var(s),
    because committing RAW files to the repo is not expected.
    """
    path = _get_test_path()
    if not path:
        pytest.skip(
            "Set IMAGE_SCORING_TEST_RAW_FILE (or IMAGE_SCORING_TEST_PIL_EXIF_FILE) to run"
        )
    if not os.path.exists(path):
        pytest.skip(f"Sample file not found: {path}")

    try:
        with Image.open(path) as img:
            # Accessors should not raise
            _ = img.format
            _ = img.info

            exif = img.getexif()
            if exif:
                _ = exif.get(306)  # DateTime
                _ = exif.get(36867)  # DateTimeOriginal

            # Some Pillow formats expose _getexif; this is optional.
            if hasattr(img, "_getexif"):
                _ = img._getexif()  # noqa: SLF001
    except Exception as e:
        pytest.fail(f"Pillow EXIF smoke test failed: {e}")

    # Basic filesystem timestamps should be readable (platform-dependent semantics).
    _ = datetime.datetime.fromtimestamp(os.path.getctime(path))
    _ = datetime.datetime.fromtimestamp(os.path.getmtime(path))
