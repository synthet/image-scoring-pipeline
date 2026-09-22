"""Unit tests for the TypeSafe (Jev) adapter.

Hardware- and network-free: no ``typesafe-sdk`` install, no API key, no
outbound call. A fake SDK module exercises question building, response
normalization and the fail-safe paths.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

from modules import config
from modules.typesafe import rubrics as rubrics_mod
from modules.typesafe.client import TypeSafeClient
from modules.typesafe.normalize import evidence_hash, noul_confidence, normalize

_STATE = {"cluster_id": "burst-42", "candidates": [{"image_id": "A"}]}


class _Answer:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Response:
    def __init__(self, nouls=None, scores=None, choices=None, model="jev-test"):
        self.model = model
        self.nouls = nouls or {}
        self.scores = scores or {}
        self.choices = choices or {}


def _fake_sdk(response=None, raises=None) -> types.ModuleType:
    """Build a stand-in ``typesafe_sdk`` module."""
    mod = types.ModuleType("typesafe_sdk")
    captured: dict = {}

    class _Q:
        def __init__(self, **kw):
            self.kw = kw

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def system_one(self, **kwargs):
            captured.update(kwargs)
            if raises is not None:
                raise raises
            return response

    for attr, value in (
        ("Noul", _Q),
        ("Score", _Q),
        ("Choice", _Q),
        ("TypeSafeClient", _Client),
        ("captured", captured),
    ):
        setattr(mod, attr, value)
    return mod


@pytest.fixture
def install_fake_sdk(monkeypatch):
    def _install(mod):
        monkeypatch.setitem(sys.modules, "typesafe_sdk", mod)
        return mod

    return _install


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(config, "get_secret", lambda svc: {"api_key": "k-test"})


# -- availability --------------------------------------------------------


def test_disabled_by_default_makes_no_call(monkeypatch):
    """AC-1: flag off -> unavailable, no judgments, nothing imported."""
    monkeypatch.setattr(config, "get_config_section", lambda name: {"enabled": False})
    client = TypeSafeClient()
    assert client.available is False
    assert client.judge(_STATE, ["culling.redundancy"]) == {}
    assert "typesafe.enabled is false" in (client.unavailable_reason or "")


def test_missing_api_key_degrades(monkeypatch):
    """AC-2: enabled but no credential -> unavailable, no raise."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("JEV_TOKEN", raising=False)
    monkeypatch.setattr(config, "get_secret", lambda svc: None)
    client = TypeSafeClient(enabled=True)
    assert client.available is False
    assert "no API key" in (client.unavailable_reason or "")
    assert client.judge(_STATE, ["culling.redundancy"]) == {}


def test_jev_token_alias_is_exported_for_sdk(monkeypatch, install_fake_sdk):
    install_fake_sdk(_fake_sdk(_Response()))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("JEV_TOKEN", "jev-operator-key")
    monkeypatch.setattr(config, "get_secret", lambda svc: None)

    client = TypeSafeClient(enabled=True)

    assert client.available is True
    assert os.environ["TYPESAFE_API_KEY"] == "jev-operator-key"


def test_missing_sdk_degrades(monkeypatch, with_key):
    """AC-2: key present but ``typesafe-sdk`` absent -> unavailable, no raise."""
    monkeypatch.setitem(sys.modules, "typesafe_sdk", None)
    client = TypeSafeClient(enabled=True)
    assert client.available is False
    assert client.judge(_STATE, ["culling.redundancy"]) == {}


def test_operator_env_key_wins_over_secrets(monkeypatch, with_key, install_fake_sdk):
    install_fake_sdk(_fake_sdk(_Response()))
    monkeypatch.setenv("TYPESAFE_API_KEY", "operator-key")
    client = TypeSafeClient(enabled=True)
    assert client.available is True
    assert os.environ["TYPESAFE_API_KEY"] == "operator-key"


# -- judging -------------------------------------------------------------


def test_judge_attaches_evidence_completeness(with_key, install_fake_sdk):
    """AC-4: model confidence and evidence completeness stay separate."""
    response = _Response(
        scores={
            "culling.distinctiveness": _Answer(
                score=2, confidence=0.81, probabilities={"a": 0.8}, legend=["x"]
            )
        },
        nouls={"evidence.sufficiency": _Answer(noul=0.9)},
    )
    sdk = install_fake_sdk(_fake_sdk(response))
    client = TypeSafeClient(enabled=True)

    out = client.judge(_STATE, ["culling.distinctiveness"])

    assert set(out) == {"culling.distinctiveness"}
    judgment = out["culling.distinctiveness"]
    assert judgment.value == 2
    assert judgment.confidence == 0.81
    assert judgment.evidence_completeness == pytest.approx(0.9)
    assert judgment.confidence != judgment.evidence_completeness
    # AC-3: provenance recorded.
    assert judgment.rubric_version == "v1"
    assert judgment.model == "jev-test"
    assert judgment.evidence_hash == evidence_hash(_STATE)
    # The sufficiency question rode along in the same call.
    assert set(sdk.captured["questions"]) == {
        "culling.distinctiveness",
        "evidence.sufficiency",
    }


