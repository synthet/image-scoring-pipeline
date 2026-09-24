"""Client for Everypixel Labs photo analysis APIs.

Credentials are read from ``EVERYPIXEL_CLIENT_ID`` and
``EVERYPIXEL_SECRET_KEY``. Images are uploaded over HTTPS and are never sent as
public URLs by this client.

Camera RAW files must be decoded to JPEG before upload; use
:func:`prepare_jpeg_for_api` or :meth:`EverypixelClient.analyze_sync`.

Pricing (USD, pay-as-you-go): see https://labs.everypixel.com/pricing
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Literal

import requests

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.everypixel.com/v1"
QualityModel = Literal["stock", "ugc"]
SyncEndpointKind = Literal["keywords", "captioning", "faces", "stock", "ugc"]

# (free_trial_requests, usd_per_1000_requests) — labs.everypixel.com/pricing
SYNC_ENDPOINT_PRICING: dict[SyncEndpointKind, tuple[int, float]] = {
    "keywords": (500, 0.6),
    "captioning": (100, 1.2),
    "faces": (500, 0.6),
    "stock": (500, 0.6),
    "ugc": (500, 0.6),
}

DEFAULT_SPEND_LIMIT_USD = 10.0


def usd_per_quality_request() -> float:
    return SYNC_ENDPOINT_PRICING["ugc"][1] / 1000.0


def _unit_price(kind: SyncEndpointKind) -> float:
    return SYNC_ENDPOINT_PRICING[kind][1] / 1000.0


@dataclass
class EverypixelUsageStats:
    """Successful API call counters by sync endpoint kind."""

    stock_requests: int = 0
    ugc_requests: int = 0
    keywords_requests: int = 0
    captioning_requests: int = 0
    faces_requests: int = 0

    def count_for(self, kind: SyncEndpointKind) -> int:
        return getattr(self, f"{kind}_requests")

    def record_success(self, kind: SyncEndpointKind) -> None:
        attr = f"{kind}_requests"
        setattr(self, attr, getattr(self, attr) + 1)

    @classmethod
    def load(cls, path: Path) -> EverypixelUsageStats:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Everypixel usage state unreadable (%s): %s", path, exc)
            return cls()
        return cls(
            stock_requests=int(raw.get("stock_requests", 0)),
            ugc_requests=int(raw.get("ugc_requests", 0)),
            keywords_requests=int(raw.get("keywords_requests", 0)),
            captioning_requests=int(raw.get("captioning_requests", 0)),
            faces_requests=int(raw.get("faces_requests", 0)),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")


def _free_quota_for(
    kind: SyncEndpointKind,
    *,
    assume_free_quota_stock: int,
    assume_free_quota_ugc: int,
    assume_free_quota_keywords: int,
    assume_free_quota_captioning: int,
    assume_free_quota_faces: int,
) -> int:
    overrides = {
        "stock": assume_free_quota_stock,
        "ugc": assume_free_quota_ugc,
        "keywords": assume_free_quota_keywords,
        "captioning": assume_free_quota_captioning,
        "faces": assume_free_quota_faces,
    }
    return max(0, overrides.get(kind, SYNC_ENDPOINT_PRICING[kind][0]))


def estimated_cost_usd(
    stats: EverypixelUsageStats,
    *,
    free_stock: int = 500,
    free_ugc: int = 500,
    free_keywords: int = 500,
    free_captioning: int = 100,
    free_faces: int = 500,
) -> float:
    """Estimated spend from recorded successful requests and assumed remaining free quota."""
    free_map = {
        "stock": free_stock,
        "ugc": free_ugc,
        "keywords": free_keywords,
        "captioning": free_captioning,
        "faces": free_faces,
    }
    total = 0.0
    for kind in SYNC_ENDPOINT_PRICING:
        paid = max(0, stats.count_for(kind) - max(0, free_map[kind]))
        total += paid * _unit_price(kind)
    return total


def marginal_cost_usd(
    kind: SyncEndpointKind,
    stats: EverypixelUsageStats,
    *,
    free_stock: int = 500,
    free_ugc: int = 500,
    free_keywords: int = 500,
    free_captioning: int = 100,
    free_faces: int = 500,
) -> float:
    free = _free_quota_for(
        kind,
        assume_free_quota_stock=free_stock,
        assume_free_quota_ugc=free_ugc,
        assume_free_quota_keywords=free_keywords,
        assume_free_quota_captioning=free_captioning,
        assume_free_quota_faces=free_faces,
    )
    if stats.count_for(kind) < free:
        return 0.0
    return _unit_price(kind)


class EverypixelError(RuntimeError):
    """Raised when Everypixel credentials, transport, or response is invalid."""


class EverypixelBudgetExceeded(EverypixelError):
    """Raised when a call would exceed the configured local spend limit."""


def _env_float(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default", name, raw)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


_RAW_EXT = frozenset({".nef", ".nrw", ".cr2", ".dng", ".arw", ".orf", ".cr3", ".rw2"})
_RASTER_EXT = frozenset({".jpg", ".jpeg", ".png"})


def prepare_jpeg_for_api(
    source_path: str | Path,
    *,
    max_side: int = 2048,
    quality: int = 88,
) -> tuple[Path, bool]:
    """Return ``(upload_path, is_temporary)`` suitable for Everypixel ``data`` upload.

    RAW inputs are decoded via :func:`modules.thumbnails.open_image_for_ml` (embedded
    JPEG preview → rawpy → ImageMagick). Raster JPEG/PNG are uploaded as-is unless
    resize is needed.
    """
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)

    ext = source.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return source, False

    from modules.thumbnails import open_rendition_for_ml

    if ext in _RAW_EXT:
        image, route = open_rendition_for_ml(str(source))
        logger.info("Everypixel upload prep: %s via %s", source.name, route.value)
    elif ext in _RASTER_EXT:
        from PIL import Image

        image = Image.open(source)
        route = None
    else:
        raise EverypixelError(f"Unsupported image type for Everypixel upload: {ext}")
    image = image.convert("RGB")
    w, h = image.size
    if max(w, h) > max_side:
        image.thumbnail((max_side, max_side))

    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", prefix="everypixel_", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    image.save(tmp_path, format="JPEG", quality=quality, optimize=True)
    return tmp_path, True


@contextmanager
def jpeg_upload_path(source_path: str | Path, **kwargs: Any) -> Iterator[Path]:
    path, is_temp = prepare_jpeg_for_api(source_path, **kwargs)
    try:
        yield path
    finally:
        if is_temp:
            path.unlink(missing_ok=True)


class EverypixelClient:
    """Synchronous client for Everypixel stock/UGC quality and related sync APIs."""

    def __init__(
        self,
        client_id: str | None = None,
        secret_key: str | None = None,
        *,
        timeout: float = 30.0,
        spend_limit_usd: float | None = None,
        assume_free_quota_stock: int | None = None,
        assume_free_quota_ugc: int | None = None,
        assume_free_quota_keywords: int | None = None,
        assume_free_quota_captioning: int | None = None,
        assume_free_quota_faces: int | None = None,
        usage: EverypixelUsageStats | None = None,
        usage_state_path: Path | str | None = None,
    ) -> None:
        self.client_id = (client_id or os.environ.get("EVERYPIXEL_CLIENT_ID", "")).strip()
        self.secret_key = (secret_key or os.environ.get("EVERYPIXEL_SECRET_KEY", "")).strip()
        self.timeout = timeout
        if not self.client_id or not self.secret_key:
            raise EverypixelError(
                "Set EVERYPIXEL_CLIENT_ID and EVERYPIXEL_SECRET_KEY to use Everypixel."
            )

        limit = spend_limit_usd if spend_limit_usd is not None else _env_float(
            "EVERYPIXEL_SPEND_LIMIT_USD", DEFAULT_SPEND_LIMIT_USD
        )
        self.spend_limit_usd: float | None = limit
        if self.spend_limit_usd is not None and self.spend_limit_usd <= 0:
            self.spend_limit_usd = None

        self.assume_free_quota_stock = (
            assume_free_quota_stock
            if assume_free_quota_stock is not None
            else _env_int("EVERYPIXEL_ASSUME_FREE_QUOTA_STOCK", 500)
        )
        self.assume_free_quota_ugc = (
            assume_free_quota_ugc
            if assume_free_quota_ugc is not None
            else _env_int("EVERYPIXEL_ASSUME_FREE_QUOTA_UGC", 500)
        )
        self.assume_free_quota_keywords = (
            assume_free_quota_keywords
            if assume_free_quota_keywords is not None
            else _env_int("EVERYPIXEL_ASSUME_FREE_QUOTA_KEYWORDS", 500)
        )
        self.assume_free_quota_captioning = (
            assume_free_quota_captioning
            if assume_free_quota_captioning is not None
            else _env_int("EVERYPIXEL_ASSUME_FREE_QUOTA_CAPTIONING", 100)
        )
        self.assume_free_quota_faces = (
            assume_free_quota_faces
            if assume_free_quota_faces is not None
            else _env_int("EVERYPIXEL_ASSUME_FREE_QUOTA_FACES", 500)
        )

        state_raw = usage_state_path if usage_state_path is not None else os.environ.get(
            "EVERYPIXEL_USAGE_STATE_PATH", ""
        ).strip()
        self._usage_state_path = Path(state_raw) if state_raw else None

        if usage is not None:
            self.usage = usage
        elif self._usage_state_path is not None:
            self.usage = EverypixelUsageStats.load(self._usage_state_path)
        else:
            self.usage = EverypixelUsageStats()

    def _free_kwargs(self) -> dict[str, int]:
        return {
            "free_stock": self.assume_free_quota_stock,
            "free_ugc": self.assume_free_quota_ugc,
            "free_keywords": self.assume_free_quota_keywords,
            "free_captioning": self.assume_free_quota_captioning,
            "free_faces": self.assume_free_quota_faces,
        }

    def usage_summary(self) -> dict:
        """Counts and estimated USD for successful requests recorded by this client."""
        cost = estimated_cost_usd(self.usage, **self._free_kwargs())
        return {
            "stock_requests": self.usage.stock_requests,
            "ugc_requests": self.usage.ugc_requests,
            "keywords_requests": self.usage.keywords_requests,
            "captioning_requests": self.usage.captioning_requests,
            "faces_requests": self.usage.faces_requests,
            "estimated_cost_usd": round(cost, 6),
            "spend_limit_usd": self.spend_limit_usd,
            "free_quota_assumptions": {
                "stock": self.assume_free_quota_stock,
                "ugc": self.assume_free_quota_ugc,
                "keywords": self.assume_free_quota_keywords,
                "captioning": self.assume_free_quota_captioning,
                "faces": self.assume_free_quota_faces,
            },
        }

    def _enforce_budget(self, kind: SyncEndpointKind) -> None:
        if self.spend_limit_usd is None:
            return
        fk = self._free_kwargs()
        next_cost = marginal_cost_usd(kind, self.usage, **fk)
        projected = estimated_cost_usd(self.usage, **fk) + next_cost
        if projected > self.spend_limit_usd + 1e-12:
            summary = self.usage_summary()
            raise EverypixelBudgetExceeded(
                "Everypixel estimated spend would exceed the local limit "
                f"(${self.spend_limit_usd:.2f}): projected ${projected:.4f} "
                f"(next={kind} +${next_cost:.4f}, usage={summary}). "
                "Adjust EVERYPIXEL_SPEND_LIMIT_USD or free-quota assumptions, "
                "or reset EVERYPIXEL_USAGE_STATE_PATH counters if trial quota is exhausted."
            )

    def _persist_usage(self) -> None:
        if self._usage_state_path is not None:
            self.usage.save(self._usage_state_path)

    def _post_image(
        self,
        endpoint: str,
        jpeg_path: Path,
        *,
        params: dict[str, Any] | None = None,
        kind: SyncEndpointKind,
    ) -> dict:
        self._enforce_budget(kind)
        try:
            with jpeg_path.open("rb") as image:
                response = requests.post(
                    f"{API_BASE_URL}/{endpoint}",
                    auth=(self.client_id, self.secret_key),
                    params=params or {},
                    files={"data": ("upload.jpg", image, "image/jpeg")},
                    timeout=self.timeout,
                )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            body = ""
            resp = getattr(exc, "response", None)
            if resp is not None:
                try:
                    body = (resp.text or "")[:500]
                except Exception:
                    pass
            status_text = f" (HTTP {status})" if status else ""
            detail = f" {body}" if body else ""
            raise EverypixelError(f"Everypixel {endpoint} failed{status_text}.{detail}") from exc
        except ValueError as exc:
            raise EverypixelError(f"Everypixel {endpoint} returned invalid JSON.") from exc

        self.usage.record_success(kind)
        self._persist_usage()
        return payload

    def keywords(
        self,
        image_path: str | Path,
        *,
        num_keywords: int = 8,
        lang: str = "en",
    ) -> dict:
        with jpeg_upload_path(image_path) as jpeg:
            return self._post_image(
                "keywords",
                jpeg,
                params={"num_keywords": num_keywords, "lang": lang},
                kind="keywords",
            )

    def caption(self, image_path: str | Path, *, caption_len: str = "normal") -> dict:
        with jpeg_upload_path(image_path) as jpeg:
            return self._post_image(
                "image_captioning",
                jpeg,
                params={"caption_len": caption_len},
                kind="captioning",
            )

    def faces(self, image_path: str | Path) -> dict:
        with jpeg_upload_path(image_path) as jpeg:
            return self._post_image("faces", jpeg, kind="faces")

    def score(self, image_path: str | Path, *, model: QualityModel = "ugc") -> dict:
        """Score image quality; ``stock`` or ``ugc`` model."""
        endpoints = {"stock": "quality", "ugc": "quality_ugc"}
        if model not in endpoints:
            raise ValueError("model must be 'stock' or 'ugc'")

        with jpeg_upload_path(image_path) as jpeg:
            payload = self._post_image(endpoints[model], jpeg, kind=model)

        try:
            score = float(payload["quality"]["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EverypixelError("Everypixel response did not include quality.score.") from exc
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise EverypixelError("Everypixel returned a score outside the expected 0–1 range.")
        return payload

    def score_value(self, image_path: str | Path, *, model: QualityModel = "ugc") -> float:
        return float(self.score(image_path, model=model)["quality"]["score"])

    def analyze_sync(
        self,
        image_path: str | Path,
        *,
        include: tuple[SyncEndpointKind, ...] = (
            "keywords",
            "captioning",
            "faces",
            "stock",
            "ugc",
        ),
    ) -> dict[str, Any]:
        """Run selected sync endpoints on one image; return combined payloads and errors."""
        source = str(Path(image_path).resolve())
        out: dict[str, Any] = {
            "source_path": source,
            "endpoints": {},
            "errors": {},
        }
        runners: dict[SyncEndpointKind, Any] = {
            "keywords": lambda: self.keywords(image_path),
            "captioning": lambda: self.caption(image_path),
            "faces": lambda: self.faces(image_path),
            "stock": lambda: self.score(image_path, model="stock"),
            "ugc": lambda: self.score(image_path, model="ugc"),
        }
        for kind in include:
            if kind not in runners:
                continue
            try:
                out["endpoints"][kind] = runners[kind]()
            except Exception as exc:
                out["errors"][kind] = str(exc)
        out["usage"] = self.usage_summary()
        return out
