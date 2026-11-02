"""Call FastAPI REST operations on the running WebUI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from modules.mcp.actions.errors import McpActionError

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_RESPONSE_BYTES = 200_000


class WebuiUnavailableError(McpActionError):
    code = "webui_unavailable"


class HttpError(McpActionError):
    code = "http_error"


def api_base_url() -> str:
    """VEXLUM_API_URL → IMGSCORE_WEBUI_MCP_SSE_URL origin → webui.lock port → 127.0.0.1:7860."""
    explicit = (os.environ.get("VEXLUM_API_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    sse = (os.environ.get("IMGSCORE_WEBUI_MCP_SSE_URL") or "").strip()
    if sse:
        parsed = urlparse(sse)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    lock = ROOT / "webui.lock"
    try:
        port = int(json.loads(lock.read_text(encoding="utf-8")).get("port") or 7860)
        return f"http://127.0.0.1:{port}"
    except Exception:  # noqa: BLE001
        return "http://127.0.0.1:7860"


def _api_key() -> str | None:
    env = (os.environ.get("API_KEY") or "").strip()
    if env:
        return env
    try:
        from modules import config

        val = str(config.get_config_value("api.key", "") or "").strip()
        return val or None
    except Exception:  # noqa: BLE001
        return None


def _max_bytes() -> int:
    try:
        return int(os.environ.get("VEXLUM_MAX_RESPONSE_BYTES") or DEFAULT_MAX_RESPONSE_BYTES)
    except ValueError:
        return DEFAULT_MAX_RESPONSE_BYTES


def build_request(record: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    ex = record["executor"]
    path = str(ex["path"])
    for name in ex.get("path_params") or []:
        if name not in args:
            raise McpActionError(f"missing path parameter {name}", details={"path": path})
        path = path.replace("{" + name + "}", quote(str(args[name]), safe=""))
    query = {k: args[k] for k in (ex.get("query_params") or []) if k in args and args[k] is not None}
    headers = {k: str(args[k]) for k in (ex.get("header_params") or []) if k in args and args[k] is not None}
    req: dict[str, Any] = {
        "method": ex["method"],
        "url": api_base_url() + path,
        "params": query,
        "headers": headers,
    }
    if ex.get("has_body") and "body" in args:
        req["json"] = args["body"]
    return req


def _truncate(payload: Any) -> tuple[Any, bool, int]:
    raw = json.dumps(payload, default=str)
    size = len(raw.encode("utf-8"))
    limit = _max_bytes()
    if size <= limit:
        return payload, False, size
    return {"preview": raw[:limit]}, True, size


def run_rest(record: dict[str, Any], args: dict[str, Any], *, client: Any = None) -> dict[str, Any]:
    import httpx

    req = build_request(record, args)
    headers = dict(req.pop("headers"))
    key = _api_key()
    if key:
        headers["X-API-Key"] = key
    owns_client = client is None
    http = client or httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
    try:
        resp = http.request(req["method"], req["url"], params=req["params"], json=req.get("json"), headers=headers)
    except httpx.TransportError as exc:
        raise WebuiUnavailableError(
            f"WebUI API unreachable at {api_base_url()}. Start it (docker compose up -d db webui) "
            "or set VEXLUM_API_URL.",
            details={"error": str(exc), "url": req["url"]},
        ) from exc
    finally:
        if owns_client:
            http.close()

    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            body: Any = resp.json()
        except ValueError:
            body = resp.text
    elif ctype.startswith("text/") or not resp.content:
        body = resp.text
    else:
        body = f"<binary content-type={ctype} len={len(resp.content)}>"

    if resp.status_code >= 400:
        snippet, _trunc, _size = _truncate(body)
        raise HttpError(
            f"{req['method']} {record['executor']['path']} -> HTTP {resp.status_code}",
            details={"http_status": resp.status_code, "body": snippet},
        )

    data, truncated, size = _truncate(body)
    return {"http_status": resp.status_code, "body": data, "truncated": truncated, "size_bytes": size}


def describe_request(record: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Dry-run view: the request that would be sent (no API key)."""
    req = build_request(record, args)
    return {"would_request": req}