def test_judge_can_skip_evidence_check(with_key, install_fake_sdk):
    response = _Response(nouls={"culling.redundancy": _Answer(noul=0.7)})
    sdk = install_fake_sdk(_fake_sdk(response))
    client = TypeSafeClient(enabled=True)

    out = client.judge(_STATE, ["culling.redundancy"], check_evidence=False)

    assert set(sdk.captured["questions"]) == {"culling.redundancy"}
    assert out["culling.redundancy"].evidence_completeness is None


def test_model_pinned_only_when_configured(with_key, install_fake_sdk):
    answer = {"culling.redundancy": _Answer(noul=0.5)}
    sdk = install_fake_sdk(_fake_sdk(_Response(nouls=answer)))
    TypeSafeClient(enabled=True).judge(_STATE, ["culling.redundancy"])
    assert "model" not in sdk.captured

    sdk2 = install_fake_sdk(_fake_sdk(_Response(nouls=answer)))
    TypeSafeClient(enabled=True, model="jev-2026-01").judge(
        _STATE, ["culling.redundancy"]
    )
    assert sdk2.captured["model"] == "jev-2026-01"


def test_timeout_is_explicit_and_configurable(with_key, install_fake_sdk):
    answer = {"culling.redundancy": _Answer(noul=0.5)}
    sdk = install_fake_sdk(_fake_sdk(_Response(nouls=answer)))
    TypeSafeClient(enabled=True, timeout_seconds=12.5).judge(
        _STATE, ["culling.redundancy"]
    )
    assert sdk.captured["timeout"] == pytest.approx(12.5)


def test_api_failure_returns_empty_and_does_not_raise(with_key, install_fake_sdk):
    """AC-2: a paid network judge must never break the caller."""
    install_fake_sdk(_fake_sdk(raises=RuntimeError("502 upstream")))
    client = TypeSafeClient(enabled=True)
    assert client.judge(_STATE, ["culling.redundancy"]) == {}


def test_unknown_rubric_returns_empty(with_key, install_fake_sdk):
    install_fake_sdk(_fake_sdk(_Response()))
    client = TypeSafeClient(enabled=True)
    assert client.judge(_STATE, ["nope.not_registered"]) == {}


def test_missing_answer_is_skipped_not_fatal(with_key, install_fake_sdk):
    """A partial response still yields the answers that did arrive."""
    response = _Response(nouls={"evidence.sufficiency": _Answer(noul=0.4)})
    install_fake_sdk(_fake_sdk(response))
    client = TypeSafeClient(enabled=True)
    assert client.judge(_STATE, ["culling.redundancy"]) == {}


# -- normalization + registry -------------------------------------------


@pytest.mark.parametrize(
    "value,expected", [(0.5, 0.0), (1.0, 1.0), (0.0, 1.0), (0.75, 0.5)]
)
def test_noul_confidence_maps_distance_from_coinflip(value, expected):
    assert noul_confidence(value) == pytest.approx(expected)


def test_noul_confidence_handles_garbage():
    assert noul_confidence(None) is None
    assert noul_confidence("nope") is None


def test_evidence_hash_is_order_independent():
    assert evidence_hash({"a": 1, "b": 2}) == evidence_hash({"b": 2, "a": 1})
    assert evidence_hash({"a": 1}) != evidence_hash({"a": 2})


def test_normalize_derives_confidence_for_noul():
    response = _Response(nouls={"culling.redundancy": _Answer(noul=0.9)})
    judgment = normalize(response, rubrics_mod.get_rubric("culling.redundancy"))
    assert judgment is not None
    assert judgment.value == 0.9
    assert judgment.confidence == pytest.approx(0.8)


def test_culling_action_is_one_coherent_choice_distribution(
    with_key, install_fake_sdk
):
    response = _Response(
        choices={
            "culling.action": _Answer(
                choice="reject",
                confidence=0.72,
                probabilities={"pick": 0.08, "keep": 0.20, "reject": 0.72},
            )
        },
        nouls={"evidence.sufficiency": _Answer(noul=0.85)},
    )
    install_fake_sdk(_fake_sdk(response))

    judgment = TypeSafeClient(enabled=True).judge(
        _STATE, ["culling.action"]
    )["culling.action"]

    assert judgment.value == "reject"
    assert judgment.probabilities == {
        "pick": 0.08,
        "keep": 0.20,
        "reject": 0.72,
    }
    assert sum(judgment.probabilities.values()) == pytest.approx(1.0)
    assert judgment.evidence_completeness == pytest.approx(0.85)


def test_every_rubric_is_versioned_and_typed():
    """AC-3: no rubric ships without a version."""
    valid = {rubrics_mod.NOUL, rubrics_mod.CHOICE, rubrics_mod.SCORE}
    for key, rubric in rubrics_mod.REGISTRY.items():
        assert rubric.key == key
        assert rubric.version
        assert rubric.question_type in valid
        if rubric.question_type == rubrics_mod.SCORE:
            assert rubric.criteria, f"{key} is a Score with no criteria"


def test_get_rubric_rejects_unknown_key():
    with pytest.raises(KeyError):
        rubrics_mod.get_rubric("does.not.exist")
