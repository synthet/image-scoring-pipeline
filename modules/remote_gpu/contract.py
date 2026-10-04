"""Wire contract shared by the GPU runner server and the host client.

The runner sits at the model-method boundary: each endpoint runs one method of a
model class the local runners already use, with the same arguments. Everything
around that call (preprocessing, idempotency checks, persistence, XMP) stays on
the host, so local and remote runs share that code.
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

API_VERSION = 1

HEALTHZ = "/healthz"
HEALTH = "/v1/health"
DETECTOR_INFO = "/v1/detector/info"
SCORING = "/v1/scoring/run_all_models"
KEYWORDS = "/v1/keywords/predict"
ACCESSIBILITY = "/v1/keywords/accessibility"
CAPTION = "/v1/keywords/caption"
EMBEDDING = "/v1/culling/embed"
DETECT = "/v1/detector/raw_boxes"
SCENE = "/v1/localization/scene"
BIOCLIP = "/v1/bird_species/classify"

#: Config sections the remote models read, per phase. Both sides hash these and
#: refuse to run when they differ, so the runner can never silently use a stale
#: copy of the host's settings.
PHASE_CONFIG_SECTIONS: dict[str, tuple[str, ...]] = {
    "scoring": ("scoring",),
    "keywords": ("tagging",),
    "culling": (),
    "localization": ("bird_detection",),
    "bird_species": ("bird_detection",),
}

ENDPOINT_PHASE = {
    SCORING: "scoring",
    KEYWORDS: "keywords",
    ACCESSIBILITY: "keywords",
    CAPTION: "keywords",
    EMBEDDING: "culling",
    DETECT: "localization",
    SCENE: "localization",
    BIOCLIP: "bird_species",
    DETECTOR_INFO: "localization",
}

FINGERPRINT_HEADER = "X-Config-Fingerprint"


class RemoteGpuError(RuntimeError):
    """The GPU runner call failed. Callers surface it; nothing falls back to the local GPU."""


def json_default(value: Any) -> Any:
    """Serialize numpy scalars and arrays the models return."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def dumps(value: Any) -> str:
    return json.dumps(value, default=json_default, separators=(",", ":"))


def section_hashes(cfg: dict[str, Any], phase: str) -> dict[str, str]:
    """``{section: sha256}`` for the sections ``phase`` depends on."""
    out = {}
    for name in PHASE_CONFIG_SECTIONS[phase]:
        canonical = json.dumps(cfg.get(name) or {}, sort_keys=True, default=str, separators=(",", ":"))
        out[name] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return out


def phase_fingerprint(cfg: dict[str, Any], phase: str) -> str:
    hashes = section_hashes(cfg, phase)
    joined = "\x1f".join(f"{name}={digest}" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(f"v{API_VERSION}\x1f{phase}\x1f{joined}".encode()).hexdigest()


_PNG_MODES = frozenset({"1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"})


def encode_png(image) -> bytes:
    """Lossless transport for a decoded PIL image, so the runner sees the host's pixels."""
    if image.mode not in _PNG_MODES:
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


def decode_png(data: bytes):
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def encode_array(array) -> bytes:
    import numpy as np

    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(array), allow_pickle=False)
    return buf.getvalue()


def decode_array(data: bytes):
    import numpy as np

    return np.load(io.BytesIO(data), allow_pickle=False)


def as_vector(value: Any):
    """JSON list -> float32 array (the dtype the local models hand to the persist path)."""
    if value is None:
        return None
    import numpy as np

    return np.asarray(value, dtype=np.float32)
