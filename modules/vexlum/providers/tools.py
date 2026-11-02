"""Python MCP tools: curated action registry + every legacy tool in mcp/tool_catalog.json."""

from __future__ import annotations

import inspect
import logging
import types
import typing
from typing import Any

from modules.mcp.actions.registry import load_action_registry, registry_actions
from modules.mcp.catalog import catalog_tools, load_tool_catalog

logger = logging.getLogger(__name__)

# Tier overrides for legacy tools (tool_catalog.json `risk` is unreliable: it marks
# run_processing_job as read_only). Anything not listed is ``read``.
WRITE_TOOLS = frozenset(
    {
        "run_processing_job",
        "manage_runners",
        "set_config_value",
        "set_image_metadata",
        "process_newly_imported_folders",
        "export_debug_bundle",
        "propagate_tags",
    }
)
DESTRUCTIVE_TOOLS = frozenset(
    {
        "prune_missing_files",
        "rebase_file_paths",
        "execute_code",
    }
)

_TOOL_NOTES = {
    "run_processing_job": [
        "Needs in-process runners (WebUI). From gpu-shell prefer api.* job endpoints, e.g. search('start scoring').",
    ],
    "manage_runners": ["Needs in-process runners (WebUI); prefer api.* start/stop endpoints from gpu-shell."],
    "execute_code": [
        "Only works inside the WebUI process with ENABLE_MCP_EXECUTE_CODE=1 (Gradio context). RCE-equivalent.",
    ],
}

_REGISTRY_LEVEL_TO_TIER = {
    "read_only": "read",
    "write": "write",
    "writes_files": "write",
    "elevated": "destructive",
    "destructive": "destructive",
}

_PY_TO_JSON = {
    int: "integer",
    float: "number",
    str: "string",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def tier_for_tool(name: str) -> str:
    if name in DESTRUCTIVE_TOOLS:
        return "destructive"
    if name in WRITE_TOOLS:
        return "write"
    return "read"


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {}
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        inner = _annotation_schema(args[0]) if len(args) == 1 else {}
        if "type" in inner:
            inner = dict(inner)
            inner["type"] = [inner["type"], "null"]
        return inner
    if origin in (list, tuple):
        return {"type": "array"}
    if origin is dict:
        return {"type": "object"}
    json_type = _PY_TO_JSON.get(annotation)
    return {"type": json_type} if json_type else {}


def schema_from_callable(fn: Any) -> tuple[dict[str, Any], bool]:
    """JSON Schema for a tool function; second item is True when it takes ``dry_run``.

    ``dry_run`` is hidden from the schema — vexlum maps its own ``dry_run`` flag onto it.
    """
    sig = inspect.signature(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    native_dry_run = False
    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if name == "dry_run":
            native_dry_run = True
            continue
        spec = _annotation_schema(param.annotation)
        if param.default is inspect.Parameter.empty:
            required.append(name)
        elif param.default is not None:
            spec["default"] = param.default
        props[name] = spec
    schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema, native_dry_run


def _legacy_callable(name: str) -> Any | None:
    try:
        from modules import mcp_server

        fn = getattr(mcp_server, name, None)
        return fn if callable(fn) else None
    except Exception:  # noqa: BLE001 - catalog must load even without the full stack
        logger.debug("modules.mcp_server import failed; legacy tool schemas are permissive", exc_info=True)
        return None


def _first_doc_line(fn: Any) -> str:
    doc = inspect.getdoc(fn) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def _registry_record(action: dict[str, Any]) -> dict[str, Any]:
    level = str(action.get("side_effect_level") or "read_only")
    return {
        "action_id": action["action_id"],
        "source": "tool",
        "title": action.get("title") or action["action_id"],
        "description": action.get("description") or "",
        "category": action.get("category") or "tool",
        "tags": list(action.get("tags") or []),
        "aliases": list(action.get("aliases") or []),
        "intent_examples": list(action.get("intent_examples") or []),
        "input_schema": action.get("input_schema") or {"type": "object", "properties": {}},
        "tier": _REGISTRY_LEVEL_TO_TIER.get(level, "write"),
        "native_dry_run": False,
        "executor": {"kind": "registry", "action_id": action["action_id"]},
        "canonical_docs": list(action.get("canonical_docs") or []),
        "legacy_tool_name": action.get("legacy_tool_name"),
        "notes": [],
    }


def _legacy_record(tool: dict[str, Any]) -> dict[str, Any]:
    name = str(tool["name"])
    domain = str(tool.get("domain") or "tool")
    fn = _legacy_callable(name)
    if fn is not None:
        schema, native_dry_run = schema_from_callable(fn)
        description = tool.get("description") or _first_doc_line(fn)
    else:
        schema, native_dry_run = {"type": "object", "properties": {}}, False
        description = tool.get("description") or ""
    return {
        "action_id": f"{domain}.{name}",
        "source": "tool",
        "title": name.replace("_", " ").capitalize(),
        "description": description,
        "category": domain,
        "tags": list(tool.get("tags") or []),
        "aliases": [name.replace("_", " ")],
        "intent_examples": list(tool.get("examples") or []),
        "input_schema": schema,
        "tier": tier_for_tool(name),
        "native_dry_run": native_dry_run,
        "executor": {"kind": "python", "module": "modules.mcp_server", "function": name},
        "canonical_docs": ["docs/technical/MCP_DEBUGGING_TOOLS.md"],
        "legacy_tool_name": name,
        "notes": list(_TOOL_NOTES.get(name, [])),
    }


def load_tool_actions() -> list[dict[str, Any]]:
    """Registry actions (curated) first; then every remaining legacy tool."""
    out: list[dict[str, Any]] = []
    covered: set[str] = set()
    reg = load_action_registry()
    for action in registry_actions(reg):
        if action.get("handler_domain") == "playwright":
            continue  # browser provider owns these
        if not action.get("dispatch_enabled"):
            continue
        out.append(_registry_record(action))
        if action.get("legacy_tool_name"):
            covered.add(str(action["legacy_tool_name"]))

    for tool in catalog_tools(load_tool_catalog()):
        name = str(tool.get("name") or "")
        if not name or name in covered:
            continue
        out.append(_legacy_record(tool))
        covered.add(name)
    return out
