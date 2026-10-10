"""Regressions for HTTP admission, cached config and invalid model output."""

from __future__ import annotations

import asyncio
import copy
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from modules.remote_gpu.client import GpuRunnerClient
from modules.remote_gpu.contract import (
    FINGERPRINT_HEADER,
    KEYWORDS,
    RemoteGpuError,
    phase_fingerprint,
)
from modules.remote_gpu.server import GuardMiddleware, create_app


@pytest.mark.parametrize("length", [b"invalid", b"-1"])
def test_invalid_content_length_returns_400_without_reading(length):
    async def check():
        messages = []

        async def downstream(*args):
            pytest.fail("invalid length reached downstream")

        async def receive():
            pytest.fail("invalid length read the body")

        async def send(message):
            messages.append(message)

        await GuardMiddleware(downstream, token="", max_body_bytes=32)(
            {"type": "http", "path": KEYWORDS, "method": "POST",
             "headers": [(b"content-length", length)]}, receive, send,
        )
        assert messages[0]["status"] == 400

    asyncio.run(check())


def test_actual_upload_size_is_bounded_even_when_declared_length_lies():
    async def check():
        messages = []
        chunks = iter([b"1234", b"56789"])

        async def downstream(scope, receive, send):
            await receive()
            await receive()
            pytest.fail("oversize upload reached the handler")

        async def receive():
            return {"type": "http.request", "body": next(chunks), "more_body": True}

        async def send(message):
            messages.append(message)

        await GuardMiddleware(downstream, token="", max_body_bytes=8)(
            {"type": "http", "path": KEYWORDS, "method": "POST",
             "headers": [(b"content-length", b"4")]}, receive, send,
        )
        assert messages[0]["status"] == 413

    asyncio.run(check())


def test_requests_are_admitted_before_body_read():
    async def check():
        entered, release = asyncio.Event(), asyncio.Event()
        rejected = []

        async def downstream(scope, receive, send):
            entered.set()
            await release.wait()

        async def receive():
            pytest.fail("busy request read its body")

        async def send(message):
            rejected.append(message)

        guard = GuardMiddleware(downstream, token="", max_body_bytes=8, max_concurrency=1)
        scope = {"type": "http", "path": KEYWORDS, "method": "POST",
                 "headers": [(b"content-length", b"4")]}
        first = asyncio.create_task(guard(scope, receive, send))
        await entered.wait()
        try:
            await guard(scope, receive, send)
            assert rejected[0]["status"] == 503
        finally:
            release.set()
            await first
        # Admission is released after completion.
        await guard(scope, receive, send)

    asyncio.run(check())


