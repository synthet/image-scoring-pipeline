"""GPU runner: a stateless HTTP service that runs model methods for a remote host.

Run it in the container from ``docker-compose.gpu-runner.yml`` on the GPU machine.
It opens no database and writes no XMP; the host sends the input and persists
the returned output. One inference runs at a time.

    GPU_RUNNER_TOKEN=... python -m modules.remote_gpu.server
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import tempfile
import threading
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from modules.remote_gpu.contract import (
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
    as_vector,
    decode_array,
    decode_png,
    json_default,
    phase_fingerprint,
    section_hashes,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_BODY_MB = 256
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


class GuardMiddleware:
    """Checks the bearer token and the declared body size before any body is read."""

    def __init__(self, app, *, token: str, max_body_bytes: int) -> None:
        self.app = app
        self._expected = f"Bearer {token}".encode() if token else None
        self._max_body = max_body_bytes

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
            if int(declared) > self._max_body:
                await _json(413, {"error": f"body exceeds {self._max_body} bytes"})(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(
    *,
    token: str = "",
    provider: ModelProvider | None = None,
    config_loader=None,
    max_body_bytes: int = DEFAULT_MAX_BODY_MB * 1024 * 1024,
) -> FastAPI:
    """Build the runner app. Tests inject a fake ``provider`` and ``config_loader``."""
    if config_loader is None:
        from modules import config

        config_loader = config.load_config
    provider = provider or ModelProvider()
    gpu_lock = threading.Lock()
    app = FastAPI(title="Vexlum GPU runner", version=str(API_VERSION))
    app.add_middleware(GuardMiddleware, token=token, max_body_bytes=max_body_bytes)

    def run(request: Request, endpoint: str, fn, *args, **kwargs):
        """Check the host's config fingerprint, then run ``fn`` under the GPU lock."""
        phase = ENDPOINT_PHASE[endpoint]
        cfg = config_loader() or {}
        if request.headers.get(FINGERPRINT_HEADER) != phase_fingerprint(cfg, phase):
            return _json(409, {
                "error": f"config fingerprint mismatch for phase {phase}",
                "phase": phase,
                "sections": section_hashes(cfg, phase),
            })
        try:
            with gpu_lock:
                result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — reported to the host, which fails the image
            logger.exception("gpu_runner: %s failed", endpoint)
            return _json(500, {"error": f"{type(exc).__name__}: {exc}"})
        return _json(200, result)

    def temp_input(upload: UploadFile, data: bytes) -> str:
        suffix = os.path.splitext(upload.filename or "")[1].lower()
        if not suffix[1:].isalnum() or len(suffix) > 9:
            suffix = ".bin"
        fd, path = tempfile.mkstemp(prefix="gpu-runner-", suffix=suffix)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return path

    def with_temp_file(upload: UploadFile, fn):
        data = upload.file.read()

        def call():
            path = temp_input(upload, data)
            try:
                return fn(path)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    logger.debug("gpu_runner: temp cleanup failed for %s", path, exc_info=True)

        return call

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
            "phase_sections": {phase: section_hashes(cfg, phase) for phase in PHASE_CONFIG_SECTIONS},
        })

    @app.get(DETECTOR_INFO)
    def detector_info():
        with gpu_lock:
            return _json(200, provider.detector_info())

    @app.post(SCORING)
    def scoring(request: Request, meta: str = Form(...), file: UploadFile = File(...)):
        params = json.loads(meta)

        def score(path: str):
            return provider.scoring_host().run_all_models(
                path,
                external_scores=params.get("external_scores") or None,
                logger=lambda msg: logger.debug("gpu_runner scoring: %s", msg),
                write_metadata=False,
            )

        return run(request, SCORING, with_temp_file(file, score))

    @app.post(KEYWORDS)
    def keywords(request: Request, meta: str = Form(...), file: UploadFile = File(...)):
        params = json.loads(meta)

        def predict(path: str):
            scorer = provider.keyword_scorer()
            tags, confidence_map, relevance_map = scorer.predict(
                path,
                keywords=params.get("keywords"),
                threshold=float(params.get("threshold", 0.2)),
                top_k=int(params.get("top_k", 5)),
                return_scores=True,
                image_embedding=as_vector(params.get("image_embedding")),
            )
            return {
                "keywords": tags,
                "confidence_map": confidence_map,
                "relevance_map": relevance_map,
                "last_image_embedding": scorer.last_image_embedding,
            }

        return run(request, KEYWORDS, with_temp_file(file, predict))

    @app.post(CAPTION)
    def caption(request: Request, meta: str = Form(...), file: UploadFile = File(...)):
        params = json.loads(meta)

        def generate(path: str):
            captioner = provider.captioner()
            text = captioner.generate(path, extract_embedding=bool(params.get("extract_embedding")))
            return {"caption": text, "last_image_embedding": captioner.last_image_embedding}

        return run(request, CAPTION, with_temp_file(file, generate))

    @app.post(EMBEDDING)
    def embedding(request: Request, meta: str = Form("{}"), file: UploadFile = File(...)):
        batch = decode_array(file.file.read())

        def predict():
            return {"vectors": provider.embedding_model().predict(batch, verbose=0)}

        return run(request, EMBEDDING, predict)

    @app.post(DETECT)
    def detect(request: Request, meta: str = Form(...), file: UploadFile = File(...)):
        params = json.loads(meta)
        image = decode_png(file.file.read())

        def raw_boxes():
            detector = provider.bird_detector()
            detector.confidence = float(params["conf"])
            detector.imgsz = int(params["imgsz"])
            detector.max_det = int(params["max_det"])
            return {"boxes": detector._predict_raw_boxes(image)}

        return run(request, DETECT, raw_boxes)

    @app.post(SCENE)
    def scene(request: Request, meta: str = Form(...), file: UploadFile = File(...)):
        params = json.loads(meta)
        image = decode_png(file.file.read())

        def classify():
            classifier = provider.scene_classifier(str(params["backend"]), str(params["prompt_set"]))
            classifier.classify(image)
            # The host scores these with the same ``score`` a local run uses.
            return {
                "version": classifier.version,
                "image_feat": classifier.last_embedding,
                "label_feats": classifier._label_feats,
                "logit_scale": classifier._logit_scale,
            }

        return run(request, SCENE, classify)

    @app.post(BIOCLIP)
    def bird_species(request: Request, meta: str = Form(...), file: UploadFile = File(...)):
        params = json.loads(meta)

        def classify(path: str):
            classifier = provider.bioclip()
            region = params.get("region")
            predictions = classifier.classify(
                path,
                list(params.get("candidate_species") or []),
                threshold=float(params.get("threshold", 0.1)),
                top_k=int(params.get("top_k", 1)),
                region=tuple(region) if region is not None else None,
                use_detector=bool(params.get("use_detector", True)),
            )
            return {
                "predictions": [[name, prob] for name, prob in predictions],
                "last_bbox": classifier.last_bbox,
                "last_image_embedding": classifier.last_image_embedding,
            }

        return run(request, BIOCLIP, with_temp_file(file, classify))

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
    app = create_app(token=token, max_body_bytes=max_body)
    uvicorn.run(
        app,
        host=host,
        port=port,
        limit_concurrency=int(os.environ.get("GPU_RUNNER_MAX_CONCURRENCY", "16")),
        timeout_keep_alive=30,
        ssl_certfile=os.environ.get("GPU_RUNNER_SSL_CERTFILE") or None,
        ssl_keyfile=os.environ.get("GPU_RUNNER_SSL_KEYFILE") or None,
    )


if __name__ == "__main__":
    main()
