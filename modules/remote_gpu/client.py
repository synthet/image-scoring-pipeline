"""Host-side HTTP client for the GPU runner."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from modules.remote_gpu.contract import (
    DETECTOR_INFO,
    ENDPOINT_PHASE,
    FINGERPRINT_HEADER,
    HEALTH,
    PHASE_CONFIG_SECTIONS,
    RemoteGpuError,
    dumps,
    phase_fingerprint,
    section_hashes,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10.0
HEALTH_TIMEOUT_SECONDS = 60.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 600.0
#: Waits before re-sending a request the runner refused with 503 (busy).
BUSY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def _config() -> dict[str, Any]:
    from modules import config

    return config.load_config() or {}


#: Set inside the runner process: it shares the host's config.json, and must
#: never route a model back to a runner.
_serving = False


def mark_serving() -> None:
    global _serving
    _serving = True


def phase_is_remote(phase_code: str) -> bool:
    """True when ``gpu_runner`` routes ``phase_code`` to the remote runner.

    Config errors raise instead of quietly running the phase on the local GPU.
    """
    if _serving:
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
    ) -> None:
        import httpx

        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS)
        self._http = http if http is not None else httpx.Client()
        self._config_loader = config_loader or _config

    # -- calls -----------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._send("GET", HEALTH, timeout=HEALTH_TIMEOUT_SECONDS)

    def detector_info(self) -> dict[str, Any]:
        """Weights identity of the runner's bird detector (loads it on first call)."""
        return self._send("GET", DETECTOR_INFO, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS)

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

    def _send(self, method: str, path: str, *, headers=None, data=None, files=None, timeout=None) -> dict[str, Any]:
        import httpx

        url = f"{self.base_url}{path}"
        all_headers = {**self._headers, **(headers or {})}
        req_timeout = self._timeout if timeout is None else httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS)
        connect_retried = False
        busy_waits = list(BUSY_BACKOFF_SECONDS)
        while True:
            try:
                response = self._http.request(
                    method, url, headers=all_headers, data=data, files=files, timeout=req_timeout,
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Nothing reached the runner, so re-sending cannot duplicate work.
                if connect_retried:
                    raise RemoteGpuError(f"GPU runner unreachable at {self.base_url}: {exc}") from exc
                connect_retried = True
                logger.warning("gpu_runner: connect to %s failed (%s); retrying once", self.base_url, exc)
                time.sleep(1.0)
                continue
            except httpx.TimeoutException as exc:
                # The request was delivered; a retry would run the inference again.
                raise RemoteGpuError(f"GPU runner timed out on {path}: {exc}") from exc
            except httpx.HTTPError as exc:
                raise RemoteGpuError(f"GPU runner request to {path} failed: {exc}") from exc

            if response.status_code == 503 and busy_waits:
                wait = busy_waits.pop(0)
                logger.info("gpu_runner: busy on %s; retrying in %.0fs", path, wait)
                time.sleep(wait)
                continue
            return _decode(response, path)


def _decode(response, path: str) -> dict[str, Any]:
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        body = None
    if response.status_code == 200 and isinstance(body, dict):
        return body
    detail = body.get("error") if isinstance(body, dict) else (response.text or "")[:300]
    raise RemoteGpuError(f"GPU runner {path} returned HTTP {response.status_code}: {detail}")


_client_lock = threading.Lock()
_client: GpuRunnerClient | None = None
_client_key: tuple | None = None


def get_client() -> GpuRunnerClient:
    """Process-wide client for the configured runner (rebuilt when url, token or timeout change)."""
    global _client, _client_key
    runner = _config().get("gpu_runner") or {}
    url = str(runner.get("url") or "").strip()
    if not url:
        raise RemoteGpuError("gpu_runner.url is not set")
    timeout = float(runner.get("request_timeout_seconds") or DEFAULT_REQUEST_TIMEOUT_SECONDS)
    key = (url, _token(), timeout)
    with _client_lock:
        if _client is None or _client_key != key:
            _client = GpuRunnerClient(url, key[1], timeout=timeout)
            _client_key = key
        return _client


def ready_client(phase: str) -> GpuRunnerClient:
    """The configured client, after :meth:`GpuRunnerClient.check_phase` passed for ``phase``."""
    client = get_client()
    client.check_phase(phase)
    return client
