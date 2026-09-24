"""Shadow localization phase, slice 1 (#387): registry, gating, decode, outcomes.

No database: persistence is stubbed here and exercised for real in
``tests/integration/test_localization_shadow_e2e.py`` (``-m postgres``).
"""

from __future__ import annotations

import sys
import types

import pytest
from PIL import Image

from modules import localization as loc
from modules import phases
from modules.bird_detection import rank_boxes
from modules.rendition import DecodeRoute


@pytest.fixture
def localization_flag(monkeypatch):
    """Set ``localization.enabled`` without touching the real config file."""
    state = {"enabled": False}

    def _get(key, default=None):
        if key == "localization.enabled":
            return state["enabled"]
        return default

    monkeypatch.setattr("modules.config.get_config_value", _get)
    return state


# ---------------------------------------------------------------------------
# Registry (AC-1, AC-2, AC-3, AC-5)
# ---------------------------------------------------------------------------

def test_ac1_localization_follows_metadata_with_metadata_as_only_prereq():
    order = [p.value for p in phases.PIPELINE_PHASE_ORDER]
    assert order.index("localization") == order.index("metadata") + 1
    assert phases.PHASE_PREREQUISITES["localization"] == ("metadata",)


def test_ac2_localization_is_preferred_before_its_consumers():
    assert phases.PHASE_PREFERRED_BEFORE["localization"] == ("scoring", "keywords", "bird_species")


@pytest.mark.parametrize("consumer, satisfied", [
    ("scoring", {"indexing", "metadata"}),
    ("keywords", {"indexing", "metadata", "scoring"}),
    ("bird_species", {"indexing", "metadata", "scoring", "keywords"}),
])
def test_ac3_missing_localization_never_blocks_a_consumer(consumer, satisfied):
    assert "localization" not in satisfied
    assert phases.missing_prerequisites([consumer], satisfied) == {}


def test_ac5_autodrive_default_targets_exclude_localization():
    from modules import runs_autodrive

    assert "localization" not in runs_autodrive.DEFAULT_TARGET_PHASES
    assert "localization" not in runs_autodrive.normalize_target_phases(None)


# ---------------------------------------------------------------------------
# Gating (AC-4) and public vocabulary (AC-17)
# ---------------------------------------------------------------------------

def test_ac4_submission_error_names_the_config_key(localization_flag):
    msg = phases.disabled_phase_submission_error(["metadata", "localization"])
    assert msg and "localization.enabled" in msg
    localization_flag["enabled"] = True
    assert phases.disabled_phase_submission_error(["metadata", "localization"]) is None


def test_ac4_ungated_phases_are_never_rejected(localization_flag):
    assert phases.disabled_phase_submission_error(["indexing", "scoring", "tagging"]) is None


def test_ac4_dispatcher_rejects_localization_while_disabled(localization_flag):
    from modules.job_dispatcher import JobDispatcher

    class _Runner:
        is_running = False
        started = False

        def start_batch(self, *_a, **_k):
            self.started = True
            return "Started"

    runner = _Runner()
    dispatcher = JobDispatcher(localization_runner=runner)
    ok, err = dispatcher._start_job({"id": 7, "job_type": "localization", "input_path": "/x"}, {})
    assert ok is False
    assert "localization.enabled" in err
    assert runner.started is False


def test_ac4_runner_refuses_to_start_while_disabled(localization_flag):
    from modules.localization_runner import LocalizationRunner

    runner = LocalizationRunner()
    assert "localization.enabled" in runner.start_batch("/x", job_id=1)
    assert runner.is_running is False


def test_ac17_public_phase_codes_hide_localization_until_enabled(localization_flag):
    assert "localization" not in phases.public_phase_codes()
    localization_flag["enabled"] = True
    assert phases.public_phase_codes() == [p.value for p in phases.PIPELINE_PHASE_ORDER]


