"""Legacy ``images.bird_bbox`` -> normalized localization mapping (issue #370).

Pure-function coverage: no database. The import itself is exercised against a real
PostgreSQL by ``tests/integration/test_localization_import_e2e.py``.

These tests pin the classification table in
``docs/architecture/pipeline/localization-rollout.md`` stage 2, and the rule that matters
most for the migration: an unrecognised payload becomes a *visible terminal error*, never
a silent ``no_detection``. Guessing would erase the fact that something went wrong.
"""

from __future__ import annotations

import pytest

from modules.bird_detection import RETRYABLE_BBOX_ERRORS
from modules.localization_legacy import (
    LEGACY_OBJECT_CLASS,
    classify_legacy_bbox,
    legacy_payload_from_normalized,
    normalized_region_from_legacy,
    redact_error_detail,
)

# A real payload copied from the live column, keys and all.
REAL_BOX = {
    "x1": 4460, "x2": 7709, "y1": 934, "y2": 3959,
    "conf": 0.6913, "img_h": 5504, "img_w": 8256, "area_frac": 0.216283,
}


# ---------------------------------------------------------------------------
# classify_legacy_bbox — the stage 2 mapping table
# ---------------------------------------------------------------------------

def test_null_is_not_an_attempt():
    """NULL means never scanned, so there is no run row at all.

    This is the distinction the whole design rests on: absence of a run means
    "not attempted", and it must never be confused with "attempted, found nothing".
    """
    assert classify_legacy_bbox(None) is None


def test_real_box_is_detected():
    v = classify_legacy_bbox(REAL_BOX)
    assert v["status"] == "detected"
    assert v["is_retryable"] is False
    assert v["error_code"] is None


def test_detected_false_is_no_detection():
    v = classify_legacy_bbox({"detected": False})
    assert v["status"] == "no_detection"
    assert v["is_retryable"] is False


def test_detector_unavailable_is_retryable():
    v = classify_legacy_bbox({"detected": False, "error": "detector_unavailable"})
    assert v["status"] == "retryable_error"
    assert v["is_retryable"] is True
    assert v["error_code"] == "detector_unavailable"


@pytest.mark.parametrize("reason", [
    "file_missing",
    "decode_error: cannot identify or decode RAW image file '/mnt/d/Photos/x.NEF'",
    "detect_error: boom",
    "classify_error: boom",
])
def test_data_terminal_reasons_are_terminal(reason):
    v = classify_legacy_bbox({"detected": False, "error": reason})
    assert v["status"] == "terminal_error"
    assert v["is_retryable"] is False


def test_retryability_is_not_redefined_here():
    """The retryable set lives in modules.bird_detection; this module must defer to it.

    If someone adds a reason there, classification has to follow without a second edit --
    two copies of this set is exactly the drift the consolidation work exists to prevent.
    """
    for reason in RETRYABLE_BBOX_ERRORS:
        v = classify_legacy_bbox({"detected": False, "error": reason})
        assert v["status"] == "retryable_error", reason
        assert v["is_retryable"] is True, reason


@pytest.mark.parametrize("payload,label", [
    ([1, 2, 3], "non-object"),
    ("not json at all", "unparseable string"),
    ({"weird": 1}, "object with neither geometry nor detected"),
    (42, "bare number"),
])
def test_unrecognised_payloads_are_visible_terminal_errors(payload, label):
    """A shape we do not understand must stay visible, not become 'no detection'."""
    v = classify_legacy_bbox(payload)
    assert v["status"] == "terminal_error", label
    assert v["error_code"] == "malformed_payload", label


def test_json_string_payload_is_parsed():
    """psycopg2 hands back parsed JSONB, but callers may pass raw text."""
    import json

    assert classify_legacy_bbox(json.dumps(REAL_BOX))["status"] == "detected"
    assert classify_legacy_bbox(json.dumps({"detected": False}))["status"] == "no_detection"


