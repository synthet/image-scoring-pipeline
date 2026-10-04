"""GPU runner: a stateless HTTP service that runs model methods for a remote host.

Run it in the container from ``docker-compose.gpu-runner.yml`` on the GPU machine.
It opens no database and writes no XMP; the host sends the input and persists
the returned output. One inference runs at a time.

    GPU_RUNNER_TOKEN=... python -m modules.remote_gpu.server
"""

from __future__ import annotations

import asyncio
import copy
import hmac
import json
import logging
import os
import threading
import time
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, FiniteFloat, ValidationError

from modules.remote_gpu.contract import (
    ACCESSIBILITY,
    API_VERSION,
    BIOCLIP,
    CAPTION,
    DETECT,
    DETECTOR_INFO,
    EMBEDDING,
    ENDPOINT_PHASE,
    FINGERPRINT_HEADER,
    HEALTH,
    HEALTHZ,
    KEYWORDS,
    PHASE_CONFIG_SECTIONS,
    SCENE,
    SCORING,
    json_default,
    phase_fingerprint,
    section_hashes,
)
from modules.remote_gpu.runtime import InferenceRuntime

logger = logging.getLogger(__name__)

DEFAULT_MAX_BODY_MB = 256
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_UPLOAD_TIMEOUT_SECONDS = 60.0
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


