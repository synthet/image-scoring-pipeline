"""search -> resolve -> execute over the unified vexlum catalog."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from modules.mcp.actions.errors import McpActionError, UnknownActionError, ValidationError
from modules.mcp.actions.schema import schema_arg_lists, validate_arguments
from modules.vexlum import catalog, policy

logger = logging.getLogger(__name__)

LOW_CONFIDENCE_THRESHOLD = 0.35
LOW_CONFIDENCE_GAP = 0.08
_RERANK_TOP_K = 8
_RERANK_MIN_CONFIDENCE = 0.5


# --------------------------------------------------------------------------- search


def _row(action: dict[str, Any], confidence: float, include_schemas: bool) -> dict[str, Any]:
    req, opt = schema_arg_lists(action.get("input_schema"))
    row: dict[str, Any] = {
        "action_id": action["action_id"],
        "title": action.get("title"),
        "description": (action.get("description") or "")[:240],
        "source": action["source"],
        "category": action.get("category"),
        "tier": action["tier"],
        "confidence": round(confidence, 4),
        "required_args": req,
        "optional_args": opt,
    }
    if include_schemas:
        row["input_schema"] = action.get("input_schema")
    return row


def search(
    query: str = "",
    limit: int = 10,
    source: str | None = None,
    category: str | None = None,
    tier: str | None = None,
    include_schemas: bool = False,
    # Accepted for compatibility with the old is-be-mcp search signature.
    read_only_only: bool = False,
    side_effect_level: str | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    cat = catalog.get_catalog()
    q = (query or "").strip()
    limit = max(1, min(int(limit or 10), 50))
    if read_only_only or side_effect_level == "read_only":
        tier = "read"

    def keep(action: dict[str, Any]) -> bool:
        if source and action["source"] != source:
            return False
        if category and action.get("category") != category and not str(action.get("category", "")).startswith(
            f"{category}."
        ):
            return False
        if tier and action["tier"] != tier:
            return False
        return True

    if not q:
        rows = [_row(a, 0.0, include_schemas) for a in cat["actions"] if keep(a)][:limit]
        return {
            "query": q,
            "count": len(rows),
            "results": rows,
            "low_confidence": True,
            "catalog": catalog.counts(),
            "hint": "Pass a query, or filter by source/category. Then resolve(action_id) before execute.",
        }

    hits = cat["index"].search(q, limit=200)
    rows: list[dict[str, Any]] = []
    max_raw = hits[0][1] if hits else 1.0
    for entry, raw in hits:
        action = cat["by_id"].get(entry["action_id"])
        if action is None or not keep(action):
            continue
        rows.append(_row(action, min(1.0, raw / max_raw) if max_raw > 0 else 0.0, include_schemas))
        if len(rows) >= max(limit, _RERANK_TOP_K):
            break

    low = True
    if rows:
        top = rows[0]["confidence"]
        second = rows[1]["confidence"] if len(rows) > 1 else 0.0
        low = top < LOW_CONFIDENCE_THRESHOLD or (top - second) < LOW_CONFIDENCE_GAP

    out: dict[str, Any] = {"query": q, "count": len(rows[:limit]), "results": rows[:limit], "low_confidence": low}
    if low and len(rows) >= 2:
        try:
            from modules.mcp.actions.search import _jev_pick, _rerank_enabled

            if _rerank_enabled():
                pick = _jev_pick(q, rows[:_RERANK_TOP_K])
                if pick is not None and pick[1] >= _RERANK_MIN_CONFIDENCE:
                    chosen = next(r for r in rows if r["action_id"] == pick[0])
                    out["results"] = ([chosen] + [r for r in rows if r is not chosen])[:limit]
                    out["rerank"] = {"by": "jev", "action_id": pick[0], "confidence": round(pick[1], 4)}
        except Exception:  # noqa: BLE001 - rerank is best-effort
            logger.debug("vexlum rerank skipped", exc_info=True)
    out["next"] = "resolve(action_id) for the full schema and policy, then execute(action_id, arguments)"
    return out


# --------------------------------------------------------------------------- resolve


def _example_value(spec: dict[str, Any]) -> Any:
    if "default" in spec:
        return spec["default"]
    if "enum" in spec and spec["enum"]:
        return spec["enum"][0]
    t = spec.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    return {"integer": 0, "number": 0, "boolean": False, "array": [], "object": {}}.get(str(t), "<string>")


def _example_args(schema: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties") or {}
    return {k: _example_value(props.get(k) or {}) for k in (schema.get("required") or [])}


def _executor_view(record: dict[str, Any]) -> dict[str, Any]:
    ex = record.get("executor") or {}
    kind = ex.get("kind")
    if kind == "rest":
        return {"kind": "rest", "method": ex.get("method"), "path": ex.get("path"), "operation_id": ex.get("operation_id")}
    if kind == "python":
        return {"kind": "python", "handler": f"{ex.get('module')}.{ex.get('function')}"}
    return {k: v for k, v in ex.items() if k in ("kind", "op", "action_id", "legacy_tool_name")}


def _unknown(action_id: str) -> UnknownActionError:
    return UnknownActionError(
        f"Unknown action_id: {action_id}",
        details={
            "suggestions": catalog.suggest(action_id) if action_id else [],
            "hint": "search(query) first; ids also accept legacy tool names, REST operationIds and 'METHOD /path'.",
        },
    )


def _require(action_id: str) -> dict[str, Any]:
    resolved = catalog.resolve_id(action_id)
    if not resolved:
        raise _unknown(action_id)
    return catalog.get_catalog()["by_id"][resolved]


def resolve(action_id: str) -> dict[str, Any]:
    try:
        record = _require(action_id)
    except McpActionError as exc:
        return exc.to_dict(action_id=action_id)
    tier = record["tier"]
    example_args = _example_args(record.get("input_schema") or {})
    call: dict[str, Any] = {"action_id": record["action_id"], "arguments": example_args}
    steps: list[dict[str, Any]] = []
    if tier == "write":
        call["confirmed"] = True
    elif tier == "destructive":
        steps = [
            {**call, "dry_run": True},
            {**call, "confirmed": True, "confirm_token": "<from dry_run data.confirm_token>"},
        ]
    return {
        "status": "success",
        "action_id": record["action_id"],
        "resolved_from": action_id if action_id != record["action_id"] else None,
        "source": record["source"],
        "title": record.get("title"),
        "description": record.get("description"),
        "category": record.get("category"),
        "tier": tier,
        "requires": policy.requirements(tier),
        "dry_run": (
            "native preview"
            if record.get("native_dry_run")
            else "shows the HTTP request"
            if record["source"] == "api"
            else "validates arguments only"
        ),
        "input_schema": record.get("input_schema"),
        "executor": _executor_view(record),
        "legacy_tool_name": record.get("legacy_tool_name"),
        "notes": record.get("notes") or [],
        "canonical_docs": record.get("canonical_docs") or [],
        "example": steps or [call],
        "cli": f"vexlum exec {record['action_id']} --args '{json.dumps(example_args)}'"
        + (" --confirm" if tier == "write" else "")
        + (" --dry-run   # then: --confirm --token <confirm_token>" if tier == "destructive" else ""),
    }


# --------------------------------------------------------------------------- execute


def _validate(record: dict[str, Any], arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    try:
        return validate_arguments(record.get("input_schema"), arguments), []
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001 - e.g. jsonschema.SchemaError on generated REST schemas
        return dict(arguments), [f"schema validation skipped: {type(exc).__name__}: {exc}"]


def _status(_args: dict[str, Any]) -> dict[str, Any]:
    from modules.vexlum.executors.rest import api_base_url

    out: dict[str, Any] = {"server": "vexlum", "catalog": catalog.counts()}
    base = api_base_url()
    try:
        import httpx

        resp = httpx.get(base + "/api/health", timeout=3.0)
        out["api"] = {"url": base, "reachable": resp.status_code < 500, "http_status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        out["api"] = {"url": base, "reachable": False, "error": str(exc)}
    try:
        from modules.vexlum.executors.sql import run_query

        run_query({"query": "SELECT 1 AS ok", "max_rows": 1})
        out["db"] = {"reachable": True}
    except Exception as exc:  # noqa: BLE001
        out["db"] = {"reachable": False, "error": str(exc)}
    try:
        from modules.mcp.webui_client import WebuiMcpClient

        client = WebuiMcpClient()
        ok, err = asyncio.run(client.probe())
        out["live_sse"] = {"url": client.url, "reachable": ok, "error": err}
    except Exception as exc:  # noqa: BLE001
        out["live_sse"] = {"reachable": False, "error": str(exc)}
    out["elevated_enabled"] = policy.elevated_allowed()
    return out


def _categories(args: dict[str, Any]) -> dict[str, Any]:
    src = args.get("source")
    rows: dict[str, dict[str, Any]] = {}
    for a in catalog.get_catalog()["actions"]:
        if src and a["source"] != src:
            continue
        row = rows.setdefault(a["category"], {"category": a["category"], "source": a["source"], "count": 0, "tiers": {}})
        row["count"] += 1
        row["tiers"][a["tier"]] = row["tiers"].get(a["tier"], 0) + 1
    return {"categories": sorted(rows.values(), key=lambda r: (r["source"], r["category"]))}


def _run(record: dict[str, Any], args: dict[str, Any], *, dry_run: bool, request_id: str) -> Any:
    kind = (record.get("executor") or {}).get("kind")
    if kind == "registry":
        from modules.vexlum.executors.python_handler import run_registry

        return run_registry(record, args, request_id=request_id)
    if kind == "python":
        from modules.vexlum.executors.python_handler import run_python

        return run_python(record, args, dry_run=dry_run)
    if kind == "rest":
        from modules.vexlum.executors.rest import run_rest

        return run_rest(record, args)
    if kind == "sql":
        from modules.vexlum.executors import sql

        op = record["executor"]["op"]
        if op == "query":
            return sql.run_query(args)
        if op == "execute":
            return sql.run_execute(args, dry_run=dry_run)
        return sql.run_schema(args)
    if kind == "system":
        op = record["executor"]["op"]
        return _status(args) if op == "status" else _categories(args)
    raise McpActionError(f"no executor for kind={kind!r}", details={"action_id": record["action_id"]})


def _preview(record: dict[str, Any], args: dict[str, Any], *, request_id: str) -> Any:
    if record.get("native_dry_run"):
        return _run(record, args, dry_run=True, request_id=request_id)
    if (record.get("executor") or {}).get("kind") == "rest":
        from modules.vexlum.executors.rest import describe_request

        return describe_request(record, args)
    return {"validated_arguments": args, "would_invoke": _executor_view(record)}


def _envelope(record: dict[str, Any], *, request_id: str, dry_run: bool, data: Any, warnings: list[str],
              started: float) -> dict[str, Any]:
    return {
        "status": "success",
        "action_id": record["action_id"],
        "request_id": request_id,
        "source": record["source"],
        "tier": record["tier"],
        "dry_run": dry_run,
        "summary": f"{'Dry run: ' if dry_run else ''}{record.get('title') or record['action_id']}",
        "data": data,
        "warnings": warnings,
        "notes": record.get("notes") or [],
        "canonical_docs": record.get("canonical_docs") or [],
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def execute(
    action_id: str,
    arguments: dict[str, Any] | None = None,
    dry_run: bool = False,
    confirmed: bool = False,
    confirm_token: str | None = None,
    request_id: str | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    rid = (request_id or "").strip() or str(uuid.uuid4())
    started = time.perf_counter()
    record: dict[str, Any] | None = None
    try:
        if arguments is not None and not isinstance(arguments, dict):
            raise ValidationError("arguments must be an object")
        record = _require(action_id)
        validated, warnings = _validate(record, dict(arguments or {}))
        policy.check(record, validated, dry_run=dry_run, confirmed=confirmed, confirm_token=confirm_token)
        if record["action_id"] != action_id:
            warnings.append(f"resolved {action_id!r} -> {record['action_id']!r}")

        if dry_run:
            data: dict[str, Any] = {"preview": _preview(record, validated, request_id=rid)}
            if record["tier"] != "read":
                data.update(policy.issue_token(record["action_id"], validated))
                data["next"] = {
                    "action_id": record["action_id"],
                    "arguments": validated,
                    "confirmed": True,
                    **({"confirm_token": data["confirm_token"]} if record["tier"] == "destructive" else {}),
                }
            return _envelope(record, request_id=rid, dry_run=True, data=data, warnings=warnings, started=started)

        if record["source"] == "browser":
            return {
                "status": "proxy",
                "code": "playwright_delegate",
                "action_id": record["action_id"],
                "request_id": rid,
                "legacy_tool_name": record["executor"].get("legacy_tool_name"),
                "validated_args": validated,
                "tier": record["tier"],
                "side_effect_level": "read_only" if record["tier"] == "read" else record["tier"],
            }

        data = _run(record, validated, dry_run=False, request_id=rid)
        out = _envelope(record, request_id=rid, dry_run=False, data=data, warnings=warnings, started=started)
        if record["tier"] != "read":
            logger.info(
                "vexlum_execute action=%s tier=%s request_id=%s duration_ms=%s",
                record["action_id"], record["tier"], rid, out["duration_ms"],
            )
        return out
    except McpActionError as exc:
        err = exc.to_dict(action_id=action_id, request_id=rid)
        if record is not None:
            err["tier"] = record["tier"]
            err["source"] = record["source"]
        return err
    except Exception as exc:  # noqa: BLE001
        logger.exception("vexlum execute %s failed", action_id)
        return {
            "status": "error",
            "code": "handler_error",
            "message": str(exc),
            "action_id": action_id,
            "request_id": rid,
            "details": {"type": type(exc).__name__},
        }


def dispatch_alias(
    action_id: str,
    arguments: dict[str, Any] | None = None,
    dry_run: bool = False,
    confirmed: bool = False,
    request_id: str | None = None,
    confirm_token: str | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    """Deprecated ``dispatch`` (is-be-mcp contract) -> ``execute``."""
    out = execute(action_id, arguments, dry_run=dry_run, confirmed=confirmed, confirm_token=confirm_token,
                  request_id=request_id)
    if isinstance(out.get("warnings"), list):
        out["warnings"].append("dispatch is deprecated; use execute (vexlum). See docs/technical/VEXLUM_MCP.md")
    else:
        out["deprecation"] = "dispatch is deprecated; use execute (vexlum)"
    return out


def invoke(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Single entry for the worker / CLI: search | resolve | execute (+ deprecated aliases)."""
    payload = dict(args or {})
    if tool == "search":
        return search(**payload)
    if tool == "resolve":
        return resolve(str(payload.get("action_id") or ""))
    if tool == "execute":
        return execute(**payload)
    if tool == "dispatch":
        return dispatch_alias(**payload)
    if tool == "list":
        return list_actions(**payload)
    if tool == "sse_status":
        return execute("system.status")
    return {"status": "error", "code": "unknown_tool", "message": f"Unknown vexlum tool: {tool}"}


def list_actions(
    source: str | None = None,
    category: str | None = None,
    tier: str | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    rows = [
        {"action_id": a["action_id"], "tier": a["tier"], "source": a["source"], "title": a.get("title")}
        for a in catalog.get_catalog()["actions"]
        if (not source or a["source"] == source)
        and (not category or str(a.get("category", "")).startswith(category))
        and (not tier or a["tier"] == tier)
    ]
    return {"status": "success", "count": len(rows), "actions": rows}
