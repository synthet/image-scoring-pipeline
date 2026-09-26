"""Routing priced per context rebuild, not per token.

From the Jev design note: handing work to a cheaper model only saves money
when the helper gets a small purpose-built context and the frontier model does
not have to reread everything the helper produced. This module prices three
paths for one subtask and asks Jev whether the subtask can leave the frontier
model on the brief alone.

Token symbols follow the note: X session context, Y generated output, Z extra
tokens read while working, B the purpose-built brief, S the returned summary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scripts.agent_harness import policy
from scripts.agent_harness.jev_gate import JevGate, noul_value


@dataclass
class RouteEstimate:
    brief_tokens: int
    stay_cost: float
    naive_delegate_cost: float
    brief_delegate_cost: float
    leave_frontier_p: float | None
    restricted_files: list[str]
    recommendation: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def costs(
    *, x: int, y: int, z: int, b: int, s: int, prices: dict[str, Any]
) -> tuple[float, float, float]:
    """(stay, naive delegate, brief delegate) in USD for one subtask."""
    f_in, f_out = float(prices["frontier"]["input"]), float(prices["frontier"]["output"])
    d_in, d_out = float(prices["delegate"]["input"]), float(prices["delegate"]["output"])
    per = 1_000_000
    stay = (f_out * y + f_in * z) / per
    naive = (d_in * x + d_out * y + d_in * z + f_in * (y + z)) / per
    brief = (d_in * b + d_out * y + d_in * z + f_in * s) / per
    return stay, naive, brief


def estimate(
    gate: JevGate,
    task: str,
    files: list[str],
    *,
    session_tokens: int = 50_000,
    output_tokens: int = 2_000,
    read_tokens: int | None = None,
    summary_tokens: int = 400,
) -> RouteEstimate:
    cfg = gate.config.get("route") or {}
    cpt = max(1, int(cfg.get("chars_per_token", 4)))
    sizes = 0
    restricted: list[str] = []
    for f in files:
        if policy.classify_path(f, gate.repo, gate.config) == policy.RESTRICTED:
            restricted.append(f)
        try:
            sizes += (gate.repo / policy.normalize_path(f, gate.repo)).stat().st_size
        except OSError:
            pass
    brief = (len(task) + sizes) // cpt
    z = brief if read_tokens is None else read_tokens
    stay, naive, brief_cost = costs(
        x=session_tokens, y=output_tokens, z=z, b=brief, s=summary_tokens, prices=cfg
    )

    p = None
    if not restricted:
        state = {
            "subtask": task[:2000],
            "brief_files": files[:40],
            "brief_tokens": brief,
            "expected_output_tokens": output_tokens,
        }
        p = noul_value(gate.ask("route", "harness.route.leave_frontier", state))

    threshold = float(cfg.get("leave_frontier_threshold", 0.7))
    if restricted:
        rec, why = "stay", "restricted files: keep on the first-party frontier model, never an external tool"
    elif brief_cost >= stay:
        rec, why = "stay", "delegating costs more than staying even with a purpose-built brief"
    elif p is not None and gate.acts("route"):
        if p >= threshold:
            rec, why = "delegate", f"Jev: brief is sufficient (p={p:.2f}) and brief delegation is cheaper"
        else:
            rec, why = "stay", f"Jev: brief is likely insufficient (p={p:.2f})"
    else:
        rec, why = "delegate?", "cheaper on the brief, but sufficiency is unverified (Jev off/unavailable)"

    gate.log_event({"decision": "route", "task": task[:200], "recommendation": rec, "p": p})
    return RouteEstimate(brief, round(stay, 4), round(naive, 4), round(brief_cost, 4), p, restricted, rec, why)


def format_estimate(est: RouteEstimate, files: list[str]) -> str:
    lines = [
        f"recommendation: {est.recommendation} — {est.reason}",
        f"cost (USD, illustrative prices): stay {est.stay_cost} | naive delegate {est.naive_delegate_cost} | brief delegate {est.brief_delegate_cost}",
        f"brief: ~{est.brief_tokens:,} tokens; leave-frontier p = {est.leave_frontier_p}",
    ]
    if est.recommendation.startswith("delegate"):
        lines.append("hand the sub-agent only: the subtask, these files, and the expected output shape:")
        lines.extend(f"  - {f}" for f in files)
        lines.append("ask for a compact result (findings with file:line), not a transcript")
    return "\n".join(lines)
