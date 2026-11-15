"""#869: species abstains (no_bird_box) instead of storing a whole-frame species when no bird box is found.

The whole-frame BioCLIP embedding is still produced and persisted (decision E1 on #869). A transient
failure to get a box (detector unavailable, stored-box lookup failed) is retryable, not an abstention.
"""
import pytest

import modules.bird_species as bs
from modules.bird_detection import BBOX_NOT_DETECTED, bbox_scan_failed
from modules.bird_species import BirdSpeciesRunner, no_box_outcome
from modules.bird_species_eligibility import (
    BIRD_SPECIES_NO_BOX_SKIP_REASON,
    BirdSpeciesEligibility,
    _sql_bird_species_exhausted_ips,
    classify_image_row,
)

_BOX = {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "conf": 0.5, "img_w": 10, "img_h": 10}
#: The real authority path, captured before the autouse fixture below stubs it out for legacy-path tests.
_ORIGINAL_AUTHORITY = BirdSpeciesRunner._process_authority_species


class _Clf:
    def __init__(self, last_bbox=None, mode="full_frame", last_error=None):
        self.last_bbox, self.last_input_mode, self.last_error = last_bbox, mode, last_error


# --------------------------------------------------------------------------- the outcome helper

@pytest.mark.parametrize("choice,clf,expected", [
    # Embedded detector ran and found no bird -> abstain.
    ({"mode": "legacy"}, _Clf(dict(BBOX_NOT_DETECTED)), "no_box"),
    # Any scan error is retried; only a real not-detected result is final (#869 condition 2).
    ({"mode": "legacy"}, _Clf(bbox_scan_failed("detect_error: boom")), "transient"),
    # The detector could not load: retry later, store nothing.
    ({"mode": "legacy"}, _Clf(bbox_scan_failed("detector_unavailable")), "transient"),
    # A box was found: classify as before.
    ({"mode": "legacy"}, _Clf(dict(_BOX), mode="detector_crop"), None),
    # Retired detector: a stored not-detected sentinel abstains; never scanned, scan failed or a
    # failed lookup is retried.
    ({"mode": "full_frame", "region": None, "stored_not_detected": True}, _Clf(None), "no_box"),
    ({"mode": "full_frame", "region": None}, _Clf(None), "transient"),
    ({"mode": "full_frame", "region": None, "lookup_failed": True}, _Clf(None), "transient"),
    # A small selection excluded on purpose (#598) keeps its current behaviour (out of scope).
    ({"mode": "full_frame", "region": None, "exclusion_reason": "selected_area_below_0.005"}, _Clf(None), None),
    # Region and stored-box crops are unaffected.
    ({"mode": "region", "region": (0, 0, 1, 1)}, _Clf(None, mode="region"), None),
    ({"mode": "stored_box", "region": (0, 0, 1, 1)}, _Clf(None, mode="region"), None),
    # A classify failure is handled by the existing failure path, not as an abstention.
    ({"mode": "legacy"}, _Clf(dict(BBOX_NOT_DETECTED), last_error="decode failed"), None),
])
def test_no_box_outcome(choice, clf, expected):
    assert no_box_outcome(choice, clf) == expected


@pytest.mark.parametrize("stored,not_detected", [
    ({"detected": False}, True),
    ('{"detected": false}', True),
    (None, False),                                              # never scanned
    ({"detected": False, "error": "file_missing"}, False),      # scan failed
    ({"x1": 1, "y1": 2, "x2": 3, "y2": 4, "img_w": 10, "img_h": 10}, False),
])
def test_stored_box_input_flags_only_a_real_not_detected(monkeypatch, stored, not_detected):
    monkeypatch.setattr("modules.localization_legacy.read_bird_bbox",
                        lambda conn, image_id, prefer_normalized=None: stored)
    monkeypatch.setattr(bs.db, "get_connector", lambda: object())
    choice = bs.stored_box_input(3, {"mode": "legacy"})
    assert bool(choice.get("stored_not_detected")) is not_detected


def test_stored_box_lookup_failure_is_flagged(monkeypatch):
    def boom(conn, image_id, prefer_normalized=None):
        raise RuntimeError("db down")

    monkeypatch.setattr("modules.localization_legacy.read_bird_bbox", boom)
    monkeypatch.setattr(bs.db, "get_connector", lambda: object())
    choice = bs.stored_box_input(3, {"mode": "legacy"})
    assert choice["mode"] == "full_frame" and choice["lookup_failed"] is True


