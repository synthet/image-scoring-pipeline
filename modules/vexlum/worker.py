"""JSONL worker for the vexlum TS host. One ``{"id", "tool", "args"}`` request per stdin line."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def json_default(obj: Any) -> Any:
    """Make common DB/driver types JSON-serializable."""
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (UUID, Path)):
        return str(obj)
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return bytes(obj).decode("utf-8", errors="replace")
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def dumps(payload: Any, **kwargs: Any) -> str:
    return json.dumps(payload, default=json_default, **kwargs)


def handle_line(raw: str, invoke: Any = None) -> dict[str, Any]:
    if invoke is None:
        from modules.vexlum.service import invoke
    try:
        req = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"status": "error", "code": "invalid_json", "message": str(e)}
    req_id = req.get("id")
    tool = str(req.get("tool") or "").strip()
    try:
        if not tool:
            result: dict[str, Any] = {"status": "error", "code": "missing_tool", "message": "tool is required"}
        else:
            result = invoke(tool, req.get("args") or {})
            if not isinstance(result, dict):
                result = {"status": "success", "data": result}
    except Exception as e:  # noqa: BLE001 - keep the worker alive
        logger.exception("vexlum tool %s failed", tool)
        result = {"status": "error", "code": "handler_error", "message": str(e)}
    if req_id is not None:
        result = {**result, "_request_id": req_id}
    return result


def _warm() -> None:
    """Build the catalog, then import the tool stack, so first calls answer fast."""
    try:
        from modules.vexlum import catalog

        catalog.get_catalog()
        import modules.mcp_server  # noqa: F401 - heavy import done off the request path
    except Exception:  # noqa: BLE001
        logger.debug("vexlum warm-up failed", exc_info=True)


def main() -> int:
    import os
    import threading

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    if (os.environ.get("VEXLUM_WARM") or "1").strip() != "0":
        threading.Thread(target=_warm, name="vexlum-warm", daemon=True).start()
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "__shutdown__":
            break
        response = handle_line(stripped)
        try:
            payload = dumps(response)
        except Exception as e:  # noqa: BLE001
            logger.exception("failed to serialize vexlum response")
            fallback: dict[str, Any] = {"status": "error", "code": "serialization_error", "message": str(e)}
            if response.get("_request_id") is not None:
                fallback["_request_id"] = response["_request_id"]
            payload = json.dumps(fallback)
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()
    return 0
