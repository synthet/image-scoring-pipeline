"""GPU runner: transport guards and local-vs-remote parity with fake models.

Parity tests run the *same* fake model locally and behind the runner (FastAPI
TestClient, no network, no GPU) and require identical outputs, so a drift in
transport or host-side handling fails here rather than in the database.
"""

from __future__ import annotations

import os

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from modules.bird_detection import BirdDetector
from modules.remote_gpu import client as client_mod
from modules.remote_gpu.client import GpuRunnerClient, phase_is_remote
from modules.remote_gpu.contract import KEYWORDS, RemoteGpuError
from modules.remote_gpu.server import create_app, require_token
from modules.tagging import CaptionGenerator

pytestmark = pytest.mark.filterwarnings(
    "ignore:You should not use the 'timeout' argument:DeprecationWarning"
)

TOKEN = "test-token"
CFG = {
    "scoring": {"models": {"spaq": {"enabled": True}}},
    "tagging": {"clip_model": "openai/clip-vit-base-patch32"},
    "bird_detection": {"enabled": True, "confidence": 0.25, "imgsz": 640, "max_det": 5},
}
BIRD_CFG = CFG["bird_detection"]


# ---------------------------------------------------------------------------
# Fake models (used on both sides of each parity check)
# ---------------------------------------------------------------------------

class FakeYoloDetector(BirdDetector):
    """Real BirdDetector post-processing over a pixel-dependent fake forward pass."""

    def __init__(self, config=None):
        super().__init__(config=dict(config or BIRD_CFG), device="cpu")
        self.calls = 0

    def load_model(self):
        pass

    def _predict_raw_boxes(self, image):
        self.calls += 1
        arr = np.asarray(image.convert("RGB"), dtype=np.float64)
        m = float(arr.mean())
        w, h = image.size
        return [
            {"xyxy": (w * 0.1 + m / 100, h * 0.2, w * 0.6, h * 0.7 + 0.25), "conf": 0.5 + m / 1000},
            {"xyxy": (w * 0.5, h * 0.5, w * 0.9, h * 0.95), "conf": 0.5 + m / 1000},  # tie
            {"xyxy": (w * 0.9, h * 0.9, w * 0.2, h * 0.3), "conf": 0.99},  # inverted: dropped
        ]


class FakeKeywordScorer:
    def __init__(self):
        self.last_image_embedding = None

    def predict(self, image_path, keywords=None, threshold=0.2, top_k=5, return_scores=False, image_embedding=None):
        arr = np.asarray(Image.open(image_path).convert("RGB"), dtype=np.float32)
        self.last_image_embedding = (arr.mean(axis=(0, 1)) / 255.0).astype(np.float32)
        tags = list(keywords or ["bird", "sky"])[:top_k]
        conf = {t: round(0.9 - i * 0.1, 4) for i, t in enumerate(tags)}
        rel = {t: 0.5 for t in tags}
        return (tags, conf, rel) if return_scores else tags


class FakeCaptioner:
    def __init__(self):
        self.last_image_embedding = None

    def generate(self, image_path, extract_embedding=False):
        size = Image.open(image_path).size
        self.last_image_embedding = np.array([size[0], size[1]], dtype=np.float32) if extract_embedding else None
        return f"A bird {size[0]}x{size[1]}"


class FakeEmbeddingModel:
    def predict(self, batch, verbose=0):
        flat = np.asarray(batch, dtype=np.float32).reshape(len(batch), -1)
        return np.stack([flat.mean(axis=1), flat.max(axis=1), flat.min(axis=1)], axis=1).astype(np.float32)


class FakeBioCLIP:
    """Mimics classify: decodes upright pixels from the path, sets the side effects."""

    def __init__(self):
        self.last_bbox = None
        self.last_image_embedding = None

    def classify(self, image_path, candidate_species, threshold=0.1, top_k=1, region=None, use_detector=True):
        from modules.thumbnails import open_oriented_for_ml

        img = open_oriented_for_ml(image_path)
        arr = np.asarray(img, dtype=np.float64)
        self.last_bbox = {"x1": 1, "y1": 2, "x2": img.size[0] - 1, "y2": img.size[1] - 2, "conf": 0.77,
                          "img_w": img.size[0], "img_h": img.size[1]} if use_detector and region is None else None
        self.last_image_embedding = np.array([arr[..., 0].mean(), arr[..., 2].mean()], dtype=np.float32)
        score = round(float(arr[0, 0, 0]) / 255.0, 4)
        return [(name, score) for name in candidate_species][:top_k]


