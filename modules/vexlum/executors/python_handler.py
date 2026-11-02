"""Run Python MCP tools: curated registry actions and legacy ``modules.mcp_server`` functions."""

from __future__ import annotations

import importlib
from typing import Any

from modules.mcp.actions.errors import McpActionError


def _sanitize(data: Any) -> Any:
    try:
        from modules.mcp_server import _sanitize_for_mcp

        return _sanitize_for_mcp(data)
    except Exception:  # noqa: BLE001
        return data


def run_registry(record: dict[str, Any], args: dict[str, Any], *, request_id: str) -> Any:
    """Curated registry actions keep their existing handler wiring (run_doctor, debug bundle, …).

    Vexlum policy has already authorized the call, so ``confirmed=True`` only satisfies the
    legacy dispatcher's own confirmation check.
    """
    from modules.mcp.actions.dispatch import dispatch_action

    out = dispatch_action(record["executor"]["action_id"], args, confirmed=True, request_id=request_id)
    if out.get("status") != "success":
        err = McpActionError(str(out.get("message") or "action failed"), details=out.get("details") or {})
        err.code = str(out.get("code") or "action_error")
        raise err
    data = out.get("data")
    if out.get("review_reminder"):
        data = {"result": data, "review_reminder": out["review_reminder"]}
    return data


def run_python(record: dict[str, Any], args: dict[str, Any], *, dry_run: bool = False) -> Any:
    ex = record["executor"]
    mod = importlib.import_module(str(ex["module"]))
    fn = getattr(mod, str(ex["function"]), None)
    if fn is None or not callable(fn):
        raise McpActionError(f"handler not callable: {ex['module']}.{ex['function']}")
    call_args = dict(args)
    if record.get("native_dry_run"):
        call_args["dry_run"] = bool(dry_run)
    result = fn(**call_args)
    if isinstance(result, dict) and set(result.keys()) == {"error"}:
        raise McpActionError(str(result["error"]), details={"handler": f"{ex['module']}.{ex['function']}"})
    return _sanitize(result)
