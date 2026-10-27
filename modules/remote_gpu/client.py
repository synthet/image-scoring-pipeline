"""Host-side HTTP client for the GPU runner."""

from __future__ import annotations

import json
import logging
import math
import random
import threading
import time
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

from modules.remote_gpu.contract import (
    API_VERSION,
    DETECT,
    DETECTOR_INFO,
    ENDPOINT_PHASE,
    FINGERPRINT_HEADER,
    HEALTH,
    PHASE_CONFIG_SECTIONS,
    RemoteGpuAmbiguous,
    RemoteGpuError,
    RemoteGpuUnavailable,
    dumps,
    phase_fingerprint,
    section_hashes,
)
from modules.remote_gpu.resilience import RetryPolicy, positive_seconds, retry_after_seconds

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5.0
HEALTH_TIMEOUT_SECONDS = 5.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 600.0


def _config() -> dict[str, Any]:
    from modules import config

    return config.load_config() or {}


#: Set inside the runner process: it shares the host's config.json, and must
#: never route a model back to a runner.
_serving = False
_execution = threading.local()


@contextmanager
def local_inference():
    """Prevent embedded model factories from recursively routing back to HTTP."""
    previous = getattr(_execution, "local", False)
    _execution.local = True
    try:
        yield
    finally:
        _execution.local = previous


def mark_serving() -> None:
    global _serving
    _serving = True


def phase_is_remote(phase_code: str) -> bool:
    """True when ``gpu_runner`` routes ``phase_code`` to the remote runner.

    Config errors raise instead of quietly running the phase on the local GPU.
    """
    if _serving or getattr(_execution, "local", False):
        return False
    runner = _config().get("gpu_runner") or {}
    if not runner.get("enabled"):
        return False
    mode = (runner.get("phases") or {}).get(phase_code, "local")
    if mode not in ("local", "remote"):
        raise RemoteGpuError(f"gpu_runner.phases.{phase_code} must be 'local' or 'remote', got {mode!r}")
    return mode == "remote"


def current_mode_or_none(model, phase_code: str, base_cls: type = object):
    """``model``, or None when it was built for the other ``gpu_runner`` mode of ``phase_code``.

    Runners cache their models for the life of the process; this lets them notice a
    config switch between local and remote and rebuild. Objects that are not
    ``base_cls`` (injected test engines, mocks) are returned untouched.
    """
    if model is None or not isinstance(model, base_cls):
        return model
    built_remote = getattr(type(model), "runs_remotely", False) is True
    return model if built_remote == phase_is_remote(phase_code) else None


def _token() -> str:
    from modules import config

    secret = config.get_secret("gpu_runner")
    if isinstance(secret, dict):
        return str(secret.get("token") or "")
    return str(secret or "")


