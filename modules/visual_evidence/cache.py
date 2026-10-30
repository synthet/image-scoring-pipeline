"""Atomic, image-scoped derived artifacts with bounded bundle eviction."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time

_KEY = re.compile(r"^[a-f0-9]{64}$")
_ARTIFACT = re.compile(r"^([a-f0-9]{64})_([a-f0-9]{64})\.(png|jpg)$")
LAYERS = ("sharpness", "peaking", "noise", "mask", "head")


class EvidenceCache:
    def __init__(self, root, max_bytes=2 * 1024 ** 3):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(1, int(max_bytes))
        self._lock = threading.RLock()
        self._pins = {}

    def bundle(self, image_id, key):
        if isinstance(image_id, bool) or not isinstance(image_id, int) or image_id <= 0 or not _KEY.fullmatch(key):
            raise ValueError("Invalid artifact identity")
        result = self.root / str(image_id) / key
        if not result.resolve().is_relative_to(self.root) or result.is_symlink():
            raise ValueError("Artifact outside cache")
        return result

    @contextmanager
    def pin(self, image_id, key):
        identity = (image_id, key)
        with self._lock:
            self._pins[identity] = self._pins.get(identity, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                self._pins[identity] -= 1
                if not self._pins[identity]:
                    del self._pins[identity]

    @staticmethod
    def _atomic(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".partial-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def artifact(self, image_id, artifact_id):
        match = _ARTIFACT.fullmatch(artifact_id)
        if not match:
            raise ValueError("Invalid artifact id")
        path = self.bundle(image_id, match[1]) / (match[2] + "." + match[3])
        if not path.resolve().is_relative_to(self.root) or path.is_symlink() or not path.is_file():
            raise FileNotFoundError("Artifact expired or unavailable")
        os.utime(path.parent, None)
        return path

    def write_artifact(self, image_id, key, data, extension):
        if extension not in ("png", "jpg"):
            raise ValueError("Unsupported artifact format")
        digest = hashlib.sha256(data).hexdigest()
        folder = self.bundle(image_id, key)
        with self._lock:
            self._atomic(folder / f"{digest}.{extension}", data)
            os.utime(folder, None)
        return f"{key}_{digest}.{extension}"

    def get(self, image_id, key, layer):
        if layer not in (*LAYERS, "source"):
            raise ValueError("Unsupported layer")
        folder = self.bundle(image_id, key)
        with self._lock:
            try:
                value = json.loads((folder / f"{layer}.json").read_text(encoding="utf-8"))
                for artifact_id in value.get("artifacts", {}).values():
                    self.artifact(image_id, artifact_id)
                os.utime(folder, None)
                return value
            except (OSError, ValueError, TypeError):
                return None

    def put(self, image_id, key, layer, value):
        if layer not in (*LAYERS, "source"):
            raise ValueError("Unsupported layer")
        folder = self.bundle(image_id, key)
        data = json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
        with self._lock:
            self._atomic(folder / f"{layer}.json", data)
            os.utime(folder, None)

    def prune(self):
        with self._lock:
            groups = []
            for parent in self.root.iterdir():
                if not parent.name.isdecimal() or parent.is_symlink() or not parent.is_dir():
                    continue
                for folder in parent.iterdir():
                    if not _KEY.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir():
                        continue
                    files = [item for item in folder.iterdir() if item.is_file() and not item.is_symlink()]
                    groups.append((folder.stat().st_mtime, sum(item.stat().st_size for item in files), folder))
            total = sum(size for _, size, _ in groups)
            for _, size, folder in sorted(groups):
                if total <= self.max_bytes:
                    break
                identity = (int(folder.parent.name), folder.name)
                if identity in self._pins:
                    continue
                if folder.resolve().is_relative_to(self.root) and not folder.is_symlink():
                    shutil.rmtree(folder)
                    total -= size
            return {"bytes": total, "budget": self.max_bytes, "checked_at": time.time()}
