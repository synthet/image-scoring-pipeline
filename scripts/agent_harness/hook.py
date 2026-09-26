#!/usr/bin/env python3
"""Claude Code hook entrypoint for the Jev harness.

Usage (from .claude/settings.json)::

    python "$CLAUDE_PROJECT_DIR/scripts/agent_harness/hook.py" <event> [--repo PATH]

Events:
  user-prompt     UserPromptSubmit — inject conditional instruction packs
  session-compact SessionStart(compact) — re-pin packs after compaction
  pre-bash        PreToolUse(Bash) — programmable permissions
  pre-review      PreToolUse(mcp__*__run_subagent) — sensitivity routing

Reads the event JSON on stdin, writes hook JSON on stdout. Any internal error
exits 0 with no output, which leaves Claude Code's normal behaviour in place.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent_harness import packs as packs_mod  # noqa: E402
from scripts.agent_harness import policy  # noqa: E402
from scripts.agent_harness.jev_gate import (  # noqa: E402
    JevGate,
    STATE_REL,
    contains_secret,
    redact,
    resolve_repo,
    top_choice,
)

logger = logging.getLogger("agent_harness")

_HEADER = "[jev-harness] Conditional instructions selected for this request."
_PIN_HEADER = "[jev-harness] Re-pinned instructions that were active before compaction."
_SHORT_PROMPT = 20
_PROMPT_KEEP = 2000


def _pack_rungs(gate: JevGate, packs: list[packs_mod.Pack], prompt: str) -> dict[str, str]:
    """Rung per pack: deterministic prefilter, Jev when it is allowed to act."""
    fallback = packs_mod.deterministic_rungs(packs, prompt)
    if not packs or (len(prompt.strip()) < _SHORT_PROMPT and not any(r != "hide" for r in fallback.values())):
        return fallback
    state = {
        "request": prompt[:_PROMPT_KEEP],
        "repository": gate.repo.name,
        "packs": {p.name: p.description for p in packs},
    }
    answers = gate.ask_subjects("context", "harness.context.visibility", state, [p.name for p in packs])
    if not answers or not gate.acts("context"):
        return fallback
    min_conf = float(gate.config.get("min_confidence", 0.5))
    rungs = dict(fallback)
    for name, answer in answers.items():
        label, p = top_choice(answer)
        if label in packs_mod.RANK and p >= min_conf:
            rungs[name] = label
    return rungs


def on_user_prompt(event: dict[str, Any], gate: JevGate) -> dict[str, Any] | None:
    prompt = str(event.get("prompt") or "")
    session = gate.load_session()
    session["last_prompt"] = redact(prompt[:300])
    packs = packs_mod.load_packs(gate.repo, gate.config)
    rungs = _pack_rungs(gate, packs, prompt)

    injected: dict[str, str] = dict(session.get("injected") or {})
    new = {
        n: r
        for n, r in rungs.items()
        if packs_mod.RANK.get(r, 0) > packs_mod.RANK.get(injected.get(n, "hide"), 0)
    }
    injected.update(new)
    session["injected"] = injected
    gate.save_session(session)
    gate.log_event({"decision": "context", "event": "user-prompt", "injected": new})

    text = packs_mod.render_injection(packs, new, _HEADER)
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}


def on_session_compact(event: dict[str, Any], gate: JevGate) -> dict[str, Any] | None:
    session = gate.load_session()
    injected = {n: r for n, r in (session.get("injected") or {}).items() if r != "hide"}
    if not injected:
        return None
    packs = packs_mod.load_packs(gate.repo, gate.config)
    text = packs_mod.render_injection(packs, injected, _PIN_HEADER)
    gate.log_event({"decision": "context", "event": "session-compact", "pinned": injected})
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def _permission_output(decision: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": "jev-harness: " + "; ".join(dict.fromkeys(reasons))[:600],
        }
    }


def on_pre_bash(event: dict[str, Any], gate: JevGate) -> dict[str, Any] | None:
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return None
    verdict = policy.check_command(command, gate.repo, gate.config)

    if verdict.script and verdict.decision != "deny":
        session = gate.load_session()
        state = {
            "command": command[:500],
            "script": verdict.script,
            "findings": verdict.findings,
            "script_excerpt": verdict.excerpt[:4000],
            "deterministic_decision": verdict.decision or "no objection",
            "task_scope": session.get("last_prompt") or "",
            "policy": (
                "Deny: reading or shipping secrets, writing .git/config. "
                "Ask: sending data off the machine, destructive SQL or deletes, "
                "anything the task scope does not justify."
            ),
        }
        answer = gate.ask("permission", "harness.permission.exec", state)
        label, p = top_choice(answer)
        if answer and gate.acts("permission"):
            # Escalate only — Jev never relaxes the deterministic floor.
            if label == "deny" and p >= float(gate.config.get("permission_deny_threshold", 0.8)):
                verdict.escalate("deny", f"Jev judged unsafe (p={p:.2f})")
            elif label == "ask" and p >= float(gate.config.get("permission_ask_threshold", 0.6)):
                verdict.escalate("ask", f"Jev asks for confirmation (p={p:.2f})")

    if verdict.decision or verdict.findings:
        gate.log_event(
            {
                "decision": "permission",
                "event": "pre-bash",
                "command": redact(command[:200]),
                "verdict": verdict.decision,
                "reasons": verdict.reasons,
            }
        )
    if verdict.decision:
        return _permission_output(verdict.decision, verdict.reasons)
    return None


def _review_files(tool_input: dict[str, Any]) -> list[str]:
    files = tool_input.get("files") or []
    if isinstance(files, str):
        files = [files]
    return [str(f) for f in files if f]


def on_pre_review(event: dict[str, Any], gate: JevGate) -> dict[str, Any] | None:
    tool_input = event.get("tool_input") or {}
    files = _review_files(tool_input)
    reasons: list[str] = []
    decision: str | None = None

    for key in ("task", "extraContext", "extra_context", "prompt"):
        if contains_secret(str(tool_input.get(key) or "")):
            decision = "deny"
            reasons.append(f"{key} contains a secret-looking value; remove it before sending to an external reviewer")

    classes = {f: policy.classify_path(f, gate.repo, gate.config) for f in files}
    restricted = [f for f, c in classes.items() if c == policy.RESTRICTED]
    if restricted:
        decision = "deny"
        reasons.append("restricted files must not go to external reviewers: " + ", ".join(restricted[:10]))

    unknown = [f for f, c in classes.items() if c == policy.UNKNOWN]
    if unknown and decision != "deny":
        meta = {}
        for f in unknown[:25]:
            path = gate.repo / policy.normalize_path(f, gate.repo)
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            meta[f] = {"extension": Path(f).suffix, "directory": str(Path(f).parent), "size_bytes": size}
        answers = gate.ask_subjects(
            "review_sensitivity", "harness.review.sensitivity", {"files": meta}, list(meta)
        )
        if answers and gate.acts("review_sensitivity"):
            threshold = float(gate.config.get("sensitivity_threshold", 0.6))
            flagged = [f for f, a in answers.items() if top_choice(a)[0] == "restricted" and top_choice(a)[1] >= threshold]
            if flagged:
                decision = "deny"
                reasons.append("Jev classified as restricted: " + ", ".join(flagged[:10]))

    gate.log_event(
        {"decision": "review_sensitivity", "event": "pre-review", "files": classes, "verdict": decision}
    )
    if decision:
        return _permission_output(decision, reasons)
    return None


HANDLERS = {
    "user-prompt": on_user_prompt,
    "session-compact": on_session_compact,
    "pre-bash": on_pre_bash,
    "pre-review": on_pre_review,
}


def run(event_name: str, event: dict[str, Any], repo: str | None = None, gate: JevGate | None = None) -> dict[str, Any] | None:
    if gate is None:
        target = resolve_repo(repo, event.get("cwd"))
        gate = JevGate(repo=target, session_id=event.get("session_id"))
    return HANDLERS[event_name](event, gate)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("event", choices=sorted(HANDLERS))
    parser.add_argument("--repo", default=None)
    args = parser.parse_args(argv)
    try:
        event = json.loads(sys.stdin.read() or "{}")
        target = resolve_repo(args.repo, event.get("cwd"))
        log_dir = target / STATE_REL
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_dir / "harness.log"),
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
        out = run(args.event, event, repo=str(target))
        if out:
            sys.stdout.write(json.dumps(out))
    except Exception:  # noqa: BLE001 - a hook must never break the session
        logger.exception("hook %s failed", args.event)
    return 0


if __name__ == "__main__":
    sys.exit(main())
