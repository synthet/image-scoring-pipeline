"""Tests for similar image search (modules.similar_search)."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

# Import after path is set by conftest
from modules import similar_search


class TestNormalize:
    """Tests for _normalize (L2 normalization)."""

    def test_normalize_1d_unit_vector_unchanged(self):
        v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        out = similar_search._normalize(v)
        np.testing.assert_array_almost_equal(out, v)

    def test_normalize_1d_scales_to_unit(self):
        v = np.array([3.0, 4.0], dtype=np.float32)
        out = similar_search._normalize(v)
        np.testing.assert_almost_equal(np.linalg.norm(out), 1.0)
        np.testing.assert_array_almost_equal(out, [0.6, 0.8])

    def test_normalize_1d_zero_vector_unchanged(self):
        v = np.array([0.0, 0.0], dtype=np.float32)
        out = similar_search._normalize(v)
        np.testing.assert_array_almost_equal(out, v)

    def test_normalize_2d_row_wise(self):
        m = np.array([[3.0, 4.0], [0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
        out = similar_search._normalize(m)
        np.testing.assert_almost_equal(np.linalg.norm(out[0]), 1.0)
        np.testing.assert_almost_equal(np.linalg.norm(out[2]), 1.0)
        np.testing.assert_array_almost_equal(out[0], [0.6, 0.8])
        np.testing.assert_array_almost_equal(out[1], [0.0, 0.0])  # zero row unchanged


class TestSearchSimilarImages:
    """Tests for search_similar_images with mocked DB."""

    def test_error_when_no_example_provided(self):
        result = similar_search.search_similar_images()
        assert isinstance(result, dict)
        assert "error" in result
        assert "example_path" in result["error"] or "example_image_id" in result["error"]

    def test_error_when_example_path_not_in_db(self):
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {}
            result = similar_search.search_similar_images(example_path="/nonexistent.jpg")
        assert isinstance(result, dict)
        assert "error" in result
        assert "not found" in result["error"].lower() or "Image" in result["error"]

    def test_returns_list_sorted_by_similarity(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        c1 = q.copy()
        c2 = np.random.randn(dim).astype(np.float32)
        c2 = c2 / np.linalg.norm(c2)
        # Ensure c1 is more similar to q than c2
        sim1 = float(np.dot(q, c1))
        sim2 = float(np.dot(q, c2))
        assert sim1 >= sim2

        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            mock_db.get_embeddings_for_search.return_value = [
                (2, "/c1.jpg", c1.tobytes()),
                (3, "/c2.jpg", c2.tobytes()),
            ]
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=10
            )
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["similarity"] >= result[1]["similarity"]
        assert result[0]["image_id"] == 2
        assert result[0]["file_path"] == "/c1.jpg"
        assert "similarity" in result[0]

    def test_excludes_self_from_results(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 42, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            # Only candidate is the same image (id 42)
            mock_db.get_embeddings_for_search.return_value = [
                (42, "/q.jpg", q.tobytes()),
            ]
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=10
            )
        assert isinstance(result, list)
        assert len(result) == 0

    def test_min_similarity_filter(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        c_high = q * 0.99  # very similar
        c_low = np.random.randn(dim).astype(np.float32)
        c_low = c_low / np.linalg.norm(c_low)
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            mock_db.get_embeddings_for_search.return_value = [
                (2, "/high.jpg", c_high.tobytes()),
                (3, "/low.jpg", c_low.tobytes()),
            ]
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=10, min_similarity=0.9
            )
        assert isinstance(result, list)
        assert all(r["similarity"] >= 0.9 for r in result)
        assert len(result) <= 2

    def test_limit_respected(self):
        dim = 1280
        q = np.random.randn(dim).astype(np.float32)
        q = q / np.linalg.norm(q)
        candidates = [
            (i, f"/img{i}.jpg", (q + np.random.randn(dim).astype(np.float32) * 0.1).tobytes())
            for i in range(2, 12)
        ]
        for i, _, b in candidates:
            # normalize would be applied in search; we just need valid bytes
            pass
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = q.tobytes()
            mock_db.get_embeddings_for_search.return_value = candidates
            result = similar_search.search_similar_images(
                example_path="/q.jpg", limit=3
            )
        assert isinstance(result, list)
        assert len(result) == 3

    def test_error_when_no_embeddings_in_db(self):
        with patch("modules.similar_search.db") as mock_db:
            mock_db.get_image_details.return_value = {"id": 1, "file_path": "/q.jpg"}
            mock_db.get_image_embedding.return_value = np.random.randn(1280).astype(np.float32).tobytes()
            mock_db.get_embeddings_for_search.return_value = []
            result = similar_search.search_similar_images(example_path="/q.jpg")
        assert isinstance(result, dict)
        assert "error" in result
        assert "embedding" in result["error"].lower() or "Run clustering" in result["error"]


@pytest.mark.firebird
@pytest.mark.ml
class TestSearchSimilarImagesIntegration:
    """Integration test: requires test DB and optional TF. Skip if no embeddings."""

    def test_search_similar_images_import_and_call(self):
        """Smoke test: call search with example_image_id only (no path)."""
        from modules import db
        db.init_db()
        # Get any image id from test DB
        conn = db.get_db()
        c = conn.cursor()
        try:
            c.execute("SELECT id FROM images LIMIT 1")
            row = c.fetchone()
            conn.close()
        except Exception:
            conn.close()
            pytest.skip("No images table or no rows")
        if not row:
            pytest.skip("Test DB has no images")
        image_id = row[0]
        result = similar_search.search_similar_images(example_image_id=image_id, limit=5)
        # Either list of results or error (e.g. no embeddings)
        assert isinstance(result, (list, dict))
        if isinstance(result, dict) and "error" in result:
            assert "embedding" in result["error"].lower() or "Could not" in result["error"]
        elif isinstance(result, list):
            assert all("image_id" in r and "similarity" in r for r in result)
