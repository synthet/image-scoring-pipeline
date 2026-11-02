"""Playwright browser actions (mcp/actions/playwright_registry.json); executed by the TS host."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PLAYWRIGHT_REGISTRY_PATH = ROOT / "mcp" / "actions" / "playwright_registry.json"

# Observation / navigation — no page state change worth gating.
_READ = frozenset(
    {
        "browser.navigate",
        "browser.navigate_back",
        "browser.snapshot",
        "browser.take_screenshot",
        "browser.console_messages",
        "browser.network_request",
        "browser.network_requests",
        "browser.wait_for",
        "browser.tabs",
        "browser.resize",
        "browser.hover",
        "browser.close",
    }
)
_DESTRUCTIVE = frozenset({"browser.run_code_unsafe"})


def _enabled() -> bool:
    return os.environ.get("MCP_PLAYWRIGHT_ENABLED", "1").strip() != "0"


def tier_for_browser(action_id: str) -> str:
    if action_id in _DESTRUCTIVE:
        return "destructive"
    if action_id in _READ:
        return "read"
    return "write"  # click, type, fill_form, select_option, press_key, drag, drop, upload, dialog, evaluate


def load_browser_actions(path: Path | None = None) -> list[dict[str, Any]]:
    reg_path = path or PLAYWRIGHT_REGISTRY_PATH
    if not _enabled() or not reg_path.exists():
        return []
    data = json.loads(reg_path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for entry in data.get("actions") or []:
        if not isinstance(entry, dict) or not entry.get("action_id"):
            continue
        aid = str(entry["action_id"])
        out.append(
            {
                "action_id": aid,
                "source": "browser",
                "title": entry.get("title") or aid,
                "description": entry.get("description") or "",
                "category": "browser",
                "tags": list(entry.get("tags") or []),
                "aliases": list(entry.get("aliases") or []),
                "intent_examples": list(entry.get("intent_examples") or []),
                "input_schema": entry.get("input_schema") or {"type": "object", "properties": {}},
                "tier": tier_for_browser(aid),
                "native_dry_run": False,
                "executor": {"kind": "browser", "legacy_tool_name": entry.get("legacy_tool_name")},
                "canonical_docs": list(entry.get("canonical_docs") or []),
                "legacy_tool_name": entry.get("legacy_tool_name"),
                "notes": ["Executed by the vexlum TS host (mcp-server/). Not available from python -m modules.vexlum."],
            }
        )
    return out
