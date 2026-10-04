"""BLIP caption decoding guards against repetition loops (#546). No model download."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("torch")

from modules import tagging  # noqa: E402


@pytest.mark.parametrize("raw, expected", [
    ("a man with dread dread dread dread hair", "a man with dread hair"),
    ("a table with a tray of ass ass ass", "a table with a tray of ass"),
    ("a church with a steep steep on the side of the road", "a church with a steep on the side of the road"),
    ("A bird on a branch", "A bird on a branch"),
    ("", ""),
])
def test_collapse_repeated_words(raw, expected):
    assert tagging.collapse_repeated_words(raw) == expected


def test_generate_uses_beam_search_with_repetition_control(monkeypatch):
    import modules.thumbnails as thumbnails

    monkeypatch.setattr(thumbnails, "open_image_for_ml", lambda _p: MagicMock())
    gen = tagging.CaptionGenerator(device="cpu")
    gen.processor = MagicMock()
    gen.processor.decode.return_value = "a table with a tray of ass ass ass"
    gen.model = MagicMock()

    assert gen.generate("x.jpg") == "A table with a tray of ass"
    kwargs = gen.model.generate.call_args.kwargs
    assert kwargs["num_beams"] > 1
    assert kwargs["no_repeat_ngram_size"] == 2
    assert kwargs["repetition_penalty"] > 1.0
