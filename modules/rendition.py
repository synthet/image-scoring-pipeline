"""Canonical inference renditions: one deterministic way to obtain pixels.

Stage 3 of the early-localization rollout (#375, epic #345).

A *rendition* is the pixel representation an inference run actually saw, plus enough
provenance to decide later whether a stored artifact still describes it. Stage 2 can
record that a region was found; without this it cannot record *what it was found in*, so
``coord_space`` had to be ``legacy_unverified``. This module supplies the verified
counterpart.

Three facts make a rendition non-obvious for this library:

* **A RAW file has several valid decodings.** ``open_image_for_ml`` tries an embedded
  preview, then ``rawpy``, then ImageMagick. They differ in size, colour and sometimes
  crop. Which one ran is part of the identity, not an implementation detail -- two runs
  that picked different routes did not see the same image.
* **Orientation is not baked in by default.** ``generate_thumbnail`` resizes and copies
  the EXIF Orientation *tag* for RAW rather than transposing pixels, so stored thumbnail
  pixels are not display-oriented. Coordinates only mean something once the space they
  live in is stated.
* **Display dimensions are not the file's dimensions.** An orientation of 5..8 swaps
  width and height; a resized rendition changes both. Normalized coordinates are only
  reproducible against the dimensions they were computed from.

Nothing here performs inference or writes to the database.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

#: Bump when the descriptor's *meaning* changes in a way that invalidates stored
#: artifacts -- a new field that affects pixels, or a changed normalization rule.
#: Adding a purely informational field does not require a bump.
RENDITION_DESCRIPTOR_VERSION = "1"

#: Bump when the colour pipeline changes (white balance, gamma, profile handling).
#: Kept separate from the descriptor version because it moves for different reasons.
COLOR_POLICY_VERSION = "1"

#: Coordinate space for regions computed against a verified, display-oriented rendition.
#: The counterpart to ``legacy_unverified`` in ``modules/localization_legacy.py``, whose
#: orientation could not be recovered.
COORD_SPACE_DISPLAY = "display_normalized"


class DecodeRoute(str, Enum):
    """Which code path produced the pixels.

    Part of the rendition identity: an embedded preview and a ``rawpy`` postprocess of
    the same NEF are different images, and a region found in one may not sit in the same
    place in the other.
    """

    DIRECT = "direct"                    # PIL.Image.open on a raster file
    RAW_EMBEDDED_PREVIEW = "raw_preview"  # exiftool JpgFromRaw / PreviewImage, or dcraw -e
    RAW_RAWPY = "raw_rawpy"              # rawpy.imread().postprocess()
    RAW_IMAGEMAGICK = "raw_magick"       # magick ... -resize 2048x2048>
    UNKNOWN = "unknown"                  # pixels from a caller that did not say


#: Decode routes that resize as a side effect, so their pixel dimensions are not the
#: sensor dimensions. Recorded because a crop taken from one cannot be compared to a
#: crop from a full-resolution route by pixel coordinates alone.
RESIZING_ROUTES = frozenset({DecodeRoute.RAW_IMAGEMAGICK})


@dataclass(frozen=True)
class RenditionDescriptor:
    """Identity of the pixels an inference run saw.

    Frozen: a descriptor describes something that already happened. Producing different
    pixels means producing a *new* descriptor, never mutating one -- that is what lets it
    be used as a cache key without a defensive copy.
    """

    source_path: str
    source_hash: str
    source_hash_version: str
    decode_route: DecodeRoute
    #: The EXIF orientation that was *applied* to reach these pixels, 1..8. A
    #: descriptor is only ever built after transposition, so the pixels it describes
    #: are display-oriented by construction -- this records which transform got there,
    #: which is what lets a coordinate be mapped back to the source frame.
    orientation: int
    display_width: int
    display_height: int
    color_policy_version: str = COLOR_POLICY_VERSION
    descriptor_version: str = RENDITION_DESCRIPTOR_VERSION
    #: Informational only, excluded from the hash -- e.g. which exiftool tag hit.
    notes: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not 1 <= int(self.orientation) <= 8:
            raise ValueError(f"orientation must be 1..8, got {self.orientation!r}")
        if int(self.display_width) <= 0 or int(self.display_height) <= 0:
            raise ValueError(
                f"display dimensions must be positive, got "
                f"{self.display_width}x{self.display_height}"
            )

    @property
    def rendition_hash(self) -> str:
        """Stable digest of every field that affects the pixels.

        ``source_path`` is deliberately **excluded**: the same bytes decoded the same way
        are the same rendition whether the file was moved or renamed. ``notes`` is
        excluded because it is informational.
        """
        parts = (
            self.source_hash,
            self.source_hash_version,
            self.decode_route.value,
            str(int(self.orientation)),
            str(int(self.display_width)),
            str(int(self.display_height)),
            self.color_policy_version,
            self.descriptor_version,
        )
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        """Flat mapping for persistence and diagnostics."""
        return {
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "source_hash_version": self.source_hash_version,
            "decode_route": self.decode_route.value,
            "orientation": int(self.orientation),
            "display_width": int(self.display_width),
            "display_height": int(self.display_height),
            "color_policy_version": self.color_policy_version,
            "descriptor_version": self.descriptor_version,
            "rendition_hash": self.rendition_hash,
            "coord_space": COORD_SPACE_DISPLAY,
        }


#: Version of the source-hash algorithm below. Bump if the sampling changes, so old
#: hashes are not silently compared against new ones.
SOURCE_HASH_VERSION = "size-mtime-head-1"


def source_identity(path: str, *, read_bytes: int = 65536) -> tuple[str, str]:
    """Cheap, stable identity for a source file: ``(hash, hash_version)``.

    Deliberately **not** a full-content digest. This runs per image on a library of tens
    of thousands of multi-megabyte RAW files, and its job is to answer "is this still the
    same file?" for cache invalidation -- not to be a cryptographic content address.

    Combines size, mtime and the leading bytes. Editing a RAW in place without changing
    size or mtime would defeat it; that is an accepted trade, and the reason the version
    tag exists is so the rule can be tightened later without ambiguity.
    """
    st = os.stat(path)
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    h.update(b"\x1f")
    h.update(str(int(st.st_mtime)).encode())
    h.update(b"\x1f")
    with open(path, "rb") as fh:
        h.update(fh.read(read_bytes))
    return h.hexdigest(), SOURCE_HASH_VERSION


def build_rendition_descriptor(
    source_path: str,
    image: Any,
    decode_route: DecodeRoute,
    orientation: int,
) -> RenditionDescriptor:
    """Describe pixels that have **already** been decoded and oriented.

    ``image`` must be the display-oriented image a detector will actually see -- its size
    is taken as the display dimensions, which for orientations 5..8 is the transpose of
    the stored file's. Passing the pre-orientation image would record the wrong frame and
    every normalized region against it would point at the wrong pixels.

    ``orientation`` is the EXIF value that was applied (1 when none was).
    """
    source_hash, source_hash_version = source_identity(source_path)
    width, height = image.size
    return RenditionDescriptor(
        source_path=str(source_path),
        source_hash=source_hash,
        source_hash_version=source_hash_version,
        decode_route=decode_route,
        orientation=int(orientation or 1),
        display_width=int(width),
        display_height=int(height),
    )


# ---------------------------------------------------------------------------
# Crop policy — padding is a versioned decision, not a bare float
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CropPolicy:
    """How a detector box becomes a crop.

    The rollout is explicit that *detector boxes are unpadded facts, and padding belongs
    to a versioned consumer crop policy*. ``BirdDetector.crop_to_box`` currently takes a
    bare ``padding`` float from config, so a config edit silently changes every crop ever
    produced with no way to tell old from new. Naming and versioning the policy makes that
    change visible in the cache key instead.

    ``pad_frac`` expands the box by a fraction of its own width/height on each side, then
    the result is clamped to the frame -- so a box already touching an edge simply grows
    less, rather than being shifted inward.
    """

    name: str
    pad_frac: float = 0.0
    #: Longest edge of the emitted crop, or None to keep native resolution.
    target_size: int | None = None
    image_format: str = "JPEG"
    version: str = "1"

    def __post_init__(self) -> None:
        if self.pad_frac < 0:
            raise ValueError(f"pad_frac must be >= 0, got {self.pad_frac!r}")
        if self.target_size is not None and int(self.target_size) <= 0:
            raise ValueError(f"target_size must be positive or None, got {self.target_size!r}")

    def key_parts(self) -> tuple[str, ...]:
        return (
            self.name,
            f"{float(self.pad_frac):.6f}",
            "native" if self.target_size is None else str(int(self.target_size)),
            self.image_format.upper(),
            self.version,
        )


#: The detector's historical behaviour (``bird_detection`` default ``padding=0.10``),
#: named so crops produced under it stay identifiable after the default moves.
CROP_POLICY_BIRD_V1 = CropPolicy(name="bird_v1", pad_frac=0.10, version="1")

#: No padding: the detector box exactly. Useful for evaluation, where padding would
#: confound a comparison against ground-truth geometry.
CROP_POLICY_TIGHT = CropPolicy(name="tight", pad_frac=0.0, version="1")


def crop_cache_key(
    descriptor: RenditionDescriptor,
    region: tuple[float, float, float, float],
    policy: CropPolicy,
) -> str:
    """Content address for one crop.

    Every input that can change the emitted pixels is in the digest: the rendition
    identity (which already folds in source hash, decode route, orientation, display
    dimensions and colour policy), the normalized geometry, and the full crop policy.

    Geometry is quantized to 6 decimals before hashing. Without it, float noise far below
    one pixel -- 8256 * 1e-7 is under a thousandth of a pixel -- would produce cache
    misses for crops that are byte-identical.
    """
    x1, y1, x2, y2 = (float(v) for v in region)
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        raise ValueError(f"region out of range or inverted: {(x1, y1, x2, y2)!r}")
    parts = (
        descriptor.rendition_hash,
        f"{x1:.6f}", f"{y1:.6f}", f"{x2:.6f}", f"{y2:.6f}",
        *policy.key_parts(),
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def padded_pixel_box(
    region: tuple[float, float, float, float],
    width: int,
    height: int,
    policy: CropPolicy,
) -> tuple[int, int, int, int]:
    """Normalized region + policy -> integer pixel box, clamped to the frame.

    Padding expands by a fraction of the box's own size on each side, so a small subject
    gains a small margin and a large one a large margin -- a fixed pixel pad would swamp
    a distant bird and barely touch a close one.

    Clamping is why the result can be *narrower* than the requested padding near an edge.
    The alternative -- shifting the box inward to preserve the padded size -- would move
    the subject off-centre and silently include pixels the detector never saw as context.

    Always returns a box of at least one pixel: rounding a sub-pixel region to integers
    can otherwise collapse it, and PIL raises on a zero-area crop.
    """
    x1, y1, x2, y2 = (float(v) for v in region)
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        raise ValueError(f"region out of range or inverted: {(x1, y1, x2, y2)!r}")
    w, h = int(width), int(height)
    if w <= 0 or h <= 0:
        raise ValueError(f"frame must be positive, got {w}x{h}")

    pad_x = (x2 - x1) * float(policy.pad_frac)
    pad_y = (y2 - y1) * float(policy.pad_frac)
    px1 = max(0.0, x1 - pad_x) * w
    py1 = max(0.0, y1 - pad_y) * h
    px2 = min(1.0, x2 + pad_x) * w
    py2 = min(1.0, y2 + pad_y) * h

    ix1, iy1 = int(round(px1)), int(round(py1))
    ix2, iy2 = int(round(px2)), int(round(py2))
    ix1 = max(0, min(ix1, w - 1))
    iy1 = max(0, min(iy1, h - 1))
    ix2 = max(ix1 + 1, min(ix2, w))
    iy2 = max(iy1 + 1, min(iy2, h))
    return ix1, iy1, ix2, iy2


def normalize_pixel_box(
    box: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[float, float, float, float] | None:
    """Pixel box -> normalized 0..1, or ``None`` when the geometry is unusable.

    Rejects rather than clamps, for the same reason the legacy import does: a box that is
    inverted, zero-area or outside the frame is a detector or bookkeeping fault, and
    coercing it into range would manufacture a plausible-looking region nobody detected.
    """
    w, h = float(width), float(height)
    if w <= 0 or h <= 0:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    nx1, ny1, nx2, ny2 = x1 / w, y1 / h, x2 / w, y2 / h
    if not (0.0 <= nx1 < nx2 <= 1.0 and 0.0 <= ny1 < ny2 <= 1.0):
        return None
    return nx1, ny1, nx2, ny2


def area_frac(region: tuple[float, float, float, float]) -> float:
    """Fraction of the frame a normalized region covers."""
    x1, y1, x2, y2 = (float(v) for v in region)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


#: A box covering at least this fraction of the frame is *recorded* as suspicious, not
#: rejected. The Sept 7 audit saw one accepted box at 93% of the image; one outlier is
#: not grounds for a universal ceiling, and the rollout says so explicitly. This exists
#: to make the distribution measurable before anyone proposes a threshold.
SUSPICIOUS_AREA_FRAC = 0.90


def is_suspicious_geometry(region: tuple[float, float, float, float]) -> bool:
    """Near-full-frame check for evaluation metrics. Never a rejection."""
    return area_frac(region) >= SUSPICIOUS_AREA_FRAC
