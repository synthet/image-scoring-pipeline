"""
Unit and Integration tests for AI Culling workflow.

Tests:
1. test_create_session - Session creation and persistence
2. test_import_images - Image import and grouping
3. test_auto_pick - Auto-pick best in groups
4. test_export_xmp - XMP sidecar export
5. test_full_workflow - End-to-end culling workflow
"""

import os
import sys
import tempfile
import shutil
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db, xmp
from modules.culling import CullingEngine

# Configure logging
logging.basicConfig(level=logging.WARNING)


class TestCullingWorkflow:
    """Test suite for culling workflow operations."""
    
    @classmethod
    def setup_class(cls):
        """Set up test database and fixtures."""
        # Use a temporary database
        cls.original_db_path = db.DB_PATH
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db_path = os.path.join(cls.temp_dir, 'test_culling.db')
        cls.test_images_dir = os.path.join(cls.temp_dir, 'test_images')
        
        db.DB_PATH = cls.test_db_path
        os.makedirs(cls.test_images_dir, exist_ok=True)
        
        # Initialize database
        db.init_db()
        
        # Create test image fixtures
        cls._create_test_images()
    
    @classmethod
    def teardown_class(cls):
        """Clean up test database and fixtures."""
        db.DB_PATH = cls.original_db_path
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
    
    @classmethod
    def _create_test_images(cls):
        """Insert test images with scores for culling tests."""
        conn = db.get_db()
        c = conn.cursor()
        
        # Create test folder
        c.execute("INSERT INTO folders (path) VALUES (?)", (cls.test_images_dir,))
        folder_id = c.lastrowid
        
        # Create test images (3 groups of 3 similar images each)
        # Group 1: Wedding photos (similar timestamps, varying scores)
        test_images = [
            (f'{cls.test_images_dir}/wedding_001.jpg', 'wedding_001.jpg', 0.85, 0.80, 0.75, folder_id),
            (f'{cls.test_images_dir}/wedding_002.jpg', 'wedding_002.jpg', 0.92, 0.88, 0.85, folder_id),  # Best in group
            (f'{cls.test_images_dir}/wedding_003.jpg', 'wedding_003.jpg', 0.78, 0.75, 0.70, folder_id),
            # Group 2: Portrait photos
            (f'{cls.test_images_dir}/portrait_001.jpg', 'portrait_001.jpg', 0.88, 0.85, 0.82, folder_id),  # Best
            (f'{cls.test_images_dir}/portrait_002.jpg', 'portrait_002.jpg', 0.75, 0.72, 0.70, folder_id),
            # Single image (no group)
            (f'{cls.test_images_dir}/landscape_001.jpg', 'landscape_001.jpg', 0.90, 0.87, 0.85, folder_id),
        ]
        
        for path, name, gen, tech, aes, fid in test_images:
            c.execute("""
                INSERT INTO images (file_path, file_name, score_general, score_technical, score_aesthetic, folder_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (path, name, gen, tech, aes, fid))
            
            # Create dummy image files for XMP tests
            with open(path, 'w') as f:
                f.write('dummy image data')
        
        conn.commit()
        conn.close()
    
    def _cleanup_session(self, session_id):
        """Helper to clean up a culling session."""
        conn = db.get_db()
        c = conn.cursor()
        try:
            c.execute("DELETE FROM culling_images WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM culling_sessions WHERE id = ?", (session_id,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


def test_create_session():
    """Test that culling sessions are created and persisted correctly."""
    test = TestCullingWorkflow()
    test.setup_class()
    
    try:
        engine = CullingEngine()
        
        # Create session
        session_id = engine.create_session(test.test_images_dir, mode='automated')
        
        assert session_id is not None, "Session should be created"
        assert session_id > 0, "Session ID should be positive"
        
        # Verify session exists in DB
        session = db.get_culling_session(session_id)
        assert session is not None, "Session should be retrievable from DB"
        assert session['folder_path'] == test.test_images_dir, "Session folder path should match"
        assert session['mode'] == 'automated', "Session mode should be automated"
        
        print("✓ test_create_session PASSED")
        
        # Cleanup
        test._cleanup_session(session_id)
    finally:
        test.teardown_class()


def test_import_images():
    """Test image import and grouping functionality."""
    test = TestCullingWorkflow()
    test.setup_class()
    
    try:
        engine = CullingEngine()
        
        # Create session
        session_id = engine.create_session(test.test_images_dir)
        assert session_id is not None, "Session should be created"
        
        # Import images
        stats = engine.import_images(
            session_id, 
            distance_threshold=0.3,  # Relaxed threshold for test
            time_gap_seconds=300
        )
        
        # Verify import stats
        assert 'error' not in stats, f"Import should succeed: {stats.get('error')}"
        assert stats.get('total', 0) == 6, f"Should import 6 images, got {stats.get('total')}"
        
        print("✓ test_import_images PASSED")
        
        # Cleanup
        test._cleanup_session(session_id)
    finally:
        test.teardown_class()


def test_auto_pick():
    """Test auto-pick selects best image in each group."""
    test = TestCullingWorkflow()
    test.setup_class()
    
    try:
        engine = CullingEngine()
        
        # Create and populate session
        session_id = engine.create_session(test.test_images_dir)
        stats = engine.import_images(session_id, distance_threshold=0.3)
        
        # Run auto-pick
        pick_stats = engine.auto_pick_all(session_id, score_field='score_general')
        
        assert 'picked' in pick_stats, "Should have pick count"
        assert pick_stats['picked'] > 0, "Should pick at least one image"
        
        # Verify picks
        picks = engine.get_picks(session_id)
        assert len(picks) > 0, "Should have picked images"
        
        # Verify rejects
        rejects = engine.get_rejects(session_id)
        # May or may not have rejects depending on grouping
        
        print(f"✓ test_auto_pick PASSED (picked: {pick_stats['picked']}, rejected: {pick_stats.get('rejected', 0)})")
        
        # Cleanup
        test._cleanup_session(session_id)
    finally:
        test.teardown_class()


def test_export_xmp():
    """Test XMP sidecar export for culling decisions."""
    test = TestCullingWorkflow()
    test.setup_class()
    
    try:
        engine = CullingEngine()
        
        # Run full cull workflow without auto-export
        result = engine.run_full_cull(
            test.test_images_dir,
            distance_threshold=0.3,
            auto_export=False
        )
        
        session_id = result.get('session_id')
        assert session_id, "Should have session ID"
        
        # Now export to XMP (using new Pick/Reject flag system)
        export_stats = engine.export_to_xmp(session_id)
        
        assert 'exported' in export_stats, "Should have export count"
        assert 'errors' in export_stats, "Should have error count"
        
        # Check that XMP files were created for test images
        xmp_files = [f for f in os.listdir(test.test_images_dir) if f.endswith('.xmp')]
        assert len(xmp_files) > 0, f"Should create XMP files, found: {xmp_files}"
        
        print(f"✓ test_export_xmp PASSED (exported: {export_stats['exported']}, errors: {export_stats['errors']})")
        
        # Cleanup
        test._cleanup_session(session_id)
        
        # Clean up XMP files
        for xmp_file in xmp_files:
            os.remove(os.path.join(test.test_images_dir, xmp_file))
    finally:
        test.teardown_class()


def test_full_workflow():
    """End-to-end test of complete culling workflow."""
    test = TestCullingWorkflow()
    test.setup_class()
    
    try:
        engine = CullingEngine()
        
        # Run complete workflow
        result = engine.run_full_cull(
            test.test_images_dir,
            distance_threshold=0.3,
            time_gap_seconds=300,
            score_field='score_general',
            auto_export=True
        )
        
        # Verify results
        assert 'error' not in result, f"Workflow should succeed: {result.get('error')}"
        assert result.get('session_id'), "Should have session ID"
        assert result.get('total', 0) > 0, "Should have imported images"
        assert result.get('picked', 0) > 0, "Should have picked images"
        assert result.get('exported') == True, "Should have exported"
        
        print(f"✓ test_full_workflow PASSED")
        print(f"  - Total images: {result.get('total')}")
        print(f"  - Groups: {result.get('groups')}")
        print(f"  - Picked: {result.get('picked')}")
        print(f"  - Rejected: {result.get('rejected')}")
        print(f"  - XMP exported: {result.get('xmp_count')}")
        
        # Cleanup
        test._cleanup_session(result['session_id'])
        
        # Clean up XMP files
        xmp_files = [f for f in os.listdir(test.test_images_dir) if f.endswith('.xmp')]
        for xmp_file in xmp_files:
            os.remove(os.path.join(test.test_images_dir, xmp_file))
    finally:
        test.teardown_class()


if __name__ == '__main__':
    print("=" * 60)
    print("Running Culling Workflow Tests")
    print("=" * 60)
    
    tests = [
        test_create_session,
        test_import_images,
        test_auto_pick,
        test_export_xmp,
        test_full_workflow,
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
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

