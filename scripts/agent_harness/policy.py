"""Deterministic policy layer: file sensitivity, command rules, script inspection.

This is the cheap first pass. It decides the clear cases on its own and hands
only the residue to Jev. It never returns ``allow``; granting is left to the
settings allowlist, so the harness can only tighten permissions.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

PUBLIC, STANDARD, RESTRICTED, UNKNOWN = "public", "standard", "restricted", "unknown"

# Secret-bearing files. Repos extend this via ``restricted_globs`` in
# .agent/jev_harness.json (e.g. the gallery's config.json holds DB DSNs).
BASE_RESTRICTED = (
    "secrets.json",
    "**/secrets.json",
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "**/*.pem",
    "**/*.key",
    "id_rsa*",
    "id_ed25519*",
    "**/.ssh/**",
    "~/.ssh/**",
    ".npmrc",
    ".pypirc",
)
BASE_PUBLIC = (
    "*.md",
    "**/*.md",
    "docs/**",
    "LICENSE*",
    "*.example",
    "*.example.*",
    "**/*.example.*",
    ".env.example",
)
BASE_STANDARD = (
    "modules/**",
    "scripts/**",
    "tests/**",
    "migrations/**",
    "frontend/src/**",
    "src/**",
    "electron/**",
    "mcp-server/src/**",
    "server/**",
    "*.py",
    "*.ts",
    "*.tsx",
)
# ``.example`` files are documentation even when they look like env/config.
_NEVER_RESTRICTED = (".env.example", "*.example", "*.example.*", "**/*.example.*")

# Verbs that only touch metadata, so naming a restricted path is fine.
_METADATA_VERBS = {"ls", "stat", "test", "file", "du", "echo", "printf"}
# Search verbs whose first positional argument is a pattern, not a path.
_SEARCH_VERBS = {"rg", "grep", "egrep", "fgrep", "ag"}
_GIT_METADATA = {"check-ignore", "ls-files", "status", "rm"}

_SCRATCH_PREFIXES = (
    ".agent/scratch",
    ".agent-runs",
    "/tmp",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
    ".ruff_cache",
    "thumbnails/tmp",
)


def _matches(rel: str, patterns: tuple[str, ...] | list[str]) -> bool:
    name = PurePosixPath(rel).name
    for pat in patterns:
        if fnmatch.fnmatchcase(rel, pat) or ("/" not in pat and fnmatch.fnmatchcase(name, pat)):
            return True
    return False


def normalize_path(path: str, repo: Path | None = None) -> str:
    """Repo-relative POSIX path when inside ``repo``; else the cleaned input."""
    raw = path.strip().strip("'\"").replace("\\", "/")
    if repo is not None:
        try:
            p = Path(raw)
            if p.is_absolute():
                return p.resolve().relative_to(repo.resolve()).as_posix()
        except (ValueError, OSError):
            pass
    while raw.startswith("./"):
        raw = raw[2:]
    return raw


def classify_path(path: str, repo: Path | None = None, config: dict[str, Any] | None = None) -> str:
    """``restricted`` > ``public`` > ``standard``; ``unknown`` otherwise."""
    cfg = config or {}
    rel = normalize_path(path, repo)
    restricted = tuple(BASE_RESTRICTED) + tuple(cfg.get("restricted_globs") or ())
    if _matches(rel, restricted) and not _matches(rel, _NEVER_RESTRICTED):
        return RESTRICTED
    if _matches(rel, tuple(BASE_PUBLIC) + tuple(cfg.get("public_globs") or ())):
        return PUBLIC
    if _matches(rel, tuple(BASE_STANDARD) + tuple(cfg.get("standard_globs") or ())):
        return STANDARD
    return UNKNOWN


@dataclass
class Verdict:
    """Deterministic outcome for one command. ``decision`` is deny/ask/None."""

    decision: str | None = None
    reasons: list[str] = field(default_factory=list)
    script: str | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    excerpt: str = ""

    def escalate(self, decision: str, reason: str) -> None:
        order = {None: 0, "ask": 1, "deny": 2}
        if order[decision] > order[self.decision]:
            self.decision = decision
        self.reasons.append(reason)


def split_segments(command: str) -> list[list[str]]:
    """Split a shell line on ``&& || ; |`` into token lists (best effort)."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok and set(tok) <= set(";&|"):
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def _strip_env(tokens: list[str]) -> list[str]:
    i = 0
    while i < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]):
        i += 1
    if i < len(tokens) and tokens[i] in {"sudo", "env", "time", "nice", "timeout"}:
        i += 1
        while i < len(tokens) and (tokens[i].startswith("-") or tokens[i][:1].isdigit()):
            i += 1
    return tokens[i:]