# --------------------------------------------------------------------------- eligibility

def test_no_bird_box_skip_counts_as_exhausted():
    assert classify_image_row(image_id=1, has_birds=True, has_species=False, has_exhausted_marker=False,
                              ips_status="skipped", ips_skip_reason=BIRD_SPECIES_NO_BOX_SKIP_REASON
                              ) == BirdSpeciesEligibility.EXHAUSTED
    sql = _sql_bird_species_exhausted_ips("i")
    assert "'no_species_match'" in sql and "'no_bird_box'" in sql


# --------------------------------------------------------------------------- the legacy runner path

@pytest.fixture(autouse=True)
def _legacy_species_path(monkeypatch):
    monkeypatch.setattr(BirdSpeciesRunner, "_process_authority_species", lambda self, *a, **k: None)


class _RunClf:
    def __init__(self, last_bbox, mode="full_frame"):
        self.last_bbox, self.last_input_mode, self.last_error = last_bbox, mode, None

    def classify(self, path, species, threshold, top_k, region=None, use_detector=True):
        return [("Purple Martin", 0.65)]


def _run(monkeypatch, tmp_path, *, last_bbox, choice=None, refresh=False, detector_on=True, mode="full_frame",
         stored=None):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    rec = {"keywords": [], "exhausted": [], "phase": [], "embeddings": []}
    runner = BirdSpeciesRunner()
    runner.classifier = _RunClf(last_bbox, mode=mode)
    monkeypatch.setattr(bs, "use_regions_enabled", lambda: True)
    monkeypatch.setattr(bs, "species_input_for_image", lambda image_id: choice or {"mode": "legacy"})
    monkeypatch.setattr("modules.bird_detection.embedded_detector_enabled", lambda: detector_on)
    monkeypatch.setattr("modules.localization_legacy.read_bird_bbox",
                        lambda conn, image_id, prefer_normalized=None: stored)
    monkeypatch.setattr(runner, "_persist_bioclip_embedding", lambda image_id: rec["embeddings"].append(image_id))
    monkeypatch.setattr(bs, "write_legacy_bird_bbox", lambda i, b: None)
    monkeypatch.setattr(bs.db, "get_connector", lambda: object())
    monkeypatch.setattr(bs.db, "set_image_phase_status", lambda *a, **kw: rec["phase"].append((a, kw)))
    monkeypatch.setattr(bs.db, "get_resolved_image_keywords",
                        lambda image_id, legacy_fallback=None, hide_internal=False: "birds,species:purple martin")
    monkeypatch.setattr("modules.bird_species_eligibility.build_bird_species_keyword_csv",
                        lambda image_id, legacy_csv, new_species: ",".join(["birds", *new_species]))
    monkeypatch.setattr(bs.db, "update_image_keywords_for_image",
                        lambda image_id, csv, **kw: rec["keywords"].append(csv))
    monkeypatch.setattr("modules.bird_species_eligibility.mark_species_exhausted",
                        lambda image_id, **kw: rec["exhausted"].append((image_id, kw.get("skip_reason"))))
    result = runner._process_bird_species_image_row(
        {"id": 3, "file_path": str(img)}, species_list=["Purple Martin"], threshold=0.5, top_k=1,
        phase_code="bird_species", log=lambda *a, **kw: None, refresh=refresh)
    return result, rec


def test_no_box_stores_no_species_but_keeps_the_embedding(monkeypatch, tmp_path):
    result, rec = _run(monkeypatch, tmp_path, last_bbox=dict(BBOX_NOT_DETECTED))
    assert result == (0, 1)
    assert rec["keywords"] == []                                   # no species written
    assert rec["exhausted"] == [(3, BIRD_SPECIES_NO_BOX_SKIP_REASON)]
    assert rec["embeddings"] == [3]                                # E1: whole-frame embedding kept


def test_no_box_on_refresh_removes_a_stored_species(monkeypatch, tmp_path):
    """Owner decision on #869: a re-run under the new rule removes a stored whole-frame species."""
    _, rec = _run(monkeypatch, tmp_path, last_bbox=dict(BBOX_NOT_DETECTED), refresh=True)
    assert rec["keywords"] == ["birds"]
    assert rec["exhausted"] == [(3, BIRD_SPECIES_NO_BOX_SKIP_REASON)]


