"""TypeSafe (Jev / System One) client adapter — experimental, off by default.

Jev evaluates *typed questions against text state* and returns typed answers
with probability distributions. It is **not** a vision model: state must be a
string, JSON object, or array of text values, and images, audio and video are
not supported (https://docs.typesafe.ai/concepts/state). Anything visual has to
be turned into structured text by the existing scoring/vision pipeline before it
reaches this adapter.

Gated on ``typesafe.enabled`` in ``config.json`` (default ``false``). The API
key lives in ``secrets.json`` under the ``typesafe`` service, never in
``config.json``. ``typesafe_sdk`` is an optional dependency: if it or the key is
missing, ``available`` is ``False`` and callers skip the feature.

Nothing here raises on a TypeSafe failure — a paid, network-bound judge must
never take down a local pipeline phase.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from modules import config
from modules.typesafe import rubrics as rubrics_mod
from modules.typesafe.normalize import Judgment, normalize

logger = logging.getLogger(__name__)

_API_KEY_ENV = "TYPESAFE_API_KEY"
_SECRETS_SERVICE = "typesafe"


class TypeSafeClient:
    """Lazy, fail-safe wrapper around ``typesafe_sdk.TypeSafeClient``."""

    def __init__(self, *, enabled: bool | None = None, model: str | None = None) -> None:
        section = config.get_config_section("typesafe") or {}
        self.enabled = (
            bool(section.get("enabled", False)) if enabled is None else bool(enabled)
        )
        # Pin the model for reproducibility-sensitive runs; empty means "let the
        # SDK choose", which is fine for exploration but not for experiments.
        self.model = (model if model is not None else section.get("model") or "").strip()
        self._sdk: Any = None
        self._checked = False
        self._unavailable_reason: str | None = None

    # -- availability ----------------------------------------------------

    def _resolve_api_key(self) -> str | None:
        """Prefer an already-exported env var, else fall back to secrets.json."""
        env_key = os.environ.get(_API_KEY_ENV)
        if env_key:
            return env_key
        secret = config.get_secret(_SECRETS_SERVICE)
        if isinstance(secret, dict):
            return secret.get("api_key") or None
        if isinstance(secret, str):
            return secret or None
        return None

    def _ensure_sdk(self) -> bool:
        if self._checked:
            return self._sdk is not None
        self._checked = True

        if not self.enabled:
            self._unavailable_reason = "typesafe.enabled is false"
            return False

        api_key = self._resolve_api_key()
        if not api_key:
            self._unavailable_reason = (
                f"no API key ({_API_KEY_ENV} unset and secrets.json has no "
                f"'{_SECRETS_SERVICE}.api_key')"
            )
            logger.warning("TypeSafe disabled: %s", self._unavailable_reason)
            return False
        # The SDK reads the key from the environment; export it only if the
        # operator has not already done so themselves.
        os.environ.setdefault(_API_KEY_ENV, api_key)

        try:
            import typesafe_sdk
        except ImportError as exc:
            self._unavailable_reason = f"typesafe-sdk not installed ({exc})"
            logger.warning("TypeSafe disabled: %s", self._unavailable_reason)
            return False

        self._sdk = typesafe_sdk
        return True

    @property
    def available(self) -> bool:
        """True when the flag is on, a key is resolvable, and the SDK imports."""
        return self._ensure_sdk()

    @property
    def unavailable_reason(self) -> str | None:
        self._ensure_sdk()
        return self._unavailable_reason

    # -- judging ---------------------------------------------------------

    def judge(
        self,
        state: Any,
        rubric_keys: list[str],
        *,
        check_evidence: bool = True,
    ) -> dict[str, Judgment]:
        """Ask ``rubric_keys`` about ``state``; return judgments by rubric key.

        When ``check_evidence`` is set, the ``evidence.sufficiency`` rubric is
        asked in the same call and its value is attached to every other judgment
        as ``evidence_completeness`` — model confidence and evidence
        completeness are tracked separately on purpose.

        Returns an empty dict if the adapter is unavailable or the call fails.
        Never raises.
        """
        if not self.available:
            return {}

        keys = list(dict.fromkeys(rubric_keys))
        evidence_key = rubrics_mod.EVIDENCE_SUFFICIENCY_KEY
        want_evidence = check_evidence and evidence_key not in keys
        if want_evidence:
            keys.append(evidence_key)

        try:
            selected = [rubrics_mod.get_rubric(k) for k in keys]
        except KeyError as exc:
            logger.error("Unknown TypeSafe rubric %s", exc)
            return {}

        try:
            questions = {r.key: rubrics_mod.build_question(r) for r in selected}
        except Exception:
            logger.exception("Failed to build TypeSafe questions")
            return {}

        kwargs: dict[str, Any] = {"state": state, "questions": questions}
        if self.model:
            kwargs["model"] = self.model

        try:
            with self._sdk.TypeSafeClient() as client:
                response = client.system_one(**kwargs)
        except Exception:
            # Paid + network-bound: a failure here must not break the caller.
            logger.exception("TypeSafe system_one call failed")
            return {}

        completeness: float | None = None
        evidence_rubric = rubrics_mod.get_rubric(evidence_key)
        if evidence_key in questions:
            evidence_judgment = normalize(response, evidence_rubric, state=state)
            if evidence_judgment is not None:
                try:
                    completeness = float(evidence_judgment.value)
                except (TypeError, ValueError):
                    completeness = None

        out: dict[str, Judgment] = {}
        for rubric in selected:
            if want_evidence and rubric.key == evidence_key:
                continue
            judgment = normalize(
                response,
                rubric,
                completeness=None if rubric.key == evidence_key else completeness,
                state=state,
            )
            if judgment is not None:
                out[rubric.key] = judgment
        return out

    def judge_subjects(
        self,
        state: Any,
        rubric_key: str,
        subjects: list[str],
        *,
        check_evidence: bool = True,
    ) -> dict[str, Judgment]:
        """Ask one rubric about many ``subjects`` in a **single** call.

        Used where the same question applies per item — every candidate keyword
        on one image, say — so the cost is one request per image rather than one
        per keyword. Returns judgments keyed by subject.

        Returns an empty dict if the adapter is unavailable or the call fails.
        Never raises.
        """
        if not self.available:
            return {}

        wanted = [s for s in dict.fromkeys(subjects) if s]
        if not wanted:
            return {}

        try:
            rubric = rubrics_mod.get_rubric(rubric_key)
        except KeyError:
            logger.error("Unknown TypeSafe rubric %r", rubric_key)
            return {}

        evidence_key = rubrics_mod.EVIDENCE_SUFFICIENCY_KEY
        evidence_rubric = rubrics_mod.get_rubric(evidence_key)

        try:
            questions = {
                rubrics_mod.subject_question_id(rubric_key, s): (
                    rubrics_mod.build_question(rubric)
                )
                for s in wanted
            }
            if check_evidence:
                questions[evidence_key] = rubrics_mod.build_question(evidence_rubric)
        except Exception:
            logger.exception("Failed to build TypeSafe questions")
            return {}

        kwargs: dict[str, Any] = {"state": state, "questions": questions}
        if self.model:
            kwargs["model"] = self.model

        try:
            with self._sdk.TypeSafeClient() as client:
                response = client.system_one(**kwargs)
        except Exception:
            logger.exception("TypeSafe system_one call failed")
            return {}

        completeness: float | None = None
        if check_evidence:
            evidence_judgment = normalize(response, evidence_rubric, state=state)
            if evidence_judgment is not None:
                try:
                    completeness = float(evidence_judgment.value)
                except (TypeError, ValueError):
                    completeness = None

        out: dict[str, Judgment] = {}
        for subject in wanted:
            judgment = normalize(
                response,
                rubric,
                completeness=completeness,
                state=state,
                answer_key=rubrics_mod.subject_question_id(rubric_key, subject),
            )
            if judgment is not None:
                out[subject] = judgment
        return out
