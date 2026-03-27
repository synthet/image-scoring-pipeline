"""
Generate favicon.ico for static/ and (via frontend/public/) static/app/.

If static/favicon.png exists, builds a multi-resolution .ico from it (matches WebUI branding).
Otherwise falls back to a minimal vector-style placeholder.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATIC_DIR = os.path.join(REPO_ROOT, "static")
PNG_PATH = os.path.join(STATIC_DIR, "favicon.png")
ICO_PATH = os.path.join(STATIC_DIR, "favicon.ico")
PUBLIC_ICO_PATH = os.path.join(REPO_ROOT, "frontend", "public", "favicon.ico")

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _ico_from_png() -> bool:
    if not os.path.isfile(PNG_PATH):
        return False
    with Image.open(PNG_PATH) as src:
        rgba = src.convert("RGBA")
        rgba.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)
    return True


def _fallback_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    yellow = (255, 215, 0, 255)
    center = size // 2
    outer_radius = int(size * 0.42)
    inner_radius = int(size * 0.125)
    outer_bbox = [
        center - outer_radius,
        center - outer_radius,
        center + outer_radius,
        center + outer_radius,
    ]
    draw.ellipse(outer_bbox, outline=yellow, width=max(1, size // 16))
    inner_bbox = [
        center - inner_radius,
        center - inner_radius,
        center + inner_radius,
        center + inner_radius,
    ]
    draw.ellipse(inner_bbox, fill=yellow)
    if size >= 32:
        line_width = max(1, size // 24)
        draw.line(
            [center, center - outer_radius, center, center + outer_radius],
            fill=yellow,
            width=line_width,
        )
        draw.line(
            [center - outer_radius, center, center + outer_radius, center],
            fill=yellow,
            width=line_width,
        )
    return img


def _ico_from_placeholder() -> None:
    master = _fallback_icon(256)
    master.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)


def _mirror_to_public() -> None:
    if not os.path.isfile(ICO_PATH):
        return
    public_dir = os.path.dirname(PUBLIC_ICO_PATH)
    if not os.path.isdir(public_dir):
        return
    with open(ICO_PATH, "rb") as src_f, open(PUBLIC_ICO_PATH, "wb") as dst_f:
        dst_f.write(src_f.read())


def generate_favicon() -> None:
    if _ico_from_png():
        print(f"Generated favicon.ico from {PNG_PATH}")
    else:
        print(f"No {PNG_PATH}; using placeholder ICO")
        _ico_from_placeholder()

    if os.path.exists(ICO_PATH):
        print(f"Saved: {ICO_PATH} ({os.path.getsize(ICO_PATH)} bytes)")

    _mirror_to_public()
    if os.path.isfile(PUBLIC_ICO_PATH):
        print(f"Copied to: {PUBLIC_ICO_PATH}")


if __name__ == "__main__":
    generate_favicon()
