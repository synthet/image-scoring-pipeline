import pytest
import numpy as np
from modules.diversity import compute_pairwise_similarities, reorder_with_mmr

def create_mock_embedding(vec):
    """Helper to create bytes from a numpy array representing an embedding."""
    return np.array(vec, dtype=np.float32).tobytes()

def test_compute_pairwise_similarities_empty():
    sim = compute_pairwise_similarities([])
    assert sim.shape == (0, 0)

def test_compute_pairwise_similarities_missing():
    # 3 embeddings, where the second is None
    e1 = np.array([1.0, 0.0], dtype=np.float32)
    e3 = np.array([0.0, 1.0], dtype=np.float32)
    
    sim = compute_pairwise_similarities([e1, None, e3])
    
    assert sim.shape == (3, 3)
    # E1 vs E1 = 1.0
    assert np.isclose(sim[0, 0], 1.0)
    # E1 vs E3 = 0.0 (orthogonal)
    assert np.isclose(sim[0, 2], 0.0)
    assert np.isclose(sim[2, 0], 0.0)
    # E3 vs E3 = 1.0
    assert np.isclose(sim[2, 2], 1.0)
    
    # Missing vectors have 0 similarity to everything
    assert np.all(sim[1, :] == 0.0)
    assert np.all(sim[:, 1] == 0.0)

def test_reorder_with_mmr_basic():
    """Test basic MMR reordering where diversity overrides pure score."""
    
    # 4 images, we want to pick 2
    images = [
        {"id": 1, "score_general": 90},
        {"id": 2, "score_general": 89}, # Very similar to 1 in embedding
        {"id": 3, "score_general": 85}, # Different from 1
        {"id": 4, "score_general": 80}, # Different from 1 and 3
    ]
    
    # Embeddings: 1 and 2 are almost identical. 3 is orthogonal.
    e1 = create_mock_embedding([1.0, 0.0, 0.0])
    e2 = create_mock_embedding([0.9, 0.1, 0.0])
    e3 = create_mock_embedding([0.0, 1.0, 0.0])
    e4 = create_mock_embedding([0.0, 0.0, 1.0])
    
    embeddings_dict = {
        1: e1,
        2: e2,
        3: e3,
        4: e4
    }
    
    # High lambda (mostly score): Should pick 1 and 2
    res_score = reorder_with_mmr(images, k=2, embeddings_dict=embeddings_dict, lambda_val=0.99)
    assert [img["id"] for img in res_score[:2]] == [1, 2]
    
    # Low lambda (mostly diversity): Should pick 1 and 3 (3 is more diverse from 1 than 2 is)
    res_div = reorder_with_mmr(images, k=2, embeddings_dict=embeddings_dict, lambda_val=0.5)
    assert [img["id"] for img in res_div[:2]] == [1, 3]
    
    # Test lengths remain the same
    assert len(res_div) == 4
    # Ensure remaining items are correctly populated
    assert set([img["id"] for img in res_div]) == {1, 2, 3, 4}

def test_reorder_with_mmr_missing_embeddings():
    """Test MMR ignores missing embeddings properly and falls back to score via 0 similarity."""
    images = [
        {"id": 1, "score_general": 90},
        {"id": 2, "score_general": 89},
        {"id": 3, "score_general": 88}, 
    ]
    
    # Only image 2 has an embedding
    e2 = create_mock_embedding([1.0, 0.0])
    embeddings_dict = {2: e2}
    
    # 1 lacks embedding -> similarity to anything is 0.
    # 2 has embedding.
    # 3 lacks embedding -> similarity 0.
    
    # First pick is always the one with highest score (id=1).
    res = reorder_with_mmr(images, k=2, embeddings_dict=embeddings_dict, lambda_val=0.5)
    
    assert res[0]["id"] == 1
    # Next pick between 2 and 3. Since both 2 and 3 have 0 similarity to 1 (which lacks embedding),
    # MMR relies on normalized score: 2 has higher score than 3, so 2 should be picked.
    assert res[1]["id"] == 2

def test_reorder_with_mmr_small_stack():
    """Test that it doesn't try to MMR for lists <= 2."""
    images = [
        {"id": 1, "score_general": 90},
        {"id": 2, "score_general": 89},
    ]
    embeddings_dict = {1: create_mock_embedding([1.0]), 2: create_mock_embedding([1.0])}
    
    # With k=1
    res = reorder_with_mmr(images, k=1, embeddings_dict=embeddings_dict, lambda_val=0.0)
    assert [img["id"] for img in res] == [1, 2]