def test_ac17_scope_preview_omits_localization_while_disabled(localization_flag, monkeypatch):
    from modules.api.routers import electron_scope_helpers

    monkeypatch.setattr("modules.db.get_folder_phase_summary", lambda *_a, **_k: [])
    monkeypatch.setattr(electron_scope_helpers, "scope_count_images_on_disk", lambda *_a: (0, 0))
    preview = electron_scope_helpers.compute_scope_preview_for_resolved_paths(["/x"], True)
    blob = repr(preview)
    assert "localization" not in blob
    assert "scoring" in blob


def test_ac17_seed_syncs_enabled_flag_for_gated_phase(localization_flag, monkeypatch):
    """``pipeline_phases.enabled`` follows the flag, which hides it from folder summaries."""
    from modules import db_legacy

    executed: list[tuple[str, tuple]] = []

    class _Tx:
        def execute(self, sql, params=()):
            executed.append((sql, tuple(params or ())))

        def query_one(self, _sql, params=()):
            return {"id": 1}  # every code already exists -> update branch

    class _Conn:
        def run_transaction(self, fn):
            return fn(_Tx())

    monkeypatch.setattr(db_legacy, "get_connector", lambda: _Conn())
    db_legacy.seed_pipeline_phases()
    enabled_updates = [p for sql, p in executed if "SET enabled" in sql]
    assert enabled_updates == [(0, "localization")]

    executed.clear()
    localization_flag["enabled"] = True
    db_legacy.seed_pipeline_phases()
    assert [p for sql, p in executed if "SET enabled" in sql] == [(1, "localization")]


# ---------------------------------------------------------------------------
# Detector identity (AC-13, decision 4)
# ---------------------------------------------------------------------------

def test_ac13_config_hash_covers_weights_and_every_knob():
    base = loc.detector_config_hash("w" * 64, 640, 0.25, 10)
    assert base == loc.detector_config_hash("w" * 64, 640, 0.25, 10)
    variants = {
        loc.detector_config_hash("x" * 64, 640, 0.25, 10),
        loc.detector_config_hash("w" * 64, 1280, 0.25, 10),
        loc.detector_config_hash("w" * 64, 640, 0.30, 10),
        loc.detector_config_hash("w" * 64, 640, 0.25, 5),
    }
    assert base not in variants and len(variants) == 4


def test_weights_hash_is_cached_on_path_size_mtime(tmp_path, monkeypatch):
    import hashlib
    import os

    weights = tmp_path / "w.pt"
    weights.write_bytes(b"abc")
    monkeypatch.setattr(loc, "_WEIGHTS_HASH_CACHE", {})
    first = loc.weights_sha256(str(weights))
    assert first == hashlib.sha256(b"abc").hexdigest()

    opened: list[str] = []
    real_open = open
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: opened.append(p) or real_open(p, *a, **k))
    assert loc.weights_sha256(str(weights)) == first
    assert opened == []  # served from cache

    weights.write_bytes(b"abcd")
    os.utime(weights, ns=(1, 2_000_000_000))
    assert loc.weights_sha256(str(weights)) == hashlib.sha256(b"abcd").hexdigest()


def test_ac10_disabled_detector_is_never_constructed_or_loaded(monkeypatch):
    from modules import bird_detection

    def _boom(*_a, **_k):
        raise AssertionError("detector must not load while disabled")

    monkeypatch.setattr(bird_detection.BirdDetector, "load_model", _boom)
    monkeypatch.setattr(bird_detection.BirdDetector, "_resolve_weights_path", _boom)
    ctx = loc.load_detector_context({"detectors": {"bird": {"enabled": False}}}, bird_cfg={})
    assert ctx.enabled is False and ctx.detector is None
    assert ctx.config_hash == loc.detector_config_hash("disabled", 640, 0.25, 10)


def test_ac9_detector_load_failure_becomes_a_context_error(monkeypatch):
    from modules import bird_detection

    def _fail(*_a, **_k):
        raise RuntimeError("no weights at /secret/path/w.pt")

    monkeypatch.setattr(bird_detection.BirdDetector, "_resolve_weights_path", _fail)
    ctx = loc.load_detector_context({}, bird_cfg={})
    assert ctx.enabled is True and ctx.detector is None
    assert ctx.load_error.startswith("detector_unavailable")
    assert "/secret/path" not in ctx.load_error


