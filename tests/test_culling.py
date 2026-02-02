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
import shutil
import logging
import uuid
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db
from modules.culling import CullingEngine

# Configure logging
logging.basicConfig(level=logging.WARNING)


class TestCullingWorkflow:
    """Test suite for culling workflow operations."""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_database_fixture(self):
        """Fixture for setting up and tearing down the test database."""
        # Use a temporary database
        original_db_path = db.DB_PATH
        # Use local temp dir to avoid Firebird permission issues in AppData
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'temp_test_cull')
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Configure Firebird Driver
        from firebird.driver import driver_config
        if hasattr(driver_config, 'fb_client_library'):
             fb_dll = os.path.abspath(os.path.join(os.path.dirname(db.__file__), "..", "Firebird", "fbclient.dll"))
             if os.path.exists(fb_dll):
                 driver_config.fb_client_library.value = fb_dll
                 print(f"Configured test FB driver: {fb_dll}")

        test_db_path = os.path.abspath(f"TEST_culling_{uuid.uuid4().hex}.fdb")
        self.__class__.test_db_path = test_db_path
        self.__class__.test_images_dir = os.path.join(temp_dir, 'test_images')
        os.makedirs(self.test_images_dir, exist_ok=True)
        
        # Copy template DB
        # Run scripts/debug/debug_firebird.py to create template if missing
        template_db = "template.fdb"
        if not os.path.exists(template_db):
             raise Exception("Template DB missing - run scripts/debug/debug_firebird.py first")
        
        try:
             if os.path.exists(test_db_path):
                 os.remove(test_db_path)
             shutil.copy2(template_db, test_db_path)
        except Exception as e:
             print(f"Error copying template DB: {e}")
             raise
        
        
        # CRITICAL: Override DB_PATH to use test database
        db.DB_PATH = test_db_path
        
        # Skip DDL - Template is seeded
        os.environ['SKIP_DB_INIT'] = '1'

        # Initialize DB with test path
        db.init_db()
        
        # Create test image fixtures
        self._create_test_images()

        yield

        # Teardown logic
        db.DB_PATH = original_db_path
        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
             # Close connection explicitely
             try: db.get_db().close()
             except: pass
             
             # Force garbage collection to release file handles
             import gc
             gc.collect()
             
             if os.path.exists(test_db_path):
                 print(f"Cleaning up {test_db_path}")
                 import time
                 MAX_RETRIES = 5
                 for i in range(MAX_RETRIES):
                     try:
                         os.remove(test_db_path)
                         break
                     except PermissionError:
                         if i < MAX_RETRIES - 1:
                             time.sleep(0.5)
                         else:
                             print(f"Warning: Failed to cleanup DB after retries") 
        except Exception as e:
             print(f"Warning: Failed to cleanup DB: {e}")
    

    def _create_test_images(self):
        """Insert test images with scores for culling tests."""
        conn = db.get_db()
        c = conn.cursor()
        
        # Create test folder
        # Create test folder using DB logic to ensure path normalization matches
        folder_id = db.get_or_create_folder(self.test_images_dir)


        
        # Create test images (3 groups of 3 similar images each)
        # Group 1: Wedding photos (similar timestamps, varying scores)

        test_images = [
            (f'{self.test_images_dir}/wedding_001.jpg', 'wedding_001.jpg', 0.85, 0.80, 0.75, folder_id),
            (f'{self.test_images_dir}/wedding_002.jpg', 'wedding_002.jpg', 0.92, 0.88, 0.85, folder_id),  # Best in group
            (f'{self.test_images_dir}/wedding_003.jpg', 'wedding_003.jpg', 0.78, 0.75, 0.70, folder_id),
            # Group 2: Portrait photos
            (f'{self.test_images_dir}/portrait_001.jpg', 'portrait_001.jpg', 0.88, 0.85, 0.82, folder_id),  # Best
            (f'{self.test_images_dir}/portrait_002.jpg', 'portrait_002.jpg', 0.75, 0.72, 0.70, folder_id),
            # Single image (no group)
            (f'{self.test_images_dir}/landscape_001.jpg', 'landscape_001.jpg', 0.90, 0.87, 0.85, folder_id),
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
        try:
            conn = db.get_db()
            c = conn.cursor()
            c.execute("DELETE FROM culling_images WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM culling_sessions WHERE id = ?", (session_id,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


    def test_create_session(self):
        """Test that culling sessions are created and persisted correctly."""
        print("\nDEBUG: TestCullingWorkflow.test_create_session STARTED")
        
        engine = CullingEngine()
        
        # Create session
        print("DEBUG: Calling engine.create_session")
        session_id = engine.create_session(self.test_images_dir, mode='automated')
        
        assert session_id is not None, "Session should be created"
        assert session_id > 0, "Session ID should be positive"
        
        # Verify session exists in DB
        session = db.get_culling_session(session_id)
        assert session is not None, "Session should be retrievable from DB"
        assert session['folder_path'] == self.test_images_dir, "Session folder path should match"
        assert session['mode'] == 'automated', "Session mode should be automated"
        
        # Cleanup
        self._cleanup_session(session_id)


    def test_import_images(self):
        """Test image import and grouping functionality."""
        
        engine = CullingEngine()
        
        # Create session
        session_id = engine.create_session(self.test_images_dir)
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
        
        # Cleanup
        self._cleanup_session(session_id)


    def test_auto_pick(self):
        """Test auto-pick selects best image in each group."""
        
        engine = CullingEngine()
        
        # Create and populate session
        session_id = engine.create_session(self.test_images_dir)
        stats = engine.import_images(session_id, distance_threshold=0.3)
        
        # Run auto-pick
        pick_stats = engine.auto_pick_all(session_id, score_field='score_general')
        
        assert 'picked' in pick_stats, "Should have pick count"
        assert pick_stats['picked'] > 0, "Should pick at least one image"
        
        # Verify picks
        picks = engine.get_picks(session_id)
        assert len(picks) > 0, "Should have picked images"
        
        # Cleanup
        self._cleanup_session(session_id)


    def test_export_xmp(self):
        """Test XMP sidecar export for culling decisions."""
        
        engine = CullingEngine()
        
        # Run full cull workflow without auto-export
        result = engine.run_full_cull(
            self.test_images_dir,
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
        xmp_files = [f for f in os.listdir(self.test_images_dir) if f.endswith('.xmp')]
        assert len(xmp_files) > 0, f"Should create XMP files, found: {xmp_files}"
        
        # Cleanup
        self._cleanup_session(session_id)
        
        # Clean up XMP files
        for xmp_file in xmp_files:
            try:
                os.remove(os.path.join(self.test_images_dir, xmp_file))
            except: pass


    def test_full_workflow(self):
        """End-to-end test of complete culling workflow."""
        
        engine = CullingEngine()
        
        # Run complete workflow
        result = engine.run_full_cull(
            self.test_images_dir,
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
        
        # Cleanup
        self._cleanup_session(result['session_id'])
        
        # Clean up XMP files
        xmp_files = [f for f in os.listdir(self.test_images_dir) if f.endswith('.xmp')]
        for xmp_file in xmp_files:
            try:
                os.remove(os.path.join(self.test_images_dir, xmp_file))
            except: pass


