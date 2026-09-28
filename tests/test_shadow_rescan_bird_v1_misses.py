"""Guards for the one-time v1 shadow rescan cohort."""

from scripts.maintenance.shadow_rescan_bird_v1_misses import candidate_state


def _state(**overrides):
    row = {
        "bird_bbox": {"detected": False},
        "run_id": 42,
        "status": "no_detection",
        "detector_version": "legacy_unversioned",
        "detector_config_hash": "legacy",
    }
    row.update(overrides)
    return row


def test_only_the_frozen_legacy_no_detection_is_eligible():
    assert candidate_state(_state(), 42, "v1") == "ready"
    assert candidate_state(_state(run_id=43), 42, "v1") == "shadow_changed"
    assert candidate_state(_state(status="detected"), 42, "v1") == "shadow_changed"
    assert candidate_state(_state(bird_bbox={"detected": False, "error": "decode_error"}), 42, "v1") == "production_changed"
    assert candidate_state(_state(bird_bbox={"img_w": 100}), 42, "v1") == "production_changed"


def test_v1_result_is_idempotent():
    row = _state(detector_version="synthet/bird-detect-v0/bird_detect_v1.pt",
                 detector_config_hash="v1", status="detected", run_id=99)
    assert candidate_state(row, 42, "v1") == "already_v1"
    assert candidate_state(row, 42, "other_config") == "shadow_changed"
