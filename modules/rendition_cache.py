"""Decode-once inference renditions: a bounded on-disk cache of ~2048 px display-oriented JPEGs.

Spec 01 (#406), slice 1: the cache and its pruner. No consumer reads it yet.

Why a cache at all: decoding a 45 MP NEF (reading the file, extracting the full-size embedded
JPEG, decoding it) costs about 1.5 s, several times the detector and pose passes together
(eye keypoint backfill, 2026-09-27). Reading a cached 2048 px JPEG costs a few tens of ms.

Design:

* **The decode is localization's.** Pixels come from :func:`modules.localization.
  decode_for_localization` (route order, orientation baked on every route), then are resized to
  :data:`RENDITION_LONG_EDGE` and encoded at a fixed JPEG quality. Localization and this cache
  therefore agree on route and orientation; only the resolution differs, and the descriptor
  records it (``display_width``/``display_height`` are the rendition's).
* **A hit never decodes the source.** The key is the cheap source identity
  (:func:`modules.rendition.source_identity`: size, mtime, leading bytes) plus the rendition
  policy, so it is known before decoding. The descriptor is stored beside the JPEG.
* **Callers always see the cached bytes.** On a miss the rendition is written, then re-read, so
  the first caller and every later one get identical pixels (JPEG round trip included).
* **Eviction loses nothing.** Encoding is deterministic (fixed quality, no metadata): an evicted
  rendition regenerates byte-identically. :func:`prune_rendition_cache` removes the least
  recently used first; a hit refreshes the file's mtime.
* **Non-RAW sources are not cached** (decision R-3): they are already JPEG/TIFF on disk, so they
  are decoded directly, oriented and resized.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from modules.rendition import DecodeRoute, RenditionDescriptor, source_identity

logger = logging.getLogger(__name__)

RENDITION_CACHE_DIR = str(Path(__file__).resolve().parent.parent / "thumbnails" / "renditions")
RENDITION_LONG_EDGE = 2048
#: Decision R-2: quality 90, subject to the scoring parity gate (AC-12).
_JPEG_QUALITY = 90
#: Bump when the resize or encode changes, so old files are not served under new keys.
RENDITION_CACHE_VERSION = "1"

_RAW_EXTENSIONS = frozenset({".nef", ".nrw", ".cr2", ".dng", ".arw", ".orf", ".cr3", ".rw2"})

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _key_lock(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


def rendition_key(source_hash: str, source_hash_version: str, long_edge: int = RENDITION_LONG_EDGE) -> str:
    parts = (source_hash, source_hash_version, str(int(long_edge)), str(_JPEG_QUALITY), RENDITION_CACHE_VERSION)
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def rendition_paths(key: str, cache_dir: str | None = None) -> tuple[str, str]:
    """``(jpeg, descriptor json)`` for a key, fanned out like the thumbnail cache (AC-4)."""
    base = os.path.join(cache_dir or RENDITION_CACHE_DIR, key[:2], key)
    return base + ".jpg", base + ".json"


def _resize(image: Any, long_edge: int) -> Any:
    from PIL import Image

    w, h = image.size
    scale = long_edge / max(w, h)
    if scale >= 1:
        return image
    return image.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def _descriptor_for(source_path: str, base: RenditionDescriptor, image: Any) -> RenditionDescriptor:
    return RenditionDescriptor(
        source_path=source_path,
        source_hash=base.source_hash,
        source_hash_version=base.source_hash_version,
        decode_route=base.decode_route,
        orientation=base.orientation,
        display_width=image.size[0],
        display_height=image.size[1],
        notes={"full_width": base.display_width, "full_height": base.display_height,
               "long_edge": RENDITION_LONG_EDGE, "jpeg_quality": _JPEG_QUALITY},
    )


def _write_atomically(path: str, write) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            write(fh)
        try:
            os.replace(tmp, path)
        except PermissionError:
            # Windows sharing violation: a concurrent writer produced the same bytes first.
            if not os.path.isfile(path):
                raise
            os.unlink(tmp)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load(jpg: str, meta: str, source_path: str):
    from PIL import Image

    with open(meta, encoding="utf-8") as fh:
        d = json.load(fh)
    img = Image.open(jpg)
    img.load()
    desc = RenditionDescriptor(
        source_path=source_path, source_hash=d["source_hash"], source_hash_version=d["source_hash_version"],
        decode_route=DecodeRoute(d["decode_route"]), orientation=int(d["orientation"]),
        display_width=int(d["display_width"]), display_height=int(d["display_height"]),
        notes=d.get("notes") or {},
    )
    if img.size != (desc.display_width, desc.display_height):
        raise ValueError(f"cached rendition {jpg} is {img.size}, descriptor says "
                         f"{desc.display_width}x{desc.display_height}")
    return img.convert("RGB"), desc


def get_inference_rendition(path: str, *, cache_dir: str | None = None) -> tuple[Any, RenditionDescriptor, dict]:
    """Return ``(RGB image, descriptor, info)`` for ``path`` at :data:`RENDITION_LONG_EDGE` (AC-1).

    ``info`` is ``{"cache": "hit" | "miss" | "direct", "seconds": float, "decode_route": str}``
    for decode-time reporting (AC-13). Raises :class:`modules.localization.DecodeError` when no
    route produces pixels.
    """
    from modules.localization import decode_for_localization

    t0 = time.perf_counter()
    path = str(path)
    if Path(path).suffix.lower() not in _RAW_EXTENSIONS:
        decoded = decode_for_localization(path)
        img = _resize(decoded.image, RENDITION_LONG_EDGE)
        desc = _descriptor_for(path, decoded.descriptor, img)
        return img, desc, {"cache": "direct", "seconds": time.perf_counter() - t0,
                           "decode_route": desc.decode_route.value}

    source_hash, source_hash_version = source_identity(path)
    key = rendition_key(source_hash, source_hash_version)
    jpg, meta = rendition_paths(key, cache_dir)
    with _key_lock(key):
        state = "hit"
        if not (os.path.isfile(jpg) and os.path.isfile(meta)):
            state = "miss"
            decoded = decode_for_localization(path)
            img = _resize(decoded.image, RENDITION_LONG_EDGE)
            if img.mode != "RGB":
                img = img.convert("RGB")
            desc = _descriptor_for(path, decoded.descriptor, img)
            # No `exif=`: metadata would make identical pixels encode differently (AC-5).
            _write_atomically(jpg, lambda fh: img.save(fh, "JPEG", quality=_JPEG_QUALITY))
            record = {k: v for k, v in desc.as_dict().items() if k != "source_path"}
            record["notes"] = desc.notes
            _write_atomically(meta, lambda fh: fh.write(json.dumps(record, sort_keys=True).encode("utf-8")))
        else:
            now = time.time()
            for f in (jpg, meta):
                try:
                    os.utime(f, (now, now))  # least-recently-used order for the pruner (AC-6)
                except OSError:
                    pass
        img, desc = _load(jpg, meta, path)
    return img, desc, {"cache": state, "seconds": time.perf_counter() - t0,
                       "decode_route": desc.decode_route.value}


def prune_rendition_cache(max_bytes: int, *, cache_dir: str | None = None) -> dict[str, int]:
    """Delete least recently used renditions until the cache is at most ``max_bytes`` (AC-6).

    Removes each JPEG together with its descriptor; in-flight ``.tmp-*.part`` files are left
    alone. Returns ``{"removed", "freed_bytes", "remaining_bytes"}``.
    """
    root = Path(cache_dir or RENDITION_CACHE_DIR)
    entries = []
    total = 0
    for jpg in root.glob("*/*.jpg"):
        meta = jpg.with_suffix(".json")
        try:
            size = jpg.stat().st_size + (meta.stat().st_size if meta.exists() else 0)
            entries.append((jpg.stat().st_mtime, size, jpg, meta))
        except OSError:
            continue
        total += size
    removed = freed = 0
    for _, size, jpg, meta in sorted(entries, key=lambda e: e[0]):
        if total <= max_bytes:
            break
        for f in (jpg, meta):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        total -= size
        freed += size
        removed += 1
    return {"removed": removed, "freed_bytes": freed, "remaining_bytes": total}
