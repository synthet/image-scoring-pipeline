"""Subgoal ledger with deduplication (Jev design note §VI.B).

Before spawning a subtask in a goal-driven loop, register it here. Exact and
near-exact repeats are caught deterministically; the remaining close
candidates are put to Jev in one call. Work already done or in flight is never
launched twice.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from scripts.agent_harness.jev_gate import JevGate, noul_value

_WORD = re.compile(r"[a-z0-9_]+")
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "is", "it", "this", "that"}


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def jaccard(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def default_ledger(gate: JevGate) -> Path:
    return gate.state_dir / "subgoals.jsonl"


def load(ledger: Path) -> list[dict[str, Any]]:
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    # Last record per id wins (status updates are appended).
    latest: dict[str, dict[str, Any]] = {}
    for rec in out:
        latest[rec["id"]] = {**latest.get(rec["id"], {}), **rec}
    return list(latest.values())


def _append(ledger: Path, record: dict[str, Any]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def add(gate: JevGate, text: str, ledger: Path | None = None) -> dict[str, Any]:
    """Register ``text`` unless it duplicates a live subgoal."""
    ledger = ledger or default_ledger(gate)
    live = [r for r in load(ledger) if r.get("status") != "dropped"]
    norm = " ".join(sorted(_words(text)))
    for rec in live:
        if " ".join(sorted(_words(rec["text"]))) == norm:
            return {"duplicate_of": rec["id"], "by": "exact", "status": rec.get("status")}

    ranked = sorted(live, key=lambda r: jaccard(text, r["text"]), reverse=True)[:10]
    if ranked and jaccard(text, ranked[0]["text"]) >= 0.85:
        return {"duplicate_of": ranked[0]["id"], "by": "lexical", "status": ranked[0].get("status")}

    if ranked:
        state = {"new_subgoal": text, "prior_subgoals": {r["id"]: r["text"] for r in ranked}}
        answers = gate.ask_subjects("subgoal_dedup", "harness.subgoal.duplicate", state, [r["id"] for r in ranked])
        if answers and gate.acts("subgoal_dedup"):
            best = max(answers.items(), key=lambda kv: noul_value(kv[1]) or 0.0)
            p = noul_value(best[1]) or 0.0
            if p >= float(gate.config.get("subgoal_duplicate_threshold", 0.7)):
                prior = next(r for r in ranked if r["id"] == best[0])
                return {"duplicate_of": best[0], "by": "jev", "p": round(p, 3), "status": prior.get("status")}

    new_id = f"sg-{len(load(ledger)) + 1:03d}"
    _append(ledger, {"id": new_id, "text": text, "status": "in_flight", "t": time.time()})
    return {"registered": new_id}


def set_status(ledger: Path, sid: str, status: str) -> None:
    _append(ledger, {"id": sid, "status": status, "t": time.time()})
