"""Content-addressed, on-disk cache for region crops.

Stage 3 of the early-localization rollout (#375, AC-3 and AC-4). The key comes from
:func:`modules.rendition.crop_cache_key`; this module stores and serves the pixels.

Three properties matter more than speed:

* **A cached file is always complete.** Crops are encoded to a temp file in the target
  directory and moved into place with :func:`os.replace`, which is atomic on the same
  filesystem. Another process -- or a reader racing this one -- either sees no file or a
  whole one, never a half-written JPEG.
* **Concurrent requests for one key do the work once** within a process, via a per-key
  lock. Across processes -- which the lock cannot see -- duplicate work is harmless: both
  writers produce identical bytes. On POSIX the last rename wins. On Windows the losing
  ``os.replace`` raises a sharing violation instead, which :func:`_write_atomically`
  treats as success once it sees the winner's file in place.
* **Eviction loses nothing.** The durable identity of a crop is its key -- rendition,
  region and policy -- not the file. Encoding is deterministic (fixed quality, no
  metadata), so a crop evicted by :func:`prune_crop_cache` regenerates byte-identically on
  the next request.

Nothing in production reads this yet; it is additive until stage 5.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from modules.rendition import (
    CropPolicy,
    RenditionDescriptor,
    crop_cache_key,
    padded_pixel_box,
)

logger = logging.getLogger(__name__)

#: Alongside ``thumbnails/{hash[:2]}/`` and ``thumbnails/previews/``; gitignored with them.
CROP_CACHE_DIR = str(Path(__file__).resolve().parent.parent / "thumbnails" / "crops")

#: Fixed so the same crop always encodes to the same bytes -- that is what makes an
#: evicted crop reproducible, and a regenerated one verifiable.
_JPEG_QUALITY = 92

_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _key_lock(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


def crop_path(key: str, policy: CropPolicy, cache_dir: str | None = None) -> str:
    """Where a crop with this key lives, fanned out like ``get_thumb_path``."""
    ext = _EXTENSIONS.get(policy.image_format.upper(), policy.image_format.lower())
    return os.path.join(cache_dir or CROP_CACHE_DIR, key[:2], f"{key}.{ext}")


def _render(image: Any, region, policy: CropPolicy):
    width, height = image.size
    crop = image.crop(padded_pixel_box(region, width, height, policy))
    if policy.target_size is not None:
        crop.thumbnail((int(policy.target_size), int(policy.target_size)))
    if policy.image_format.upper() == "JPEG" and crop.mode not in ("RGB", "L"):
        crop = crop.convert("RGB")
    return crop


def _write_atomically(crop: Any, path: str, policy: CropPolicy) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            kwargs = {"quality": _JPEG_QUALITY} if policy.image_format.upper() == "JPEG" else {}
            # No `exif=`: metadata would make identical pixels encode differently.
            crop.save(fh, policy.image_format.upper(), **kwargs)
        try:
            os.replace(tmp, path)
        except PermissionError:
            # Windows refuses to replace a file another writer or reader has open
            # (a sharing violation; POSIX would just swap the inode). If the target now
            # exists, a concurrent writer -- another thread, or another process that the
            # in-process lock cannot see -- won the race. Encoding is deterministic, so
            # its bytes are exactly ours: that is success, not failure.
            if not os.path.isfile(path):
                raise
            os.unlink(tmp)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def materialize_crop(
    image: Any,
    descriptor: RenditionDescriptor,
    region: tuple[float, float, float, float],
    policy: CropPolicy,
    *,
    cache_dir: str | None = None,
) -> str:
    """Return the path of the crop for ``region``, producing it if not already cached.

    ``image`` must be the display-oriented pixels ``descriptor`` describes. Its size is
    checked against the descriptor: a mismatch means the caller is cropping a different
    rendition than the one the key names, which would cache wrong pixels under a
    trustworthy-looking key.
    """
    if tuple(image.size) != (descriptor.display_width, descriptor.display_height):
        raise ValueError(
            f"image is {image.size[0]}x{image.size[1]} but descriptor names "
            f"{descriptor.display_width}x{descriptor.display_height}; refusing to cache "
            "a crop of a different rendition under this key"
        )

    key = crop_cache_key(descriptor, region, policy)
    path = crop_path(key, policy, cache_dir)
    if os.path.isfile(path):
        return path

    with _key_lock(key):
        if os.path.isfile(path):  # produced while we waited
            return path
        _write_atomically(_render(image, region, policy), path, policy)
        logger.debug("crop cache: produced %s", path)
    return path


def prune_crop_cache(max_bytes: int, *, cache_dir: str | None = None) -> dict[str, int]:
    """Delete oldest crops (by mtime) until the cache is at most ``max_bytes``.

    Only removes finished crops -- in-flight ``.tmp-*.part`` files belong to a writer and
    are left alone. Returns ``{"removed", "freed_bytes", "remaining_bytes"}``.
    """
    root = cache_dir or CROP_CACHE_DIR
    entries = []
    total = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.startswith(".tmp-"):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, full))
            total += st.st_size

    removed = freed = 0
    entries.sort()
    for _mtime, size, full in entries:
        if total <= max_bytes:
            break
        try:
            os.unlink(full)
        except OSError:
            continue
        total -= size
        freed += size
        removed += 1
    return {"removed": removed, "freed_bytes": freed, "remaining_bytes": total}
