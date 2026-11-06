"""Capture key: identifies a frame by what the camera recorded, wherever the file lives.

Format: ``<Model>|<ShutterCount>|<YYYY-MM-DDTHH:MM:SS>``. Sub-seconds and time zone
offsets are dropped. The value is ``None`` unless all three fields are usable.

A card original has no ``ImageUniqueID`` (the metadata phase writes it to the library
copy), so tombstones use this key to recognise a deleted frame at a new path.

The format is a contract. Keep ``image_capture_key()`` in ``modules/db_schema/review.py``
and the gallery's copy in step, using ``tests/fixtures/capture_key_vectors.json``.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping
from typing import Any

_DATE = re.compile(r"^\s*(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


def _second(value: Any) -> str | None:
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    match = _DATE.match(str(value)) if value else None
    if not match:
        return None
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        parsed = datetime.datetime(year, month, day, hour, minute, second)
    except ValueError:  # cameras write 0000:00:00 00:00:00 when the clock is unset
        return None
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def _shutter(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        count = int(str(value).strip())
    except ValueError:
        return None
    return count if count > 0 else None


def capture_key(model: Any, shutter_count: Any, date_time_original: Any) -> str | None:
    """Return the capture key, or ``None`` when a field is missing or unusable."""
    name = str(model).strip() if model is not None else ""
    count = _shutter(shutter_count)
    second = _second(date_time_original)
    if not name or count is None or second is None:
        return None
    return f"{name}|{count}|{second}"


def capture_key_from_exif(exif: Mapping[str, Any] | None) -> str | None:
    """Build the key from ``exif_extractor.extract_exif`` output."""
    if not exif:
        return None
    return capture_key(exif.get("model"), exif.get("shutter_count"), exif.get("date_time_original"))