def test_error_wins_over_geometry():
    """A payload carrying both is a failed scan, not a detection."""
    both = dict(REAL_BOX, error="decode_error: boom")
    assert classify_legacy_bbox(both)["status"] == "terminal_error"


# ---------------------------------------------------------------------------
# redact_error_detail
# ---------------------------------------------------------------------------

def test_redaction_drops_paths_but_keeps_the_code():
    detail = "decode_error: cannot identify or decode RAW image file '/mnt/d/Photos/Z8/a.NEF'"
    out = redact_error_detail(detail)
    assert out.startswith("decode_error:")
    assert "/mnt/d/Photos" not in out
    assert "<path>" in out


def test_redaction_handles_windows_paths_and_none():
    assert "D:" not in (redact_error_detail(r"decode_error: D:\Photos\a.NEF") or "")
    assert redact_error_detail(None) is None
    assert redact_error_detail("") is None


def test_redaction_is_length_capped():
    assert len(redact_error_detail("x" * 500)) <= 200


# ---------------------------------------------------------------------------
# normalized_region_from_legacy
# ---------------------------------------------------------------------------

def test_region_is_normalized_against_the_payloads_own_dimensions():
    """Dimensions come from the payload, never the current images row.

    The file may have been replaced since the scan; using today's dimensions would
    silently move the box.
    """
    r = normalized_region_from_legacy(REAL_BOX)
    assert r["object_class"] == LEGACY_OBJECT_CLASS
    assert r["rank"] == 0
    assert r["x1"] == pytest.approx(4460 / 8256)
    assert r["y2"] == pytest.approx(3959 / 5504)
    assert r["confidence"] == pytest.approx(0.6913)
    assert (r["display_width"], r["display_height"]) == (8256, 5504)


@pytest.mark.parametrize("payload,label", [
    ({"detected": False}, "no geometry"),
    ({"x1": 10, "y1": 10, "x2": 50, "y2": 50}, "no dimensions"),
    ({"x1": 10, "y1": 10, "x2": 50, "y2": 50, "img_w": 0, "img_h": 100}, "zero width"),
    ({"x1": 10, "y1": 10, "x2": 5, "y2": 50, "img_w": 100, "img_h": 100}, "inverted x"),
    ({"x1": 10, "y1": 10, "x2": 10, "y2": 50, "img_w": 100, "img_h": 100}, "zero area"),
    ({"x1": -5, "y1": 10, "x2": 50, "y2": 50, "img_w": 100, "img_h": 100}, "negative"),
    ({"x1": 10, "y1": 10, "x2": 150, "y2": 50, "img_w": 100, "img_h": 100}, "past the edge"),
], ids=lambda v: v if isinstance(v, str) else "")
def test_unusable_geometry_yields_no_region(payload, label):
    """Rejected rather than clamped -- clamping would invent a box nobody detected.

    The run row still records `detected`; only the geometry is dropped.
    """
    assert normalized_region_from_legacy(payload) is None, label


def test_out_of_range_confidence_is_dropped_not_clamped():
    r = normalized_region_from_legacy(dict(REAL_BOX, conf=1.4))
    assert r is not None
    assert r["confidence"] is None


# ---------------------------------------------------------------------------
# legacy_payload_from_normalized — the compatibility projection
# ---------------------------------------------------------------------------

def test_imported_rows_reproduce_their_payload_verbatim():
    """Byte-for-byte, malformed shapes included.

    Stage 8 retires `images.bird_bbox` behind this projection, so an imported row has to
    return exactly what the column held -- which is why legacy_payload is stored at all.
    """
    for original in (REAL_BOX, {"detected": False}, {"weird": 1}, {"detected": False, "error": "x"}):
        run = {"status": "detected", "legacy_payload": original}
        assert legacy_payload_from_normalized(run, []) is original


