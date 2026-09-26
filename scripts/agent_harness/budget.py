"""Measure the always-on instruction text an agent pays for on every turn.

Counts what Claude Code loads unconditionally: root ``CLAUDE.md``, rules in
``.claude/rules`` without ``paths:``, and the name + description listing of
model-invocable skills and commands. Path-scoped rules and
``disable-model-invocation`` skills are reported separately as on-demand.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.agent_harness.packs import parse_frontmatter


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def measure(repo: Path) -> dict[str, Any]:
    always: dict[str, int] = {}
    on_demand: dict[str, int] = {}

    claude_md = _read(repo / "CLAUDE.md")
    if claude_md:
        always["CLAUDE.md"] = len(claude_md)

    for path in sorted((repo / ".claude" / "rules").glob("*.md")):
        text = _read(path)
        meta, _ = parse_frontmatter(text)
        key = f".claude/rules/{path.name}"
        (on_demand if meta.get("paths") else always)[key] = len(text)

    listing = 0
    hidden = 0
    entries = [p for p in (repo / ".claude" / "skills").glob("*/SKILL.md")]
    entries += list((repo / ".claude" / "commands").glob("*.md"))
    for path in entries:
        meta, _ = parse_frontmatter(_read(path))
        default = path.parent.name if path.name == "SKILL.md" else path.stem
        name = str(meta.get("name") or default)
        size = len(name) + len(str(meta.get("description") or ""))
        if meta.get("disable-model-invocation") is True:
            hidden += size
        else:
            listing += size
    always["skill+command listing"] = listing
    if hidden:
        on_demand["user-only skills/commands (listing)"] = hidden

    return {
        "repo": repo.name,
        "always_on_chars": sum(always.values()),
        "always_on": always,
        "on_demand_chars": sum(on_demand.values()),
        "on_demand": on_demand,
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [f"{report['repo']}: always-on {report['always_on_chars']:,} chars (~{report['always_on_chars'] // 4:,} tokens)"]
    for k, v in sorted(report["always_on"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {v:>7,}  {k}")
    lines.append(f"on-demand {report['on_demand_chars']:,} chars")
    for k, v in sorted(report["on_demand"].items(), key=lambda kv: -kv[1]):
        lines.append(f"  {v:>7,}  {k}")
    return "\n".join(lines)
