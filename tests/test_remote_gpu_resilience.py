"""Retry and circuit policies are bounded and safe under concurrent outages."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from modules.remote_gpu import client as clients
from modules.remote_gpu.contract import KEYWORDS, RemoteGpuError
from tests.test_remote_gpu_fallback import Backend, unavailable


def scripted_http(script):
    calls = []
    items = iter(script)

    def request(*args, **kwargs):
        calls.append(kwargs)
        item = next(items)
        if isinstance(item, Exception):
            raise item
        return item

    return SimpleNamespace(request=request, calls=calls)


def test_safe_connection_retries_use_bounded_exponential_jitter():
    waits = []
    http = scripted_http([httpx.ConnectError("offline")] * 3 + [httpx.Response(200, json={"ok": True})])
    client = clients.GpuRunnerClient("http://r", "", http=http, sleep=waits.append, random_fn=lambda: 0.5)
    assert client.call(KEYWORDS, {}) == {"ok": True}
    assert waits == [0.5, 1.0, 2.0]
    assert len(http.calls) == 4


def test_retry_budget_prevents_another_attempt_or_excessive_sleep():
    from modules.remote_gpu.resilience import RetryPolicy

    waits = []
    http = scripted_http([httpx.ConnectError("offline")])
    client = clients.GpuRunnerClient("http://r", "", http=http, retry=RetryPolicy(base_delay_seconds=2, budget_seconds=1),
                                   sleep=waits.append, random_fn=lambda: 1, clock=lambda: 0)
    with pytest.raises(clients.RemoteGpuUnavailable):
        client.call(KEYWORDS, {})
    assert len(http.calls) == 1
    assert waits == []


@pytest.mark.parametrize("status", [429, 503])
def test_admission_refusal_honors_retry_after(status):
    waits = []
    http = scripted_http([httpx.Response(status, headers={"Retry-After": "2"}), httpx.Response(200, json={"ok": True})])
    client = clients.GpuRunnerClient("http://r", "", http=http, sleep=waits.append, random_fn=lambda: 0)
    assert client.call(KEYWORDS, {})["ok"]
    assert waits == [2.0]


def test_long_retry_after_falls_back_without_retrying_before_server_deadline():
    waits = []
    http = scripted_http([httpx.Response(503, headers={"Retry-After": "120"})])
    client = clients.GpuRunnerClient("http://r", "", http=http, sleep=waits.append)
    with pytest.raises(clients.RemoteGpuUnavailable) as exc:
        client.call(KEYWORDS, {})
    assert exc.value.retry_after == 120
    assert len(http.calls) == 1
    assert waits == []


def test_retry_after_supports_http_date_and_ignores_invalid_values():
    from modules.remote_gpu.resilience import retry_after_seconds

    assert retry_after_seconds("Thu, 01 Jan 1970 00:00:12 GMT", now=10) == 2
    assert retry_after_seconds("invalid", now=10) == 0
    assert retry_after_seconds("-1", now=10) == 0


def test_each_io_timeout_is_explicit_and_health_checks_are_short():
    http = scripted_http([httpx.Response(200, json={"ok": True}), httpx.Response(200, json={"ok": True})])
    client = clients.GpuRunnerClient("http://r", "", http=http, timeout=600,
                                   timeout_options={"connect_seconds": 3, "write_seconds": 15, "pool_seconds": 2, "health_seconds": 4})
    client.call(KEYWORDS, {})
    timeout = http.calls[0]["timeout"]
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (3, 600, 15, 2)
    client.health()
    assert http.calls[1]["timeout"].read == 4


def test_pool_exhaustion_can_retry_before_a_request_is_submitted():
    waits = []
    http = scripted_http([httpx.PoolTimeout("no connection"), httpx.Response(200, json={"ok": True})])
    client = clients.GpuRunnerClient("http://r", "", http=http, sleep=waits.append, random_fn=lambda: 1)
    assert client.call(KEYWORDS, {})["ok"]
    assert waits == [1]


@pytest.mark.parametrize("failure", [httpx.WriteTimeout("partial upload"), httpx.ReadTimeout("computing"), httpx.ReadError("disconnected")])
def test_submitted_failures_never_retry(failure):
    waits = []
    http = scripted_http([failure])
    client = clients.GpuRunnerClient("http://r", "", http=http, sleep=waits.append)
    with pytest.raises(clients.RemoteGpuAmbiguous):
        client.call(KEYWORDS, {})
    assert len(http.calls) == 1
    assert waits == []


def test_circuit_cooldown_grows_exponentially_and_is_capped():
    events, now = [], [0]
    route = clients.FallbackGpuClient([Backend("remote", events, unavailable()), Backend("local", events)],
                                     cooldown=30, max_cooldown=120, random_fn=lambda: 1, clock=lambda: now[0])
    route.call(KEYWORDS, {})
    now[0] = 31
    route.call(KEYWORDS, {})
    now[0] = 80
    route.call(KEYWORDS, {})
    assert len([e for e in events if e[0] == "remote"]) == 2
    now[0] = 92
    route.call(KEYWORDS, {})
    now[0] = 200
    route.call(KEYWORDS, {})
    assert len([e for e in events if e[0] == "remote"]) == 3
    now[0] = 213
    route.call(KEYWORDS, {})
    now[0] = 334  # capped at 120 rather than increasing to 240
    route.call(KEYWORDS, {})
    assert len([e for e in events if e[0] == "remote"]) == 5


def test_only_one_recovery_probe_runs_while_other_callers_use_fallback():
    import concurrent.futures
    import threading

    events, now = [], [0]
    entered, release = threading.Event(), threading.Event()
    remote = Backend("remote", events, unavailable())
    route = clients.FallbackGpuClient([remote, Backend("local", events)], clock=lambda: now[0], random_fn=lambda: 1)
    route.call(KEYWORDS, {})
    remote.error = None
    probes = []

    def probe(phase):
        probes.append(phase)
        entered.set()
        assert release.wait(5)
        return {"ok": True}

    remote.check_phase = probe
    now[0] = 31
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(route.call, KEYWORDS, {})
        try:
            assert entered.wait(5)
            assert route.call(KEYWORDS, {}) == {"backend": "local"}
            assert probes == ["keywords"]
        finally:
            release.set()
        assert future.result(timeout=5) == {"backend": "remote"}


@pytest.mark.parametrize("options", [{"max_retries": -1}, {"max_retries": 1000}, {"budget_seconds": float("nan")},
                                    {"base_delay_seconds": 0}, {"max_delay_seconds": -1}])
def test_invalid_retry_settings_fail_fast(options):
    from modules.remote_gpu.resilience import RetryPolicy

    with pytest.raises(RemoteGpuError):
        RetryPolicy(**options)


def test_busy_embedded_runner_has_a_bounded_queue_wait():
    import concurrent.futures
    import threading

    entered, release = threading.Event(), threading.Event()

    class Runtime:
        def execute(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            return {"ok": True}

    client = clients.EmbeddedGpuClient(runtime_factory=Runtime, config_loader=lambda: {}, pool_timeout=0.01)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.call, KEYWORDS, {}, b"image")
        try:
            assert entered.wait(5)
            with pytest.raises(clients.RemoteGpuUnavailable, match="embedded.*busy"):
                client.call(KEYWORDS, {}, b"another image")
        finally:
            release.set()
        assert future.result(timeout=5)["ok"]


def test_server_retry_after_also_delays_circuit_recovery():
    events, now = [], [0]
    failure = clients.RemoteGpuUnavailable("rate limited", retry_after=120)
    route = clients.FallbackGpuClient([Backend("remote", events, failure), Backend("local", events)],
                                     cooldown=30, clock=lambda: now[0], random_fn=lambda: 1)
    route.call(KEYWORDS, {})
    now[0] = 119
    route.call(KEYWORDS, {})
    assert len([e for e in events if e[0] == "remote"]) == 1
    now[0] = 121
    route.call(KEYWORDS, {})
    assert len([e for e in events if e[0] == "remote"]) == 2
