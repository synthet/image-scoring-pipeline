#!/usr/bin/env python3
"""
Test Model Sources - Verify all TensorFlow Hub and Kaggle Hub model paths

This script tests the availability and accessibility of all model sources
defined in run_all_musiq_models.py without actually loading the full models.
"""

import os
import sys
import argparse
from typing import Dict, Optional, Tuple

import pytest

pytestmark = [pytest.mark.wsl, pytest.mark.network]

# This module depends on TensorFlow tooling and is intended for WSL/Linux.
if sys.platform.startswith("win"):
    pytest.skip("WSL-only (TensorFlow/Kaggle model source checks)", allow_module_level=True)


# Test imports
if __name__ == "__main__":
    print("Testing imports...")
    try:
        import tensorflow as tf
        print(f"✓ TensorFlow: {tf.__version__}")
    except ImportError as e:
        print(f"✗ TensorFlow not available: {e}")
        sys.exit(1)

    try:
        import tensorflow_hub as hub
        print(f"✓ TensorFlow Hub available")
    except ImportError as e:
        print(f"✗ TensorFlow Hub not available: {e}")
        sys.exit(1)

    try:
        import kagglehub
        print(f"✓ Kaggle Hub available")
        KAGGLE_AVAILABLE = True
    except ImportError as e:
        print(f"⚠ Kaggle Hub not available: {e}")
        KAGGLE_AVAILABLE = False
else:
    # When imported by pytest, just try to import without exiting
    try:
        import tensorflow as tf
        import tensorflow_hub as hub
        import kagglehub
        KAGGLE_AVAILABLE = True
    except ImportError:
        KAGGLE_AVAILABLE = False



def _bool_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


# Model sources (from run_all_musiq_models.py v2.3.0)
# Get base directory for local checkpoints
base_dir = os.path.dirname(os.path.abspath(__file__))
checkpoint_dir = os.path.join(base_dir, "..", "models", "checkpoints")

MODEL_SOURCES = {
    "spaq": {
        "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
        "kaggle": "google/musiq/tensorFlow2/spaq",
        "local": os.path.join(checkpoint_dir, "spaq_ckpt.npz")
    },
    "ava": {
        "tfhub": "https://tfhub.dev/google/musiq/ava/1",
        "kaggle": "google/musiq/tensorFlow2/ava",
        "local": os.path.join(checkpoint_dir, "ava_ckpt.npz")
    },
    "vila": {
        "tfhub": "https://tfhub.dev/google/vila/image/1",
        "kaggle": "google/vila/tensorFlow2/image",
        "local": os.path.join(checkpoint_dir, "vila-tensorflow2-image-v1")
    }
}


def test_model_sources_table_is_well_formed():
    """Fast, no-network sanity check."""
    assert isinstance(MODEL_SOURCES, dict)
    assert MODEL_SOURCES, "MODEL_SOURCES should not be empty"

    for model_name, src in MODEL_SOURCES.items():
        assert isinstance(model_name, str) and model_name
        assert isinstance(src, dict)
        assert set(src.keys()) >= {"tfhub", "kaggle", "local"}


@pytest.mark.parametrize(
    "model_name,kaggle_path",
    [(mn, src["kaggle"]) for mn, src in MODEL_SOURCES.items() if src.get("kaggle")],
)
def test_kaggle_paths_have_expected_format(model_name: str, kaggle_path: str):
    """
    Format-only test (no download).
    Expected: org/model/framework/variant (>= 4 segments).
    """
    parts = kaggle_path.split("/")
    assert len(parts) >= 4, f"{model_name}: invalid kaggle path format: {kaggle_path}"


@pytest.mark.parametrize(
    "model_name,url",
    [(mn, src["tfhub"]) for mn, src in MODEL_SOURCES.items() if src.get("tfhub")],
)
def test_tfhub_urls_optional_network(model_name: str, url: str):
    """
    Optional network test.
    Enable with: IMAGE_SCORING_RUN_NETWORK_TESTS=1
    """
    if not _bool_env("IMAGE_SCORING_RUN_NETWORK_TESTS"):
        pytest.skip("Set IMAGE_SCORING_RUN_NETWORK_TESTS=1 to check TFHub URLs")

    success, msg = check_tfhub_url(model_name, url)
    assert success, msg