def _verb(tokens: list[str]) -> str:
    return PurePosixPath(tokens[0].replace("\\", "/")).name.lower() if tokens else ""


def _is_scratch(target: str) -> bool:
    t = normalize_path(target)
    return any(t == p or t.startswith(p + "/") for p in _SCRATCH_PREFIXES)


def check_command(command: str, repo: Path, config: dict[str, Any] | None = None) -> Verdict:
    """Apply the deterministic command policy to one Bash tool call."""
    cfg = config or {}
    verdict = Verdict()
    if "extensions.worktreeConfig" in command or "worktreeconfig" in command.lower():
        verdict.escalate("deny", "touches extensions.worktreeConfig (breaks embedded git libraries)")
    if re.search(r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+(TABLE\s+)?\w)", command, re.I):
        verdict.escalate("ask", "destructive SQL in command")

    for raw in split_segments(command):
        tokens = _strip_env(raw)
        if not tokens:
            continue
        verb = _verb(tokens)
        args = tokens[1:]

        # Restricted files: naming one is a deny unless the verb is metadata-only.
        git_sub = args[0] if verb == "git" and args else ""
        metadata_only = verb in _METADATA_VERBS or (verb == "git" and git_sub in _GIT_METADATA)
        for tok in _path_like_tokens(verb, tokens):
            candidate = tok.lstrip("@<>")
            if classify_path(candidate, repo, cfg) == RESTRICTED and not metadata_only:
                verdict.escalate("deny", f"reads or ships restricted file {candidate!r}")

        if verb == "git":
            _check_git(args, verdict)
        elif verb == "rm" and any(
            a == "--recursive" or (re.fullmatch(r"-[A-Za-z]+", a) and "r" in a.lower()) for a in args
        ):
            targets = [a for a in args if not a.startswith("-")]
            outside = [t for t in targets if not _is_scratch(t)]
            if outside:
                verdict.escalate("ask", f"recursive delete outside scratch: {' '.join(outside)[:120]}")
        elif verb == "alembic" and "downgrade" in args:
            verdict.escalate("ask", "alembic downgrade rewrites the schema")
        elif verb in {"docker", "docker-compose"}:
            joined = " ".join(args)
            if re.search(r"\bdown\b", joined) and re.search(r"(^|\s)(-v|--volumes)\b", joined):
                verdict.escalate("ask", "docker compose down -v deletes volumes (the database)")
            if re.search(r"\bvolume\s+(rm|prune)\b", joined):
                verdict.escalate("ask", "docker volume removal")
        elif verb == "psql":
            joined = " ".join(args)
            if re.search(r"\bDELETE\s+FROM\b(?![^;]*\bWHERE\b)", joined, re.I):
                verdict.escalate("ask", "DELETE without WHERE via psql")

        script = find_script(tokens, repo)
        if script is not None and verdict.script is None:
            if not _matches(script, tuple(cfg.get("inspect_skip") or ())):
                inspect_script(repo / script, script, verdict)
    return verdict


def _path_like_tokens(verb: str, tokens: list[str]) -> list[str]:
    """Tokens that could name a file: no flags, no prose, no search patterns."""
    out: list[str] = []
    skip_next = False
    pattern_seen = verb not in _SEARCH_VERBS
    for tok in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if tok in {"-e", "--regexp", "-m", "--message"}:
            skip_next = True
            pattern_seen = True
            continue
        if not tok or tok.startswith("-") or any(c.isspace() for c in tok):
            continue
        if not pattern_seen:
            pattern_seen = True
            continue
        out.append(tok)
    return out


def _check_git(args: list[str], verdict: Verdict) -> None:
    if not args:
        return
    sub, rest = args[0], args[1:]
    if sub == "config":
        read_flags = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin"}
        if any(a in read_flags for a in rest) or len([a for a in rest if not a.startswith("-")]) <= 1:
            return
        if "--global" in rest or "--system" in rest:
            verdict.escalate("ask", "git config write outside this repo")
        else:
            verdict.escalate("deny", "git config write modifies .git/config (forbidden by repo rules)")
    elif sub == "push" and any(a in {"--force", "-f"} or a.startswith("--force") or a.startswith("+") for a in rest):
        protected = any(re.search(r"(^|[:+/])(master|main)$", a) for a in rest)
        if protected:
            verdict.escalate("deny", "force-push to master/main")
        else:
            verdict.escalate("ask", "force-push rewrites remote history")
    elif sub == "reset" and "--hard" in rest:
        verdict.escalate("ask", "git reset --hard discards local work")
    elif sub == "clean" and any(a.startswith("-") and "f" in a for a in rest):
        verdict.escalate("ask", "git clean -f deletes untracked files")


