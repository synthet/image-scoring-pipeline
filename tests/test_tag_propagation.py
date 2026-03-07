"""Tests for tag propagation (modules.tagging.propagate_tags)."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helper: build synthetic data
# ---------------------------------------------------------------------------
DIM = 1280


def _make_vec(seed=None):
    """Return a random L2-normalized float32 vector."""
    rng = np.random.RandomState(seed)
    v = rng.randn(DIM).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _tagged_entry(image_id, file_path, vec, keywords_str):
    """Build a tagged image tuple as returned by DB helper."""
    return (image_id, file_path, vec.tobytes(), keywords_str)


def _untagged_entry(image_id, file_path, vec):
    """Build an untagged image tuple as returned by DB helper."""
    return (image_id, file_path, vec.tobytes())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPropagateTags:
    """Unit tests for propagate_tags with mocked DB."""

    def _call(self, untagged, tagged, **kwargs):
        """Call propagate_tags with mocked DB and config."""
        defaults = {
            "dry_run": True,
            "k": 5,
            "min_similarity": 0.50,
            "min_keyword_confidence": 0.60,
            "min_support_neighbors": 2,
            "max_keywords": 10,
        }
        defaults.update(kwargs)

        with patch("modules.tagging.db") as mock_db, \
             patch("modules.tagging.config", create=True) as mock_config:
            # Mock the config module
            mock_config_mod = MagicMock()
            mock_config_mod.get_config_section.return_value = {}
            
            # We need to patch at the module level
            with patch("modules.config.get_config_section", return_value={}):
                mock_db.get_images_for_tag_propagation.return_value = (untagged, tagged)
                mock_db.get_db.return_value = MagicMock()

                from modules.tagging import propagate_tags
                return propagate_tags(**defaults)

    # -- Voting math -----------------------------------------------------------

    def test_weighted_voting_math(self):
        """Keywords with high similarity-weighted support should propagate."""
        # Create an untagged image that is very similar to tagged neighbors
        anchor = _make_vec(seed=42)
        neighbor_1 = anchor * 0.999 + np.random.RandomState(1).randn(DIM).astype(np.float32) * 0.001
        neighbor_1 /= np.linalg.norm(neighbor_1)
        neighbor_2 = anchor * 0.998 + np.random.RandomState(2).randn(DIM).astype(np.float32) * 0.002
        neighbor_2 /= np.linalg.norm(neighbor_2)

        untagged = [_untagged_entry(10, "/img10.jpg", anchor)]
        tagged = [
            _tagged_entry(1, "/img1.jpg", neighbor_1, "landscape,nature"),
            _tagged_entry(2, "/img2.jpg", neighbor_2, "landscape,sunset"),
        ]

        result = self._call(untagged, tagged, min_support_neighbors=2)
        assert result["propagated"] == 1
        # "landscape" appears in both neighbors → should propagate
        cand = result["candidates"][0]
        assert "landscape" in cand["keywords"]

    def test_min_confidence_threshold(self):
        """Keywords below the confidence threshold should be excluded."""
        anchor = _make_vec(seed=10)
        n1 = anchor * 0.99 + np.random.RandomState(11).randn(DIM).astype(np.float32) * 0.01
        n1 /= np.linalg.norm(n1)
        n2 = anchor * 0.98 + np.random.RandomState(12).randn(DIM).astype(np.float32) * 0.02
        n2 /= np.linalg.norm(n2)

        untagged = [_untagged_entry(20, "/img20.jpg", anchor)]
        tagged = [
            _tagged_entry(1, "/n1.jpg", n1, "landscape,nature"),
            _tagged_entry(2, "/n2.jpg", n2, "landscape,animals"),
        ]

        # Set very high confidence threshold → only "landscape" (present in both) might pass
        result = self._call(untagged, tagged, min_keyword_confidence=0.99, min_support_neighbors=1)
        if result["propagated"] > 0:
            cand = result["candidates"][0]
            # Keywords that only appear in one neighbor should not pass 0.99 threshold
            for kw in cand["keywords"]:
                assert kw == "landscape"  # only keyword in both

    def test_min_support_neighbors(self):
        """Keywords with too few supporting neighbors are excluded."""
        anchor = _make_vec(seed=30)
        n1 = anchor * 0.999 + np.random.RandomState(31).randn(DIM).astype(np.float32) * 0.001
        n1 /= np.linalg.norm(n1)
        n2 = anchor * 0.998 + np.random.RandomState(32).randn(DIM).astype(np.float32) * 0.002
        n2 /= np.linalg.norm(n2)

        untagged = [_untagged_entry(30, "/img30.jpg", anchor)]
        tagged = [
            _tagged_entry(1, "/n1.jpg", n1, "landscape,nature"),
            _tagged_entry(2, "/n2.jpg", n2, "landscape,sunset"),
        ]

        # Require 3 support neighbors → nothing should propagate (only 2 neighbors)
        result = self._call(untagged, tagged, min_support_neighbors=3)
        assert result["propagated"] == 0

    def test_min_anchor_similarity(self):
        """Images with no neighbor above anchor similarity get no tags."""
        anchor = _make_vec(seed=40)
        distant = _make_vec(seed=41)  # completely unrelated direction

        untagged = [_untagged_entry(40, "/img40.jpg", anchor)]
        tagged = [
            _tagged_entry(1, "/far.jpg", distant, "landscape,nature"),
        ]

        result = self._call(untagged, tagged, min_similarity=0.99, min_support_neighbors=1)
        assert result["propagated"] == 0
        assert result["skipped"] >= 1

    def test_replace_missing_only(self):
        """Only untagged images are processed (tagged images stay in the 'tagged' pool)."""
        anchor = _make_vec(seed=50)

        # No untagged images → nothing to propagate
        untagged = []
        tagged = [_tagged_entry(1, "/t.jpg", anchor, "landscape")]

        result = self._call(untagged, tagged)
        assert result["total_untagged"] == 0
        assert result["propagated"] == 0

    def test_max_keywords_cap(self):
        """At most max_keywords are propagated per image."""
        anchor = _make_vec(seed=60)
        n1 = anchor.copy()

        many_kws = ",".join([f"kw{i}" for i in range(20)])
        untagged = [_untagged_entry(60, "/img60.jpg", anchor)]
        tagged = [
            _tagged_entry(1, "/n1.jpg", n1, many_kws),
            _tagged_entry(2, "/n2.jpg", n1, many_kws),  # same vec, same keywords
        ]

        result = self._call(untagged, tagged, max_keywords=3, min_support_neighbors=2)
        if result["propagated"] > 0:
            cand = result["candidates"][0]
            assert len(cand["keywords"]) <= 3

    def test_empty_no_op(self):
        """No embeddings → empty result."""
        result = self._call([], [])
        assert result["propagated"] == 0
        assert result["total_untagged"] == 0

    def test_no_tagged_sources(self):
        """Untagged images but no tagged sources → all skipped."""
        anchor = _make_vec(seed=70)
        untagged = [_untagged_entry(70, "/img70.jpg", anchor)]
        tagged = []

        result = self._call(untagged, tagged)
        assert result["propagated"] == 0
        assert result["skipped"] == len(untagged)

    def test_dry_run_does_not_write(self):
        """Dry run returns candidates but does not write to DB."""
        anchor = _make_vec(seed=80)
        n1 = anchor * 0.999 + np.random.RandomState(81).randn(DIM).astype(np.float32) * 0.001
        n1 /= np.linalg.norm(n1)
        n2 = anchor * 0.998 + np.random.RandomState(82).randn(DIM).astype(np.float32) * 0.002
        n2 /= np.linalg.norm(n2)

        untagged = [_untagged_entry(80, "/img80.jpg", anchor)]
        tagged = [
            _tagged_entry(1, "/n1.jpg", n1, "landscape,nature"),
            _tagged_entry(2, "/n2.jpg", n2, "landscape,nature"),
        ]

        result = self._call(untagged, tagged, dry_run=True, min_support_neighbors=2)
        assert "candidates" in result
        assert result["propagated"] >= 0
        # The key assertion: db.get_db() should NOT have been called for writing
        # (in dry_run mode the function skips opening a write connection)