class ModelProvider:
    """Lazily builds the same model classes the local runners use."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._models: dict[str, Any] = {}
        self._detector_info: dict[str, Any] | None = None

    def _get(self, name: str, build):
        with self._lock:
            if name not in self._models:
                self._models[name] = build()
            return self._models[name]

    def scoring_host(self):
        def build():
            from modules.engines.factory import create_production_scoring_host, load_production_models

            host = create_production_scoring_host()
            ok, message = load_production_models(host)
            if not ok:
                raise RuntimeError(message)
            return host

        return self._get("scoring", build)

    def keyword_scorer(self):
        def build():
            from modules.tagging import KeywordScorer

            scorer = KeywordScorer()
            scorer.load_model()
            return scorer

        return self._get("keywords", build)

    def captioner(self):
        def build():
            from modules.tagging import CaptionGenerator

            captioner = CaptionGenerator()
            captioner.load_model()
            return captioner

        return self._get("caption", build)

    def embedding_model(self):
        def build():
            from modules.clustering import ClusteringEngine

            engine = ClusteringEngine()
            engine.load_model()
            return engine.model

        return self._get("embedding", build)

    def bird_detector(self):
        def build():
            from modules.bird_detection import BirdDetector

            detector = BirdDetector()
            detector.load_model()
            return detector

        return self._get("detector", build)

    def detector_info(self) -> dict[str, Any]:
        """Weights identity for ``detector_config_hash``. Loads the detector once."""
        if self._detector_info is None:
            from modules.bird_detection import BirdDetector
            from modules.localization import redact_error_detail, weights_sha256

            try:
                detector = self.bird_detector()
                info = {"weights_sha256": weights_sha256(detector._resolve_weights_path()), "load_error": None}
            except Exception as exc:  # noqa: BLE001 — reported to the host as an outcome
                logger.warning("gpu_runner: bird detector unavailable: %s", exc)
                info = {"weights_sha256": None, "load_error": redact_error_detail(f"detector_unavailable: {exc}")}
            probe = BirdDetector(device="cpu")
            info["version"] = f"{probe.model_repo}/{probe.model_file}"
            self._detector_info = info
        return self._detector_info

    def scene_classifier(self, backend: str, prompt_set: str):
        def build():
            from modules.scene_route import SceneClassifier

            classifier = SceneClassifier(backend, prompt_set=prompt_set)
            classifier.load()
            return classifier

        return self._get(f"scene:{backend}:{prompt_set}", build)

    def bioclip(self):
        def build():
            from modules.bird_species import BioCLIPClassifier

            classifier = BioCLIPClassifier()
            classifier.load_model()
            return classifier

        return self._get("bioclip", build)


def _gpu_name() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return str(torch.cuda.get_device_name(0))
    except Exception:  # noqa: BLE001 — informational only
        logger.debug("gpu_runner: GPU name unavailable", exc_info=True)
    return "cpu"


def _json(status: int, payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=status, content=json.loads(json.dumps(payload, default=json_default)))


class _UploadRejected(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message


class ScoringParams(BaseModel):
    external_scores: dict[str, Any] = Field(default_factory=dict)


class KeywordParams(BaseModel):
    keywords: list[str] | None = None
    threshold: FiniteFloat = Field(default=0.2, ge=0, le=1)
    top_k: int = Field(default=5, ge=1)
    image_embedding: list[FiniteFloat] | None = None


class CaptionParams(BaseModel):
    extract_embedding: bool = False


class DetectorParams(BaseModel):
    conf: FiniteFloat = Field(ge=0, le=1)
    imgsz: int = Field(gt=0)
    max_det: int = Field(gt=0)


class SceneParams(BaseModel):
    backend: str = Field(min_length=1)
    prompt_set: str = Field(min_length=1)


class BioCLIPParams(BaseModel):
    candidate_species: list[str] = Field(default_factory=list)
    threshold: FiniteFloat = Field(default=0.1, ge=0, le=1)
    top_k: int = Field(default=1, ge=1)
    region: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat] | None = None
    use_detector: bool = True


class AccessibilityParams(BaseModel):
    prompts: list[str] = Field(min_length=1)
    image_embedding: list[FiniteFloat] | None = None


_PARAM_MODELS = {
    SCORING: ScoringParams, KEYWORDS: KeywordParams, CAPTION: CaptionParams,
    DETECT: DetectorParams, SCENE: SceneParams, BIOCLIP: BioCLIPParams,
    ACCESSIBILITY: AccessibilityParams,
}


def validate_params(endpoint: str, params) -> dict[str, Any]:
    """Shared method validation for HTTP uploads and embedded execution."""
    if not isinstance(params, dict):
        raise ValueError("meta must be a JSON object")
    model = _PARAM_MODELS.get(endpoint)
    return model.model_validate(params).model_dump() if model is not None else params


def parse_meta(request: Request, meta: str = Form("{}")) -> dict[str, Any]:
    """Malformed metadata is an input error, rather than a failed inference."""
    try:
        params = json.loads(meta)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "meta must be a JSON object") from exc
    if not isinstance(params, dict):
        raise HTTPException(422, "meta must be a JSON object")
    try:
        return validate_params(request.url.path, params)
    except ValidationError as exc:
        detail = [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()]
        raise HTTPException(422, detail) from exc


class GuardMiddleware:
    """Authenticate and admit requests before parsing uploads; bound streamed bytes and time."""

    def __init__(self, app, *, token: str, max_body_bytes: int,
                 max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
                 upload_timeout: float = DEFAULT_UPLOAD_TIMEOUT_SECONDS, check_config=None) -> None:
        if max_body_bytes <= 0 or max_concurrency <= 0 or upload_timeout <= 0:
            raise ValueError("GPU runner limits must be positive")
        self.app = app
        self._expected = f"Bearer {token}".encode() if token else None
        self._max_body = max_body_bytes
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._upload_timeout = upload_timeout
        self._check_config = check_config

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == HEALTHZ:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        if self._expected is not None and not hmac.compare_digest(
            headers.get(b"authorization", b""), self._expected,
        ):
            await _json(401, {"error": "unauthorized"})(scope, receive, send)
            return
        if scope["method"] == "POST":
            declared = headers.get(b"content-length")
            if declared is None:
                await _json(411, {"error": "content-length required"})(scope, receive, send)
                return
            if not declared.isdigit():
                await _json(400, {"error": "invalid content-length"})(scope, receive, send)
                return
            if len(declared) > 20 or int(declared) > self._max_body:
                await _json(413, {"error": f"body exceeds {self._max_body} bytes"})(scope, receive, send)
                return
        if self._check_config is not None:
            fingerprint = headers.get(FINGERPRINT_HEADER.lower().encode(), b"").decode("ascii", errors="replace")
            error = self._check_config(scope["path"], fingerprint)
            if error is not None:
                await error(scope, receive, send)
                return
        if not self._slots.acquire(blocking=False):
            await _json(503, {"error": "GPU runner busy"})(scope, receive, send)
            return
        received = 0
        deadline = time.monotonic() + self._upload_timeout

        async def bounded_receive():
            nonlocal received
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0, deadline - time.monotonic()))
            except TimeoutError as exc:
                raise _UploadRejected(408, "upload deadline exceeded") from exc
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_body:
                    raise _UploadRejected(413, f"body exceeds {self._max_body} bytes")
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except _UploadRejected as exc:
            await _json(exc.status, {"error": exc.message})(scope, receive, send)
        finally:
            self._slots.release()


def create_app(
    *,
    token: str = "",
    provider: ModelProvider | None = None,
    config_loader=None,
    max_body_bytes: int = DEFAULT_MAX_BODY_MB * 1024 * 1024,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    upload_timeout: float = DEFAULT_UPLOAD_TIMEOUT_SECONDS,
) -> FastAPI:
    """Build the runner app. Tests inject a fake ``provider`` and ``config_loader``."""
    if config_loader is None:
        from modules import config

        config_loader = config.load_config
    provider = provider or ModelProvider()
    runtime = InferenceRuntime(provider)
    # Loaded model instances must never be paired with a newer configuration.
    # A restart is required to apply a changed model configuration safely.
    startup_cfg = copy.deepcopy(config_loader() or {})
    gpu_lock = threading.Lock()
    app = FastAPI(title="Vexlum GPU runner", version=str(API_VERSION))

    def check_config(endpoint: str, fingerprint: str):
        phase = ENDPOINT_PHASE.get(endpoint)
        if phase is None:
            return None
        expected = phase_fingerprint(startup_cfg, phase)
        if phase_fingerprint(config_loader() or {}, phase) != expected:
            return _json(409, {"error": f"GPU runner config changed for {phase}; restart the runner", "phase": phase})
        if fingerprint != expected:
            return _json(409, {
                "error": f"config fingerprint mismatch for phase {phase}", "phase": phase,
                "sections": section_hashes(startup_cfg, phase),
            })
        return None

    app.add_middleware(
        GuardMiddleware, token=token, max_body_bytes=max_body_bytes,
        max_concurrency=max_concurrency, upload_timeout=upload_timeout, check_config=check_config,
    )

    def run(request: Request, endpoint: str, fn, *args, **kwargs):
        """Check the host's config fingerprint, then run ``fn`` under the GPU lock."""
        try:
            with gpu_lock:
                error = check_config(endpoint, request.headers.get(FINGERPRINT_HEADER, ""))
                if error is not None:
                    return error
                result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — reported to the host, which fails the image
            logger.exception("gpu_runner: %s failed", endpoint)
            return _json(500, {"error": f"{type(exc).__name__}: {exc}"})
        return _json(200, result)

    def execute(request, endpoint, params, file=None):
        data = file.file.read() if file is not None else None
        filename = (file.filename or "input.bin") if file is not None else "input.bin"
        return run(request, endpoint, runtime.execute, endpoint, params, data, filename=filename)

    @app.get(HEALTHZ)
    def healthz():
        return {"ok": True}

    @app.get(HEALTH)
    def health():
        cfg = config_loader() or {}
        return _json(200, {
            "ok": True,
            "api_version": API_VERSION,
            "gpu": _gpu_name(),
            "phase_sections": {phase: section_hashes(startup_cfg, phase) for phase in PHASE_CONFIG_SECTIONS},
            "restart_required": [phase for phase in PHASE_CONFIG_SECTIONS
                                 if phase_fingerprint(cfg, phase) != phase_fingerprint(startup_cfg, phase)],
        })

    @app.get(DETECTOR_INFO)
    def detector_info(request: Request):
        return execute(request, DETECTOR_INFO, {})

    @app.post(SCORING)
    def scoring(request: Request, params: dict = Depends(parse_meta), file: UploadFile = File(...)):
        return execute(request, SCORING, params, file)

    @app.post(KEYWORDS)
    def keywords(request: Request, params: dict = Depends(parse_meta), file: UploadFile = File(...)):
        return execute(request, KEYWORDS, params, file)

    @app.post(CAPTION)
    def caption(request: Request, params: dict = Depends(parse_meta), file: UploadFile = File(...)):
        return execute(request, CAPTION, params, file)

    @app.post(ACCESSIBILITY)
    def accessibility(request: Request, params: dict = Depends(parse_meta), file: UploadFile | None = File(None)):
        prompts = params.get("prompts")
        if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) for p in prompts):
            raise HTTPException(422, "prompts must be a nonempty list of strings")
        image_embedding = params.get("image_embedding")
        if image_embedding is None and file is None:
            raise HTTPException(422, "an image file or image_embedding is required")

        return execute(request, ACCESSIBILITY, params, file if image_embedding is None else None)

    @app.post(EMBEDDING)
    def embedding(request: Request, params: dict = Depends(parse_meta), file: UploadFile = File(...)):
        return execute(request, EMBEDDING, params, file)

    @app.post(DETECT)
    def detect(request: Request, params: dict = Depends(parse_meta), file: UploadFile = File(...)):
        return execute(request, DETECT, params, file)

    @app.post(SCENE)
    def scene(request: Request, params: dict = Depends(parse_meta), file: UploadFile = File(...)):
        return execute(request, SCENE, params, file)

    @app.post(BIOCLIP)
    def bird_species(request: Request, params: dict = Depends(parse_meta), file: UploadFile = File(...)):
        return execute(request, BIOCLIP, params, file)

    return app


