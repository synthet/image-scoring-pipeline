"""Availability failover must preserve the inference and persistence boundary."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from modules.remote_gpu import client as clients
from modules.remote_gpu.contract import DETECT, KEYWORDS, RemoteGpuError


class Backend:
    def __init__(self, name, events, error=None):
        self.base_url = name
        self.events = events
        self.error = error

    def check_phase(self, phase):
        self.events.append((self.base_url, "check", phase))
        if self.error:
            raise self.error
        return {"ok": True}

    def call(self, endpoint, *args, **kwargs):
        self.events.append((self.base_url, "call", endpoint))
        if self.error:
            raise self.error
        return {"backend": self.base_url}

    def detector_info(self):
        return {"weights_sha256": self.base_url, "version": "detector-v1", "load_error": None}


def chain(backends, now=None):
    return clients.FallbackGpuClient(backends, cooldown=30, clock=now or (lambda: 0))


def unavailable():
    return clients.RemoteGpuUnavailable("unreachable")


def test_remote_outage_uses_local_side_runner_first():
    events = []
    route = chain([Backend("remote", events, unavailable()), Backend("local", events), Backend("embedded", events)])
    route.check_phase("keywords")
    assert route.call(KEYWORDS, {}, b"image") == {"backend": "local"}
    assert not any(name == "embedded" for name, *rest in events)


def test_mid_batch_outage_uses_embedded_when_both_http_runners_are_down():
    events = []
    remote = Backend("remote", events)
    route = chain([remote, Backend("local", events, unavailable()), Backend("embedded", events)])
    route.check_phase("keywords")
    remote.error = unavailable()
    assert route.call(KEYWORDS, {}, b"image") == {"backend": "embedded"}


def test_failed_runner_is_cooled_down_then_preferred_again():
    events, now = [], [0]
    remote = Backend("remote", events, unavailable())
    route = chain([remote, Backend("local", events)], now=lambda: now[0])
    route.call(KEYWORDS, {}, b"image")
    remote.error = None
    route.call(KEYWORDS, {}, b"image")
    assert len([e for e in events if e[0] == "remote"]) == 1
    now[0] = 31
    assert route.call(KEYWORDS, {}, b"image") == {"backend": "remote"}


@pytest.mark.parametrize("message", ["HTTP 401", "config mismatch", "API version", "timed out", "invalid scoring"])
def test_non_availability_errors_never_fall_back(message):
    events = []
    route = chain([Backend("remote", events, RemoteGpuError(message)), Backend("local", events)])
    with pytest.raises(RemoteGpuError, match=message):
        route.call(KEYWORDS, {}, b"image")
    assert not any(e[0] == "local" for e in events)


def test_all_unavailable_returns_useful_error():
    events = []
    route = chain([Backend("remote", events, unavailable()), Backend("local", events, unavailable())])
    with pytest.raises(RemoteGpuError, match="all.*unavailable"):
        route.call(KEYWORDS, {}, b"image")


def test_failover_cannot_change_detector_weights_behind_existing_context():
    events = []
    remote = Backend("remote", events)
    route = chain([remote, Backend("local", events)])
    assert route.detector_info()["weights_sha256"] == "remote"
    remote.error = unavailable()
    with pytest.raises(RemoteGpuError, match="weights"):
        route.call(DETECT, {}, b"image")
    assert ("local", "call", DETECT) not in events


def test_get_client_builds_ordered_fallback_and_rebuilds_when_settings_change(monkeypatch):
    cfg = {"gpu_runner": {"url": "http://remote:7870", "fallback": {"local_url": "http://localhost:7871"}}}
    monkeypatch.setattr(clients, "_config", lambda: cfg)
    monkeypatch.setattr(clients, "_token", lambda: "test-token")
    monkeypatch.setattr(clients, "_client", None)
    monkeypatch.setattr(clients, "_client_key", None)
    monkeypatch.setattr(clients, "_embedded_client", None)
    first = clients.get_client()
    assert isinstance(first, clients.FallbackGpuClient)
    assert [b.base_url for b in first.backends] == ["http://remote:7870", "http://localhost:7871", "embedded"]
    assert clients.get_client() is first
    cfg["gpu_runner"]["fallback"]["embedded"] = False
    second = clients.get_client()
    assert second is not first
    assert len(second.backends) == 2
    cfg["gpu_runner"]["fallback"]["enabled"] = False
    assert isinstance(clients.get_client(), clients.GpuRunnerClient)


@pytest.mark.parametrize("failure", [httpx.ConnectError("refused"), httpx.ConnectTimeout("refused")])
def test_connection_failure_is_classified_safe_for_failover(monkeypatch, failure):
    monkeypatch.setattr(clients.time, "sleep", lambda _: None)
    http = SimpleNamespace(request=lambda *a, **k: (_ for _ in ()).throw(failure))
    with pytest.raises(clients.RemoteGpuUnavailable):
        clients.GpuRunnerClient("http://r", "", http=http).call(KEYWORDS, {})


def test_busy_refusal_is_classified_safe_for_failover(monkeypatch):
    monkeypatch.setattr(clients.time, "sleep", lambda _: None)
    http = SimpleNamespace(request=lambda *a, **k: httpx.Response(503, json={"error": "busy"}))
    with pytest.raises(clients.RemoteGpuUnavailable):
        clients.GpuRunnerClient("http://r", "", http=http).call(KEYWORDS, {})


def test_submitted_read_timeout_is_never_classified_safe_for_failover():
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("inference may still be running")

    client = clients.GpuRunnerClient("http://r", "", http=SimpleNamespace(request=timeout))
    with pytest.raises(RemoteGpuError) as exc:
        client.call(KEYWORDS, {})
    assert not isinstance(exc.value, clients.RemoteGpuUnavailable)


def test_embedded_execution_suppresses_remote_routing_only_in_current_thread(monkeypatch):
    import threading

    monkeypatch.setattr(clients, "_config", lambda: {"gpu_runner": {"enabled": True, "phases": {"culling": "remote"}}})
    seen = []

    class Runtime:
        def execute(self, *args, **kwargs):
            seen.append(clients.phase_is_remote("culling"))
            other = threading.Thread(target=lambda: seen.append(clients.phase_is_remote("culling")))
            other.start()
            other.join()
            return {"ok": True}

    embedded = clients.EmbeddedGpuClient(runtime_factory=Runtime, config_loader=lambda: {})
    embedded.call(KEYWORDS, {}, b"image")
    assert seen == [False, True]
    assert clients.phase_is_remote("culling") is True


def test_completed_worker_failure_can_fall_back_without_replaying_a_timeout():
    http = SimpleNamespace(request=lambda *a, **k: httpx.Response(500, json={"error": "CUDA unavailable"}))
    with pytest.raises(clients.RemoteGpuUnavailable):
        clients.GpuRunnerClient("http://r", "", http=http).call(KEYWORDS, {})


def test_health_timeout_can_fall_back_before_any_inference_is_submitted():
    http = SimpleNamespace(request=lambda *a, **k: (_ for _ in ()).throw(httpx.ReadTimeout("health blocked")))
    with pytest.raises(clients.RemoteGpuUnavailable):
        clients.GpuRunnerClient("http://r", "", http=http).check_phase("keywords")


def test_embedded_invalid_metadata_is_rejected_before_runtime_construction():
    def load():
        pytest.fail("invalid metadata loaded embedded models")

    client = clients.EmbeddedGpuClient(runtime_factory=load, config_loader=lambda: {})
    with pytest.raises(RemoteGpuError, match="metadata"):
        client.call(KEYWORDS, {"threshold": "invalid"}, b"image")


def test_embedded_errors_are_reported_and_remote_routing_is_restored(monkeypatch):
    cfg = {"gpu_runner": {"enabled": True, "phases": {"keywords": "remote"}}}
    monkeypatch.setattr(clients, "_config", lambda: cfg)

    class Runtime:
        def execute(self, *args, **kwargs):
            raise RuntimeError("local weights unavailable")

    client = clients.EmbeddedGpuClient(runtime_factory=Runtime, config_loader=lambda: {})
    with pytest.raises(RemoteGpuError, match="embedded.*weights unavailable"):
        client.call(KEYWORDS, {}, b"image")
    assert clients.phase_is_remote("keywords")


def test_embedded_model_config_change_requires_restart():
    cfg = {"tagging": {"clip_model": "original"}}
    runtime = SimpleNamespace(execute=lambda *a, **k: {"ok": True})
    client = clients.EmbeddedGpuClient(runtime_factory=lambda: runtime, config_loader=lambda: cfg)
    client.call(KEYWORDS, {}, b"image")
    cfg["tagging"]["clip_model"] = "changed"
    with pytest.raises(RemoteGpuError, match="restart"):
        client.call(KEYWORDS, {}, b"image")


def test_fallback_logs_do_not_contain_url_credentials(caplog):
    events = []
    route = chain([Backend("http://user:FAKE-SECRET@remote:7870?token=FAKE-SECRET", events, unavailable()),
                   Backend("embedded", events)])
    route.call(KEYWORDS, {}, b"image")
    assert "FAKE-SECRET" not in caplog.text
    assert "user:" not in caplog.text


@pytest.mark.parametrize("endpoint", ["scoring", "keywords", "caption", "embedding", "detect", "scene", "bioclip", "accessibility", "stored_accessibility"])
def test_embedded_matches_http_worker_for_every_model_method(endpoint, monkeypatch, tmp_path):
    import json

    import numpy as np
    from fastapi.testclient import TestClient
    from PIL import Image

    from modules import clip_accessibility as ca
    from modules.remote_gpu import contract as wire
    from modules.remote_gpu.runtime import InferenceRuntime
    from modules.remote_gpu.server import create_app
    from tests.test_remote_gpu_runner import CFG, FakeProvider, _fake_scene_classifier

    providers = [FakeProvider(), FakeProvider()]
    for provider in providers:
        provider.scene_classifier = lambda *args: _fake_scene_classifier()
        provider.scorer.load_model = lambda: None
        provider.scorer._score_prompts_from_embedding = lambda *args: ([0.5], [0.5], np.array([1.0, 0.0]))
    monkeypatch.setattr(ca, "_rank_prompts_from_image_path", lambda *args, **kwargs: (np.array([1.0, 0.0]), [("bird", 0.5)]))
    http = TestClient(create_app(provider=providers[0], config_loader=lambda: CFG))
    remote = clients.GpuRunnerClient("http://testserver", "", http=http, config_loader=lambda: CFG)
    embedded = clients.EmbeddedGpuClient(runtime_factory=lambda: InferenceRuntime(providers[1]), config_loader=lambda: CFG)
    png = wire.encode_png(Image.new("RGB", (32, 32), color=(30, 60, 90)))
    specs = {
        "scoring": (wire.SCORING, {}, png),
        "keywords": (wire.KEYWORDS, {}, png),
        "caption": (wire.CAPTION, {"extract_embedding": True}, png),
        "embedding": (wire.EMBEDDING, {}, wire.encode_array(np.ones((1, 224, 224, 3), dtype=np.float32))),
        "detect": (wire.DETECT, {"conf": 0.25, "imgsz": 640, "max_det": 5}, png),
        "scene": (wire.SCENE, {"backend": "hf_clip_b32", "prompt_set": "v1"}, png),
        "bioclip": (wire.BIOCLIP, {"candidate_species": ["bird"]}, png),
        "accessibility": (wire.ACCESSIBILITY, {"prompts": ["bird"]}, png),
        "stored_accessibility": (wire.ACCESSIBILITY, {"prompts": ["bird"], "image_embedding": [1.0, 0.0]}, None),
    }
    route, params, data = specs[endpoint]
    results = [client.call(route, params, data, filename="image.png") for client in (remote, embedded)]
    for result in results:
        result.pop("image_path", None)  # temp file identity belongs to the transport
        result.pop("image_name", None)
    assert json.dumps(results[0], sort_keys=True) == json.dumps(results[1], sort_keys=True)
    if endpoint == "scoring":
        assert all(not p.scoring.seen[0]["write_metadata"] for p in providers)


def test_embedded_lazy_runtime_and_inference_are_serialized():
    import concurrent.futures
    import threading
    import time

    state = {"created": 0, "active": 0, "maximum": 0}
    lock = threading.Lock()

    class Runtime:
        def __init__(self):
            state["created"] += 1

        def execute(self, *args, **kwargs):
            with lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
            time.sleep(0.01)
            with lock:
                state["active"] -= 1
            return {"ok": True}

    client = clients.EmbeddedGpuClient(runtime_factory=Runtime, config_loader=lambda: {})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.call(KEYWORDS, {}, b"image"), range(8)))
    assert all(result["ok"] for result in results)
    assert state == {"created": 1, "active": 0, "maximum": 1}


def test_tagging_factory_uses_real_embedded_fallback_when_http_runners_are_down(monkeypatch, tmp_path):
    from modules import tagging
    from modules.remote_gpu import runtime
    from tests.test_remote_gpu_runner import CFG, FakeProvider, _image

    cfg = {**CFG, "gpu_runner": {"enabled": True, "url": "http://remote:7870", "phases": {"keywords": "remote"}}}
    monkeypatch.setattr(clients, "_config", lambda: cfg)
    monkeypatch.setattr(clients, "_token", lambda: "test-token")
    monkeypatch.setattr(clients, "_client", None)
    monkeypatch.setattr(clients, "_client_key", None)
    monkeypatch.setattr(clients, "_embedded_client", None)
    monkeypatch.setattr(clients.GpuRunnerClient, "_send", lambda *args, **kwargs: (_ for _ in ()).throw(unavailable()))
    provider = FakeProvider()
    runtime_cls = runtime.InferenceRuntime
    monkeypatch.setattr(runtime, "InferenceRuntime", lambda: runtime_cls(provider))
    scorer = tagging.new_keyword_scorer()
    result = scorer.predict(_image(tmp_path / "a.jpg"), keywords=["bird"])
    assert result == ["bird"]
    route = clients.get_client()
    embedded = route.backends[-1]
    cfg["gpu_runner"]["url"] = "http://another:7870"
    assert clients.get_client().backends[-1] is embedded


def test_matching_detector_identity_allows_mid_batch_fallback():
    events = []
    remote, local = Backend("remote", events), Backend("local", events)
    local.detector_info = remote.detector_info
    route = chain([remote, local])
    route.detector_info()
    remote.error = unavailable()
    assert route.call(DETECT, {}, b"image") == {"backend": "local"}


def test_ambiguous_failure_is_not_replayed_but_next_image_uses_fallback():
    events = []
    remote = Backend("remote", events)
    route = chain([remote, Backend("local", events)])
    route.check_phase("keywords")
    remote.error = clients.RemoteGpuAmbiguous("inference timed out")
    with pytest.raises(RemoteGpuError, match="timed out"):
        route.call(KEYWORDS, {}, b"first image")
    assert not any(e[0] == "local" for e in events)
    assert route.call(KEYWORDS, {}, b"second image") == {"backend": "local"}


@pytest.mark.parametrize("status", [502, 504])
def test_gateway_errors_do_not_replay_submitted_inference(status):
    http = SimpleNamespace(request=lambda *a, **k: httpx.Response(status, json={"error": "gateway failure"}))
    client = clients.GpuRunnerClient("http://r", "", http=http)
    with pytest.raises(clients.RemoteGpuAmbiguous):
        client.call(KEYWORDS, {}, b"image")


def test_recovered_runner_rechecks_detector_identity_before_resuming():
    events, now = [], [0]
    remote, local = Backend("remote", events), Backend("local", events)
    local.detector_info = remote.detector_info
    route = chain([remote, local], now=lambda: now[0])
    route.detector_info()
    route.call(DETECT, {}, b"image")
    remote.error = unavailable()
    route.call(DETECT, {}, b"image")
    remote.error = None
    remote.detector_info = lambda: {"weights_sha256": "changed", "version": "detector-v1", "load_error": None}
    now[0] = 31
    with pytest.raises(RemoteGpuError, match="weights"):
        route.call(DETECT, {}, b"image")