@pytest.mark.parametrize(
    "model_name,kaggle_path",
    [(mn, src["kaggle"]) for mn, src in MODEL_SOURCES.items() if src.get("kaggle")],
)
def test_kaggle_paths_optional_download(model_name: str, kaggle_path: str):
    """
    Optional Kaggle download test (uses cache if present).
    Enable with:
      - IMAGE_SCORING_RUN_NETWORK_TESTS=1
      - IMAGE_SCORING_RUN_KAGGLE_DOWNLOADS=1
    """
    if not _bool_env("IMAGE_SCORING_RUN_NETWORK_TESTS"):
        pytest.skip("Set IMAGE_SCORING_RUN_NETWORK_TESTS=1 to check Kaggle paths")
    if not _bool_env("IMAGE_SCORING_RUN_KAGGLE_DOWNLOADS"):
        pytest.skip("Set IMAGE_SCORING_RUN_KAGGLE_DOWNLOADS=1 to download Kaggle models")
    if not KAGGLE_AVAILABLE:
        pytest.skip("kagglehub not installed")
    if not check_kaggle_auth():
        pytest.skip("Kaggle auth not configured (~/.kaggle/kaggle.json)")

    success, msg = check_kaggle_path(model_name, kaggle_path, skip_download=False)
    assert success, msg




def check_kaggle_auth() -> bool:
    """Check if Kaggle authentication is configured."""
    kaggle_paths = [
        os.path.expanduser("~/.kaggle/kaggle.json"),
        os.path.expandvars("%USERPROFILE%/.kaggle/kaggle.json")
    ]
    
    for path in kaggle_paths:
        if os.path.exists(path):
            return True
    return False


def check_tfhub_url(model_name: str, url: str) -> Tuple[bool, str]:
    """
    Check if a TensorFlow Hub URL is accessible.
    
    Returns:
        (success, message)
    """
    if url is None:
        return False, "N/A - Not available on TF Hub"
    
    try:
        print(f"  Testing TF Hub: {url}")
        # Try to load model metadata (lighter than full model load)
        import tensorflow_hub as hub
        model = hub.load(url)
        
        # Quick signature check
        if hasattr(model, 'signatures'):
            sigs = list(model.signatures.keys())
            return True, f"✓ Accessible (signatures: {sigs})"
        else:
            return True, "✓ Accessible (loaded successfully)"
            
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "not found" in error_msg.lower():
            return False, f"✗ Not Found (404)"
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            return False, f"✗ Network Error"
        elif "timeout" in error_msg.lower():
            return False, f"✗ Timeout"
        else:
            return False, f"✗ Error: {error_msg[:50]}..."


def check_kaggle_path(model_name: str, path: str, skip_download: bool = False) -> Tuple[bool, str]:
    """
    Check if a Kaggle Hub path is accessible.
    
    Args:
        model_name: Name of the model
        path: Kaggle Hub path (e.g., "google/musiq/tensorFlow2/spaq")
        skip_download: If True, only check if path format is valid
    
    Returns:
        (success, message)
    """
    if not KAGGLE_AVAILABLE:
        return False, "✗ Kaggle Hub package not installed"
    
    if path is None:
        return False, "N/A - Not available on Kaggle Hub"
    
    try:
        import kagglehub
        print(f"  Testing Kaggle Hub: {path}")
        
        if skip_download:
            # Just validate path format
            parts = path.split("/")
            if len(parts) >= 4:  # Expected: org/model/framework/variant
                return True, f"⚠ Path format valid (download skipped)"
            else:
                return False, f"✗ Invalid path format"
        
        # Try to download (will use cache if already downloaded)
        model_path = kagglehub.model_download(path)
        
        # Verify downloaded path exists
        if os.path.exists(model_path):
            return True, f"✓ Accessible (cached at: {model_path[:50]}...)"
        else:
            return False, f"✗ Download succeeded but path not found"
            
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "not found" in error_msg.lower():
            return False, f"✗ Not Found (404)"
        elif "401" in error_msg or "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
            return False, f"✗ Authentication Required"
        elif "network" in error_msg.lower() or "connection" in error_msg.lower():
            return False, f"✗ Network Error"
        else:
            return False, f"✗ Error: {error_msg[:50]}..."


def check_local_checkpoint(model_name: str, path: str) -> Tuple[bool, str]:
    """
    Check if a local checkpoint exists and is accessible.
    
    Args:
        model_name: Name of the model
        path: Local file/directory path
    
    Returns:
        (success, message)
    """
    if path is None:
        return False, "N/A - No local checkpoint defined"
    
    try:
        print(f"  Testing Local: {path}")
        
        if os.path.exists(path):
            if os.path.isdir(path):
                # SavedModel directory
                saved_model_pb = os.path.join(path, "saved_model.pb")
                if os.path.exists(saved_model_pb):
                    file_size = os.path.getsize(saved_model_pb) / (1024 * 1024)  # MB
                    return True, f"✓ SavedModel found ({file_size:.1f} MB)"
                else:
                    return False, "✗ SavedModel directory incomplete"
            elif path.endswith('.npz'):
                # NumPy checkpoint file
                file_size = os.path.getsize(path) / (1024 * 1024)  # MB
                return True, f"✓ Checkpoint found ({file_size:.1f} MB)"
            else:
                return True, f"✓ File found"
        else:
            return False, f"✗ Not found (download from Google Cloud Storage)"
            
    except Exception as e:
        error_msg = str(e)
        return False, f"✗ Error: {error_msg[:50]}..."