def test_synthesis_round_trips_a_native_run_to_pixels():
    """A natively-written run has no legacy_payload, so the shape is rebuilt."""
    run = {
        "status": "detected", "legacy_payload": None,
        "display_width": 8256, "display_height": 5504, "error_code": None,
    }
    regions = [{
        "object_class": "bird", "rank": 0,
        "x1": 4460 / 8256, "y1": 934 / 5504, "x2": 7709 / 8256, "y2": 3959 / 5504,
        "confidence": 0.6913,
    }]
    out = legacy_payload_from_normalized(run, regions)
    assert (out["x1"], out["y1"], out["x2"], out["y2"]) == (4460, 934, 7709, 3959)
    assert (out["img_w"], out["img_h"]) == (8256, 5504)
    assert out["conf"] == pytest.approx(0.6913)


def test_synthesis_uses_the_top_ranked_region():
    run = {"status": "detected", "legacy_payload": None,
           "display_width": 100, "display_height": 100, "error_code": None}
    regions = [
        {"rank": 1, "x1": 0.0, "y1": 0.0, "x2": 0.1, "y2": 0.1, "confidence": 0.3},
        {"rank": 0, "x1": 0.5, "y1": 0.5, "x2": 0.9, "y2": 0.9, "confidence": 0.9},
    ]
    out = legacy_payload_from_normalized(run, regions)
    assert (out["x1"], out["y1"]) == (50, 50)


@pytest.mark.parametrize("status", ["retryable_error", "terminal_error"])
def test_synthesis_of_an_error_run_keeps_the_sentinel_shape(status):
    run = {"status": status, "legacy_payload": None, "error_code": "decode_error",
           "display_width": None, "display_height": None}
    assert legacy_payload_from_normalized(run, []) == {
        "detected": False, "error": "decode_error",
    }


def test_synthesis_of_no_detection():
    run = {"status": "no_detection", "legacy_payload": None,
           "display_width": None, "display_height": None, "error_code": None}
    assert legacy_payload_from_normalized(run, []) == {"detected": False}