# ---------------------------------------------------------------------------
# Decode (AC-18, AC-19, AC-20)
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_file(tmp_path, monkeypatch):
    path = tmp_path / "DSC_0001.NEF"
    path.write_bytes(b"\x00" * 4096)
    monkeypatch.setattr("modules.localization.shutil.which", lambda _name: "/usr/bin/exiftool")
    monkeypatch.setattr("modules.thumbnails.read_orientation", lambda _p: None)
    return str(path)


def _embedded(monkeypatch, sizes: dict[str, tuple[int, int] | None]):
    monkeypatch.setattr(
        loc, "_exiftool_jpeg",
        lambda _path, tag: Image.new("RGB", sizes[tag]) if sizes.get(tag) else None,
    )


@pytest.fixture
def fake_rawpy(monkeypatch):
    calls: list[dict] = []

    class _Raw:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def postprocess(self, **kwargs):
            import numpy as np

            calls.append(kwargs)
            return np.zeros((4000, 6000, 3), dtype="uint8")

    monkeypatch.setitem(sys.modules, "rawpy", types.SimpleNamespace(imread=lambda _p: _Raw()))
    return calls


def test_ac18_full_size_jpgfromraw_is_used(raw_file, monkeypatch, fake_rawpy):
    _embedded(monkeypatch, {"JpgFromRaw": (8256, 5504), "PreviewImage": (1620, 1080)})
    decoded = loc.decode_for_localization(raw_file)
    assert decoded.descriptor.decode_route is DecodeRoute.RAW_JPG_FROM_RAW
    assert (decoded.descriptor.display_width, decoded.descriptor.display_height) == (8256, 5504)
    assert fake_rawpy == []


def test_ac19_small_previews_fall_through_to_rawpy(raw_file, monkeypatch, fake_rawpy):
    _embedded(monkeypatch, {"JpgFromRaw": None, "PreviewImage": (1620, 1080)})
    decoded = loc.decode_for_localization(raw_file)
    assert decoded.descriptor.decode_route is DecodeRoute.RAW_RAWPY
    assert decoded.notes == {"rejected_PreviewImage_long_edge": 1620}
    # Orientation is applied once, by our EXIF rule, never also by libraw.
    assert fake_rawpy and fake_rawpy[0]["user_flip"] == 0


def test_ac19_a_full_size_previewimage_is_acceptable(raw_file, monkeypatch, fake_rawpy):
    _embedded(monkeypatch, {"JpgFromRaw": None, "PreviewImage": (2048, 1365)})
    decoded = loc.decode_for_localization(raw_file)
    assert decoded.descriptor.decode_route is DecodeRoute.RAW_EMBEDDED_PREVIEW
    assert fake_rawpy == []


def test_ac20_route_distinguishes_jpgfromraw_from_preview(raw_file, monkeypatch, fake_rawpy):
    _embedded(monkeypatch, {"JpgFromRaw": (8256, 5504)})
    full = loc.decode_for_localization(raw_file).descriptor
    _embedded(monkeypatch, {"JpgFromRaw": None, "PreviewImage": (8256, 5504)})
    preview = loc.decode_for_localization(raw_file).descriptor
    assert full.decode_route != preview.decode_route
    assert full.rendition_hash != preview.rendition_hash


def test_orientation_from_source_is_applied_and_recorded(raw_file, monkeypatch, fake_rawpy):
    _embedded(monkeypatch, {"JpgFromRaw": (6000, 4000)})
    monkeypatch.setattr("modules.thumbnails.read_orientation", lambda _p: 6)
    d = loc.decode_for_localization(raw_file).descriptor
    assert d.orientation == 6
    assert (d.display_width, d.display_height) == (4000, 6000)


def test_decode_failure_raises_decode_error(tmp_path):
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"not an image")
    with pytest.raises(loc.DecodeError):
        loc.decode_for_localization(str(bad))


# ---------------------------------------------------------------------------
# Per-image outcomes (AC-6..AC-10, AC-14) with persistence stubbed
# ---------------------------------------------------------------------------

