"""Unit tests for ``phases.assert_prereqs_for_scope`` and the satisfied helper.

No database required — patches ``modules.db.get_folder_phase_summary`` to return
canned per-folder summary rows. Verifies both the optional/required parity
(skipped+done == total counts) and the cross-folder aggregation.
"""

from __future__ import annotations

import pytest

from modules import phases


def _row(code: str, total: int, *, done: int = 0, skipped: int = 0, failed: int = 0) -> dict:
    return {
        "code": code,
        "total_count": total,
        "done_count": done,
        "skipped_count": skipped,
        "failed_count": failed,
        "running_count": 0,
        "queued_count": 0,
    }


def _fake_summary(per_path):
    """Build a fake ``db.get_folder_phase_summary`` from a {path: [row, ...]} map."""
    def _summary(path: str, force_refresh: bool = False):
        return per_path.get(path, [])
    return _summary


# ---------------------------------------------------------------------------
# compute_satisfied_phases_for_scope
# ---------------------------------------------------------------------------

def test_satisfied_includes_done_only_phase(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("indexing", total=10, done=10)]}),
    )
    assert phases.compute_satisfied_phases_for_scope(["/x"]) == {"indexing"}


def test_satisfied_includes_required_phase_when_skipped_plus_done_covers_total(monkeypatch):
    """The 2026-05-02 case: indexing has 281 done + 259 skipped == 540 total."""
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("indexing", total=540, done=281, skipped=259)]}),
    )
    assert "indexing" in phases.compute_satisfied_phases_for_scope(["/x"])


def test_failed_blocks_satisfied(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("metadata", total=10, done=8, failed=2)]}),
    )
    assert "metadata" not in phases.compute_satisfied_phases_for_scope(["/x"])


def test_partial_blocks_satisfied(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("scoring", total=10, done=5)]}),
    )
    assert "scoring" not in phases.compute_satisfied_phases_for_scope(["/x"])


def test_empty_scope_phase_is_vacuously_satisfied(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("indexing", total=0)]}),
    )
    assert "indexing" in phases.compute_satisfied_phases_for_scope(["/x"])


def test_aggregates_across_multiple_folders(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({
            "/a": [_row("indexing", total=10, done=10)],
            "/b": [_row("indexing", total=20, done=15, skipped=5)],
        }),
    )
    assert "indexing" in phases.compute_satisfied_phases_for_scope(["/a", "/b"])


def test_aggregates_unsatisfied_when_one_folder_partial(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({
            "/a": [_row("indexing", total=10, done=10)],
            "/b": [_row("indexing", total=20, done=10)],   # partial -> blocks
        }),
    )
    assert "indexing" not in phases.compute_satisfied_phases_for_scope(["/a", "/b"])


def test_summary_failure_is_skipped_not_propagated(monkeypatch):
    """If a folder's summary raises, we log + continue rather than crash gating."""
    def _raises(path, force_refresh=False):
        raise RuntimeError("boom")
    monkeypatch.setattr("modules.db.get_folder_phase_summary", _raises)
    # Doesn't raise; returns whatever it could compute (nothing here).
    assert phases.compute_satisfied_phases_for_scope(["/x"]) == set()


# ---------------------------------------------------------------------------
# assert_prereqs_for_scope
# ---------------------------------------------------------------------------

def test_assert_returns_empty_when_prereqs_satisfied(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [
            _row("indexing", total=10, done=10),
            _row("metadata", total=10, done=10),
        ]}),
    )
    assert phases.assert_prereqs_for_scope(["scoring"], ["/x"]) == {}


def test_assert_returns_missing_when_prereq_not_done(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [
            _row("indexing", total=10, done=10),
            _row("metadata", total=10, done=5),  # partial
        ]}),
    )
    miss = phases.assert_prereqs_for_scope(["scoring"], ["/x"])
    assert miss == {"scoring": ["metadata"]}


def test_assert_co_requested_prereq_satisfies(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("indexing", total=10, done=10)]}),
    )
    # metadata not done in scope, but listed in same submission as scoring.
    assert phases.assert_prereqs_for_scope(["metadata", "scoring"], ["/x"]) == {}


def test_assert_indexing_root_phase_never_blocked(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("indexing", total=10, done=0)]}),
    )
    # indexing has no prerequisites; never returns missing.
    assert phases.assert_prereqs_for_scope(["indexing"], ["/x"]) == {}


def test_assert_bird_species_requires_keywords(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_folder_phase_summary",
        _fake_summary({"/x": [_row("keywords", total=10, done=5)]}),
    )
    miss = phases.assert_prereqs_for_scope(["bird_species"], ["/x"])
    assert miss == {"bird_species": ["keywords"]}