@pytest.mark.parametrize("meta", ["{broken", "[]", "null"])
def test_malformed_metadata_is_a_client_error(meta):
    cfg = {"tagging": {}}
    provider = SimpleNamespace(keyword_scorer=lambda: pytest.fail("invalid meta loaded a model"))
    http = TestClient(create_app(provider=provider, config_loader=lambda: cfg), raise_server_exceptions=False)
    response = http.post(
        KEYWORDS, headers={FINGERPRINT_HEADER: phase_fingerprint(cfg, "keywords")},
        data={"meta": meta}, files={"file": ("a.jpg", b"unused")},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("meta", [
    '{"threshold":"bad"}', '{"top_k":-1}', '{"image_embedding":[[1.0]]}',
])
def test_invalid_keyword_arguments_are_rejected_before_model_load(meta):
    provider = SimpleNamespace(keyword_scorer=lambda: pytest.fail("invalid input loaded a model"))
    http = TestClient(create_app(provider=provider, config_loader=lambda: {}), raise_server_exceptions=False)
    response = http.post(
        KEYWORDS, headers={FINGERPRINT_HEADER: phase_fingerprint({}, "keywords")},
        data={"meta": meta}, files={"file": ("a.jpg", b"unused")},
    )
    assert response.status_code == 422


def test_model_config_change_requires_worker_restart_before_inference():
    cfg = {"tagging": {"clip_model": "original"}}
    calls = []

    class Scorer:
        last_image_embedding = None

        def predict(self, *args, **kwargs):
            calls.append(1)
            return ["bird"], {}, {}

    provider = SimpleNamespace(keyword_scorer=lambda: Scorer())
    http = TestClient(create_app(provider=provider, config_loader=lambda: cfg))
    host_cfg = copy.deepcopy(cfg)
    client = GpuRunnerClient("http://testserver", "", http=http, config_loader=lambda: host_cfg)
    assert client.call(KEYWORDS, {}, b"image")["keywords"] == ["bird"]
    cfg["tagging"]["clip_model"] = "changed"
    host_cfg["tagging"]["clip_model"] = "changed"
    with pytest.raises(RemoteGpuError, match="restart"):
        client.check_phase("keywords")
    with pytest.raises(RemoteGpuError, match="409"):
        client.call(KEYWORDS, {}, b"image")
    assert len(calls) == 1


@pytest.mark.parametrize("result", [
    {},
    {"models": {}, "summary": {"total_models": 0}},
    {"models": {"spaq": {"status": "success", "normalized_score": float("nan")}},
     "summary": {"total_models": 1, "successful_predictions": 1, "failed_predictions": 0}},
    {"models": {"spaq": {"status": "failed"}},
     "summary": {"total_models": 1, "successful_predictions": 1, "failed_predictions": 0}},
])
def test_invalid_remote_scores_are_rejected(result, tmp_path):
    from modules.remote_gpu.proxies import RemoteScoringHost

    path = tmp_path / "a.jpg"
    path.write_bytes(b"image")
    client = SimpleNamespace(call=lambda *args, **kwargs: result)
    backend = SimpleNamespace(is_raw_file=lambda path: False, VERSION="test")
    registry = SimpleNamespace(all_active=lambda: [])
    with pytest.raises(RemoteGpuError, match="scoring"):
        RemoteScoringHost(client, backend, registry).run_all_models(str(path), write_metadata=False)


def test_health_rejects_incompatible_api_version():
    client = GpuRunnerClient("http://testserver", "")
    client.health = lambda: {"api_version": 999, "phase_sections": {"culling": {}}}
    with pytest.raises(RemoteGpuError, match="version"):
        client.check_phase("culling")


@pytest.mark.parametrize("stored", [False, True])
def test_accessibility_ranking_uses_remote_scorer(monkeypatch, stored):
    from modules import clip_accessibility as ca
    from modules.remote_gpu import client as client_mod

    monkeypatch.setattr(client_mod, "phase_is_remote", lambda phase: False)
    emb = np.array([1.0, 0.0], dtype=np.float32) if stored else None
    prompts = ["a photo of a bird"]
    calls = []

    class Remote:
        runs_remotely = True

        def rank_accessibility(self, image_path, prompts, image_embedding=None):
            calls.append((image_path, prompts, image_embedding))
            return np.array([1.0, 0.0]), [(prompts[0], 0.9)]

    monkeypatch.setattr(ca, "get_stored_clip_embedding", lambda iid: emb)
    monkeypatch.setattr(ca, "existing_accessibility_fields", lambda *args: {})
    monkeypatch.setattr(ca, "_rank_prompts_by_embedding", lambda *args: pytest.fail("local text tower"))
    monkeypatch.setattr(ca, "_rank_prompts_from_image_path", lambda *args, **kw: pytest.fail("local image tower"))
    result = ca.describe_from_clip(image_id=1, image_path="a.jpg", scorer=Remote(), prompts=prompts)
    assert result["alt_text"]
    assert len(calls) == 1
    assert calls[0][2] is emb


@pytest.mark.parametrize("stored", [False, True])
def test_accessibility_transport_preserves_ranking(monkeypatch, stored, tmp_path):
    from modules import clip_accessibility as ca
    from modules.remote_gpu.proxies import RemoteKeywordScorer

    prompts = ["bird", "sky"]
    ranked = [("sky", 0.8), ("bird", 0.2)]
    emb = np.array([1.0, 0.0], dtype=np.float32)
    calls = []

    class Scorer:
        def load_model(self):
            pass

        def _score_prompts_from_embedding(self, image_embedding, candidate_prompts):
            calls.append(candidate_prompts)
            return [0.2, 0.8], [0.2, 0.8], emb

    def image_rank(path, candidate_prompts, scorer=None):
        assert open(path, "rb").read() == b"image"
        calls.append(candidate_prompts)
        return emb, ranked

    monkeypatch.setattr(ca, "_rank_prompts_from_image_path", image_rank)
    provider = SimpleNamespace(keyword_scorer=lambda: Scorer())
    http = TestClient(create_app(provider=provider, config_loader=lambda: {}))
    client = GpuRunnerClient("http://testserver", "", http=http, config_loader=lambda: {})
    path = tmp_path / "a.jpg"
    path.write_bytes(b"image")
    actual_emb, actual_ranked = RemoteKeywordScorer(client).rank_accessibility(
        str(path), prompts, image_embedding=emb if stored else None,
    )
    np.testing.assert_array_equal(actual_emb, emb)
    assert actual_ranked == ranked
    assert calls == [prompts]


def test_upload_deadline_releases_admission():
    async def check():
        messages = []

        async def downstream(scope, receive, send):
            await receive()

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)

        guard = GuardMiddleware(downstream, token="", max_body_bytes=32,
                                max_concurrency=1, upload_timeout=0.01)
        scope = {"type": "http", "path": KEYWORDS, "method": "POST",
                 "headers": [(b"content-length", b"4")]}
        await guard(scope, receive, send)
        await guard(scope, receive, send)
        assert [msg["status"] for msg in messages if msg["type"] == "http.response.start"] == [408, 408]

    asyncio.run(check())


