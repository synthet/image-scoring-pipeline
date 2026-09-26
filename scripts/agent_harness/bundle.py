"""One shared retrieval pass for read-only reviewers (Jev design note §X).

Finding what is relevant to a change is the expensive part of every review.
Build it once per HEAD (+ dirty state) into ``.agent-runs/bundle-<key>.md`` and
let every read-only consumer — cross-model review, critical-commit audit,
PR-ready hygiene — start from the same file.

Each changed file is a chunk on the visibility ladder (hide / short / full),
chosen by Jev against the review question when available, then trimmed to the
character budget. Restricted files are listed as excluded and never read.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.agent_harness import policy
from scripts.agent_harness.jev_gate import JevGate, top_choice

RUNG_RANK = {"hide": 0, "short": 1, "full": 2}


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace"
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def default_base(repo: Path) -> str:
    for ref in ("origin/master", "origin/main", "master", "main"):
        if _git(repo, "rev-parse", "--verify", "--quiet", ref).strip():
            return ref
    return "HEAD~1"


def _bundle_key(repo: Path, base: str, question: str) -> str:
    head = _git(repo, "rev-parse", "HEAD").strip()[:12] or "nohead"
    dirty = _git(repo, "diff", base, "--stat")
    digest = hashlib.sha256((base + question + dirty).encode("utf-8")).hexdigest()[:8]
    return f"{head}-{digest}"


def _referencing_files(repo: Path, path: str, limit: int = 5) -> list[str]:
    stem = Path(path).stem
    if len(stem) < 4 or stem in {"index", "__init__", "utils", "types"}:
        return []
    try:
        out = subprocess.run(
            ["rg", "-l", "--max-count", "1", "-w", stem, "--glob", "!*.md", "."],
            cwd=repo, capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    hits = [h.removeprefix("./") for h in out.splitlines() if h.removeprefix("./") != path]
    return sorted(hits)[:limit]


def build(
    gate: JevGate,
    *,
    base: str | None = None,
    question: str = "Review this change for correctness bugs.",
    budget_chars: int = 60_000,
    refresh: bool = False,
) -> tuple[Path, dict[str, Any]]:
    repo = gate.repo
    base = base or default_base(repo)
    out_dir = repo / ".agent-runs"
    out_path = out_dir / f"bundle-{_bundle_key(repo, base, question)}.md"
    if out_path.exists() and not refresh:
        return out_path, {"reused": True}

    names = [n for n in _git(repo, "diff", "--name-only", base).splitlines() if n]
    numstat = {}
    for line in _git(repo, "diff", "--numstat", base).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            numstat[parts[2]] = f"+{parts[0]} -{parts[1]}"

    excluded = [n for n in names if policy.classify_path(n, repo, gate.config) == policy.RESTRICTED]
    files = [n for n in names if n not in excluded]
    diffs = {f: _git(repo, "diff", base, "--", f) for f in files}
    summaries = {
        f: f"{numstat.get(f, '')} hunks: "
        + "; ".join(re.findall(r"^@@[^@]*@@ ?(.*)$", diffs[f], re.M)[:6])
        for f in files
    }

    rungs = {f: "full" for f in files}
    if files:
        answers = gate.ask_subjects(
            "context", "harness.bundle.visibility", {"request": question, "changed_files": summaries}, files
        )
        if answers and gate.acts("context"):
            min_conf = float(gate.config.get("min_confidence", 0.5))
            for f, a in answers.items():
                label, p = top_choice(a)
                if label in RUNG_RANK and p >= min_conf:
                    rungs[f] = label

    # Fit the budget: demote the largest full diffs to short until it fits.
    def size() -> int:
        return sum(len(diffs[f]) if r == "full" else len(summaries[f]) for f, r in rungs.items())

    for f in sorted(files, key=lambda f: -len(diffs[f])):
        if size() <= budget_chars:
            break
        if rungs[f] == "full":
            rungs[f] = "short"

    head = _git(repo, "rev-parse", "--short", "HEAD").strip()
    parts = [
        f"# Review bundle — {repo.name} @ {head} vs {base}",
        "",
        f"Question: {question}",
        "",
        "Built once by `python scripts/agent_harness/cli.py bundle`; every read-only reviewer should start here "
        "instead of re-running its own search. Rungs chosen per file (full / short / hide).",
        "",
        "## Changed files",
        "",
    ]
    for f in files:
        refs = _referencing_files(repo, f) if rungs[f] != "hide" else []
        ref_txt = f" — referenced by: {', '.join(refs)}" if refs else ""
        parts.append(f"- `{f}` [{rungs[f]}] {numstat.get(f, '')}{ref_txt}")
    if excluded:
        parts += ["", "## Excluded (restricted — never send to external reviewers)", ""]
        parts += [f"- `{f}`" for f in excluded]
    for f in files:
        if rungs[f] == "full":
            parts += ["", f"## {f}", "", "```diff", diffs[f].rstrip(), "```"]
        elif rungs[f] == "short":
            parts += ["", f"## {f} (summary)", "", summaries[f]]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    gate.log_event({"decision": "bundle", "path": out_path.name, "rungs": rungs, "excluded": excluded})
    return out_path, {"reused": False, "rungs": rungs, "excluded": excluded}
