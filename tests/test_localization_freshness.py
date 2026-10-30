"""Selected-versus-current scenarios reused from the skills authority experiments."""
import pytest

from modules.localization_freshness import selection_freshness


def run(**extra):
    return {"id": 11, "is_current": False, "status": "detected", "detector_key": "bird",
            "coord_space": "display_normalized", "source_hash": "s1", "source_hash_version": "v1",
            "rendition_hash": "r1", "rendition_version": "display/1", "detector_version": "model/1",
            "detector_config_hash": "c1", **extra}


def test_selected_noncurrent_run_remains_usable_when_source_and_rendition_match():
    assert selection_freshness(run(), current_run=run(id=12, is_current=True)).usable


@pytest.mark.parametrize("change,reason", [
    ({"source_hash": "s2"}, "source_changed"),
    ({"source_hash_version": "v2"}, "source_changed"),
    ({"rendition_hash": "r2"}, "rendition_changed"),
    ({"coord_space": "legacy_unverified"}, "coordinate_space_unverified"),
])
def test_stale_or_unsupported_selected_artifact_is_excluded(change, reason):
    result = selection_freshness(run(**change), current_run=run(id=12, is_current=True))
    assert not result.usable and result.reason == reason


def test_observed_source_change_wins_even_before_a_new_run_exists():
    result = selection_freshness(run(), source={"status": "available", "hash": "s2", "version": "v1"})
    assert not result.usable and result.reason == "source_changed"


@pytest.mark.parametrize("source", [None, {"status": "unreadable"}, {"status": "not_observed"}])
def test_managed_authority_requires_verified_source_and_approval(source):
    result = selection_freshness(run(), source=source, approval={"active": True}, managed=True)
    assert not result.usable


def test_revoked_policy_is_unavailable_without_waiting_for_cleanup():
    result = selection_freshness(run(), source={"status": "available", "hash": "s1", "version": "v1"},
                                 approval={"active": False}, managed=True)
    assert not result.usable and result.reason == "policy_revoked"


def test_unknown_historical_source_keeps_explicit_legacy_compatibility():
    result = selection_freshness(run(source_hash=None, source_hash_version=None))
    assert result.usable and result.reason == "legacy_unverified"


def test_control_read_failure_never_silently_disables_freshness():
    from types import SimpleNamespace
    from modules.localization_freshness import freshness_enabled

    def unavailable(_):
        raise RuntimeError('temporary database failure')
    with pytest.raises(RuntimeError,match='temporary'):
        freshness_enabled(SimpleNamespace(query_one=unavailable))
