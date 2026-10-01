"""Scene route arithmetic, versioning and routing (spec 05 AC-5, AC-9; #412). No model is loaded."""

import numpy as np

from modules import scene_route
from modules.scene_route import (
    SceneResult,
    detectors_to_run,
    label_text_features,
    prompt_set_hash,
    score,
)


def test_label_features_are_normalized_prompt_means():
    feats = label_text_features([[2, 0], [0, 2], [0, 5]], [2, 1])
    assert np.allclose(feats[0], [2 ** -0.5, 2 ** -0.5])
    assert np.allclose(feats[1], [0, 1])


def test_score_softmax_and_top_label():
    labels = ["a", "b"]
    r = score([1, 0], np.array([[1.0, 0.0], [0.0, 1.0]]), labels, logit_scale=100.0, version="v")
    assert r.top_label == "a" and r.cosines == {"a": 1.0, "b": 0.0}
    assert abs(sum(r.probs.values()) - 1) < 1e-6 and r.top_prob > 0.99
    flat = score([1, 0], np.array([[1.0, 0.0], [1.0, 0.0]]), labels, logit_scale=100.0, version="v")
    assert flat.probs == {"a": 0.5, "b": 0.5}


def test_version_changes_with_prompts_and_backend():
    base = prompt_set_hash("hf_clip_b32")
    assert base == prompt_set_hash("hf_clip_b32")
    assert base != prompt_set_hash("openclip_l14")
    changed = {**scene_route.LABELS, "other": ("a photo of a rock",)}
    assert base != prompt_set_hash("hf_clip_b32", changed)


def _result(**probs):
    return SceneResult(probs=probs, cosines={}, top_label=max(probs, key=probs.get),
                       top_prob=max(probs.values()), version="v")


def test_detectors_run_at_threshold_even_when_not_top():
    r = _result(landscape=0.55, wildlife_bird=0.30)
    assert detectors_to_run(r, {"wildlife_bird": 0.30}) == ["bird"]
    assert detectors_to_run(r, {"wildlife_bird": 0.31}) == []


def test_labels_without_threshold_or_route_run_nothing():
    r = _result(wildlife_bird=0.9, wildlife_mammal=0.1)
    assert detectors_to_run(r, {}) == []
    assert detectors_to_run(r, {"wildlife_mammal": 0.0}) == []  # no mammal detector routed yet