def test_synthesis_without_dimensions_does_not_invent_a_box():
    """A detected run whose dimensions were never recorded cannot produce pixel coords."""
    run = {"status": "detected", "legacy_payload": None,
           "display_width": None, "display_height": None, "error_code": None}
    regions = [{"rank": 0, "x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5, "confidence": 0.5}]
    assert legacy_payload_from_normalized(run, regions) == {"detected": False}


# ---------------------------------------------------------------------------
# read_bird_bbox — the compatibility reader (no database; fake connector)
# ---------------------------------------------------------------------------

class _FakeConn:
    """Minimal query_one/query connector recording what was asked.

    Deliberately not a mock: the point is to assert *which source was consulted*, which
    is the whole behavioural contract of a normalized-first reader with fallback.
    """

    def __init__(self, *, legacy=None, run=None, regions=None, fail_on=()):
        self.legacy = legacy
        self.run = run
        self.regions = regions or []
        self.fail_on = fail_on
        self.queries: list[str] = []

    def _tag(self, sql: str) -> str:
        if "image_localization_runs" in sql:
            return "run"
        if "image_regions" in sql:
            return "regions"
        return "legacy"

    def query_one(self, sql, params=()):
        tag = self._tag(sql)
        self.queries.append(tag)
        if tag in self.fail_on:
            raise RuntimeError("boom")
        if tag == "run":
            return dict(self.run) if self.run else None
        return {"bird_bbox": self.legacy}

    def query(self, sql, params=()):
        tag = self._tag(sql)
        self.queries.append(tag)
        if tag in self.fail_on:
            raise RuntimeError("boom")
        return list(self.regions)


def _read(conn, **kw):
    from modules.localization_legacy import read_bird_bbox

    return read_bird_bbox(conn, 42, **kw)


def test_reader_is_a_plain_column_read_when_disabled():
    """Flag off must be indistinguishable from today's SELECT -- that is what makes it
    safe to land before anything writes the normalized tables."""
    conn = _FakeConn(legacy=REAL_BOX, run={"id": 1, "status": "detected"})
    assert _read(conn, prefer_normalized=False) == REAL_BOX
    assert conn.queries == ["legacy"], "normalized tables must not be touched"


def test_reader_returns_none_for_never_scanned_when_disabled():
    conn = _FakeConn(legacy=None)
    assert _read(conn, prefer_normalized=False) is None


def test_reader_prefers_an_imported_run_and_replays_its_payload():
    conn = _FakeConn(
        legacy={"detected": False},  # deliberately different, to prove which one wins
        run={"id": 1, "status": "detected", "legacy_payload": REAL_BOX,
             "display_width": 8256, "display_height": 5504, "error_code": None},
    )
    assert _read(conn, prefer_normalized=True) == REAL_BOX
    assert "legacy" not in conn.queries
    assert "regions" not in conn.queries, "an imported run replays its payload, no region read"


def test_reader_synthesizes_from_regions_for_a_native_run():
    conn = _FakeConn(
        legacy=None,
        run={"id": 7, "status": "detected", "legacy_payload": None,
             "display_width": 8256, "display_height": 5504, "error_code": None},
        regions=[{"object_class": "bird", "rank": 0,
                  "x1": 4460 / 8256, "y1": 934 / 5504,
                  "x2": 7709 / 8256, "y2": 3959 / 5504, "confidence": 0.6913}],
    )
    out = _read(conn, prefer_normalized=True)
    assert (out["x1"], out["y1"], out["x2"], out["y2"]) == (4460, 934, 7709, 3959)
    assert conn.queries == ["run", "regions"]


def test_reader_falls_back_to_the_column_when_no_current_run():
    """During the import, and for any image it skipped, the column is still the only
    source. A missing run must not read as 'no bird'."""
    conn = _FakeConn(legacy=REAL_BOX, run=None)
    assert _read(conn, prefer_normalized=True) == REAL_BOX
    assert conn.queries == ["run", "legacy"]


def test_missing_run_is_distinguished_from_a_run_projecting_to_none():
    """A never-scanned image and a missing run both look 'empty' -- they must not be
    conflated, or the legacy fallback silently stops firing."""
    conn = _FakeConn(legacy=None, run=None)
    assert _read(conn, prefer_normalized=True) is None
    assert conn.queries == ["run", "legacy"], "fallback must still be attempted"


def test_reader_projects_no_detection_without_consulting_the_column():
    conn = _FakeConn(
        legacy=REAL_BOX,
        run={"id": 2, "status": "no_detection", "legacy_payload": {"detected": False},
             "display_width": None, "display_height": None, "error_code": None},
    )
    assert _read(conn, prefer_normalized=True) == {"detected": False}
    assert "legacy" not in conn.queries


@pytest.mark.parametrize("fail_on,expected_tail", [
    (("run",), ["run", "legacy"]),
    (("regions",), ["run", "regions", "legacy"]),
])
def test_a_normalized_lookup_failure_falls_back_instead_of_raising(fail_on, expected_tail):
    """A reader must never take down a caller that has a working legacy column."""
    conn = _FakeConn(
        legacy=REAL_BOX, fail_on=fail_on,
        run={"id": 3, "status": "detected", "legacy_payload": None,
             "display_width": 100, "display_height": 100, "error_code": None},
    )
    assert _read(conn, prefer_normalized=True) == REAL_BOX
    assert conn.queries == expected_tail


def test_flag_defaults_to_false(monkeypatch):
    """Normalized reads ship dark; enabling them must be a deliberate act."""
    from modules import localization_legacy as mod

    monkeypatch.setattr(
        "modules.config.get_config_value",
        lambda key, default=None: default,
    )
    assert mod.read_normalized_first_enabled() is False


def test_reader_consults_the_flag_when_not_overridden(monkeypatch):
    from modules import localization_legacy as mod

    seen = {}

    def _fake_get(key, default=None):
        seen["key"] = key
        return True

    monkeypatch.setattr("modules.config.get_config_value", _fake_get)
    conn = _FakeConn(legacy=REAL_BOX, run=None)
    mod.read_bird_bbox(conn, 42)
    assert seen["key"] == mod.READ_NORMALIZED_FIRST_KEY
    assert conn.queries == ["run", "legacy"], "flag on => normalized consulted first"