def test_disabled_liqe_does_not_load_local_gpu_in_remote_scoring(monkeypatch, tmp_path):
    import queue
    import threading

    from modules import pipeline
    from modules.pipeline import ImageJob, ScoringWorker
    from modules.remote_gpu.proxies import RemoteScoringHost

    path = tmp_path / "a.jpg"
    path.write_bytes(b"image")
    result = {"models": {"spaq": {"status": "success", "normalized_score": 0.6}},
              "summary": {"total_models": 1, "successful_predictions": 1, "failed_predictions": 0}}
    client = SimpleNamespace(call=lambda *args, **kwargs: result)
    backend = SimpleNamespace(is_raw_file=lambda path: False, VERSION="test",
                              preprocess_image=lambda path, **kwargs: path)
    registry = SimpleNamespace(all_active=lambda: [SimpleNamespace(name="spaq")])
    host = RemoteScoringHost(client, backend, registry)
    worker = ScoringWorker(queue.Queue(), queue.Queue(), threading.Event(), host)
    local_calls = []

    def local_liqe():
        local_calls.append(1)
        return SimpleNamespace(predict=lambda path: {"status": "failed"})

    monkeypatch.setattr(worker, "_get_liqe_scorer", local_liqe)
    monkeypatch.setattr(pipeline.app_config, "load_config", lambda: {})
    monkeypatch.setattr(pipeline.tempfile, "mkdtemp", lambda **kwargs: str(tmp_path))
    cache_clears = []
    fake_cuda = SimpleNamespace(is_available=lambda: True, empty_cache=lambda: cache_clears.append(1))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=fake_cuda))
    job = ImageJob(image_path=str(path), process_path=str(path), job_id=0)
    worker.process(job)
    assert job.status == "success"
    assert local_calls == []
    assert cache_clears == []  # a remote host never touches the local GPU
