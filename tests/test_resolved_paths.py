"""
Unit tests for resolved_paths functionality in modules/db.py

Tests:
1. test_convert_to_windows_path - WSL path conversion
2. test_resolve_windows_path - Stores and retrieves resolved path
3. test_get_resolved_path - Retrieves verified/unverified paths
4. test_upsert_creates_resolved_path - Integration with upsert_image
"""

import os
import sys
import sqlite3
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db


class TestResolvedPaths:
    """Test suite for resolved_paths functionality."""
    
    @classmethod
    def setup_class(cls):
        """Set up test database."""
        cls.test_dir = tempfile.mkdtemp()
        cls.test_db = os.path.join(cls.test_dir, "test_resolved.db")
        db.DB_FILE = cls.test_db
        db.init_db()
        cls._create_test_images()
    
    @classmethod
    def teardown_class(cls):
        """Clean up test database."""
        try:
            shutil.rmtree(cls.test_dir)
        except:
            pass
    
    @classmethod
    def _create_test_images(cls):
        """Insert test images with various path formats."""
        conn = sqlite3.connect(cls.test_db)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        test_images = [
            (1, "/mnt/d/Photos/test1.jpg", "test1.jpg"),
            (2, "/mnt/c/Users/Test/image2.nef", "image2.nef"),
            (3, "D:\\Photos\\test3.jpg", "test3.jpg"),
            (4, "D:/Photos/test4.png", "test4.png"),
        ]
        
        for job_id, path, name in test_images:
            c.execute("""
                INSERT INTO images (job_id, file_path, file_name, score, created_at)
                VALUES (?, ?, ?, 0.5, datetime('now'))
            """, (job_id, path, name))
        
        conn.commit()
        conn.close()


def test_convert_to_windows_path():
    """Test WSL path to Windows path conversion."""
    from modules.db import _convert_to_windows_path
    
    # Test WSL path conversion
    assert _convert_to_windows_path("/mnt/d/Photos/test.jpg") == "D:\\Photos\\test.jpg"
    assert _convert_to_windows_path("/mnt/c/Users/Test/img.nef") == "C:\\Users\\Test\\img.nef"
    
    # Test already Windows paths (backslash)
    assert _convert_to_windows_path("D:\\Photos\\test.jpg") == "D:\\Photos\\test.jpg"
    
    # Test Windows paths with forward slashes
    assert _convert_to_windows_path("D:/Photos/test.jpg") == "D:\\Photos\\test.jpg"
    
    # Test None/empty
    assert _convert_to_windows_path(None) is None
    assert _convert_to_windows_path("") is None
    
    print("✓ test_convert_to_windows_path passed")


def test_resolve_windows_path():
    """Test storing and retrieving resolved paths."""
    TestResolvedPaths.setup_class()
    
    # Get the specific image with WSL path - query by a known path
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT id, file_path FROM images WHERE file_path LIKE '/mnt/d/%' LIMIT 1")
    row = c.fetchone()
    conn.close()
    
    assert row is not None, "No WSL-format paths found in test data"
    
    image_id = row['id']
    wsl_path = row['file_path']
    
    # Resolve path (without verification since file doesn't exist)
    result = db.resolve_windows_path(image_id, wsl_path, verify=False)
    
    assert result is not None, f"resolve_windows_path returned None for path: {wsl_path}"
    # The path should be converted to Windows format with D: drive
    assert result.startswith("D:\\"), f"Expected path starting with 'D:\\', got '{result}'"
    
    # Verify it was stored
    stored = db.get_resolved_path(image_id, verified_only=False)
    assert stored == result, f"Stored path '{stored}' doesn't match result '{result}'"
    
    TestResolvedPaths.teardown_class()
    print("✓ test_resolve_windows_path passed")



def test_get_resolved_path_verified():
    """Test that verified_only parameter works correctly."""
    TestResolvedPaths.setup_class()
    
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM images LIMIT 1 OFFSET 1")
    row = c.fetchone()
    image_id = row[0]
    conn.close()
    
    # Insert an unverified path
    db.resolve_windows_path(image_id, "/mnt/c/test.jpg", verify=False)
    
    # Should be retrievable with verified_only=False
    result = db.get_resolved_path(image_id, verified_only=False)
    assert result is not None
    
    # Should NOT be retrievable with verified_only=True (default)
    result_verified = db.get_resolved_path(image_id, verified_only=True)
    assert result_verified is None
    
    TestResolvedPaths.teardown_class()
    print("✓ test_get_resolved_path_verified passed")


def test_upsert_creates_resolved_path():
    """Test that upsert_image creates resolved_path automatically."""
    TestResolvedPaths.setup_class()
    
    # Create a new image via upsert
    result = {
        "image_path": "/mnt/e/NewFolder/new_image.jpg",
        "image_name": "new_image.jpg",
        "score": 0.75,
        "score_general": 0.75,
        "score_technical": 0.65,
        "score_aesthetic": 0.70,
    }
    
    db.upsert_image(job_id=99, result=result)
    
    # Get the image ID
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM images WHERE file_path = ?", (result["image_path"],))
    row = c.fetchone()
    conn.close()
    
    assert row is not None
    image_id = row[0]
    
    # Check that resolved_path was created
    resolved = db.get_resolved_path(image_id, verified_only=False)
    assert resolved is not None
    assert resolved == "E:\\NewFolder\\new_image.jpg"
    
    TestResolvedPaths.teardown_class()
    print("✓ test_upsert_creates_resolved_path passed")


if __name__ == '__main__':
    print("=" * 60)
    print("Running Resolved Paths Unit Tests")
    print("=" * 60)
    
    tests = [
        test_convert_to_windows_path,
        test_resolve_windows_path,
        test_get_resolved_path_verified,
        test_upsert_creates_resolved_path,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} ERROR: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