class FakeScoringHost:
    def __init__(self):
        self.seen = []

    def run_all_models(self, image_path, external_scores=None, logger=print, write_metadata=True):
        self.seen.append({"external_scores": external_scores, "write_metadata": write_metadata,
                          "bytes": open(image_path, "rb").read()})
        # MultiModelHost merges model dictionaries, never transport/preprocessing scalars.
        models = {"spaq": {"status": "success", "normalized_score": 0.61, "score": 61.0},
                  **{name: value for name, value in (external_scores or {}).items() if isinstance(value, dict)}}
        return {
            "version": "fake-1",
            "image_path": image_path,
            "image_name": os.path.basename(image_path),
            "models": models,
            "summary": {"total_models": len(models), "successful_predictions": len(models), "failed_predictions": 0,
                        "weighted_scores": {"general": 0.61}, "average_normalized_score": 0.61},
        }


class FakeProvider:
    def __init__(self):
        self.detector = FakeYoloDetector()
        self.scorer = FakeKeywordScorer()
        self.caption = FakeCaptioner()
        self.embed = FakeEmbeddingModel()
        self.bio = FakeBioCLIP()
        self.scoring = FakeScoringHost()

    def scoring_host(self):
        return self.scoring

    def keyword_scorer(self):
        return self.scorer

    def captioner(self):
        return self.caption

    def embedding_model(self):
        return self.embed

    def bird_detector(self):
        return self.detector

    def detector_info(self):
        return {"weights_sha256": "a" * 64, "load_error": None, "version": "repo/file.pt"}

    def bioclip(self):
        return self.bio


@pytest.fixture
def runner():
    provider = FakeProvider()
    app = create_app(token=TOKEN, provider=provider, config_loader=lambda: CFG, max_body_bytes=8 * 1024 * 1024)
    http = TestClient(app)
    client = GpuRunnerClient("http://testserver", TOKEN, http=http, config_loader=lambda: CFG)
    return provider, client, http


def _image(path, size=(64, 48), orientation=None):
    rng = np.random.default_rng(7)
    img = Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    kwargs = {}
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        kwargs["exif"] = exif
    img.save(path, quality=95, **kwargs)
    return str(path)


# ---------------------------------------------------------------------------
# Guards and transport
# ---------------------------------------------------------------------------

