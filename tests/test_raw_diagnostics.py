"""Optional RAW probes must preserve failures and omit identifying metadata."""
import json
import subprocess

import pytest

from modules import raw_diagnostics as diag


VERBOSE = """Filename: /private/shoot.nef
Timestamp: Fri Jun 2 18:53:02 2023
Camera: Nikon Z 8 ID: 0x0
ImageUniqueID: PRIVATE-ID
Body#: PRIVATE-SERIAL Lens#: PRIVATE-LENS
Thumb size: 8256 x 5504
Full size: 8280 x 5520
Raw inset, width x height: 8256 x 5504 left: 12 top: 8
Image size: 8280 x 5520
Output size: 8280 x 5520
Image flip: 6
Makernotes WB data: coeffs EVs
  As shot 1.88477 1 1.57617 1 0.91 0.00 0.66 0.00
"""
DECODER = "/private/shoot.nef\tnikon_he_load_raw()\tF=0x0 RS=8280x5520\tNikon/Z 8\n"


def test_geometry_and_decoder_are_kept_but_serials_are_not():
    report = diag.parse_raw_identify(VERBOSE, DECODER)
    assert report["camera"] == "Nikon Z 8"
    assert report["preview_size"] == [8256, 5504]
    assert report["raw_size"] == [8280, 5520]
    assert report["raw_inset"] == {"width": 8256, "height": 5504, "left": 12, "top": 8}
    assert report["flip"] == 6
    assert report["camera_white_balance"] == [1.88477, 1.0, 1.57617, 1.0]
    assert report["decoder"] == "nikon_he_load_raw()"
    assert report["decode_support"] == "not_tested"
    assert "PRIVATE" not in json.dumps(report)
    assert "private/shoot" not in json.dumps(report)


def test_disabled_probe_does_not_spawn(monkeypatch):
    monkeypatch.delenv("RAW_DIAGNOSTICS", raising=False)
    monkeypatch.setattr(diag.subprocess, "run", lambda *a, **k: pytest.fail("spawned"))
    assert diag.probe_raw_file("missing.nef")["status"] == "disabled"


def test_missing_tool_is_reported_without_spawning(tmp_path, monkeypatch):
    source = tmp_path / "a.nef"
    source.write_bytes(b"fixture")
    monkeypatch.delenv("RAW_IDENTIFY_PATH", raising=False)
    monkeypatch.setattr(diag.shutil, "which", lambda _: None)
    assert diag.probe_raw_file(source, enabled=True)["status"] == "unavailable"


def test_probe_uses_argument_list_and_bounded_timeout(tmp_path, monkeypatch):
    source = tmp_path / "a name; harmless.nef"
    source.write_bytes(b"fixture")
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, VERBOSE if "-v" in cmd else DECODER, "")

    monkeypatch.setattr(diag.subprocess, "run", run)
    report = diag.probe_raw_file(source, tool="raw-identify", enabled=True, timeout=3)
    assert report["status"] == "ok"
    assert report["decoder"] == "nikon_he_load_raw()"
    assert len(calls) == 2
    assert all(cmd[-1] == str(source.resolve()) for cmd, _ in calls)
    assert all(0 < kwargs["timeout"] <= 3 for _, kwargs in calls)
    assert all(not kwargs.get("shell") for _, kwargs in calls)


def test_probe_does_not_start_second_call_after_total_budget_expires(tmp_path, monkeypatch):
    source = tmp_path / "a.nef"
    source.write_bytes(b"fixture")
    ticks = iter([0.0, 0.0, 4.0])
    calls = []
    monkeypatch.setattr(diag.time, "monotonic", lambda: next(ticks))

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, VERBOSE, "")

    monkeypatch.setattr(diag.subprocess, "run", run)
    assert diag.probe_raw_file(source, tool="probe", enabled=True, timeout=3)["status"] == "timeout"
    assert len(calls) == 1