class _FakeDetector:
    def __init__(self, boxes=None, error=None):
        self.boxes = boxes or []
        self.error = error
        self.calls = 0

    def detect_boxes(self, image):
        self.calls += 1
        if self.error:
            raise self.error
        return rank_boxes(self.boxes, *image.size, max_det=10)


@pytest.fixture
def jpeg(tmp_path):
    path = tmp_path / "bird.jpg"
    Image.new("RGB", (400, 300), (10, 20, 30)).save(path)
    return str(path)


@pytest.fixture
def writes(monkeypatch):
    out: list[tuple[dict, list]] = []
    monkeypatch.setattr(loc, "write_run", lambda run, regions: out.append((dict(run), list(regions))) or 1)
    monkeypatch.setattr(loc, "get_current_run", lambda _iid: None)
    return out


def _ctx(detector=None, **kw):
    return loc.DetectorContext(enabled=True, detector=detector, version="v", config_hash="h", **kw)


def test_ac6_regions_ranked_and_capped(jpeg, writes):
    boxes = [{"xyxy": (10 + i, 10, 50 + i, 60), "conf": 0.3 + i / 100} for i in range(12)]
    out = loc.localize_image(1, jpeg, _ctx(_FakeDetector(boxes)), max_regions=10)
    run, regions = writes[0]
    assert out.status == run["status"] == "detected" and out.regions == 10
    assert [r["rank"] for r in regions] == list(range(10))
    confs = [r["conf"] for r in regions]
    assert confs == sorted(confs, reverse=True)
    assert run["is_current"] is True and run["decode_route"] == "direct"
    assert (run["display_width"], run["display_height"]) == (400, 300)
    for key in ("detector_version", "detector_config_hash", "source_hash", "rendition_hash",
                "coord_space", "orientation"):
        assert run[key] is not None, key


def test_ac7_zero_boxes_is_no_detection(jpeg, writes):
    out = loc.localize_image(1, jpeg, _ctx(_FakeDetector([])), max_regions=10)
    assert out.status == writes[0][0]["status"] == "no_detection"
    assert writes[0][1] == []


def test_ac8_undecodable_source_is_terminal_and_redacted(tmp_path, writes):
    bad = tmp_path / "secret-dir" / "x.jpg"
    bad.parent.mkdir()
    bad.write_bytes(b"garbage")
    out = loc.localize_image(1, str(bad), _ctx(_FakeDetector()), max_regions=10)
    run = writes[0][0]
    assert out.status == run["status"] == "terminal_error"
    assert run["is_retryable"] is False
    assert "secret-dir" not in (run["error_detail"] or "")


def test_ac9_inference_error_is_retryable(jpeg, writes):
    out = loc.localize_image(1, jpeg, _ctx(_FakeDetector(error=RuntimeError("CUDA OOM"))), max_regions=10)
    run = writes[0][0]
    assert out.status == run["status"] == "retryable_error"
    assert run["is_retryable"] is True


def test_ac9_load_error_is_retryable_without_decoding(writes):
    out = loc.localize_image(1, "/does/not/matter.jpg", _ctx(load_error="detector_unavailable: x"), max_regions=10)
    assert out.status == writes[0][0]["status"] == "retryable_error"
    assert writes[0][0]["is_retryable"] is True


def test_ac10_disabled_detector_writes_disabled(jpeg, writes):
    ctx = loc.DetectorContext(enabled=False, version="v", config_hash="d")
    out = loc.localize_image(1, jpeg, ctx, max_regions=10)
    assert out.status == writes[0][0]["status"] == "disabled"


def test_ac14_unchanged_image_skips_detection(jpeg, writes, monkeypatch):
    detector = _FakeDetector([])
    loc.localize_image(1, jpeg, _ctx(detector), max_regions=10)
    first = writes[0][0]
    monkeypatch.setattr(loc, "get_current_run", lambda _iid: {
        "status": first["status"], "detector_config_hash": first["detector_config_hash"],
        "source_hash": first["source_hash"], "rendition_hash": first["rendition_hash"],
    })
    out = loc.localize_image(1, jpeg, _ctx(detector), max_regions=10)
    assert out.unchanged is True and detector.calls == 1 and len(writes) == 1

    # A changed detector config is not "unchanged".
    loc.localize_image(1, jpeg, loc.DetectorContext(enabled=True, detector=detector, version="v",
                                                    config_hash="other"), max_regions=10)
    assert detector.calls == 2 and len(writes) == 2