def require_token(bind_host: str, token: str) -> None:
    """Refuse to listen on a LAN address without a shared token."""
    if not token and bind_host not in _LOOPBACK:
        raise SystemExit("GPU_RUNNER_TOKEN is required when binding a non-loopback address")


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("GPU_RUNNER_HOST", "0.0.0.0")
    port = int(os.environ.get("GPU_RUNNER_PORT", "7870"))
    token = os.environ.get("GPU_RUNNER_TOKEN", "")
    require_token(host, token)
    from modules.remote_gpu.client import mark_serving

    mark_serving()
    max_body = int(os.environ.get("GPU_RUNNER_MAX_BODY_MB", str(DEFAULT_MAX_BODY_MB))) * 1024 * 1024
    concurrency = int(os.environ.get("GPU_RUNNER_MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY)))
    app = create_app(
        token=token, max_body_bytes=max_body, max_concurrency=concurrency,
        upload_timeout=float(os.environ.get("GPU_RUNNER_UPLOAD_TIMEOUT_SECONDS", str(DEFAULT_UPLOAD_TIMEOUT_SECONDS))),
    )
    uvicorn.run(
        app,
        host=host,
        port=port,
        limit_concurrency=concurrency + 2,
        timeout_keep_alive=30,
        ssl_certfile=os.environ.get("GPU_RUNNER_SSL_CERTFILE") or None,
        ssl_keyfile=os.environ.get("GPU_RUNNER_SSL_KEYFILE") or None,
    )


if __name__ == "__main__":
    main()