def test_detector_unavailable_is_retryable_and_stores_nothing(monkeypatch, tmp_path):
    result, rec = _run(monkeypatch, tmp_path, last_bbox=bbox_scan_failed("detector_unavailable"), refresh=True)
    assert result == (0, 1)
    assert rec["keywords"] == [] and rec["exhausted"] == []
    (args, kw), = rec["phase"]
    assert args[2] == "failed" and "detector_unavailable" in kw["error"]


def test_retired_detector_with_stored_not_detected_abstains(monkeypatch, tmp_path):
    _, rec = _run(monkeypatch, tmp_path, last_bbox=None, detector_on=False, stored={"detected": False})
    assert rec["keywords"] == []
    assert rec["exhausted"] == [(3, BIRD_SPECIES_NO_BOX_SKIP_REASON)]


@pytest.mark.parametrize("stored", [None, {"detected": False, "error": "detect_error: boom"}])
def test_retired_detector_without_a_scanned_box_retries(monkeypatch, tmp_path, stored):
    """A never-scanned (NULL) or failed stored box is work still owed, not a final no_bird_box."""
    result, rec = _run(monkeypatch, tmp_path, last_bbox=None, detector_on=False, stored=stored, refresh=True)
    assert result == (0, 1)
    assert rec["keywords"] == [] and rec["exhausted"] == []
    (args, kw), = rec["phase"]
    assert args[2] == "failed" and "stored_box_unavailable" in kw["error"]


def test_embedded_detect_error_retries(monkeypatch, tmp_path):
    result, rec = _run(monkeypatch, tmp_path, last_bbox=bbox_scan_failed("detect_error: boom"))
    assert result == (0, 1)
    assert rec["keywords"] == [] and rec["exhausted"] == []
    (args, kw), = rec["phase"]
    assert args[2] == "failed" and "detect_error" in kw["error"]


def test_a_found_box_still_stores_the_species(monkeypatch, tmp_path):
    result, rec = _run(monkeypatch, tmp_path, last_bbox=dict(_BOX), mode="detector_crop")
    assert result == (1, 0)
    assert rec["keywords"] == ["birds,species:Purple Martin"]
    assert rec["exhausted"] == []


# --------------------------------------------------------------------------- the authority runner path

class _FakeStore:
    published, failed = [], []

    def __init__(self, conn):
        pass

    def observe(self, image_id, source_observation=None):
        return {"status": "pending"}

    def claim_next(self, image_id=None):
        return {"id": 1, "action": "classify", "input_state": {"semantic": {"selection": None}}}

    def renew(self, claim):
        return True

    def publish(self, claim, **kw):
        _FakeStore.published.append(kw)
        return True

    def fail(self, claim, reason):
        _FakeStore.failed.append(reason)


class _ActiveConn:
    def query_one(self, sql, params=None):
        return {"mode": "active"} if "localization_authority_control" in sql else {"managed": True}


@pytest.mark.parametrize("last_bbox,published_reason,failed", [
    (dict(BBOX_NOT_DETECTED), "no_bird_box", []),
    (bbox_scan_failed("detector_unavailable"), None, ["no_bird_box_transient: detector_unavailable"]),
])
def test_authority_path_abstains_or_retries(monkeypatch, tmp_path, last_bbox, published_reason, failed):
    monkeypatch.setattr(BirdSpeciesRunner, "_process_authority_species", _ORIGINAL_AUTHORITY)
    _FakeStore.published, _FakeStore.failed = [], []
    monkeypatch.setattr(bs.db, "get_connector", lambda: _ActiveConn())
    monkeypatch.setattr("modules.localization_species.SpeciesStore", _FakeStore)
    monkeypatch.setattr("modules.localization_authority_worker.observe_source", lambda path: {"status": "available"})
    monkeypatch.setattr(bs, "species_input_for_image", lambda image_id: {"mode": "legacy"})
    monkeypatch.setattr("modules.bird_detection.embedded_detector_enabled", lambda: True)
    runner = BirdSpeciesRunner()
    clf = _RunClf(last_bbox)
    clf.last_image_embedding = [0.1] * 768
    runner.classifier = clf
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    result = runner._process_authority_species({"id": 3, "file_path": str(img)}, ["Purple Martin"], 0.5, 1)
    assert result == (0, 1)
    if published_reason:
        (kw,) = _FakeStore.published
        assert kw["predictions"] == [] and kw["no_match_reason"] == published_reason
        assert kw["embedding"] == [0.1] * 768 and kw["space_code"] == "bioclip_2_image"
    else:
        assert _FakeStore.published == []
    assert _FakeStore.failed == failed
