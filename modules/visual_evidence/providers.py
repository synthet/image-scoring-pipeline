"""Optional local model provider; a request never installs or downloads weights."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image


@lru_cache(maxsize=8)
def _digest(path, size, modified):
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


@lru_cache(maxsize=4)
def _runtime(python, modified):
    # A top-level spec avoids importing package initialization or scorers.
    probe = "import importlib.util as u,json,pathlib; p=u.find_spec('eye_quality'); s=u.find_spec('sam2'); print(json.dumps(str(pathlib.Path(p.origin).parent/'segmentation.py') if p and s else None))"
    try:
        result = subprocess.run([python, "-c", probe], capture_output=True, text=True, timeout=10, check=True)
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def mask_provider():
    root = Path(__file__).resolve().parents[2]
    isolated = root / ".agent" / "tmp" / "diagnostics-venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = Path(os.environ.get("EVIDENCE_MODEL_PYTHON") or (str(isolated) if isolated.is_file() else sys.executable))
    script = _runtime(str(python), python.stat().st_mtime_ns) if python.is_file() else None
    if not script or not Path(script).is_file():
        return {"available": False, "reason": "Local segmentation runtime is not installed", "version": "missing_provider"}
    checkpoint = Path(os.environ.get("EVIDENCE_SAM2_CHECKPOINT") or root / "models" / "sam2.1_hiera_tiny.pt")
    if not checkpoint.is_file():
        return {"available": False, "reason": "Local segmentation weights are not installed", "version": "missing_weights"}
    stat = checkpoint.stat()
    version = _digest(str(checkpoint), stat.st_size, stat.st_mtime_ns) + ":" + _digest(script, Path(script).stat().st_size, Path(script).stat().st_mtime_ns)
    return {"available": True, "checkpoint": str(checkpoint), "python": str(python), "script": script, "version": version}


def segment(path, region, *, cancelled=lambda: False, gpu_busy=lambda: False, timeout=180):
    provider = mask_provider()
    if not provider["available"]:
        return {"state": "unavailable", "reason": provider["reason"]}
    with tempfile.TemporaryDirectory(prefix="diagnostic-mask-") as folder:
        output = Path(folder) / "mask.png"
        command = [provider["python"], provider["script"], "--input", str(path), "--output", str(output),
                   "--checkpoint", provider["checkpoint"], "--box", json.dumps(region)]
        # Files avoid pipe-buffer deadlocks on warnings. Process exit releases VRAM.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            started = time.monotonic()
            try:
                while process.poll() is None:
                    if cancelled():
                        return {"state": "cancelled"}
                    if gpu_busy():
                        return {"state": "deferred"}
                    if time.monotonic() - started > timeout:
                        raise TimeoutError("Local segmentation exceeded its time budget")
                    time.sleep(.1)
                if process.returncode:
                    raise RuntimeError("Local segmentation process failed")
                stdout.seek(0)
                result = json.loads(stdout.read().decode().strip().splitlines()[-1])
                if result.get("state") == "ready":
                    with Image.open(output) as mask:
                        result["mask"] = np.asarray(mask.convert("L")) > 0
                return result
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
