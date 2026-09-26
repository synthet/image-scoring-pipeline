"""Mode, budget, cache, redaction and audit log around ``TypeSafeClient``.

Every harness question goes through :class:`JevGate`, which

* reads per-decision modes (``off`` | ``shadow`` | ``on``) from the target
  repo's ``.agent/jev_harness.json`` (``JEV_HARNESS_MODE`` overrides all);
* caps paid calls per session and caches answers by rubric version + evidence
  hash, so repeated questions (the same script run twice) cost nothing;
* redacts secret-looking strings from ``state`` before it leaves the machine;
* appends one JSON line per decision to
  ``.agent/scratch/jev-harness/decisions.jsonl`` for later agreement review.

``shadow`` still asks Jev and logs the answer; callers act only when
:meth:`JevGate.acts` is true.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from modules.typesafe import rubrics as rubrics_mod  # noqa: E402
from modules.typesafe.normalize import Judgment, evidence_hash  # noqa: E402

logger = logging.getLogger(__name__)

MODES = ("off", "shadow", "on")
CONFIG_REL = Path(".agent") / "jev_harness.json"
STATE_REL = Path(".agent") / "scratch" / "jev-harness"
_CACHE_MAX = 500

DEFAULTS: dict[str, Any] = {
    "model": "jev-1.13.0",
    "timeout_seconds": 4,
    "max_calls_per_session": 150,
    "decisions": {
        "context": "on",
        "permission": "shadow",
        "review_sensitivity": "on",
        "route": "on",
        "subgoal_dedup": "on",
        "tool_rerank": "on",
    },
}

# Order matters: the key/value pattern keeps the key name for readability.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "<redacted:private-key>",
    ),
    (
        re.compile(
            r"(?i)\b([\w.-]*(?:api[_-]?key|token|secret|passw(?:or)?d|credential)[\w.-]*)"
            r"(\s*[:=]\s*|\"\s*:\s*\")(['\"]?)[^\s'\",;]{4,}"
        ),
        r"\1\2\3<redacted>",
    ),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "<redacted>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "<redacted>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted>"),
    (re.compile(r"(?i)\b(postgres(?:ql)?|mysql|redis|amqp)://[^\s'\"]+"), r"\1://<redacted>"),
    (re.compile(r"\b[A-Fa-f0-9]{40,}\b"), "<redacted:hex>"),
    # Long base64-ish runs; require a digit and an uppercase letter so plain
    # slash-separated paths survive.
    (
        re.compile(r"\b(?=[A-Za-z0-9+/]*\d)(?=[A-Za-z0-9+/]*[A-Z])[A-Za-z0-9+/]{48,}={0,2}"),
        "<redacted:b64>",
    ),
)


def redact(value: Any) -> Any:
    """Return ``value`` with secret-looking substrings replaced, recursively."""
    if isinstance(value, str):
        out = value
        for pattern, repl in _REDACTIONS:
            out = pattern.sub(repl, out)
        return out
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def contains_secret(text: str) -> bool:
    """True when ``redact`` would change ``text``."""
    return isinstance(text, str) and redact(text) != text


def resolve_repo(explicit: str | os.PathLike[str] | None = None, cwd: str | None = None) -> Path:
    """Target repo: ``--repo``, then ``CLAUDE_PROJECT_DIR``, then event ``cwd``."""
    for candidate in (explicit, os.environ.get("CLAUDE_PROJECT_DIR"), cwd, os.getcwd()):
        if candidate:
            return Path(candidate).resolve()
    return BACKEND_ROOT


def load_config(repo: Path) -> dict[str, Any]:
    """Merge ``DEFAULTS`` with ``<repo>/.agent/jev_harness.json`` (if valid)."""
    cfg = json.loads(json.dumps(DEFAULTS))
    path = repo / CONFIG_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable %s: %s", path, exc)
        return cfg
    if isinstance(data, dict):
        for key, val in data.items():
            if key.startswith("_"):
                continue
            if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(val)
            else:
                cfg[key] = val
    return cfg


def judgment_to_dict(j: Judgment) -> dict[str, Any]:
    return {
        "key": j.key,
        "rubric_version": j.rubric_version,
        "value": j.value,
        "confidence": j.confidence,
        "probabilities": j.probabilities,
        "model": j.model,
    }


@dataclass
class JevGate:
    """One harness invocation's view of Jev for a target repo and session."""

    repo: Path
    session_id: str | None = None
    client_factory: Callable[..., Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.repo = Path(self.repo).resolve()
        if not self.config:
            self.config = load_config(self.repo)
        self.state_dir = self.repo / STATE_REL
        self._client: Any = None

    # -- modes -----------------------------------------------------------

    def mode(self, decision: str) -> str:
        override = (os.environ.get("JEV_HARNESS_MODE") or "").strip().lower()
        if override in MODES:
            return override
        mode = str((self.config.get("decisions") or {}).get(decision, "off")).lower()
        return mode if mode in MODES else "off"

    def acts(self, decision: str) -> bool:
        """True when Jev's answer should change behaviour (mode ``on``)."""
        return self.mode(decision) == "on"

    # -- session state ---------------------------------------------------

    def _session_file(self) -> Path:
        sid = re.sub(r"[^A-Za-z0-9_-]", "_", self.session_id or "default")[:80]
        return self.state_dir / f"session-{sid}.json"

    def load_session(self) -> dict[str, Any]:
        try:
            data = json.loads(self._session_file().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_session(self, data: dict[str, Any]) -> None:
        self._write_json(self._session_file(), data)

    def _write_json(self, path: Path, data: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("Could not write %s: %s", path, exc)

    # -- cache + budget --------------------------------------------------

    def _cache_path(self) -> Path:
        return self.state_dir / "cache.json"

    def _cache_key(self, rubric_keys: list[str], state: Any, extra: Any) -> str:
        versions = [
            f"{k}@{rubrics_mod.get_rubric(k).version}" for k in rubric_keys
        ]
        blob = json.dumps(
            [versions, evidence_hash(state), extra, self.config.get("model")],
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Any:
        try:
            cache = json.loads(self._cache_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        hit = cache.get(key) if isinstance(cache, dict) else None
        return hit.get("answer") if isinstance(hit, dict) else None

    def _cache_put(self, key: str, answer: Any) -> None:
        try:
            cache = json.loads(self._cache_path().read_text(encoding="utf-8"))
            if not isinstance(cache, dict):
                cache = {}
        except (OSError, ValueError):
            cache = {}
        cache[key] = {"t": time.time(), "answer": answer}
        if len(cache) > _CACHE_MAX:
            for old in sorted(cache, key=lambda k: cache[k].get("t", 0))[: len(cache) - _CACHE_MAX]:
                cache.pop(old, None)
        self._write_json(self._cache_path(), cache)

    def _spend(self) -> bool:
        """Reserve one paid call against the session budget."""
        session = self.load_session()
        used = int(session.get("jev_calls", 0))
        if used >= int(self.config.get("max_calls_per_session", 0) or 0):
            logger.info("Jev call budget spent (%s)", used)
            return False
        session["jev_calls"] = used + 1
        self.save_session(session)
        return True

    # -- client ----------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            if self.client_factory is not None:
                self._client = self.client_factory()
            else:
                from modules.typesafe.client import TypeSafeClient

                self._client = TypeSafeClient(
                    enabled=True,
                    model=str(self.config.get("model") or ""),
                    timeout_seconds=float(self.config.get("timeout_seconds") or 4),
                )
        return self._client

    def available(self) -> bool:
        try:
            return bool(self._get_client().available)
        except Exception:  # noqa: BLE001 - never let the judge break the agent
            logger.exception("Jev client unavailable")
            return False

    # -- asking ----------------------------------------------------------

    def ask(
        self,
        decision: str,
        rubric_key: str,
        state: Any,
        *,
        criteria: Any = None,
    ) -> dict[str, Any] | None:
        """Ask one rubric about ``state``; ``None`` when off/unavailable/failed."""
        out = self._ask(decision, rubric_key, state, subjects=None, criteria=criteria)
        return out.get(rubric_key) if out else None

    def ask_subjects(
        self, decision: str, rubric_key: str, state: Any, subjects: list[str]
    ) -> dict[str, dict[str, Any]] | None:
        """Ask one rubric about many ``subjects`` in a single call."""
        return self._ask(decision, rubric_key, state, subjects=subjects, criteria=None)

    def _ask(
        self,
        decision: str,
        rubric_key: str,
        state: Any,
        *,
        subjects: list[str] | None,
        criteria: Any,
    ) -> dict[str, dict[str, Any]] | None:
        mode = self.mode(decision)
        if mode == "off":
            return None
        clean_state = redact(state)
        cache_key = self._cache_key([rubric_key], clean_state, [subjects, criteria])
        cached = self._cache_get(cache_key)
        if cached is not None:
            self._log(decision, rubric_key, mode, clean_state, cached, cached=True)
            return cached
        if not self.available() or not self._spend():
            return None
        client = self._get_client()
        try:
            if subjects is not None:
                raw = client.judge_subjects(
                    clean_state, rubric_key, subjects, check_evidence=False
                )
                answer = {s: judgment_to_dict(j) for s, j in raw.items()}
            else:
                kwargs: dict[str, Any] = {"check_evidence": False}
                if criteria is not None:
                    kwargs["criteria"] = {rubric_key: criteria}
                raw = client.judge(clean_state, [rubric_key], **kwargs)
                answer = {k: judgment_to_dict(j) for k, j in raw.items()}
        except Exception:  # noqa: BLE001
            logger.exception("Jev %s call failed", rubric_key)
            return None
        if not answer:
            return None
        self._cache_put(cache_key, answer)
        self._log(decision, rubric_key, mode, clean_state, answer, cached=False)
        return answer

    def _log(
        self,
        decision: str,
        rubric_key: str,
        mode: str,
        state: Any,
        answer: Any,
        *,
        cached: bool,
    ) -> None:
        self.log_event(
            {
                "decision": decision,
                "rubric": rubric_key,
                "rubric_version": rubrics_mod.get_rubric(rubric_key).version,
                "mode": mode,
                "cached": cached,
                "evidence_hash": evidence_hash(state),
                "answer": answer,
            }
        )

    def log_event(self, record: dict[str, Any]) -> None:
        """Append one audit record (never contains unredacted state)."""
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "session": self.session_id, **record}
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with open(self.state_dir / "decisions.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("Could not append decision log: %s", exc)


def top_choice(answer: dict[str, Any] | None) -> tuple[str | None, float]:
    """(label, probability) for a Choice answer; ``(None, 0.0)`` if absent."""
    if not answer:
        return None, 0.0
    value = answer.get("value")
    probs = answer.get("probabilities") or {}
    p = probs.get(value) if isinstance(probs, dict) else None
    if p is None:
        p = answer.get("confidence")
    try:
        return (str(value) if value is not None else None), float(p or 0.0)
    except (TypeError, ValueError):
        return (str(value) if value is not None else None), 0.0


def noul_value(answer: dict[str, Any] | None) -> float | None:
    if not answer:
        return None
    try:
        return float(answer.get("value"))
    except (TypeError, ValueError):
        return None
