"""Live parity: real models, local call vs the same call through the GPU runner's HTTP stack.

Opt-in (needs the CUDA image and model weights):

    GPU_RUNNER_LIVE=1 python -m pytest tests/test_remote_gpu_runner_live.py -q

The runner app runs in-process behind ``TestClient`` with the real ``ModelProvider``.
The local side reuses the provider's model instances, so any difference comes
from transport or host-side handling, not from a second copy of the weights.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.ml,
    pytest.mark.skipif(os.environ.get("GPU_RUNNER_LIVE") != "1", reason="set GPU_RUNNER_LIVE=1 to run"),
    pytest.mark.filterwarnings("ignore:You should not use the 'timeout' argument:DeprecationWarning"),
]

SAMPLES = Path(__file__).parent / "fixtures" / "testing_samples" / "public" / "D300"
NEF = SAMPLES / "D300_50mm_f1_4.NEF"
NEF_WITH_BOX = SAMPLES / "D300_28_70mm_f2_8.NEF"


@pytest.fixture(scope="module")
def live():
    from fastapi.testclient import TestClient

    from modules.remote_gpu.client import GpuRunnerClient
    from modules.remote_gpu.server import ModelProvider, create_app

    provider = ModelProvider()
    client = GpuRunnerClient("http://testserver", "t", http=TestClient(create_app(token="t", provider=provider)))
    return provider, client


@pytest.fixture(scope="module")
def jpeg(tmp_path_factory):
    from modules.thumbnails import open_oriented_for_ml

    path = tmp_path_factory.mktemp("live") / "d300.jpg"
    img = open_oriented_for_ml(str(NEF))
    img.thumbnail((1024, 1024))
    img.save(path, quality=92)
    return str(path)


def test_keywords_and_caption(live, jpeg):
    from modules.remote_gpu.proxies import RemoteCaptionGenerator, RemoteKeywordScorer

    provider, client = live
    scorer = provider.keyword_scorer()
    local = scorer.predict(jpeg, return_scores=True)
    local_emb = np.array(scorer.last_image_embedding)
    remote_scorer = RemoteKeywordScorer(client)
    remote = remote_scorer.predict(jpeg, return_scores=True)
    assert remote[0] == local[0]
    assert remote[1] == pytest.approx(local[1], rel=1e-4)
    np.testing.assert_allclose(remote_scorer.last_image_embedding, local_emb, atol=1e-5)
    assert remote_scorer.model_name == scorer.model_name

    captioner = provider.captioner()
    assert RemoteCaptionGenerator(client).generate(jpeg) == captioner.generate(jpeg)


def test_culling_embeddings(live, jpeg):
    from PIL import Image
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

    from modules.remote_gpu.proxies import RemoteEmbeddingModel

    provider, client = live
    img = Image.open(jpeg).convert("RGB").resize((224, 224), Image.LANCZOS)
    batch = np.array([preprocess_input(np.array(img, dtype=np.float32))])
    local = provider.embedding_model().predict(batch, verbose=0)
    remote = RemoteEmbeddingModel(client).predict(batch, verbose=0)
    np.testing.assert_allclose(remote, local, atol=1e-5)


def test_detector_and_localization_hash(live):
    from modules import config
    from modules.localization import decode_for_localization, detector_config_hash, weights_sha256
    from modules.remote_gpu.proxies import RemoteBirdDetector

    provider, client = live
    # The only public sample with a detection, and only at a very low threshold.
    image = decode_for_localization(str(NEF_WITH_BOX)).image
    local = provider.bird_detector()
    local.confidence = 0.01
    remote = RemoteBirdDetector(client, config={**(config.get_config_section("bird_detection") or {}), "confidence": 0.01})
    boxes = local.detect_boxes(image)
    assert boxes, "fixture should yield at least one low-confidence box"
    assert remote.detect_boxes(image) == boxes
    assert remote.detect_best_box(image) == local.detect_best_box(image)
    knobs = (local.imgsz, local.confidence, local.max_det)
    assert detector_config_hash(remote.remote_weights_sha256(), *knobs) == detector_config_hash(
        weights_sha256(local._resolve_weights_path()), *knobs
    )


def test_bird_species(live):
    from modules.remote_gpu.proxies import RemoteBioCLIPClassifier

    provider, client = live
    species = ["American Robin", "Mallard", "Northern Cardinal", "Bald Eagle"]
    classifier = provider.bioclip()
    local = classifier.classify(str(NEF), species, top_k=4, threshold=0.0)
    local_bbox, local_emb = classifier.last_bbox, np.array(classifier.last_image_embedding)
    remote_classifier = RemoteBioCLIPClassifier(client)
    remote = remote_classifier.classify(str(NEF), species, top_k=4, threshold=0.0)
    assert [name for name, _ in remote] == [name for name, _ in local]
    assert [p for _, p in remote] == pytest.approx([p for _, p in local], abs=1e-3)
    assert remote_classifier.last_bbox == local_bbox
    np.testing.assert_allclose(remote_classifier.last_image_embedding, local_emb, atol=1e-4)


def test_scoring(live, jpeg):
    from modules.engines.registry import ModelRegistry
    from modules.engines.factory import ensure_production_registry
    from modules.remote_gpu.proxies import RemoteScoringHost
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    provider, client = live
    local = provider.scoring_host().run_all_models(jpeg, logger=lambda _m: None, write_metadata=False)
    backend = MultiModelMUSIQ(skip_gpu=True)
    remote_host = RemoteScoringHost(client, backend, ensure_production_registry(backend, registry=ModelRegistry()))
    remote = remote_host.run_all_models(jpeg, logger=lambda _m: None, write_metadata=False)
    assert any(p.get("status") == "success" for p in local["models"].values()), local["models"]
    assert remote["image_path"] == local["image_path"]
    assert set(remote["models"]) == set(local["models"])
    for name, payload in local["models"].items():
        assert remote["models"][name].get("status") == payload.get("status"), name
        if payload.get("normalized_score") is not None:
            assert remote["models"][name]["normalized_score"] == pytest.approx(payload["normalized_score"], abs=1e-3), name


def test_scene_route(live):
    from modules.localization import decode_for_localization
    from modules.remote_gpu.proxies import RemoteSceneClassifier
    from modules.scene_route import PROMPT_SET_VERSION

    provider, client = live
    image = decode_for_localization(str(NEF_WITH_BOX)).image
    local_clf = provider.scene_classifier("hf_clip_b32", PROMPT_SET_VERSION)
    local = local_clf.classify(image)
    remote = RemoteSceneClassifier(client, "hf_clip_b32").classify(image)
    assert remote.top_label == local.top_label and remote.version == local.version
    assert remote.probs == pytest.approx(local.probs, abs=1e-4)
