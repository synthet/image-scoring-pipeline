"""A decode comparison must compare declared pixels and retain failed routes."""
import io
import os
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image
import pytest

from scripts.research.rendition import compare_raw_decoders as comparison


def test_pixel_metrics_distinguish_identical_and_changed_pixels():
    image = Image.new("RGB", (16, 12), (10, 20, 30))
    same = comparison.pixel_metrics(image, image.copy(), edge=16)
    assert same["mae_8bit"] == 0
    assert same["exact_pixels"] is True
    changed = comparison.pixel_metrics(image, Image.new("RGB", image.size, (20, 30, 40)), edge=16)
    assert changed["mae_8bit"] == 10
    assert changed["exact_pixels"] is False


def test_geometry_mismatch_is_visible_even_when_resized_pixels_match():
    a = Image.new("RGB", (20, 10), "black")
    b = Image.new("RGB", (10, 5), "black")
    result = comparison.pixel_metrics(a, b, edge=16)
    assert result["native_dimensions_equal"] is False
    assert result["exact_pixels"] is False
    assert result["mae_8bit"] == 0


def test_dcraw_stdout_flags_and_orientation_policy(monkeypatch):
    data = io.BytesIO()
    Image.new("RGB", (4, 2)).save(data, "PPM")
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, data.getvalue(), b"")

    monkeypatch.setattr(comparison.subprocess, "run", run)
    img, _ = comparison.decode_route("dcraw_emu_half", "/a name.nef", dcraw="/bin/helper", timeout=2)
    assert img.size == (4, 2)
    cmd, kwargs = calls[0]
    assert cmd == ["/bin/helper", "-Z", "-", "-h", "-w", "-o", "1", "-q", "3", "-t", "0", "/a name.nef"]
    assert kwargs["timeout"] == 2
    assert "-c" not in cmd


def test_native_failure_does_not_become_a_valid_image(monkeypatch):
    monkeypatch.setattr(comparison.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 2, b"", b"unsupported"))
    with pytest.raises(RuntimeError, match="exit 2"):
        comparison.decode_route("dcraw_emu_half", "a.nef", dcraw="helper", timeout=2)


def test_failed_worker_and_timeout_are_retained_in_report(monkeypatch, tmp_path):
    killed = []

    class StuckProcess:
        pid = 12345

        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("worker", timeout)
            return "", ""

    monkeypatch.setattr(comparison.subprocess, "Popen", lambda *a, **k: StuckProcess())
    monkeypatch.setattr(comparison.os, "name", "posix")
    monkeypatch.setattr(comparison.os, "killpg", lambda pid, sig: killed.append(pid))
    result = comparison.run_worker("rawpy_half", tmp_path / "x.nef", tmp_path, timeout=1, dcraw=None)
    assert result["status"] == "timeout"
    assert result["route"] == "rawpy_half"
    assert killed == [12345]


def test_fingerprint_uses_pixels_not_file_encoding():
    a = Image.fromarray(np.arange(36, dtype=np.uint8).reshape(3, 4, 3))
    assert comparison.pixel_digest(a) == comparison.pixel_digest(a.copy())
    assert comparison.pixel_digest(a) != comparison.pixel_digest(Image.new("RGB", a.size))


@pytest.mark.skipif(not comparison.sys.platform.startswith("linux"), reason="Linux VmHWM")
def test_worker_memory_uses_current_address_space_high_water(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: "VmHWM:\t102400 kB\n")
    assert comparison._peak_rss("RUSAGE_SELF") == 100.0


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group cleanup")
def test_real_timeout_stops_worker_descendants(tmp_path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    worker = tmp_path / "stuck_worker.py"
    worker.write_text(
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])\n"
        f"Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "time.sleep(20)\n"
    )
    monkeypatch.setattr(comparison, "__file__", str(worker))
    result = comparison.run_worker("rawpy_half", tmp_path / "a.nef", tmp_path, timeout=1, dcraw=None)
    assert result["status"] == "timeout"
    child_pid = int(pid_file.read_text())
    stat = Path(f"/proc/{child_pid}/stat")
    # An adopted zombie may await init's reaper, but must not keep decoding.
    assert not stat.exists() or stat.read_text().split()[2] == "Z"
