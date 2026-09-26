#!/usr/bin/env python3
"""Jev agent harness CLI.

    python scripts/agent_harness/cli.py budget  [--json]
    python scripts/agent_harness/cli.py check   "<shell command>"
    python scripts/agent_harness/cli.py packs   "<request text>"
    python scripts/agent_harness/cli.py route   --task "<subtask>" --files a.py b.py
    python scripts/agent_harness/cli.py subgoal add "<text>" | list | done <id> | drop <id>
    python scripts/agent_harness/cli.py bundle  [--base origin/master] [--question ...]

``--repo`` targets another checkout (the gallery calls this backend copy).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.agent_harness import budget, bundle, policy, route, subgoals  # noqa: E402
from scripts.agent_harness import packs as packs_mod  # noqa: E402
from scripts.agent_harness.hook import _pack_rungs  # noqa: E402
from scripts.agent_harness.jev_gate import JevGate, resolve_repo  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Jev agent harness")
    ap.add_argument("--repo", default=None, help="target repo (default: CLAUDE_PROJECT_DIR or cwd)")
    ap.add_argument("--session", default="cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("budget", help="always-on instruction size")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("check", help="dry-run the command policy")
    p.add_argument("command")

    p = sub.add_parser("packs", help="which instruction packs a request would get")
    p.add_argument("request")

    p = sub.add_parser("route", help="price a subtask per context rebuild")
    p.add_argument("--task", required=True)
    p.add_argument("--files", nargs="*", default=[])
    p.add_argument("--session-tokens", type=int, default=50_000)
    p.add_argument("--output-tokens", type=int, default=2_000)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("subgoal", help="register/deduplicate subgoals")
    p.add_argument("action", choices=["add", "list", "done", "drop"])
    p.add_argument("value", nargs="?")
    p.add_argument("--ledger", default=None)

    p = sub.add_parser("bundle", help="shared retrieval bundle for reviewers")
    p.add_argument("--base", default=None)
    p.add_argument("--question", default="Review this change for correctness bugs.")
    p.add_argument("--budget-chars", type=int, default=60_000)
    p.add_argument("--refresh", action="store_true")

    args = ap.parse_args(argv)
    repo = resolve_repo(args.repo)
    gate = JevGate(repo=repo, session_id=args.session)

    if args.cmd == "budget":
        report = budget.measure(repo)
        print(json.dumps(report, indent=2) if args.json else budget.format_report(report))
    elif args.cmd == "check":
        v = policy.check_command(args.command, repo, gate.config)
        print(json.dumps({"decision": v.decision, "reasons": v.reasons, "script": v.script, "findings": v.findings}, indent=2))
    elif args.cmd == "packs":
        packs = packs_mod.load_packs(repo, gate.config)
        rungs = _pack_rungs(gate, packs, args.request)
        print(json.dumps({n: r for n, r in rungs.items() if r != "hide"}, indent=2))
    elif args.cmd == "route":
        est = route.estimate(gate, args.task, args.files, session_tokens=args.session_tokens, output_tokens=args.output_tokens)
        print(json.dumps(est.to_dict(), indent=2) if args.json else route.format_estimate(est, args.files))
    elif args.cmd == "subgoal":
        ledger = Path(args.ledger) if args.ledger else subgoals.default_ledger(gate)
        if args.action == "list":
            for rec in subgoals.load(ledger):
                print(f"{rec['id']}  [{rec.get('status')}]  {rec.get('text', '')}")
        elif not args.value:
            ap.error(f"subgoal {args.action} needs a value")
        elif args.action == "add":
            print(json.dumps(subgoals.add(gate, args.value, ledger)))
        else:
            subgoals.set_status(ledger, args.value, "done" if args.action == "done" else "dropped")
    elif args.cmd == "bundle":
        path, info = bundle.build(
            gate, base=args.base, question=args.question, budget_chars=args.budget_chars, refresh=args.refresh
        )
        print(json.dumps({"bundle": str(path.relative_to(repo)), **info}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
