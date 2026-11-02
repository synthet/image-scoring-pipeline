"""Unified vexlum catalog: providers -> one list of action records, a BM25 index, id resolution.

Building the tool provider imports ``modules.mcp_server`` to read tool signatures, which is
slow on the Docker Desktop bind mount (~20 s). The built action list is therefore cached in
``~/.vexlum/cache/catalog-<fingerprint>.json`` (``VEXLUM_CACHE_DIR`` overrides), keyed by a
hash of every source file, so ``search``/``resolve`` start in a few seconds.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from modules.mcp.bm25 import Bm25Index

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ("tool", "api", "db", "browser", "system")
SNAPSHOT_VERSION = 1

_WATCHED = (
    ROOT / "mcp" / "action_registry.json",
    ROOT / "mcp" / "actions" / "overlay.yaml",
    ROOT / "mcp" / "tool_catalog.json",
    ROOT / "mcp" / "actions" / "playwright_registry.json",
    ROOT / "docs" / "reference" / "api" / "openapi.yaml",
    ROOT / "mcp" / "vexlum" / "rest_overrides.yaml",
)

# Files whose content shapes the catalog (fingerprint only; not polled for reload).
_FINGERPRINTED_CODE = (
    ROOT / "modules" / "mcp_server.py",
    ROOT / "modules" / "vexlum" / "providers" / "tools.py",
    ROOT / "modules" / "vexlum" / "providers" / "rest.py",
    ROOT / "modules" / "vexlum" / "providers" / "db.py",
    ROOT / "modules" / "vexlum" / "providers" / "browser.py",
    ROOT / "modules" / "vexlum" / "providers" / "system.py",
)


def _fingerprint() -> str:
    h = hashlib.sha256(f"v{SNAPSHOT_VERSION}|pw={os.environ.get('MCP_PLAYWRIGHT_ENABLED', '1')}".encode())
    for path in (*_WATCHED, *_FINGERPRINTED_CODE):
        h.update(str(path.name).encode())
        try:
            h.update(path.read_bytes())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()[:20]


def _snapshot_path(fp: str) -> Path | None:
    if (os.environ.get("VEXLUM_CATALOG_CACHE") or "1").strip() == "0":
        return None
    base = (os.environ.get("VEXLUM_CACHE_DIR") or "").strip()
    return (Path(base) if base else Path.home() / ".vexlum" / "cache") / f"catalog-{fp}.json"


def _read_snapshot(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") == SNAPSHOT_VERSION and isinstance(data.get("actions"), list):
            return data["actions"]
    except (OSError, ValueError):
        logger.debug("vexlum catalog snapshot unreadable: %s", path, exc_info=True)
    return None


def _write_snapshot(path: Path | None, actions: list[dict[str, Any]]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": SNAPSHOT_VERSION, "actions": actions}, default=str), encoding="utf-8")
        tmp.replace(path)
        for stale in path.parent.glob("catalog-*.json"):
            if stale != path:
                stale.unlink(missing_ok=True)
    except OSError:
        logger.debug("vexlum catalog snapshot not written: %s", path, exc_info=True)

FIELD_WEIGHTS = {
    "action_id": 4.0,
    "title": 3.0,
    "aliases": 2.5,
    "tags": 2.0,
    "intent_examples": 2.5,
    "description": 1.0,
    "argument_names": 1.5,
}

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_key: tuple[float, ...] | None = None


def _mtimes() -> tuple[float, ...]:
    return tuple(p.stat().st_mtime if p.exists() else 0.0 for p in _WATCHED)


def _load_provider(name: str) -> list[dict[str, Any]]:
    try:
        if name == "tool":
            from modules.vexlum.providers.tools import load_tool_actions

            return load_tool_actions()
        if name == "api":
            from modules.vexlum.providers.rest import load_rest_actions

            return load_rest_actions()
        if name == "db":
            from modules.vexlum.providers.db import load_db_actions

            return load_db_actions()
        if name == "browser":
            from modules.vexlum.providers.browser import load_browser_actions

            return load_browser_actions()
        if name == "system":
            from modules.vexlum.providers.system import load_system_actions

            return load_system_actions()
    except Exception:
        logger.exception("vexlum provider %s failed to load", name)
    return []


def _bm25_entry(action: dict[str, Any]) -> dict[str, Any]:
    props = (action.get("input_schema") or {}).get("properties") or {}
    return {
        "action_id": action["action_id"],
        "title": action.get("title"),
        "description": action.get("description"),
        "tags": action.get("tags") or [],
        "aliases": action.get("aliases") or [],
        "intent_examples": action.get("intent_examples") or [],
        "argument_names": " ".join(str(k) for k in props),
    }


def _build_actions() -> tuple[list[dict[str, Any]], dict[str, str]]:
    actions: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    seen: set[str] = set()
    for source in SOURCES:
        loaded = _load_provider(source)
        if not loaded and source in ("tool", "api"):
            errors[source] = "provider returned no actions (see server log)"
        for action in loaded:
            aid = action["action_id"]
            if aid in seen:
                logger.warning("vexlum duplicate action_id %s from %s ignored", aid, source)
                continue
            seen.add(aid)
            actions.append(action)
    return actions, errors


def _build() -> dict[str, Any]:
    snap_path = _snapshot_path(_fingerprint())
    cached = _read_snapshot(snap_path)
    errors: dict[str, str] = {}
    if cached is not None:
        actions = cached
    else:
        actions, errors = _build_actions()
        if not errors:
            _write_snapshot(snap_path, actions)
    by_id: dict[str, dict[str, Any]] = {a["action_id"]: a for a in actions}

    legacy: dict[str, str] = {}
    for action in actions:
        name = action.get("legacy_tool_name")
        if name and name not in legacy:
            legacy[str(name)] = action["action_id"]

    # REST lookups by operationId and "METHOD /path".
    rest_keys: dict[str, str] = {}
    for action in actions:
        ex = action.get("executor") or {}
        if ex.get("kind") == "rest":
            rest_keys[str(ex.get("operation_id"))] = action["action_id"]
            rest_keys[f"{ex.get('method')} {ex.get('path')}"] = action["action_id"]

    return {
        "actions": actions,
        "by_id": by_id,
        "legacy": legacy,
        "rest_keys": rest_keys,
        "index": Bm25Index([_bm25_entry(a) for a in actions], FIELD_WEIGHTS),
        "errors": errors,
        "from_snapshot": cached is not None,
    }


def get_catalog(*, refresh: bool = False) -> dict[str, Any]:
    global _cache, _cache_key
    key = _mtimes()
    with _lock:
        if refresh or _cache is None or _cache_key != key:
            _cache = _build()
            _cache_key = key
        return _cache


def clear_catalog_cache() -> None:
    global _cache, _cache_key
    with _lock:
        _cache = None
        _cache_key = None


def resolve_id(needle: str) -> str | None:
    """Exact action_id, legacy tool name, REST operationId / "METHOD /path", or unique suffix."""
    cat = get_catalog()
    q = (needle or "").strip()
    if not q:
        return None
    if q in cat["by_id"]:
        return q
    if q in cat["legacy"]:
        return cat["legacy"][q]
    if q in cat["rest_keys"]:
        return cat["rest_keys"][q]
    if "." in q:
        tail = q.rsplit(".", 1)[-1]
        if tail in cat["legacy"]:
            return cat["legacy"][tail]
    matches = [aid for aid in cat["by_id"] if aid.endswith(f".{q}")]
    if len(matches) == 1:
        return matches[0]
    return None


def suggest(needle: str, limit: int = 5) -> list[str]:
    cat = get_catalog()
    hits = cat["index"].search(needle.replace(".", " ").replace("_", " "), limit=limit)
    return [entry["action_id"] for entry, _score in hits]


def counts() -> dict[str, Any]:
    cat = get_catalog()
    by_source: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for a in cat["actions"]:
        by_source[a["source"]] = by_source.get(a["source"], 0) + 1
        by_tier[a["tier"]] = by_tier.get(a["tier"], 0) + 1
        by_category[a["category"]] = by_category.get(a["category"], 0) + 1
    return {
        "total": len(cat["actions"]),
        "by_source": by_source,
        "by_tier": by_tier,
        "by_category": dict(sorted(by_category.items())),
        "provider_errors": cat["errors"],
    }