class GpuRunnerClient:
    """One runner endpoint. ``http`` is any ``httpx.Client``-compatible object (tests pass a TestClient)."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        http=None,
        config_loader=None,
        retry: RetryPolicy | None = None,
        timeout_options=None,
        clock=None,
        sleep=None,
        random_fn=None,
    ) -> None:
        import httpx

        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        options = timeout_options or {}
        self._health_timeout = positive_seconds(options.get("health_seconds", HEALTH_TIMEOUT_SECONDS), "timeouts.health_seconds")
        self._timeout = httpx.Timeout(
            read=positive_seconds(timeout, "request_timeout_seconds"),
            connect=positive_seconds(options.get("connect_seconds", CONNECT_TIMEOUT_SECONDS), "timeouts.connect_seconds"),
            write=positive_seconds(options.get("write_seconds", 60), "timeouts.write_seconds"),
            pool=positive_seconds(options.get("pool_seconds", 5), "timeouts.pool_seconds"),
        )
        connections = options.get("max_connections", 4)
        if type(connections) is not int or connections <= 0:
            raise RemoteGpuError("gpu_runner.timeouts.max_connections must be a positive integer")
        self._http = http if http is not None else httpx.Client(
            limits=httpx.Limits(max_connections=connections, max_keepalive_connections=connections),
        )
        self._config_loader = config_loader or _config
        self._retry = retry or RetryPolicy()
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._random = random_fn or random.random

    # -- calls -----------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._send("GET", HEALTH, timeout=self._health_timeout)

    def detector_info(self) -> dict[str, Any]:
        """Weights identity of the runner's bird detector (loads it on first call)."""
        return self._send(
            "GET", DETECTOR_INFO,
            headers={FINGERPRINT_HEADER: phase_fingerprint(self._config_loader(), "localization")},
        )

    def call(
        self,
        endpoint: str,
        meta: dict[str, Any],
        data: bytes | None = None,
        *,
        filename: str = "input.bin",
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Run one model method on the runner and return its JSON result."""
        headers = {FINGERPRINT_HEADER: phase_fingerprint(self._config_loader(), ENDPOINT_PHASE[endpoint])}
        files = {"file": (filename, data, content_type)} if data is not None else None
        return self._send("POST", endpoint, headers=headers, data={"meta": dumps(meta)}, files=files)

    def check_phase(self, phase: str) -> dict[str, Any]:
        """Fail fast before a batch: the runner must answer and share this phase's config.

        Raises RemoteGpuError naming the config sections that differ.
        """
        status = self.health()
        if status.get("api_version") != API_VERSION:
            raise RemoteGpuError(f"GPU runner API version {status.get('api_version')!r} differs from host version {API_VERSION}")
        if phase in (status.get("restart_required") or []):
            raise RemoteGpuError(f"GPU runner config changed for {phase}; restart the runner")
        theirs = (status.get("phase_sections") or {}).get(phase)
        if theirs is None:
            raise RemoteGpuError(f"GPU runner at {self.base_url} does not serve phase {phase}")
        ours = section_hashes(self._config_loader(), phase)
        differing = sorted(name for name in PHASE_CONFIG_SECTIONS[phase] if ours.get(name) != theirs.get(name))
        if differing:
            raise RemoteGpuError(
                f"GPU runner config differs from this host for phase {phase}: "
                f"{', '.join(differing)}. Copy this host's config.json to the runner and restart it."
            )
        return status

    # -- transport ---------------------------------------------------------

    def _pause_retry(self, attempt, deadline, retry_after=0):
        if attempt >= self._retry.max_retries:
            return False
        delay = self._retry.delay(attempt, self._random, retry_after)
        if delay >= deadline - self._clock():
            return False
        logger.info("gpu_runner: safe retry %s/%s on %s in %.2fs", attempt + 1, self._retry.max_retries,
                    _backend_label(self), delay)
        self._sleep(delay)
        return True

    def _send(self, method: str, path: str, *, headers=None, data=None, files=None, timeout=None) -> dict[str, Any]:
        import httpx

        url = f"{self.base_url}{path}"
        all_headers = {**self._headers, **(headers or {})}
        base_timeout = self._timeout if timeout is None else httpx.Timeout(
            read=timeout, connect=min(self._timeout.connect, timeout),
            write=min(self._timeout.write, timeout), pool=min(self._timeout.pool, timeout),
        )
        attempt = 0
        deadline = self._clock() + self._retry.budget_seconds
        while True:
            remaining = deadline - self._clock()
            if attempt and remaining <= 0:
                raise RemoteGpuUnavailable(f"GPU runner safe retry budget exhausted for {path}")
            req_timeout = base_timeout if not attempt else httpx.Timeout(
                read=base_timeout.read if method == "POST" else min(base_timeout.read, remaining),
                connect=min(base_timeout.connect, remaining), write=base_timeout.write,
                pool=min(base_timeout.pool, remaining),
            )
            try:
                response = self._http.request(
                    method, url, headers=all_headers, data=data, files=files, timeout=req_timeout,
                )
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                # Nothing reached the runner, so re-sending cannot duplicate work.
                if not self._pause_retry(attempt, deadline):
                    raise RemoteGpuUnavailable(f"GPU runner unreachable or at capacity at {_backend_label(self)}: {type(exc).__name__}") from exc
                attempt += 1
                continue
            except httpx.TimeoutException as exc:
                if method == "GET":
                    raise RemoteGpuUnavailable(f"GPU runner readiness timed out on {path}") from exc
                # The request was delivered; a retry would run the inference again.
                raise RemoteGpuAmbiguous(f"GPU runner timed out on {path}: {exc}") from exc
            except httpx.HTTPError as exc:
                if method == "GET":
                    raise RemoteGpuUnavailable(f"GPU runner readiness request to {path} failed") from exc
                raise RemoteGpuAmbiguous(f"GPU runner request to {path} failed: {exc}") from exc

            try:
                if response.status_code in (429, 503):
                    retry_after = retry_after_seconds(response.headers.get("Retry-After"))
                    response.close()
                    if self._pause_retry(attempt, deadline, retry_after):
                        attempt += 1
                        continue
                    raise RemoteGpuUnavailable(f"GPU runner {path} returned HTTP {response.status_code}: admission refused",
                                               retry_after=retry_after)
                if response.status_code == 500:
                    try:
                        error = response.json()
                    except ValueError:
                        error = None
                    # Worker error envelope confirms inference ended without a result.
                    if isinstance(error, dict) and error.get("error"):
                        raise RemoteGpuUnavailable(f"GPU runner {path} returned a completed worker failure (HTTP 500)")
                if response.status_code in (502, 504):
                    error_cls = RemoteGpuUnavailable if method == "GET" else RemoteGpuAmbiguous
                    raise error_cls(f"GPU runner {path} returned HTTP {response.status_code}")
                return _decode(response, path)
            finally:
                response.close()


def _decode(response, path: str) -> dict[str, Any]:
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        body = None
    if response.status_code == 200 and isinstance(body, dict):
        return body
    detail = (body.get("error") or body.get("detail")) if isinstance(body, dict) else (response.text or "")[:300]
    raise RemoteGpuError(f"GPU runner {path} returned HTTP {response.status_code}: {detail}")


_client_lock = threading.Lock()
_client: GpuRunnerClient | FallbackGpuClient | None = None
_client_key: tuple | None = None
_embedded_client: EmbeddedGpuClient | None = None


class EmbeddedGpuClient:
    """Execute the same worker methods in this process, with lazy local models."""

    base_url = "embedded"

    def __init__(self, *, runtime_factory=None, config_loader=None, pool_timeout=5.0):
        self._config_loader = config_loader or _config
        self._runtime_factory = runtime_factory
        self._runtime = None
        self._sections = None
        self._lock = threading.RLock()
        self._pool_timeout = positive_seconds(pool_timeout, "timeouts.pool_seconds")

    @contextmanager
    def _admit(self):
        if not self._lock.acquire(timeout=self._pool_timeout):
            raise RemoteGpuUnavailable("GPU runner embedded busy: queue wait timed out")
        try:
            yield
        finally:
            self._lock.release()

    def check_phase(self, phase):
        with self._admit():
            current = section_hashes(self._config_loader(), phase)
            if self._sections is not None and self._sections[phase] != current:
                raise RemoteGpuError(f"Embedded GPU runner config changed for {phase}; restart the host")
            return {"ok": True, "backend": self.base_url}

    def call(self, endpoint, meta, data=None, *, filename="input.bin", content_type=None):
        with self._admit(), local_inference():
            self.check_phase(ENDPOINT_PHASE[endpoint])
            from pydantic import ValidationError

            from modules.remote_gpu.server import validate_params

            try:
                params = validate_params(endpoint, json.loads(dumps(meta)))
            except (ValidationError, ValueError, TypeError) as exc:
                raise RemoteGpuError(f"GPU runner embedded invalid metadata for {endpoint}") from exc
            if self._runtime is None:
                from modules.remote_gpu.runtime import InferenceRuntime

                self._sections = {phase: section_hashes(self._config_loader(), phase) for phase in PHASE_CONFIG_SECTIONS}
                self._runtime = (self._runtime_factory or InferenceRuntime)()
            # Match the HTTP contract, including numpy -> JSON conversion.
            try:
                return json.loads(dumps(self._runtime.execute(endpoint, params, data, filename=filename)))
            except RemoteGpuError:
                raise
            except Exception as exc:
                raise RemoteGpuError(f"GPU runner embedded {endpoint} failed: {type(exc).__name__}: {exc}") from exc

    def detector_info(self):
        return self.call(DETECTOR_INFO, {})


def _backend_label(backend):
    """Never log userinfo, query strings, or fragments from a configured URL."""
    if backend.base_url == "embedded":
        return "embedded"
    url = urlsplit(backend.base_url)
    return f"{url.scheme}://{url.hostname}:{url.port or (443 if url.scheme == 'https' else 80)}"


class FallbackGpuClient:
    """Ordered availability failover shared by all phase proxies."""

    def __init__(self, backends, *, cooldown=30.0, max_cooldown=None, clock=None, random_fn=None):
        if not backends or not math.isfinite(cooldown) or cooldown < 0:
            raise RemoteGpuError("GPU runner fallback requires backends and a finite nonnegative cooldown")
        self.backends = tuple(backends)
        self._cooldown = cooldown
        self._max_cooldown = max(300.0, cooldown) if max_cooldown is None else max_cooldown
        if not math.isfinite(self._max_cooldown) or self._max_cooldown < cooldown:
            raise RemoteGpuError("GPU runner fallback maximum cooldown must be finite and at least cooldown_seconds")
        self._clock = clock or time.monotonic
        self._random = random_fn or random.random
        self._unavailable_until = {}
        self._failures = {}
        self._probing = set()
        self._ready = set()
        self._active = {}
        self._detector_identity = None
        self._verified_detectors = set()
        self._lock = threading.RLock()

    def _open_circuit(self, index, retry_after=0):
        with self._lock:
            failures = min(31, self._failures.get(index, 0) + 1)
            self._failures[index] = failures
            ceiling = min(self._max_cooldown, self._cooldown * 2 ** (failures - 1))
            delay = max(ceiling * (0.5 + 0.5 * self._random()), retry_after)
            self._unavailable_until[index] = self._clock() + delay
            self._ready = {entry for entry in self._ready if entry[0] != index}
            # A recovered worker might have restarted with new weights.
            self._verified_detectors.discard(index)
            return delay

    def _execute(self, phase, method, *args, **kwargs):
        for index, backend in enumerate(self.backends):
            with self._lock:
                probing = index in self._unavailable_until
                if probing:
                    if self._unavailable_until[index] > self._clock() or index in self._probing:
                        continue
                    # Half-open: one caller probes; other callers keep using fallback.
                    self._probing.add(index)
                ready = (index, phase) in self._ready
            try:
                if not ready:
                    status = backend.check_phase(phase)
                    with self._lock:
                        self._ready.add((index, phase))
                if method == "call" and args[0] == DETECT:
                    self._verify_detector(index, backend)
                result = status if method == "check_phase" and not ready else getattr(backend, method)(*args, **kwargs)
            except RemoteGpuUnavailable as exc:
                delay = self._open_circuit(index, exc.retry_after)
                logger.warning("gpu_runner: %s unavailable; trying next backend (cooldown %.0fs)",
                               _backend_label(backend), delay)
                continue
            except RemoteGpuAmbiguous:
                self._open_circuit(index)
                logger.warning("gpu_runner: %s response is ambiguous; input not replayed, backend in cooldown",
                               _backend_label(backend))
                raise
            finally:
                if probing:
                    with self._lock:
                        self._probing.discard(index)
            with self._lock:
                self._failures.pop(index, None)
                self._unavailable_until.pop(index, None)
                if self._active.get(phase) != index:
                    log = logger.warning if index else logger.info
                    log("gpu_runner: phase %s uses %s%s", phase, _backend_label(backend),
                        " (fallback)" if index else "")
                    self._active[phase] = index
            return result
        raise RemoteGpuUnavailable(f"GPU runner: all backends unavailable for phase {phase}")

    def _verify_detector(self, index, backend):
        with self._lock:
            if self._detector_identity is None or index in self._verified_detectors:
                return
            info = backend.detector_info()
            if (info.get("weights_sha256"), info.get("version")) != self._detector_identity or info.get("load_error"):
                raise RemoteGpuError("GPU runner fallback detector weights differ from the active localization context")
            self._verified_detectors.add(index)

    def check_phase(self, phase):
        return self._execute(phase, "check_phase", phase)

    def call(self, endpoint, *args, **kwargs):
        return self._execute(ENDPOINT_PHASE[endpoint], "call", endpoint, *args, **kwargs)

    def detector_info(self):
        info = self._execute("localization", "detector_info")
        with self._lock:
            identity = (info.get("weights_sha256"), info.get("version"))
            if self._detector_identity is not None and identity != self._detector_identity:
                raise RemoteGpuError("GPU runner fallback detector weights differ from the active localization context")
            self._detector_identity = identity
        return info


def get_client() -> GpuRunnerClient | FallbackGpuClient:
    """Process-wide route, rebuilt when endpoint, credentials, timeout or fallback settings change."""
    global _client, _client_key, _embedded_client
    runner = _config().get("gpu_runner") or {}
    url = str(runner.get("url") or "").strip()
    if not url:
        raise RemoteGpuError("gpu_runner.url is not set")
    timeout = positive_seconds(runner.get("request_timeout_seconds", DEFAULT_REQUEST_TIMEOUT_SECONDS), "request_timeout_seconds")
    fallback = runner.get("fallback") or {}
    timeout_options = runner.get("timeouts") or {}
    retry_options = runner.get("retry") or {}
    try:
        retry = RetryPolicy(**retry_options)
    except TypeError as exc:
        raise RemoteGpuError("gpu_runner.retry contains invalid policy settings") from exc
    key = (url, _token(), timeout, dumps(fallback), dumps(timeout_options), dumps(retry_options))
    with _client_lock:
        if _client is None or _client_key != key:
            _client = GpuRunnerClient(url, key[1], timeout=timeout, timeout_options=timeout_options, retry=retry)
            if fallback.get("enabled", True):
                backends = [_client]
                local_url = str(fallback.get("local_url", "http://127.0.0.1:7870")).strip().rstrip("/")
                if local_url and local_url != url.rstrip("/"):
                    backends.append(GpuRunnerClient(local_url, key[1], timeout=timeout, timeout_options=timeout_options, retry=retry))
                # Off by default: embedded models live in this (host) process. Hosts
                # without a runner container opt in with fallback.embedded = true.
                if fallback.get("embedded", False):
                    # URL/token changes must not create another set of local GPU models.
                    if _embedded_client is None:
                        _embedded_client = EmbeddedGpuClient(pool_timeout=timeout_options.get("pool_seconds", 5))
                    backends.append(_embedded_client)
                cooldown = float(fallback.get("cooldown_seconds", 30))
                _client = FallbackGpuClient(backends, cooldown=cooldown,
                                            max_cooldown=float(fallback.get("max_cooldown_seconds", max(300, cooldown))))
            _client_key = key
        return _client


def ready_client(phase: str) -> GpuRunnerClient | FallbackGpuClient:
    """The configured route after a compatible backend passed readiness for ``phase``."""
    client = get_client()
    client.check_phase(phase)
    return client
