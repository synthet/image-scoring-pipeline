"""Unit tests for shadow-mode Jev keyword verification.

Network- and credential-free. Exercises the two-flag gate, the JSONL report
sidecar, the per-image keyword cap, and the guarantee that this observation-only
channel can never break a tagging run.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from modules import config
from modules.typesafe import keyword_shadow
from modules.typesafe.client import TypeSafeClient
from modules.typesafe.normalize import Judgment

_KEYWORDS = ["osprey", "fish", "sky"]
_CAPTION = "A bird of prey flying while carrying a fish."


class _FakeClient:
    """Stands in for TypeSafeClient without touching the SDK."""

    def __init__(self, judgments=None, available=True, raises=None):
        self.available = available
        self._judgments = judgments or {}
        self._raises = raises
        self.calls = 0

    def judge_subjects(self, state, rubric_key, subjects, **_kw):
        self.calls += 1
        self.last_subjects = list(subjects)
        self.last_state = state
        if self._raises is not None:
            raise self._raises
        return {s: self._judgments[s] for s in subjects if s in self._judgments}


def _judgment(value, confidence=0.7, completeness=0.9):
    return Judgment(
        key="keywords.relevance",
        rubric_version="v1",
        question_type="noul",
        value=value,
        model="jev-test",
        confidence=confidence,
        evidence_completeness=completeness,
        evidence_hash="deadbeef",
    )


@pytest.fixture
def shadow_env(monkeypatch, tmp_path):
    """Both flags on, reports redirected into tmp_path."""
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "get_config_section",
        lambda name: {
            "enabled": True,
            "keyword_shadow": {"enabled": True, "max_keywords_per_image": 10},
        },
    )
    return tmp_path


def _records(tmp_path, job_id=7):
    path = tmp_path / "reports" / "typesafe-keyword-shadow" / f"job-{job_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# -- the gate ------------------------------------------------------------


def test_disabled_when_adapter_flag_off(monkeypatch):
    monkeypatch.setattr(
        config,
        "get_config_section",
        lambda name: {"enabled": False, "keyword_shadow": {"enabled": True}},
    )
    assert keyword_shadow.is_enabled() is False


def test_disabled_when_shadow_flag_off(monkeypatch):
    monkeypatch.setattr(
        config,
        "get_config_section",
        lambda name: {"enabled": True, "keyword_shadow": {"enabled": False}},
    )
    assert keyword_shadow.is_enabled() is False


def test_disabled_when_section_absent(monkeypatch):
    monkeypatch.setattr(config, "get_config_section", lambda name: {})
    assert keyword_shadow.is_enabled() is False


def test_enabled_needs_both_flags(shadow_env):
    assert keyword_shadow.is_enabled() is True


def test_verify_is_noop_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "get_config_section", lambda name: {"enabled": False})
    client = _FakeClient({k: _judgment(0.9) for k in _KEYWORDS})
    written = keyword_shadow.verify_image(
        1, "/p/a.jpg", _CAPTION, _KEYWORDS, {}, job_id=7, client=client
    )
    assert written == 0
    assert client.calls == 0
    assert _records(tmp_path) == []


# -- state building ------------------------------------------------------


def test_build_state_is_text_only(shadow_env):
    state = keyword_shadow.build_state(_CAPTION, _KEYWORDS, title="Osprey")
    assert state["caption"] == _CAPTION
    assert state["candidate_keywords"] == _KEYWORDS
    assert state["title"] == "Osprey"
    assert state["evidence_version"] == "v1"
    # Jev accepts text only -- nothing binary may leak into the payload.
    assert all(
        isinstance(v, (str, list, dict)) for v in state.values()
    ), "state must be text-shaped"


# -- recording -----------------------------------------------------------


def test_records_both_signals_side_by_side(shadow_env):
    client = _FakeClient({k: _judgment(0.8) for k in _KEYWORDS})
    clip_weights = {"osprey": 0.69, "fish": 0.62, "sky": 0.55}

    written = keyword_shadow.verify_image(
        11, "/p/a.jpg", _CAPTION, _KEYWORDS, clip_weights, job_id=7, client=client
    )

    assert written == 3
    rows = _records(shadow_env)
    assert len(rows) == 3
    by_kw = {r["keyword"]: r for r in rows}
    # The incumbent and the challenger are both recorded, neither overwritten.
    assert by_kw["osprey"]["clip_relevance_weight"] == 0.69
    assert by_kw["osprey"]["jev_relevance"] == 0.8
    assert by_kw["osprey"]["evidence_completeness"] == 0.9
    assert by_kw["osprey"]["rubric_version"] == "v1"
    assert by_kw["osprey"]["model"] == "jev-test"
    assert by_kw["osprey"]["image_id"] == 11


def test_one_api_call_per_image_not_per_keyword(shadow_env):
    client = _FakeClient({k: _judgment(0.8) for k in _KEYWORDS})
    keyword_shadow.verify_image(
        11, "/p/a.jpg", _CAPTION, _KEYWORDS, {}, job_id=7, client=client
    )
    assert client.calls == 1


def test_keyword_cap_is_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        config,
        "get_config_section",
        lambda name: {
            "enabled": True,
            "keyword_shadow": {"enabled": True, "max_keywords_per_image": 2},
        },
    )
    client = _FakeClient({k: _judgment(0.8) for k in _KEYWORDS})
    keyword_shadow.verify_image(
        11, "/p/a.jpg", _CAPTION, _KEYWORDS, {}, job_id=7, client=client
    )
    assert client.last_subjects == ["osprey", "fish"]


def test_appends_across_images(shadow_env):
    client = _FakeClient({k: _judgment(0.8) for k in _KEYWORDS})
    keyword_shadow.verify_image(1, "/p/a.jpg", _CAPTION, ["osprey"], {}, job_id=7, client=client)
    keyword_shadow.verify_image(2, "/p/b.jpg", _CAPTION, ["fish"], {}, job_id=7, client=client)
    rows = _records(shadow_env)
    assert [r["image_id"] for r in rows] == [1, 2]


# -- fail-open guarantees ------------------------------------------------


def test_client_explosion_is_swallowed(shadow_env):
    client = _FakeClient(raises=RuntimeError("upstream 500"))
    assert keyword_shadow.verify_image(
        1, "/p/a.jpg", _CAPTION, _KEYWORDS, {}, job_id=7, client=client
    ) == 0


def test_unavailable_client_is_skipped(shadow_env):
    client = _FakeClient({}, available=False)
    assert keyword_shadow.verify_image(
        1, "/p/a.jpg", _CAPTION, _KEYWORDS, {}, job_id=7, client=client
    ) == 0
    assert client.calls == 0


def test_blank_caption_is_skipped(shadow_env):
    client = _FakeClient({k: _judgment(0.8) for k in _KEYWORDS})
    assert keyword_shadow.verify_image(
        1, "/p/a.jpg", "   ", _KEYWORDS, {}, job_id=7, client=client
    ) == 0
    assert client.calls == 0


def test_no_keywords_is_skipped(shadow_env):
    client = _FakeClient({})
    assert keyword_shadow.verify_image(
        1, "/p/a.jpg", _CAPTION, [], {}, job_id=7, client=client
    ) == 0
    assert client.calls == 0


# -- batched subject calls on the client --------------------------------


class _Answer:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _sdk_returning(nouls):
    mod = types.ModuleType("typesafe_sdk")
    captured: dict = {}

    class _Q:
        def __init__(self, **kw):
            self.kw = kw

    class _Resp:
        model = "jev-test"
        choices: dict = {}
        scores: dict = {}

        def __init__(self):
            self.nouls = nouls

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def system_one(self, **kwargs):
            captured.update(kwargs)
            return _Resp()

    for attr, value in (
        ("Noul", _Q), ("Score", _Q), ("Choice", _Q),
        ("TypeSafeClient", _Client), ("captured", captured),
    ):
        setattr(mod, attr, value)
    return mod


def test_judge_subjects_batches_into_one_call(monkeypatch):
    monkeypatch.setattr(config, "get_secret", lambda svc: {"api_key": "k"})
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    nouls = {
        "keywords.relevance::osprey": _Answer(noul=0.95),
        "keywords.relevance::fish": _Answer(noul=0.80),
        "evidence.sufficiency": _Answer(noul=0.9),
    }
    sdk = _sdk_returning(nouls)
    monkeypatch.setitem(sys.modules, "typesafe_sdk", sdk)

    client = TypeSafeClient(enabled=True)
    out = client.judge_subjects({"caption": _CAPTION}, "keywords.relevance", ["osprey", "fish"])

    assert set(out) == {"osprey", "fish"}
    assert out["osprey"].value == 0.95
    assert out["fish"].value == 0.80
    # Completeness came from the single tag-along sufficiency question.
    assert out["osprey"].evidence_completeness == pytest.approx(0.9)
    # One request covered every subject plus the sufficiency check.
    assert set(sdk.captured["questions"]) == set(nouls)
    assert sdk.captured["questions"]["keywords.relevance::osprey"].kw[
        "instructions"
    ]["subject_under_review"] == "osprey"
    assert sdk.captured["questions"]["keywords.relevance::fish"].kw[
        "instructions"
    ]["subject_under_review"] == "fish"


def test_judge_subjects_rejects_unknown_rubric(monkeypatch):
    monkeypatch.setattr(config, "get_secret", lambda svc: {"api_key": "k"})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", _sdk_returning({}))
    client = TypeSafeClient(enabled=True)
    assert client.judge_subjects({"a": "b"}, "nope.missing", ["x"]) == {}


def test_judge_subjects_empty_subjects_short_circuits(monkeypatch):
    monkeypatch.setattr(config, "get_secret", lambda svc: {"api_key": "k"})
    monkeypatch.setitem(sys.modules, "typesafe_sdk", _sdk_returning({}))
    client = TypeSafeClient(enabled=True)
    assert client.judge_subjects({"a": "b"}, "keywords.relevance", ["", ""]) == {}
