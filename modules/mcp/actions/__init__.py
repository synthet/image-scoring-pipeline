"""MCP action registry: search + dispatch.

Exports resolve lazily (PEP 562): importing a light submodule such as
``modules.mcp.actions.errors`` must not pull in dispatch -> modules.db (slow on the
Docker Desktop bind mount; see modules/vexlum cold start).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from modules.mcp.actions.dispatch import dispatch_action
    from modules.mcp.actions.registry import action_by_id, load_action_registry, registry_actions
    from modules.mcp.actions.search import search_actions

_EXPORTS = {
    "dispatch_action": "modules.mcp.actions.dispatch",
    "action_by_id": "modules.mcp.actions.registry",
    "load_action_registry": "modules.mcp.actions.registry",
    "registry_actions": "modules.mcp.actions.registry",
    "search_actions": "modules.mcp.actions.search",
}

__all__ = [
    "action_by_id",
    "dispatch_action",
    "load_action_registry",
    "registry_actions",
    "search_actions",
]


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value