@pytest.mark.parametrize("failure,status", [
    (subprocess.TimeoutExpired("probe", 1), "timeout"),
    (OSError("PRIVATE-ERROR"), "error"),
])
def test_probe_errors_are_nonfatal_and_do_not_leak_raw_output(tmp_path, monkeypatch, failure, status):
    source = tmp_path / "a.nef"
    source.write_bytes(b"fixture")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(diag.subprocess, "run", fail)
    report = diag.probe_raw_file(source, tool="raw-identify", enabled=True)
    assert report["status"] == status
    assert "PRIVATE" not in json.dumps(report)


def test_nonzero_and_unparseable_output_cannot_claim_success(tmp_path, monkeypatch):
    source = tmp_path / "a.nef"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(diag.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", "PRIVATE"))
    assert diag.probe_raw_file(source, tool="probe", enabled=True)["status"] == "error"
    monkeypatch.setattr(diag.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "unexpected", ""))
    assert diag.probe_raw_file(source, tool="probe", enabled=True)["status"] == "unrecognized"


def test_ml_decode_failure_logs_probe_without_changing_exception(monkeypatch, caplog):
    from modules import thumbnails
    from PIL import UnidentifiedImageError

    monkeypatch.setenv("RAW_DIAGNOSTICS", "1")
    monkeypatch.setattr(thumbnails, "extract_embedded_jpeg", lambda *a, **k: None)
    monkeypatch.setattr(thumbnails.shutil, "which", lambda _: None)
    import rawpy
    monkeypatch.setattr(rawpy, "imread", lambda _: (_ for _ in ()).throw(ValueError("decode failed")))
    monkeypatch.setattr(diag, "probe_raw_file", lambda *a, **k: {"status": "ok", "decoder": "nikon_he_load_raw()"})
    with pytest.raises(UnidentifiedImageError, match="cannot identify or decode RAW"):
        thumbnails.open_rendition_for_ml("bad.nef")
    assert "nikon_he_load_raw()" in caplog.text
    assert "ml_decode" in caplog.text


@pytest.mark.parametrize("context", ["thumbnail_decode", "preview_decode"])
def test_thumbnail_and_preview_failures_report_diagnostics(tmp_path, monkeypatch, caplog, context):
    from modules import thumbnails
    import rawpy

    monkeypatch.setattr(thumbnails, "extract_embedded_jpeg", lambda *a, **k: None)
    monkeypatch.setattr(thumbnails, "get_thumb_path", lambda _: str(tmp_path / "thumb.jpg"))
    monkeypatch.setattr(thumbnails, "PREVIEW_DIR", str(tmp_path))
    monkeypatch.setattr(thumbnails.shutil, "which", lambda _: None)
    monkeypatch.setattr(rawpy, "imread", lambda _: (_ for _ in ()).throw(ValueError("bad")))
    monkeypatch.setattr(diag, "probe_raw_file", lambda *a, **k: {"status": "ok", "decoder": "nikon_he_load_raw()"})
    method = thumbnails.generate_thumbnail if context == "thumbnail_decode" else thumbnails.generate_preview
    assert method("bad.nef") is None
    assert context in caplog.text


def test_diagnostic_bug_cannot_mask_original_failure(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("probe bug")

    monkeypatch.setattr(diag, "probe_raw_file", broken)
    assert diag.log_raw_failure("bad.nef", "scoring_conversion") is None


@pytest.mark.ml
def test_scoring_converter_reports_terminal_failure(tmp_path, monkeypatch, caplog):
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    converter = object.__new__(MultiModelMUSIQ)
    monkeypatch.setattr(converter, "setup_temp_directory", lambda: str(tmp_path))
    monkeypatch.setattr(converter, "_is_safe_for_rawpy", lambda _: True)
    for name in ("exiftool", "rawpy", "dcraw", "imagemagick", "pillow"):
        monkeypatch.setattr(converter, f"_convert_with_{name}", lambda *a: (False, None))
    monkeypatch.setattr(diag, "probe_raw_file", lambda *a, **k: {"status": "ok", "decoder": "nikon_he_load_raw()"})
    assert converter.convert_raw_to_jpeg("bad.nef") is None
    assert "scoring_conversion" in caplog.text
