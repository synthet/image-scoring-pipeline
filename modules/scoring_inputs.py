"""Prepared model input descriptors; local paths never enter their provenance."""
from __future__ import annotations

import hashlib
import os
from typing import Any

from PIL import Image


def input_resolution(value: Any, default: int = 512) -> int:
    if value is None:
        value = default
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if type(value) is not int or value <= 0:
        raise ValueError(f"Model input resolution must be a positive integer: {value!r}")
    return max(224, min(2048, value))


def source_identity(path: str) -> str:
    stat = os.stat(path)
    value = f"{os.path.abspath(path)}\0{stat.st_mtime_ns}\0{stat.st_size}"
    return hashlib.sha256(value.encode()).hexdigest()


def upright_dimensions(path: str) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        if image.getexif().get(274) in (5, 6, 7, 8):
            width, height = height, width
        return width, height


def describe_input(path: str, *, source_id: str, source_size: tuple[int, int],
                   resolution: int, jpeg_quality: int, policy: str, decode_route: str = "unknown") -> dict:
    with open(path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    with Image.open(path) as image:
        if image.getexif().get(274, 1) not in (None, 1):
            raise ValueError("Model input still has unapplied EXIF orientation")
        width, height = image.size
    return {"path": path, "metadata": {
        "policy": policy, "source_id": source_id, "source_width": source_size[0],
        "source_height": source_size[1], "width": width, "height": height,
        "resolution": resolution, "jpeg_quality": jpeg_quality, "sha256": digest,
        "resize": "bicubic-inside-no-upscale", "padding": "black-square",
        "decode_route": decode_route,
    }}


def validate_input(spec: dict) -> None:
    """Validate the actual bytes before inference, including transferred variants."""
    if not isinstance(spec, dict) or not isinstance(spec.get("metadata"), dict):
        raise ValueError("Invalid model input descriptor")
    metadata = spec["metadata"]
    resolution = metadata.get("resolution")
    if type(resolution) is not int or not 224 <= resolution <= 2048:
        raise ValueError("Invalid prepared resolution")
    with open(spec["path"], "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != metadata.get("sha256"):
            raise ValueError("Model input digest mismatch")
    with Image.open(spec["path"]) as image:
        if (image.size != (resolution, resolution)
                or image.size != (metadata.get("width"), metadata.get("height"))
                or image.getexif().get(274, 1) not in (None, 1)):
            raise ValueError("Model input dimensions/orientation mismatch")
        if not all(0 < side <= 2048 for side in image.size):
            raise ValueError("Model input exceeds supported dimensions")
        image.verify()
