"""vexlum CLI: ``python -m modules.vexlum <command>``.

Commands::

    mcp                         stdio MCP server (search / resolve / execute)
    worker                      JSONL worker for the TS host (mcp-server/)
    search QUERY [--source S] [--category C] [--tier T] [--limit N] [--schemas]
    resolve ACTION_ID
    exec ACTION_ID [--args JSON | --args-file PATH] [--dry-run] [--confirm] [--token T]
    list [--source S] [--category C] [--tier T]
    status

Exit codes: 0 success, 1 action error, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vexlum", description="Vexlum Scoring: search -> resolve -> execute")
    p.add_argument("--json", action="store_true", help="print raw JSON envelopes")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("mcp", help="run the stdio MCP server")
    sub.add_parser("worker", help="run the JSONL worker for the TS host")

    s = sub.add_parser("search", help="find actions")
    s.add_argument("query", nargs="*")
    s.add_argument("--source", choices=["tool", "api", "db", "browser", "system"])
    s.add_argument("--category")
    s.add_argument("--tier", choices=["read", "write", "destructive"])
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--schemas", action="store_true")

    r = sub.add_parser("resolve", help="show one action's contract")
    r.add_argument("action_id")

    e = sub.add_parser("exec", aliases=["execute"], help="run an action")
    e.add_argument("action_id")
    g = e.add_mutually_exclusive_group()
    g.add_argument("--args", dest="args_json", help="JSON object of arguments")
    g.add_argument("--args-file", help="path to a JSON file with arguments")
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--confirm", action="store_true", help="confirmed=true (write/destructive tiers)")
    e.add_argument("--token", help="confirm_token from a dry run (destructive tier)")
    e.add_argument("--request-id")

    lst = sub.add_parser("list", help="list actions (no query)")
    lst.add_argument("--source", choices=["tool", "api", "db", "browser", "system"])
    lst.add_argument("--category")
    lst.add_argument("--tier", choices=["read", "write", "destructive"])

    sub.add_parser("status", help="catalog, DB, API and SSE reachability")
    return p


def _load_args(ns: argparse.Namespace) -> dict[str, Any]:
    if ns.args_file:
        raw = Path(ns.args_file).read_text(encoding="utf-8")
    elif ns.args_json:
        raw = ns.args_json
    else:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("--args must be a JSON object")
    return data


def _print(result: Any, as_json: bool) -> None:
    from modules.vexlum.worker import dumps

    if as_json or not isinstance(result, dict):
        sys.stdout.write(dumps(result, indent=2) + "\n")
        return
    if "results" in result and "query" in result:
        for row in result["results"]:
            req = ",".join(row.get("required_args") or [])
            sys.stdout.write(
                f"{row['confidence']:.2f}  {row['tier']:<11} {row['action_id']:<58} {row.get('title') or ''}"
                + (f"  [req: {req}]" if req else "")
                + "\n"
            )
        if result.get("low_confidence"):
            sys.stdout.write("(low confidence: refine the query or filter with --source/--category)\n")
        return
    if result.get("status") == "error":
        sys.stdout.write(f"error [{result.get('code')}]: {result.get('message')}\n")
        details = result.get("details")
        if details:
            sys.stdout.write(dumps(details, indent=2) + "\n")
        return
    sys.stdout.write(dumps(result, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    ns = _parser().parse_args(argv)

    if ns.command == "mcp":
        from modules.vexlum.mcp_stdio import run_stdio

        run_stdio()
        return 0
    if ns.command == "worker":
        from modules.vexlum.worker import main as worker_main

        return worker_main()

    import logging

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    from modules.vexlum import service

    if ns.command == "search":
        result: dict[str, Any] = service.search(" ".join(ns.query), limit=ns.limit, source=ns.source,
                                                category=ns.category, tier=ns.tier, include_schemas=ns.schemas)
    elif ns.command == "list":
        listed = service.list_actions(source=ns.source, category=ns.category, tier=ns.tier)
        rows = listed["actions"]
        if ns.json:
            _print(listed, True)
        else:
            for r in rows:
                sys.stdout.write(f"{r['tier']:<11} {r['action_id']:<58} {r['title'] or ''}\n")
            sys.stdout.write(f"{len(rows)} actions\n")
        return 0
    elif ns.command == "resolve":
        result = service.resolve(ns.action_id)
    elif ns.command in ("exec", "execute"):
        try:
            args = _load_args(ns)
        except (ValueError, OSError) as exc:
            sys.stderr.write(f"vexlum: bad arguments: {exc}\n")
            return 2
        result = service.execute(ns.action_id, args, dry_run=ns.dry_run, confirmed=ns.confirm,
                                 confirm_token=ns.token, request_id=ns.request_id)
        if result.get("status") == "proxy":
            result = {
                "status": "error",
                "code": "browser_needs_ts_host",
                "message": "browser.* actions run in the TS host: node mcp-server/dist/vexlum.js exec ...",
            }
    elif ns.command == "status":
        result = service.execute("system.status")
    else:  # pragma: no cover - argparse enforces choices
        return 2

    _print(result, ns.json)
    return 1 if isinstance(result, dict) and result.get("status") == "error" else 0