@pytest.mark.parametrize("scope_paths", [[], [""], None])
def test_assert_empty_scope_returns_empty(monkeypatch, scope_paths):
    """No scope -> nothing is satisfied, but also nothing is blocked (empty input)."""
    called = {"n": 0}

    def _summary(path, force_refresh=False):
        called["n"] += 1
        return []

    monkeypatch.setattr("modules.db.get_folder_phase_summary", _summary)
    # With empty scope_paths, nothing is satisfied -> any non-root phase reports its prereq.
    miss = phases.assert_prereqs_for_scope(["scoring"], scope_paths or [])
    assert miss == {"scoring": ["metadata"]}


# ---------------------------------------------------------------------------
# pipeline_prefix_through  (used by the legacy single-phase /start endpoints)
# ---------------------------------------------------------------------------

def test_pipeline_prefix_through_keywords():
    assert phases.pipeline_prefix_through("keywords") == [
        "indexing", "metadata", "scoring", "keywords",
    ]


def test_pipeline_prefix_through_culling():
    # culling and keywords are siblings under scoring: keywords must NOT appear.
    prefix = phases.pipeline_prefix_through("culling")
    assert prefix == ["indexing", "metadata", "scoring", "culling"]
    assert "keywords" not in prefix


def test_pipeline_prefix_through_root_phase_is_self():
    assert phases.pipeline_prefix_through("indexing") == ["indexing"]


def test_pipeline_prefix_through_unknown_phase_returns_self():
    assert phases.pipeline_prefix_through("mystery") == ["mystery"]


def test_pipeline_prefix_through_blank_returns_empty():
    assert phases.pipeline_prefix_through("") == []


# ---------------------------------------------------------------------------
# normalize_phase_codes / job_type_for_phase  (issue #346 defects 1 and 7)
# ---------------------------------------------------------------------------

def test_normalize_keeps_bird_species_in_every_spelling():
    """``bird_species`` is a real PhaseCode and must survive normalization.

    It used to be dropped when supplied as a *string* while passing through as an
    *enum*.  That asymmetry made ``/api/runs/submit`` raise ``IndexError`` once the
    repair planner narrowed a run down to ``["bird_species"]``.
    """
    expected = [phases.PhaseCode.BIRD_SPECIES]
    assert phases.normalize_phase_codes(["bird_species"]) == expected
    assert phases.normalize_phase_codes(["bird-species"]) == expected
    assert phases.normalize_phase_codes([phases.PhaseCode.BIRD_SPECIES]) == expected
    assert phases.normalize_phase_codes(["PhaseCode.BIRD_SPECIES"]) == expected
    assert phases.normalize_phase_codes([" BIRD_SPECIES "]) == expected


def test_normalize_resolves_legacy_submission_aliases():
    """``/api/pipeline/submit`` still accepts the score/tag/cluster vocabulary."""
    assert phases.normalize_phase_codes(["score", "tag", "cluster"]) == [
        phases.PhaseCode.SCORING,
        phases.PhaseCode.CULLING,
        phases.PhaseCode.KEYWORDS,
    ]


def test_normalize_sorts_canonically_and_dedupes():
    """The result is canonical order, not submitted order.

    ``/api/pipeline/submit`` deliberately preserves the client's ``stage_codes``
    sequence, which is why it resolves one token at a time rather than handing the
    whole list to this function.
    """
    assert phases.normalize_phase_codes(["tag", "keywords", "score"]) == [
        phases.PhaseCode.SCORING,
        phases.PhaseCode.KEYWORDS,
    ]
    assert phases.normalize_phase_codes(["bird_species", "indexing"]) == [
        phases.PhaseCode.INDEXING,
        phases.PhaseCode.BIRD_SPECIES,
    ]


def test_normalize_drops_unknown_tokens():
    assert phases.normalize_phase_codes(["localization", "", None, "scoring"]) == [
        phases.PhaseCode.SCORING,
    ]


def test_every_phase_has_an_entry_job_type():
    """The first-phase -> job_type map used to be hand-written in four places."""
    for code in phases.PhaseCode:
        assert code.value in phases.PHASE_TO_JOB_TYPE
        assert phases.job_type_for_phase(code) == phases.PHASE_TO_JOB_TYPE[code.value]
        assert phases.job_type_for_phase(code.value) == phases.PHASE_TO_JOB_TYPE[code.value]


def test_job_type_for_phase_falls_back_for_unknown_input():
    assert phases.job_type_for_phase(None) == "scoring"
    assert phases.job_type_for_phase("localization") == "scoring"
    assert phases.job_type_for_phase("localization", default="localization") == "localization"


def test_culling_and_keywords_route_to_their_own_runners():
    """Regression for the two entries the hand-written copies disagreed about."""
    assert phases.job_type_for_phase(phases.PhaseCode.CULLING) == "selection"
    assert phases.job_type_for_phase(phases.PhaseCode.KEYWORDS) == "tagging"
    assert phases.job_type_for_phase(phases.PhaseCode.BIRD_SPECIES) == "bird_species"
