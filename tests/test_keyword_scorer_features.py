"""Stored-image keyword scoring accepts supported CLIP text-feature outputs."""
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from modules.tagging import KeywordScorer


@pytest.mark.parametrize("output_kind", ["tensor", "text_embeds", "pooler_output"])
def test_stored_embedding_normalizes_clip_text_feature_outputs(output_kind):
    features = torch.tensor([[3.0, 0.0, 0.0], [0.0, 4.0, 0.0]])
    output = features if output_kind == "tensor" else SimpleNamespace(**{output_kind: features})
    scorer = KeywordScorer(model_name="test-clip", device="cpu")
    scorer.model = SimpleNamespace(
        get_text_features=lambda **_inputs: output,
        logit_scale=torch.tensor(0.0),
    )
    scorer.processor = lambda **_kwargs: {"input_ids": torch.zeros((2, 1), dtype=torch.long)}

    probabilities, cosines, embedding = scorer._score_prompts_from_embedding(
        [2.0, 0.0, 0.0], ["aligned", "orthogonal"],
    )

    np.testing.assert_allclose(cosines, [1.0, 0.0])
    np.testing.assert_allclose(embedding, [1.0, 0.0, 0.0])
    np.testing.assert_allclose(probabilities, np.exp([1.0, 0.0]) / np.exp([1.0, 0.0]).sum())