_INTERPRETERS = {
    "python": (".py",),
    "python3": (".py",),
    "py": (".py",),
    "bash": (".sh",),
    "sh": (".sh",),
    "zsh": (".sh",),
    "pwsh": (".ps1",),
    "powershell": (".ps1",),
    "node": (".js", ".mjs", ".cjs"),
}


def find_script(tokens: list[str], repo: Path) -> str | None:
    """Repo-relative script run by this segment, if it is a file in ``repo``."""
    verb = _verb(tokens)
    if re.fullmatch(r"python3(\.\d+)?", verb):
        verb = "python3"
    candidates: list[str] = []
    if verb in _INTERPRETERS:
        args = tokens[1:]
        i = 0
        while i < len(args):
            a = args[i]
            if a == "-m" and i + 1 < len(args):
                candidates.append(args[i + 1].replace(".", "/") + ".py")
                break
            if a in {"-c", "-e", "-Command", "-command"}:
                return None
            if a.lower() in {"-file"} and i + 1 < len(args):
                candidates.append(args[i + 1])
                break
            if not a.startswith("-"):
                candidates.append(a)
                break
            i += 1
    elif tokens[0].endswith((".py", ".sh", ".ps1")):
        candidates.append(tokens[0])
    for cand in candidates:
        rel = normalize_path(cand, repo)
        path = repo / rel
        try:
            if path.is_file() and path.resolve().is_relative_to(repo.resolve()):
                return rel
        except OSError:
            continue
    return None


_FINDING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("secret_read", re.compile(r"secrets\.json|(?<![\w.])\.env(?![\w.]*example)\b|id_rsa|\.ssh/")),
    (
        "network_client",
        re.compile(
            r"\brequests\.(get|post|put|patch|delete|request)\(|\bhttpx\.|urllib\.request|"
            r"\burlopen\(|\baiohttp\b|\bcurl\s|\bwget\s|Invoke-WebRequest|Invoke-RestMethod|\bfetch\("
        ),
    ),
    (
        "destructive_sql",
        re.compile(
            r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX)\b|\bTRUNCATE\b|"
            r"\bDELETE\s+FROM\s+[\w.\"]+\s*(;|\"|'|$)",
            re.I,
        ),
    ),
    ("recursive_delete", re.compile(r"shutil\.rmtree|\brm\s+-[a-z]*r[a-z]*f|Remove-Item[^\n]*-Recurse")),
)
_URL = re.compile(r"https?://([^/\s'\"):]+)")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", "host.docker.internal"}
_MAX_SCRIPT_BYTES = 256 * 1024


def inspect_script(path: Path, rel: str, verdict: Verdict) -> None:
    """Read a script before it runs and escalate to ``ask`` on risky content."""
    verdict.script = rel
    try:
        text = path.read_bytes()[:_MAX_SCRIPT_BYTES].decode("utf-8", errors="replace")
    except OSError:
        return
    lines = text.splitlines()
    remote_urls = [
        (i, m.group(1))
        for i, line in enumerate(lines, 1)
        for m in _URL.finditer(line)
        if m.group(1).lower() not in _LOCAL_HOSTS
    ]
    flagged: set[int] = set()
    for kind, pattern in _FINDING_PATTERNS:
        hits = [i for i, line in enumerate(lines, 1) if pattern.search(line)]
        if not hits:
            continue
        if kind == "network_client":
            if not remote_urls:
                continue  # clients that only talk to localhost are the norm here
            kind = "network_egress"
            hits = hits + [i for i, _ in remote_urls]
        verdict.findings.append({"kind": kind, "lines": sorted(set(hits))[:10]})
        flagged.update(hits[:10])
    for f in verdict.findings:
        verdict.escalate("ask", f"script {rel} {f['kind'].replace('_', ' ')} (lines {f['lines'][:5]})")
    verdict.excerpt = _excerpt(lines, flagged)


def _excerpt(lines: list[str], flagged: set[int], context: int = 2, limit: int = 60) -> str:
    if not flagged:
        chosen = range(1, min(len(lines), 40) + 1)
    else:
        wanted: set[int] = set()
        for n in sorted(flagged):
            wanted.update(range(max(1, n - context), min(len(lines), n + context) + 1))
        chosen = sorted(wanted)[:limit]
    return "\n".join(f"{n}: {lines[n - 1][:200]}" for n in chosen)
