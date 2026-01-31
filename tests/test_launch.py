import traceback
import sys
import os
import pytest

# Add current dir to path
sys.path.append(os.getcwd())

pytestmark = [pytest.mark.wsl]

if sys.platform.startswith("win"):
    pytest.skip("WSL-only (webui import requires TensorFlow stack in this repo)", allow_module_level=True)

def test_webui_import():
    """Test if webui can be imported and main function exists."""
    print("Attempting to import webui...")
    try:
        # If TensorFlow is missing/broken, skip rather than hard fail.
        try:
            import tensorflow  # noqa: F401
        except Exception as e:
            pytest.skip(f"TensorFlow not available/working: {e}")

        import webui
        assert hasattr(webui, 'main'), "webui module should have a main function"
        print("Import successful.")
    except Exception as e:
        pytest.fail(f"Failed to import webui: {e}")

if __name__ == "__main__":
    test_webui_import()

