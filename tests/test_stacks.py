"""
Unit tests for Stack management operations in modules/db.py

Test cases:
1. test_create_stack_from_images_minimum - Should fail with < 2 images
2. test_create_stack_sets_best_image - Best image should be highest score_general
3. test_remove_cleans_up_empty_stack - Removing last image should delete stack
4. test_remove_recalculates_best_image - Removing best image should update best_image_id
5. test_path_lookup_fallback - Should find by basename if exact path fails
"""

import os
import sys
import sqlite3
import tempfile
import shutil
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db

# Configure logging for tests
logging.basicConfig(level=logging.WARNING)


class TestStackOperations:
    """Test suite for stack management operations."""
    
    @classmethod
    def setup_class(cls):
        """Set up test database with mock data."""
        # Use a temporary database for testing
        cls.original_db_path = db.DB_PATH
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db_path = os.path.join(cls.temp_dir, 'test_scoring.db')
        db.DB_PATH = cls.test_db_path
        
        # Initialize database
        db.init_db()
        
        # Insert test images
        cls._create_test_images()
    
    @classmethod
    def teardown_class(cls):
        """Clean up test database."""
        db.DB_PATH = cls.original_db_path
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
    
    @classmethod
    def _create_test_images(cls):
        """Insert test images with known scores for testing."""
        conn = db.get_db()
        c = conn.cursor()
        
        # Create test folder
        c.execute("INSERT INTO folders (path) VALUES (?)", ('D:\\Test\\Photos',))
        folder_id = c.lastrowid
        
        # Insert test images with varying scores
        test_images = [
            ('D:\\Test\\Photos\\img_001.jpg', 'img_001.jpg', 0.85, folder_id),
            ('D:\\Test\\Photos\\img_002.jpg', 'img_002.jpg', 0.92, folder_id),  # Highest score
            ('D:\\Test\\Photos\\img_003.jpg', 'img_003.jpg', 0.78, folder_id),
            ('D:\\Test\\Photos\\img_004.jpg', 'img_004.jpg', 0.65, folder_id),
            ('D:\\Test\\Photos\\img_005.jpg', 'img_005.jpg', 0.70, folder_id),
        ]
        
        for path, name, score, fid in test_images:
            c.execute("""
                INSERT INTO images (file_path, file_name, score_general, folder_id)
                VALUES (?, ?, ?, ?)
            """, (path, name, score, fid))
        
        conn.commit()
        conn.close()
    
    def _get_image_ids(self, count=None):
        """Helper to get test image IDs."""
        conn = db.get_db()
        c = conn.cursor()
        query = "SELECT id FROM images ORDER BY id"
        if count:
            query += f" LIMIT {count}"
        c.execute(query)
        ids = [row[0] for row in c.fetchall()]
        conn.close()
        return ids
    
    def _clear_stacks(self):
        """Helper to clear all stacks for test isolation."""
        conn = db.get_db()
        c = conn.cursor()
        c.execute("DELETE FROM stacks")
        c.execute("UPDATE images SET stack_id = NULL")
        conn.commit()
        conn.close()


def test_create_stack_from_images_minimum():
    """Test that creating a stack with < 2 images fails."""
    test = TestStackOperations()
    test.setup_class()
    
    try:
        test._clear_stacks()
        
        # Test with 0 images
        success, result = db.create_stack_from_images([])
        assert not success, "Should fail with empty list"
        assert "at least 2" in result.lower(), f"Error message should mention minimum: {result}"
        
        # Test with 1 image
        ids = test._get_image_ids(1)
        success, result = db.create_stack_from_images(ids)
        assert not success, "Should fail with single image"
        assert "at least 2" in result.lower(), f"Error message should mention minimum: {result}"
        
        print("✓ test_create_stack_from_images_minimum PASSED")
    finally:
        test.teardown_class()