def test_ac14_a_retryable_current_run_is_retried(jpeg, writes, monkeypatch):
    detector = _FakeDetector([])
    loc.localize_image(1, jpeg, _ctx(detector), max_regions=10)
    first = writes[0][0]
    monkeypatch.setattr(loc, "get_current_run", lambda _iid: {
        "status": "retryable_error", "detector_config_hash": "h",
        "source_hash": first["source_hash"], "rendition_hash": first["rendition_hash"],
    })
    assert loc.localize_image(1, jpeg, _ctx(detector), max_regions=10).unchanged is False
    assert detector.calls == 2


# ---------------------------------------------------------------------------
# Runner: phase status (AC-11), isolation (AC-15), summary (AC-16)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status, ips", [
    ("detected", "done"), ("no_detection", "done"),
    ("terminal_error", "skipped"), ("disabled", "skipped"),
    ("retryable_error", "failed"),
])
def test_ac11_phase_status_mapping(status, ips, monkeypatch):
    from modules import localization_runner as lr

    calls = []
    monkeypatch.setattr(lr.db, "set_image_phase_status", lambda *a, **k: calls.append((a, k)))
    lr.LocalizationRunner._record_phase_status(5, loc.ImageOutcome(status=status), job_id=9)
    (args, kwargs), = calls
    assert args == (5, "localization", ips)
    assert kwargs["executor_version"] == loc.LOCALIZATION_RUNNER_VERSION


class _RecordingDb:
    """Stands in for ``modules.db`` in the runner; records every call it receives."""

    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, tuple, dict]] = []
        self.report = None

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "get_connector":
                return types.SimpleNamespace(query=lambda *_a, **_k: self.rows)
            if name == "job_should_stop_processing":
                return False
            if name == "get_job_report":
                return {"phases": {"metadata": {"images_processed": 3}}}
            if name == "save_job_report":
                self.report = args[1]
            return None
        return _call


def test_ac15_ac16_runner_writes_only_localization_state(jpeg, writes, monkeypatch):
    from modules import localization_runner as lr

    fake_db = _RecordingDb([{"id": 1, "file_path": jpeg}, {"id": 2, "file_path": jpeg},
                            {"id": 3, "file_path": "/missing.jpg"}])
    monkeypatch.setattr(lr, "db", fake_db)
    monkeypatch.setattr(lr, "localization_config", lambda: {})
    boxes = [{"xyxy": (10, 10, 50, 60), "conf": 0.9}]
    monkeypatch.setattr(lr, "load_detector_context", lambda _cfg: _ctx(_FakeDetector(boxes)))
    monkeypatch.setattr("modules.run_log.runner_emit", lambda *a, **k: None)

    lr.LocalizationRunner()._run_batch_internal("/scope", 11, [1, 2, 3], None)

    # AC-15: the only phase status touched is localization, and nothing else is written
    # besides job bookkeeping.
    allowed = {"update_job_status", "get_connector", "job_should_stop_processing",
               "set_image_phase_status", "get_job_report", "save_job_report"}
    assert {name for name, _a, _k in fake_db.calls} <= allowed
    ips = [a for name, a, _k in fake_db.calls if name == "set_image_phase_status"]
    assert {a[1] for a in ips} == {"localization"}
    assert [a[2] for a in ips] == ["done", "done", "skipped"]

    # AC-16: summary merged into the existing report, not replacing it.
    summary = fake_db.report["phases"]["localization"]
    assert fake_db.report["phases"]["metadata"] == {"images_processed": 3}
    assert summary["status_counts"] == {"detected": 2, "terminal_error": 1}
    assert summary["region_count_distribution"] == {"1": 2}
    assert summary["mean_decode_seconds"] is not None
    assert summary["mean_inference_seconds"] is not None
    assert "peak_gpu_memory_mib" in summary
