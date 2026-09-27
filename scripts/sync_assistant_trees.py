#!/usr/bin/env python3
"""Sync assistant trees between `.cursor/` and `.claude/`.

image-scoring-pipeline uses **`.cursor/` as canonical** (default direction: cursor-to-claude).
synthet-code-framework uses `.claude/` as canonical (direction: claude-to-cursor).

Mappings (cursor-to-claude):
  .cursor/commands/*.md        -> .claude/commands/*.md       (verbatim)
  .cursor/skills/<n>/**        -> .claude/skills/<n>/**       (verbatim, whole dir)
  .cursor/agents/*.md          -> .claude/agents/*.md         (verbatim)
  .cursor/rules/<n>.mdc        -> .claude/rules/<n>.md          (frontmatter translated)

Rule frontmatter is translated, because Claude Code ignores Cursor's keys and
would load every mirrored rule on every turn:
  alwaysApply: true            -> always-on (no ``paths``)
  globs: "a,b"                 -> ``paths:`` list (loaded when matching files are read)
  alwaysApply: false, no globs -> not mirrored; intent-only rules are served per
                                  request by the Jev harness UserPromptSubmit hook
                                  (scripts/agent_harness), not loaded every turn.
Rules in CURSOR_ONLY_RULES are never mirrored. Anything else in .claude/rules
(including stale ``*.mdc`` copies) is removed on sync and reported by --check.

Hand-authored files (mcp.example.json, Cursor-only skills) are left untouched.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Cursor-specific rules (they describe Cursor's own tool calling).
CURSOR_ONLY_RULES = {"mcp-schema-check"}

SUBDIRS = [
    ("commands", "commands", "files"),
    ("skills", "skills", "tree"),
    ("agents", "agents", "files"),
    ("rules", "rules", "rules"),
]


def _split_globs(value: str) -> list[str]:
    """Split a Cursor ``globs`` value on commas that are not inside ``{...}``."""
    out: list[str] = []
    depth = 0
    current = ""
    for ch in value:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return [g.strip().strip("\"'") for g in out if g.strip().strip("\"'")]


def claude_rule_text(mdc_text: str) -> str | None:
    """Translate a Cursor rule into a Claude Code rule; ``None`` = do not mirror."""
    if not mdc_text.startswith("---"):
        return mdc_text
    end = mdc_text.find("\n---", 3)
    if end == -1:
        return mdc_text
    meta: dict[str, str] = {}
    for line in mdc_text[3:end].splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    body = mdc_text[end + 4 :]
    always = meta.get("alwaysApply", "").lower() == "true"
    globs = _split_globs(meta.get("globs", "").strip().strip("\"'"))
    header = ["---"]
    if meta.get("description"):
        header.append(f"description: {meta['description']}")
    if always:
        pass
    elif globs:
        header.append("paths:")
        header.extend(f'  - "{g}"' for g in globs)
    else:
        return None
    header.append("---")
    return "\n".join(header) + body


def _expected_claude_rules(src: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for mdc in sorted(src.glob("*.mdc")):
        if mdc.stem in CURSOR_ONLY_RULES:
            continue
        text = claude_rule_text(mdc.read_text(encoding="utf-8"))
        if text is not None:
            expected[f"{mdc.stem}.md"] = text
    return expected


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_tree(src: Path, dst: Path) -> None:
    for child in sorted(src.iterdir()):
        if child.is_dir():
            shutil.copytree(child, dst / child.name)
        else:
            shutil.copy2(child, dst / child.name)


def sync_cursor_to_claude(check: bool = False) -> int:
    changes: list[str] = []
    src_root = ROOT / ".cursor"
    dst_root = ROOT / ".claude"

    for src_name, dst_name, mode in SUBDIRS:
        src = src_root / src_name
        dst = dst_root / dst_name
        if not src.is_dir():
            continue

        if mode == "rules":
            expected = _expected_claude_rules(src)
            existing = {p.name for p in dst.iterdir() if p.is_file()} if dst.is_dir() else set()
            if check:
                for name, text in expected.items():
                    target = dst / name
                    if not target.exists():
                        changes.append(f"missing in .claude: rules/{name}")
                    elif target.read_text(encoding="utf-8") != text:
                        changes.append(f"differs: rules/{name}")
                for name in sorted(existing - set(expected)):
                    changes.append(f"stale in .claude: rules/{name}")
                continue
            dst.mkdir(parents=True, exist_ok=True)
            for name in sorted(existing - set(expected)):
                (dst / name).unlink()
            for name, text in expected.items():
                (dst / name).write_text(text, encoding="utf-8")
            print(f"synced rules ({len(expected)} mirrored) -> .claude/rules")
            continue

        if check:
            changes.extend(_diff(src, dst, mode, dst_name))
            continue

        _reset_dir(dst)
        if mode == "tree":
            _copy_tree(src, dst)
        else:
            for md in sorted(src.glob("*.md")):
                shutil.copy2(md, dst / md.name)
        print(f"synced {src_name} -> .claude/{dst_name}")

    if check:
        if changes:
            print("OUT OF SYNC (.cursor/ canonical vs .claude/ mirror):")
            for c in changes:
                print(f"  {c}")
            return 1
        print("assistant trees in sync")
        return 0
    return 0


def sync_claude_to_cursor(check: bool = False) -> int:
    """Framework-original direction: .claude/ -> .cursor/."""
    changes: list[str] = []
    src_root = ROOT / ".claude"
    dst_root = ROOT / ".cursor"

    for src_name, dst_name, mode in SUBDIRS:
        src = src_root / src_name
        dst = dst_root / dst_name
        if not src.is_dir():
            continue

        if mode == "rules":
            if check:
                for md in sorted(src.glob("*.md")):
                    target = dst / f"{md.stem}.mdc"
                    if not target.exists():
                        changes.append(f"missing in .cursor: rules/{target.name}")
                    elif target.read_text(encoding="utf-8") != md.read_text(encoding="utf-8"):
                        changes.append(f"differs: rules/{target.name}")
                continue
            dst.mkdir(parents=True, exist_ok=True)
            for md in sorted(src.glob("*.md")):
                (dst / f"{md.stem}.mdc").write_text(
                    md.read_text(encoding="utf-8"), encoding="utf-8"
                )
            print(f"synced rules -> .cursor/rules")
            continue

        if check:
            changes.extend(_diff(src, dst, mode, dst_name, rules_ext=".mdc"))
            continue

        _reset_dir(dst)
        if mode == "tree":
            _copy_tree(src, dst)
        else:
            for md in sorted(src.glob("*.md")):
                shutil.copy2(md, dst / md.name)
        print(f"synced {src_name} -> .cursor/{dst_name}")

    if check:
        if changes:
            print("OUT OF SYNC:")
            for c in changes:
                print(f"  {c}")
            return 1
        print("in sync")
    return 0


def _expected_name(p: Path, mode: str, rules_ext: str = ".md") -> str:
    if mode == "rules":
        return f"{p.stem}{rules_ext}"
    return p.name


def _diff(src: Path, dst: Path, mode: str, dst_label: str, rules_ext: str = ".md") -> list[str]:
    out: list[str] = []
    if mode == "tree":
        src_names = {c.name for c in src.iterdir()}
        dst_names = {c.name for c in dst.iterdir()} if dst.is_dir() else set()
        for name in sorted(src_names - dst_names):
            out.append(f"missing in mirror: {dst_label}/{name}")
        for name in sorted(dst_names - src_names):
            out.append(f"stale in mirror: {dst_label}/{name}")
        for name in sorted(src_names & dst_names):
            s = src / name
            d = dst / name
            if s.is_dir() and d.is_dir():
                for sub in sorted(s.rglob("*")):
                    if sub.is_file():
                        rel = sub.relative_to(s)
                        mirror = d / rel
                        if not mirror.exists():
                            out.append(f"missing in mirror: {dst_label}/{name}/{rel}")
                        elif mirror.read_text(encoding="utf-8") != sub.read_text(encoding="utf-8"):
                            out.append(f"differs: {dst_label}/{name}/{rel}")
        return out
    pat = "*.md"
    for f in sorted(src.glob(pat)):
        target = dst / _expected_name(f, mode, rules_ext)
        if not target.exists():
            out.append(f"missing in mirror: {dst_label}/{target.name}")
        elif target.read_text(encoding="utf-8") != f.read_text(encoding="utf-8"):
            out.append(f"differs: {dst_label}/{target.name}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync .cursor/ and .claude/ assistant trees")
    ap.add_argument(
        "--direction",
        choices=("cursor-to-claude", "claude-to-cursor"),
        default="cursor-to-claude",
        help="Sync direction (default: cursor-to-claude for this repo)",
    )
    ap.add_argument("--check", action="store_true", help="Report drift without writing (CI gate)")
    args = ap.parse_args()

    if args.direction == "cursor-to-claude":
        return sync_cursor_to_claude(check=args.check)
    return sync_claude_to_cursor(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