def check_all_sources(test_kaggle: bool = True, skip_kaggle_download: bool = False, test_local: bool = True):
    """
    Check all model sources.
    
    Args:
        test_kaggle: Whether to test Kaggle Hub sources
        skip_kaggle_download: If True, only validate Kaggle paths without downloading
        test_local: Whether to test local checkpoints
    """
    print("\n" + "=" * 70)
    print("MODEL SOURCE AVAILABILITY TEST")
    print("=" * 70)
    
    # Check Kaggle authentication if testing Kaggle Hub
    kaggle_auth = False
    if test_kaggle and KAGGLE_AVAILABLE:
        kaggle_auth = check_kaggle_auth()
        if kaggle_auth:
            print("✓ Kaggle authentication found")
        else:
            print("⚠ Kaggle authentication not configured")
            if not skip_kaggle_download:
                print("  Kaggle downloads will likely fail without authentication")
    
    print("\n" + "=" * 70)
    print("Testing Model Sources")
    print("=" * 70)
    
    results = {}
    
    for model_name, sources in MODEL_SOURCES.items():
        print(f"\n📦 Testing {model_name.upper()} model:")
        
        results[model_name] = {
            "tfhub": None,
            "kaggle": None,
            "local": None
        }
        
        # Test TensorFlow Hub
        tfhub_url = sources.get("tfhub")
        if tfhub_url:
            success, message = check_tfhub_url(model_name, tfhub_url)
            results[model_name]["tfhub"] = (success, message)
            print(f"    TF Hub:     {message}")
        else:
            results[model_name]["tfhub"] = (False, "N/A")
            print(f"    TF Hub:     N/A - Not available on TF Hub")
        
        # Test Kaggle Hub
        if test_kaggle:
            kaggle_path = sources.get("kaggle")
            if kaggle_path:
                success, message = check_kaggle_path(model_name, kaggle_path, skip_kaggle_download)
                results[model_name]["kaggle"] = (success, message)
                print(f"    Kaggle Hub: {message}")
            else:
                results[model_name]["kaggle"] = (False, "N/A")
                print(f"    Kaggle Hub: N/A - Not available on Kaggle Hub")
        else:
            results[model_name]["kaggle"] = (False, "Skipped")
            print(f"    Kaggle Hub: Skipped (use --test-kaggle to test)")
        
        # Test Local Checkpoint
        if test_local:
            local_path = sources.get("local")
            if local_path:
                success, message = check_local_checkpoint(model_name, local_path)
                results[model_name]["local"] = (success, message)
                print(f"    Local:      {message}")
            else:
                results[model_name]["local"] = (False, "N/A")
                print(f"    Local:      N/A - No local checkpoint")
        else:
            results[model_name]["local"] = (False, "Skipped")
            print(f"    Local:      Skipped")
    
    return results


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Test all model sources (TensorFlow Hub and Kaggle Hub)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test TensorFlow Hub only (fast, no auth needed)
  python test_model_sources.py
  
  # Test both TF Hub and Kaggle Hub (validate paths only)
  python test_model_sources.py --test-kaggle --skip-download
  
  # Test both TF Hub and Kaggle Hub (full test with downloads)
  python test_model_sources.py --test-kaggle

Note: 
  - TensorFlow Hub tests are always performed
  - Kaggle Hub tests require --test-kaggle flag
  - Kaggle Hub downloads require authentication (kaggle.json)
  - Use --skip-download to avoid large downloads during testing
        """
    )
    
    parser.add_argument(
        '--test-kaggle',
        action='store_true',
        help='Test Kaggle Hub sources (requires kagglehub package)'
    )
    
    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='Skip actual downloads from Kaggle Hub (only validate paths)'
    )
    
    parser.add_argument(
        '--skip-local',
        action='store_true',
        help='Skip testing local checkpoint files'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed error messages'
    )
    
    args = parser.parse_args()
    
    # Run tests
    try:
        check_all_sources(
            test_kaggle=args.test_kaggle,
            skip_kaggle_download=args.skip_download,
            test_local=not args.skip_local
        )
        
        print("\n" + "=" * 70)
        print("Test completed successfully!")
        print("=" * 70)
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Test failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


