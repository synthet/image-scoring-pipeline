"""ExifTool embedded-JPEG extraction retries a timeout once, and a JpgFromRaw timeout still tries PreviewImage."""

import io
import subprocess
from types import SimpleNamespace

from PIL import Image

import modules.thumbnails as th


def _jpeg(size=(64, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 10, 10)).save(buf, "JPEG")
    return buf.getvalue()


def _fake_run(script):
    """``subprocess.run`` stand-in: pops one outcome per call; records (tag, timeout)."""
    calls = []

    def run(cmd, capture_output, text, timeout):
        calls.append((cmd[2], timeout))
        outcome = script.pop(0)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd, timeout)
        return SimpleNamespace(returncode=0 if outcome else 1, stdout=outcome or b"")

    return run, calls


def test_timeout_is_retried_with_longer_timeout_and_same_tag(monkeypatch):
    run, calls = _fake_run(["timeout", _jpeg((80, 40))])
    monkeypatch.setattr(th.shutil, "which", lambda name: name == "exiftool")
    monkeypatch.setattr(th.subprocess, "run", run)
    img = th.extract_embedded_jpeg("a.nef", min_size=10)
    assert img is not None and img.size == (80, 40)
    assert calls == [("-JpgFromRaw", 10), ("-JpgFromRaw", 60)]


def test_jpgfromraw_timeouts_fall_through_to_preview_image(monkeypatch):
    run, calls = _fake_run(["timeout", "timeout", _jpeg((40, 20))])
    monkeypatch.setattr(th.shutil, "which", lambda name: name == "exiftool")
    monkeypatch.setattr(th.subprocess, "run", run)
    img = th.extract_embedded_jpeg("a.nef", min_size=10)
    assert img is not None and img.size == (40, 20)
    assert [c[0] for c in calls] == ["-JpgFromRaw", "-JpgFromRaw", "-PreviewImage"]


def test_missing_tag_is_not_retried(monkeypatch):
    run, calls = _fake_run([None, _jpeg()])
    monkeypatch.setattr(th.shutil, "which", lambda name: name == "exiftool")
    monkeypatch.setattr(th.subprocess, "run", run)
    assert th.extract_embedded_jpeg("a.nef", min_size=10) is not None
    assert [c[0] for c in calls] == ["-JpgFromRaw", "-PreviewImage"]