def test_bad_token_rejected_before_handler(runner):
    provider, _client, http = runner
    resp = http.post(KEYWORDS, headers={"Authorization": "Bearer nope"}, data={"meta": "{}"},
                     files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert resp.status_code == 401
    assert provider.scorer.last_image_embedding is None


def test_oversize_body_rejected_from_declared_length(runner):
    _provider, _client, http = runner
    resp = http.post(KEYWORDS, headers={"Authorization": f"Bearer {TOKEN}"}, data={"meta": "{}"},
                     files={"file": ("a.jpg", b"\0" * (9 * 1024 * 1024), "image/jpeg")})
    assert resp.status_code == 413


def test_healthz_needs_no_token_but_health_does(runner):
    _provider, client, http = runner
    assert http.get("/healthz").json() == {"ok": True}
    assert http.get("/v1/health").status_code == 401
    assert "keywords" in client.health()["phase_sections"]


def test_non_loopback_requires_token():
    with pytest.raises(SystemExit):
        require_token("0.0.0.0", "")
    require_token("127.0.0.1", "")


def test_check_phase_names_differing_sections(runner):
    _provider, _client, http = runner
    drifted = {**CFG, "tagging": {"clip_model": "other"}}
    stale = GpuRunnerClient("http://testserver", TOKEN, http=http, config_loader=lambda: drifted)
    stale.check_phase("scoring")  # unaffected
    with pytest.raises(RemoteGpuError, match="tagging"):
        stale.check_phase("keywords")


def test_request_with_drifted_config_gets_409(runner, tmp_path):
    from modules.remote_gpu.proxies import RemoteKeywordScorer

    _provider, _client, http = runner
    drifted = {**CFG, "tagging": {"clip_model": "other"}}
    stale = GpuRunnerClient("http://testserver", TOKEN, http=http, config_loader=lambda: drifted)
    with pytest.raises(RemoteGpuError, match="409"):
        RemoteKeywordScorer(stale, model_name="m").predict(_image(tmp_path / "a.jpg"))


class _ScriptedHttp:
    """httpx.Client stand-in that replays a script of responses / exceptions."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return httpx.Response(item[0], json=item[1], request=httpx.Request(method, url))


def test_busy_runner_is_retried_with_backoff(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)
    http = _ScriptedHttp([(503, {"error": "busy"}), (503, {"error": "busy"}), (200, {"ok": True})])
    assert GpuRunnerClient("http://r", TOKEN, http=http).health() == {"ok": True}
    assert http.calls == 3


def test_connect_error_retried_once_then_fails(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)
    http = _ScriptedHttp([httpx.ConnectError("refused"), httpx.ConnectError("refused")])
    with pytest.raises(RemoteGpuError, match="unreachable"):
        GpuRunnerClient("http://r", TOKEN, http=http).health()
    assert http.calls == 2


def test_read_timeout_is_not_retried(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)
    http = _ScriptedHttp([httpx.ReadTimeout("slow"), (200, {"ok": True})])
    with pytest.raises(RemoteGpuError, match="timed out"):
        GpuRunnerClient("http://r", TOKEN, http=http).health()
    assert http.calls == 1


def test_phase_is_remote_routing(monkeypatch):
    monkeypatch.setattr(client_mod, "_config", lambda: {})
    assert phase_is_remote("scoring") is False
    monkeypatch.setattr(client_mod, "_config", lambda: {"gpu_runner": {"enabled": True, "phases": {"scoring": "remote"}}})
    assert phase_is_remote("scoring") is True
    assert phase_is_remote("keywords") is False
    monkeypatch.setattr(client_mod, "_config", lambda: {"gpu_runner": {"enabled": True, "phases": {"scoring": "socket"}}})
    with pytest.raises(RemoteGpuError):
        phase_is_remote("scoring")


def test_runner_process_never_routes_remote(monkeypatch):
    monkeypatch.setattr(client_mod, "_config", lambda: {"gpu_runner": {"enabled": True, "phases": {"culling": "remote"}}})
    monkeypatch.setattr(client_mod, "_serving", True)
    assert phase_is_remote("culling") is False


# ---------------------------------------------------------------------------
# Parity: same fake model, local vs through the runner
# ---------------------------------------------------------------------------

def test_detector_parity(runner):
    from modules.remote_gpu.proxies import RemoteBirdDetector

    _provider, client, _http = runner
    rng = np.random.default_rng(3)
    image = Image.fromarray(rng.integers(0, 255, (120, 160, 3), dtype=np.uint8))
    local = FakeYoloDetector()
    remote = RemoteBirdDetector(client, config=BIRD_CFG)
    assert remote.detect_boxes(image) == local.detect_boxes(image)
    assert remote.detect_best_box(image) == local.detect_best_box(image)


def test_localization_remote_context_matches_local_hash(runner, monkeypatch):
    from modules import localization

    _provider, client, _http = runner
    monkeypatch.setattr("modules.remote_gpu.client.phase_is_remote", lambda phase: False)
    monkeypatch.setattr(BirdDetector, "_resolve_weights_path", lambda self: "w.pt")
    monkeypatch.setattr(BirdDetector, "load_model", lambda self: None)
    monkeypatch.setattr(localization, "weights_sha256", lambda path: "a" * 64)
    local_ctx = localization.load_detector_context({}, BIRD_CFG)

    monkeypatch.setattr("modules.remote_gpu.client.phase_is_remote", lambda phase: phase == "localization")
    monkeypatch.setattr("modules.remote_gpu.client.ready_client", lambda phase: client)
    remote_ctx = localization.load_detector_context({}, BIRD_CFG)

    assert remote_ctx.load_error is None
    assert type(remote_ctx.detector).__name__ == "RemoteBirdDetector"
    assert (remote_ctx.version, remote_ctx.config_hash) == (local_ctx.version, local_ctx.config_hash)


def test_localization_through_runner_is_idempotent(runner, monkeypatch, tmp_path):
    from modules import localization
    from modules.remote_gpu.proxies import RemoteBirdDetector

    provider, client, _http = runner
    path = _image(tmp_path / "bird.jpg", size=(160, 120))
    ctx = localization.DetectorContext(enabled=True, detector=RemoteBirdDetector(client, config=BIRD_CFG),
                                       version="repo/file.pt", config_hash="h" * 64)
    written = []
    monkeypatch.setattr(localization, "write_run", lambda run, regions, **kw: written.append((dict(run), regions)))
    monkeypatch.setattr(localization, "get_current_run", lambda image_id: None)

    first = localization.localize_image(5, path, ctx, max_regions=10)
    assert first.status == localization.STATUS_DETECTED and provider.detector.calls == 1
    run, regions = written[0]
    local_regions = FakeYoloDetector().detect_boxes(localization.decode_for_localization(path).image)
    assert regions == local_regions[:10]
    assert run["source_hash"] == localization.source_identity(path)[0]  # host file, not a runner temp copy

    monkeypatch.setattr(localization, "get_current_run", lambda image_id: run)
    second = localization.localize_image(5, path, ctx, max_regions=10)
    assert second.unchanged is True
    assert provider.detector.calls == 1 and len(written) == 1


def test_bird_species_parity_with_exif_rotation(runner, tmp_path):
    from modules.remote_gpu.proxies import RemoteBioCLIPClassifier

    _provider, client, _http = runner
    path = _image(tmp_path / "rot.jpg", size=(64, 40), orientation=6)
    local = FakeBioCLIP()
    remote = RemoteBioCLIPClassifier(client)
    species = ["Robin", "Mallard"]
    assert remote.classify(path, species, top_k=2) == local.classify(path, species, top_k=2)
    assert remote.last_bbox == local.last_bbox
    assert remote.last_bbox["img_w"] == 40  # upright: rotated once, on the host
    np.testing.assert_array_equal(remote.last_image_embedding, local.last_image_embedding)
    assert remote.last_image_embedding.dtype == np.float32


def test_bird_rescan_detector_runs_remotely(runner):
    from modules.remote_gpu.proxies import RemoteBioCLIPClassifier, RemoteBirdDetector

    _provider, client, _http = runner
    detector = RemoteBioCLIPClassifier(client)._ensure_detector()
    assert isinstance(detector, RemoteBirdDetector)


def test_keywords_parity(runner, tmp_path):
    from modules.remote_gpu.proxies import RemoteCaptionGenerator, RemoteKeywordScorer

    _provider, client, _http = runner
    path = _image(tmp_path / "k.jpg")
    local, remote = FakeKeywordScorer(), RemoteKeywordScorer(client, model_name="openai/clip-vit-base-patch32")
    assert remote.predict(path, keywords=["a", "b"], return_scores=True) == local.predict(path, keywords=["a", "b"], return_scores=True)
    np.testing.assert_array_equal(remote.last_image_embedding, local.last_image_embedding)
    assert remote.predict(path) == local.predict(path)
    assert remote.model_name == "openai/clip-vit-base-patch32"

    cap_local, cap_remote = FakeCaptioner(), RemoteCaptionGenerator(client)
    assert cap_remote.generate(path, extract_embedding=True) == cap_local.generate(path, extract_embedding=True)
    np.testing.assert_array_equal(cap_remote.last_image_embedding, cap_local.last_image_embedding)
    assert cap_remote.model_name == CaptionGenerator(device="cpu").model_name


def test_culling_embedding_parity(runner):
    from modules.remote_gpu.proxies import RemoteEmbeddingModel

    _provider, client, _http = runner
    batch = np.random.default_rng(1).normal(size=(3, 224, 224, 3)).astype(np.float32)
    local = FakeEmbeddingModel().predict(batch, verbose=0)
    remote = RemoteEmbeddingModel(client).predict(batch, verbose=0)
    assert remote.dtype == np.float32
    np.testing.assert_array_equal(remote, local)


class _CpuBackend:
    VERSION = "cpu-backend"
    gpu_available = False

    def __init__(self, nef=False):
        self.nef = nef
        self.written = []

    def is_raw_file(self, path):
        return False

    def is_nef_file(self, path):
        return self.nef

    def score_to_rating(self, avg):
        return 4

    def determine_lightroom_label(self, normalized):
        return "Green"

    def write_metadata_to_nef(self, path, rating, label):
        self.written.append((path, rating, label))
        return True


class _Registry:
    def all_active(self):
        return []

    def is_shadow(self, name):
        return False


@pytest.mark.parametrize("nef", [False, True])
def test_scoring_through_runner_keeps_host_identity(runner, tmp_path, nef):
    from modules.remote_gpu.proxies import RemoteScoringHost

    provider, client, _http = runner
    path = _image(tmp_path / "s.jpg")
    backend = _CpuBackend(nef=nef)
    host = RemoteScoringHost(client, backend, _Registry())
    external = {"liqe": {"status": "success", "normalized_score": 0.7}, "_liqe_preprocess_path": "/host/only.jpg"}
    result = host.run_all_models(path, external_scores=external, logger=lambda _m: None, write_metadata=True)

    sent = provider.scoring.seen[0]
    assert sent["bytes"] == open(path, "rb").read()
    assert sent["external_scores"] == external
    assert sent["write_metadata"] is False  # the runner never writes XMP
    assert result["image_path"] == path and result["image_name"] == "s.jpg"
    assert result["models"]["liqe"]["normalized_score"] == 0.7
    if nef:
        assert backend.written == [(path, 4, "Green")]
        assert result["summary"]["nef_metadata"]["rating"] == 4
    else:
        assert backend.written == [] and "nef_metadata" not in result["summary"]


# ---------------------------------------------------------------------------
# Runner wiring: model construction is the only branch point
# ---------------------------------------------------------------------------

def _route(monkeypatch, client, remote: bool):
    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: remote)
    monkeypatch.setattr(client_mod, "ready_client", lambda phase: client)


def test_factories_build_proxies_only_when_remote(runner, monkeypatch):
    from modules import bird_species, clustering, tagging
    from modules.remote_gpu import proxies

    _provider, client, _http = runner
    _route(monkeypatch, client, remote=True)
    assert isinstance(tagging.new_keyword_scorer(), proxies.RemoteKeywordScorer)
    assert isinstance(tagging.new_caption_generator(), proxies.RemoteCaptionGenerator)
    assert isinstance(bird_species.new_bioclip_classifier(), proxies.RemoteBioCLIPClassifier)
    engine = clustering.ClusteringEngine()
    engine.load_model()
    assert isinstance(engine.model, proxies.RemoteEmbeddingModel)

    _route(monkeypatch, client, remote=False)
    assert type(tagging.new_keyword_scorer()) is tagging.KeywordScorer
    assert type(tagging.new_caption_generator()) is tagging.CaptionGenerator
    assert type(bird_species.new_bioclip_classifier()) is bird_species.BioCLIPClassifier


def test_factory_fails_fast_when_runner_not_ready(monkeypatch):
    from modules import tagging

    def not_ready(phase):
        raise RemoteGpuError("GPU runner unreachable at http://r")

    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: True)
    monkeypatch.setattr(client_mod, "ready_client", not_ready)
    with pytest.raises(RemoteGpuError, match="unreachable"):
        tagging.new_keyword_scorer()


def test_scoring_runner_uses_remote_host(monkeypatch):
    from modules import scoring
    from modules.remote_gpu import proxies

    sentinel = object()
    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: phase == "scoring")
    monkeypatch.setattr(proxies, "create_remote_scoring_host", lambda: sentinel)
    runner = scoring.ScoringRunner()
    assert runner._init_shared_scorer(lambda *a, **k: None) is True
    assert runner.shared_scorer is sentinel


# ---------------------------------------------------------------------------
# Scene route (localization GPU work besides the detector)
# ---------------------------------------------------------------------------

def _fake_scene_classifier(backend="hf_clip_b32"):
    import torch

    from modules.scene_route import SceneClassifier

    class FakeScene(SceneClassifier):
        def load(self):
            if self._model is not None:
                return
            rng = np.random.default_rng(11)
            feats = rng.normal(size=(len(self.labels), 4))
            self._label_feats = feats / np.linalg.norm(feats, axis=1, keepdims=True)
            self._logit_scale = 50.0
            self._encode_image = lambda img: torch.tensor(
                [np.asarray(img, dtype=np.float32).mean(axis=(0, 1)).tolist() + [1.0]]
            )
            self._model = object()

    return FakeScene(backend, device="cpu")


def test_scene_route_parity(runner, monkeypatch):
    from modules.remote_gpu.proxies import RemoteSceneClassifier

    provider, client, _http = runner
    server_side = _fake_scene_classifier()
    provider.scene_classifier = lambda backend, prompt_set: server_side
    image = Image.fromarray(np.random.default_rng(5).integers(0, 255, (40, 60, 3), dtype=np.uint8))

    local = _fake_scene_classifier().classify(image)
    remote_clf = RemoteSceneClassifier(client, "hf_clip_b32")
    remote = remote_clf.classify(image)
    assert remote.top_label == local.top_label and remote.version == local.version
    assert remote.probs == pytest.approx(local.probs, abs=1e-5)
    np.testing.assert_allclose(remote_clf.last_embedding, server_side.last_embedding, atol=1e-6)


def test_scene_route_prompt_drift_is_an_error(runner):
    from modules.remote_gpu.proxies import RemoteSceneClassifier

    provider, client, _http = runner
    drifted = _fake_scene_classifier()
    drifted.version = "v0/hf_clip_b32/stale"
    provider.scene_classifier = lambda backend, prompt_set: drifted
    with pytest.raises(RemoteGpuError, match="scene version"):
        RemoteSceneClassifier(client, "hf_clip_b32").classify(Image.new("RGB", (8, 8)))


def test_scene_router_goes_remote_with_localization(runner, monkeypatch):
    from modules.localization_runner import SceneRouter
    from modules.remote_gpu.proxies import RemoteSceneClassifier

    _provider, client, _http = runner
    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: phase == "localization")
    monkeypatch.setattr(client_mod, "get_client", lambda: client)
    router = SceneRouter({"backend": "hf_clip_b32", "run_thresholds": {}})
    assert isinstance(router.classifier, RemoteSceneClassifier)


# ---------------------------------------------------------------------------
# Switching gpu_runner mode while the process keeps cached models
# ---------------------------------------------------------------------------

def test_current_mode_or_none(runner, monkeypatch):
    from unittest.mock import Mock

    from modules.remote_gpu.client import current_mode_or_none
    from modules.remote_gpu.proxies import RemoteEmbeddingModel, RemoteKeywordScorer
    from modules.tagging import KeywordScorer

    _provider, client, _http = runner
    remote_scorer = RemoteKeywordScorer(client, model_name="m")
    local_scorer = KeywordScorer(model_name="m", device="cpu")
    mock = Mock()

    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: False)
    assert current_mode_or_none(remote_scorer, "keywords", KeywordScorer) is None
    assert current_mode_or_none(local_scorer, "keywords", KeywordScorer) is local_scorer
    assert current_mode_or_none(RemoteEmbeddingModel(client), "culling") is None
    assert current_mode_or_none(mock, "culling") is mock

    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: True)
    assert current_mode_or_none(local_scorer, "keywords", KeywordScorer) is None
    assert current_mode_or_none(remote_scorer, "keywords", KeywordScorer) is remote_scorer
    assert current_mode_or_none(mock, "keywords", KeywordScorer) is mock  # injected test doubles survive


def test_tagging_runner_drops_cached_models_from_other_mode(runner, monkeypatch):
    from modules import tagging
    from modules.remote_gpu.proxies import RemoteCaptionGenerator, RemoteKeywordScorer

    _provider, client, _http = runner
    tagger = tagging.TaggingRunner()
    tagger.scorer = RemoteKeywordScorer(client, model_name="m")
    tagger.captioner = RemoteCaptionGenerator(client)
    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: False)
    tagging._drop_models_from_other_mode(tagger)
    assert tagger.scorer is None and tagger.captioner is None


def test_scoring_runner_rebuilds_host_after_mode_switch(monkeypatch):
    from modules import scoring
    from modules.engines import factory
    from modules.engines.host import MultiModelHost
    from modules.remote_gpu.proxies import RemoteScoringHost

    local_host = MultiModelHost(backend=_CpuBackend(), registry=_Registry())
    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: False)
    monkeypatch.setattr(factory, "create_production_scoring_host", lambda **kw: local_host)
    monkeypatch.setattr(factory, "load_production_models", lambda host, log=None: (True, ""))

    runner = scoring.ScoringRunner()
    runner.shared_scorer = RemoteScoringHost(None, _CpuBackend(), _Registry())
    assert runner._init_shared_scorer(lambda *a, **k: None) is True
    assert runner.shared_scorer is local_host

    injected = object()  # a test-injected engine is never replaced
    runner.shared_scorer = injected
    assert runner._init_shared_scorer(lambda *a, **k: None) is True
    assert runner.shared_scorer is injected
