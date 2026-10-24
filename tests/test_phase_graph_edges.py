"""Spec 02 (#407) phase-graph edges: AC-1 and AC-2."""

from modules import phases


def test_keywords_hard_prerequisite_is_metadata_only():
    """AC-1: tagging reads the thumbnail and the stored CLIP vector, never a score."""
    assert phases.PHASE_PREREQUISITES["keywords"] == ("metadata",)


def test_pipeline_prefix_through_keywords_skips_scoring():
    """AC-2."""
    assert phases.pipeline_prefix_through("keywords") == ["indexing", "metadata", "keywords"]


def test_keywords_no_longer_waits_for_scoring():
    assert phases.missing_prerequisites(["keywords"], {"indexing", "metadata"}) == {}


def test_bird_species_still_follows_keywords():
    assert phases.pipeline_prefix_through("bird_species") == [
        "indexing", "metadata", "keywords", "bird_species",
    ]


def test_executor_projection_follows_the_registry():
    from modules.phase_executors import _prereqs

    assert _prereqs(phases.PhaseCode.KEYWORDS) == ["metadata"]