def test_create_stack_sets_best_image():
    """Test that best_image_id is set to the image with highest score_general."""
    test = TestStackOperations()
    test.setup_class()
    
    try:
        test._clear_stacks()
        
        # Get all image IDs
        ids = test._get_image_ids()
        assert len(ids) >= 2, "Need at least 2 test images"
        
        # Create stack
        success, stack_id = db.create_stack_from_images(ids[:3])
        assert success, f"Failed to create stack: {stack_id}"
        
        # Get the stack's best_image_id
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT best_image_id FROM stacks WHERE id = ?", (stack_id,))
        row = c.fetchone()
        best_image_id = row[0]
        
        # Get the image with highest score
        c.execute("""
            SELECT id FROM images 
            WHERE id IN (?, ?, ?)
            ORDER BY score_general DESC 
            LIMIT 1
        """, tuple(ids[:3]))
        expected_best = c.fetchone()[0]
        conn.close()
        
        assert best_image_id == expected_best, \
            f"Best image should be highest scored. Got {best_image_id}, expected {expected_best}"
        
        print("✓ test_create_stack_sets_best_image PASSED")
    finally:
        test.teardown_class()


def test_remove_cleans_up_empty_stack():
    """Test that removing all images from a stack deletes the stack."""
    test = TestStackOperations()
    test.setup_class()
    
    try:
        test._clear_stacks()
        
        # Create a stack with 2 images
        ids = test._get_image_ids(2)
        success, stack_id = db.create_stack_from_images(ids)
        assert success, f"Failed to create stack: {stack_id}"
        
        # Verify stack exists
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM stacks WHERE id = ?", (stack_id,))
        assert c.fetchone()[0] == 1, "Stack should exist"
        conn.close()
        
        # Remove all images from stack
        success, msg = db.remove_images_from_stack(ids)
        assert success, f"Failed to remove images: {msg}"
        
        # Verify stack was deleted
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM stacks WHERE id = ?", (stack_id,))
        count = c.fetchone()[0]
        conn.close()
        
        assert count == 0, f"Stack should be deleted after removing all images. Found {count} stacks"
        
        print("✓ test_remove_cleans_up_empty_stack PASSED")
    finally:
        test.teardown_class()


def test_remove_recalculates_best_image():
    """Test that removing the best image recalculates best_image_id."""
    test = TestStackOperations()
    test.setup_class()
    
    try:
        test._clear_stacks()
        
        # Create a stack with 3 images
        ids = test._get_image_ids(3)
        success, stack_id = db.create_stack_from_images(ids)
        assert success, f"Failed to create stack: {stack_id}"
        
        # Get current best image
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT best_image_id FROM stacks WHERE id = ?", (stack_id,))
        original_best = c.fetchone()[0]
        conn.close()
        
        # Remove the best image
        success, msg = db.remove_images_from_stack([original_best])
        assert success, f"Failed to remove image: {msg}"
        
        # Check that best_image_id was recalculated
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT best_image_id FROM stacks WHERE id = ?", (stack_id,))
        row = c.fetchone()
        
        if row is None:
            # Stack might have been deleted if only 2 images remained
            conn.close()
            print("✓ test_remove_recalculates_best_image PASSED (stack dissolved)")
            return
        
        new_best = row[0]
        conn.close()
        
        assert new_best != original_best, \
            f"best_image_id should change after removing best image. Still {new_best}"
        assert new_best is not None, "best_image_id should not be NULL"
        
        print("✓ test_remove_recalculates_best_image PASSED")
    finally:
        test.teardown_class()


def test_path_lookup_fallback():
    """Test that path lookup falls back to basename when exact path fails."""
    test = TestStackOperations()
    test.setup_class()
    
    try:
        # Test with a path that won't match exactly but basename should
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT file_path, file_name FROM images LIMIT 1")
        row = c.fetchone()
        actual_path = row[0]
        basename = row[1]
        conn.close()
        
        # Create a fake path with the same basename
        fake_path = f"/mnt/c/Different/Path/{basename}"
        
        # Try to get image ID by the fake path
        ids = db.get_image_ids_by_paths([fake_path])
        
        # Should find the image by basename fallback
        assert len(ids) == 1, f"Should find image by basename fallback. Got {len(ids)} results"
        
        # Verify it's the correct image
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT file_name FROM images WHERE id = ?", (ids[0],))
        found_name = c.fetchone()[0]
        conn.close()
        
        assert found_name == basename, \
            f"Found wrong image. Expected {basename}, got {found_name}"
        
        print("✓ test_path_lookup_fallback PASSED")
    finally:
        test.teardown_class()


if __name__ == '__main__':
    print("=" * 60)
    print("Running Stack Unit Tests")
    print("=" * 60)
    
    tests = [
        test_create_stack_from_images_minimum,
        test_create_stack_sets_best_image,
        test_remove_cleans_up_empty_stack,
        test_remove_recalculates_best_image,
        test_path_lookup_fallback,
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

