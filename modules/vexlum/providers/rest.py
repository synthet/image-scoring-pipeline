"""REST operations generated from docs/reference/api/openapi.yaml (one action per operationId)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a pinned dependency
    yaml = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = ROOT / "docs" / "reference" / "api" / "openapi.yaml"
OVERRIDES_PATH = ROOT / "mcp" / "vexlum" / "rest_overrides.yaml"

_METHODS = ("get", "post", "put", "patch", "delete")
_DEFAULT_TIER = {"get": "read", "post": "write", "put": "write", "patch": "write", "delete": "destructive"}
_MAX_REF_DEPTH = 6


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required for vexlum REST provider. pip install pyyaml")
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _resolve_refs(node: Any, spec: dict[str, Any], depth: int = 0) -> Any:
    """Inline ``#/components/...`` refs (bounded depth; cycles collapse to ``{}``)."""
    if depth > _MAX_REF_DEPTH:
        return {}
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            target: Any = spec
            for part in ref[2:].split("/"):
                target = target.get(part, {}) if isinstance(target, dict) else {}
            return _resolve_refs(target, spec, depth + 1)
        return {k: _resolve_refs(v, spec, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(v, spec, depth + 1) for v in node]
    return node


def _openapi_to_json_schema(schema: Any) -> dict[str, Any]:
    """Drop OpenAPI-only keywords jsonschema would choke on."""
    if not isinstance(schema, dict):
        return {}
    out: dict[str, Any] = {}
    for key, val in schema.items():
        if key in ("nullable", "example", "examples", "discriminator", "xml", "externalDocs", "deprecated",
                   "readOnly", "writeOnly"):
            continue
        if isinstance(val, dict):
            out[key] = _openapi_to_json_schema(val)
        elif isinstance(val, list):
            out[key] = [_openapi_to_json_schema(v) if isinstance(v, dict) else v for v in val]
        else:
            out[key] = val
    if schema.get("nullable") and isinstance(out.get("type"), str):
        out["type"] = [out["type"], "null"]
    return out


def short_name(operation_id: str, path: str, method: str) -> str:
    """FastAPI operationIds are ``{func}{path_as_underscores}_{method}``; return ``func``."""
    suffix = re.sub(r"[^0-9a-zA-Z_]", "_", path) + f"_{method}"
    if operation_id.endswith(suffix) and len(operation_id) > len(suffix):
        return operation_id[: -len(suffix)]
    return operation_id


def area_for_path(path: str) -> str:
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    if parts and parts[0] == "api":
        parts = parts[1:]
    if not parts:
        return "root"
    return re.sub(r"[^0-9a-zA-Z_]", "_", parts[0]).lower() or "root"


def _path_words(path: str) -> list[str]:
    return [w for w in re.split(r"[^0-9a-zA-Z]+", path) if w and w != "api"]


def load_rest_actions(openapi_path: Path | None = None) -> list[dict[str, Any]]:
    spec = _load_yaml(openapi_path or OPENAPI_PATH)
    overrides = (_load_yaml(OVERRIDES_PATH).get("operations") or {}) if OVERRIDES_PATH.exists() else {}
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        shared_params = item.get("parameters") or []
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            op_id = str(op.get("operationId") or f"{method}_{path}")
            area = area_for_path(path)
            action_id = f"api.{area}.{short_name(op_id, path, method)}"
            if action_id in seen:
                action_id = f"api.{area}.{op_id}"
            seen.add(action_id)

            props: dict[str, Any] = {}
            required: list[str] = []
            path_params: list[str] = []
            query_params: list[str] = []
            header_params: list[str] = []
            for raw in list(shared_params) + list(op.get("parameters") or []):
                param = _resolve_refs(raw, spec)
                if not isinstance(param, dict) or not param.get("name"):
                    continue
                loc = param.get("in")
                name = str(param["name"])
                if loc == "path":
                    path_params.append(name)
                elif loc == "query":
                    query_params.append(name)
                elif loc == "header":
                    header_params.append(name)
                else:
                    continue
                pschema = _openapi_to_json_schema(param.get("schema") or {})
                if param.get("description"):
                    pschema["description"] = str(param["description"])[:300]
                props[name] = pschema
                if param.get("required") or loc == "path":
                    required.append(name)

            body_schema: dict[str, Any] | None = None
            body = op.get("requestBody")
            if isinstance(body, dict):
                body = _resolve_refs(body, spec)
                content = body.get("content") or {}
                media = content.get("application/json") or next(iter(content.values()), {})
                body_schema = _openapi_to_json_schema((media or {}).get("schema") or {}) or {"type": "object"}
                props["body"] = {**body_schema, "description": "JSON request body"}
                if body.get("required"):
                    required.append("body")

            input_schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": False}
            if required:
                input_schema["required"] = sorted(set(required))

            ov = (
                overrides.get(f"{method.upper()} {path}")
                or overrides.get(op_id)
                or overrides.get(action_id)
                or {}
            )
            summary = str(op.get("summary") or short_name(op_id, path, method).replace("_", " "))
            description = str(op.get("description") or summary).strip()
            words = _path_words(path)
            actions.append(
                {
                    "action_id": action_id,
                    "source": "api",
                    "title": f"{method.upper()} {path} — {summary}",
                    "description": description[:600],
                    "category": f"api.{area}",
                    "tags": sorted({"api", "rest", method, area, *words, *(ov.get("tags") or [])}),
                    "aliases": list(ov.get("aliases") or []) + [summary],
                    "intent_examples": list(ov.get("intent_examples") or []),
                    "input_schema": input_schema,
                    "tier": str(ov.get("tier") or _DEFAULT_TIER[method]),
                    "native_dry_run": False,
                    "executor": {
                        "kind": "rest",
                        "method": method.upper(),
                        "path": path,
                        "operation_id": op_id,
                        "path_params": path_params,
                        "query_params": query_params,
                        "header_params": header_params,
                        "has_body": body_schema is not None,
                    },
                    "canonical_docs": ["docs/technical/API_CONTRACT.md", "docs/reference/api/openapi.yaml"],
                    "legacy_tool_name": None,
                    "notes": list(ov.get("notes") or []),
                }
            )
    return actions
