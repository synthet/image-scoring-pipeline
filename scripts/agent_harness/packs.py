"""Conditional instruction packs and the visibility ladder.

A *pack* is any ``.cursor/rules/*.mdc`` rule that is not ``alwaysApply``:
intent-only rules (served only by this harness) and path-scoped rules (which
Claude Code also loads on file access via ``paths:``). Each pack has two rungs
above ``hide``: ``short`` (its one-line ``description``) and ``full`` (its body).

Per request the harness picks a rung for every pack — Jev when available, a
keyword prefilter otherwise — and injects only packs whose rung went up since
the last injection, so the same text is not re-sent every turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RUNGS = ("hide", "short", "full")
RANK = {r: i for i, r in enumerate(RUNGS)}
FULL_BODY_LIMIT = 6000


@dataclass
class Pack:
    name: str
    description: str
    body: str
    source: str
    globs: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)

    def matches(self, text: str) -> bool:
        lowered = text.lower()
        for trig in self.triggers:
            try:
                if re.search(trig, lowered, re.I):
                    return True
            except re.error:
                if trig.lower() in lowered:
                    return True
        return False

    def render(self, rung: str) -> str:
        if rung == "full":
            body = self.body.strip()
            if len(body) > FULL_BODY_LIMIT:
                body = body[:FULL_BODY_LIMIT].rstrip() + f"\n… (truncated; read {self.source})"
            return f"### {self.name} (full) — {self.source}\n{body}"
        return f"- **{self.name}**: {self.description} — full text: `{self.source}`"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Minimal YAML frontmatter reader for rule files (scalars and lists)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta: dict[str, Any] = {}
    key: str | None = None
    block = False
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            block = val in {">", "|", ">-", "|-"}
            meta[key] = "" if block else ([] if val == "" else _scalar(val))
        elif key and block:
            meta[key] = (meta[key] + " " + line.strip()).strip()
        elif key and line.strip().startswith("- "):
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(_scalar(line.strip()[2:].strip()))
    body = text[end + 4 :].lstrip("\n")
    return meta, body


def _scalar(val: str) -> Any:
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]
    if val.lower() in {"true", "false"}:
        return val.lower() == "true"
    return val


def split_globs(value: Any) -> list[str]:
    """Cursor ``globs`` value → list; commas inside ``{a,b}`` do not split."""
    if isinstance(value, list):
        items = [str(v) for v in value]
    elif isinstance(value, str):
        items, depth, current = [], 0, ""
        for ch in value:
            depth += (ch == "{") - (ch == "}")
            if ch == "," and depth <= 0:
                items.append(current)
                current = ""
            else:
                current += ch
        items.append(current)
    else:
        return []
    return [i.strip().strip("\"'") for i in items if i.strip().strip("\"'")]


def load_packs(repo: Path, config: dict[str, Any] | None = None) -> list[Pack]:
    """Packs from ``<repo>/.cursor/rules`` plus ``packs`` extras in config."""
    cfg = (config or {}).get("packs") or {}
    packs: list[Pack] = []
    rules_dir = repo / ".cursor" / "rules"
    for path in sorted(rules_dir.glob("*.mdc")):
        try:
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if meta.get("alwaysApply") is True:
            continue
        name = path.stem
        extra = cfg.get(name) or {}
        if extra.get("disabled"):
            continue
        triggers = list(extra.get("triggers") or [])
        if not triggers:
            triggers = [re.escape(w) for w in name.split("-") if len(w) >= 5]
        packs.append(
            Pack(
                name=name,
                description=str(meta.get("description") or name),
                body=body,
                source=path.relative_to(repo).as_posix(),
                globs=split_globs(meta.get("globs")),
                triggers=triggers,
            )
        )
    return packs


def deterministic_rungs(packs: list[Pack], prompt: str) -> dict[str, str]:
    """Fallback ladder: keyword match → ``short``, else ``hide``."""
    return {p.name: ("short" if p.matches(prompt) else "hide") for p in packs}


def render_injection(packs: list[Pack], rungs: dict[str, str], header: str) -> str:
    by_name = {p.name: p for p in packs}
    shorts = [by_name[n].render("short") for n, r in rungs.items() if r == "short" and n in by_name]
    fulls = [by_name[n].render("full") for n, r in rungs.items() if r == "full" and n in by_name]
    if not shorts and not fulls:
        return ""
    parts = [header]
    if shorts:
        parts.append("Relevant rule packs (read the file if you need detail):\n" + "\n".join(shorts))
    parts.extend(fulls)
    return "\n\n".join(parts)
