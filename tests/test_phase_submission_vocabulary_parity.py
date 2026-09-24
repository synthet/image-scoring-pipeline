"""Stage 1 exit gate: the submission surfaces agree on the phase vocabulary.

    "Every phase accepted by one run-submission API is either accepted by the
     others or explicitly documented as unsupported."
    -- docs/architecture/pipeline/localization-rollout.md, stage 1 exit gate

Before the control-plane consolidation each surface carried its own token list:
/api/pipeline/submit accepted five legacy spellings and nothing else, normalize_phase_codes
dropped the string "bird_species" so every caller special-cased it, and the dispatcher
had two more alias tables. A phase accepted by one API and rejected by another shipped
silently. This module fails when that happens again.

UNSUPPORTED_BY_DESIGN is the "explicitly documented" half of the gate: an entry there is
a deliberate, reasoned divergence, not a bug. Adding one should come with the reason.

No PostgreSQL required -- db.enqueue_job and the scope preview are stubbed. See #367.
"""

from __future__ import annotations

import pathlib

import pytest

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from modules.phases import (  # noqa: E402
    PHASE_CODE_ALIASES,
    PHASE_ENABLED_CONFIG_KEYS,
    PHASE_TO_JOB_TYPE,
    PhaseCode,
)

# phase_code -> why that surface legitimately does not accept it.
UNSUPPORTED_BY_DESIGN: dict[str, dict[str, str]] = {}

# Config-gated phases (``localization``, #387 decision 1) are the other documented
# divergence: while their flag is off every surface rejects them. The every-phase tests
# below switch the flag on, so parity is still enforced for the day the phase is enabled;
# ``test_disabled_phase_is_rejected_*`` pin the rejection itself.
GATED_PHASES = sorted(PHASE_ENABLED_CONFIG_KEYS)


@pytest.fixture
def gated_phases_enabled(monkeypatch):
    monkeypatch.setattr("modules.phases.is_phase_enabled", lambda _phase: True)


@pytest.fixture
def gated_phases_disabled(monkeypatch):
    monkeypatch.setattr(
        "modules.phases.is_phase_enabled",
        lambda phase: getattr(phase, "value", phase) not in PHASE_ENABLED_CONFIG_KEYS,
    )


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda *_a, **_kw: None)
    from modules import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.create_api_router())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """A folder scope whose every phase reads satisfied, so only vocabulary is tested."""
    def _fake_resolve(raw_path: str):
        p = pathlib.Path(raw_path)
        p.mkdir(parents=True, exist_ok=True)
        resolved = str(p.resolve())
        return resolved, [resolved]

    monkeypatch.setattr("modules.utils.resolve_scope_input_path", _fake_resolve)
    monkeypatch.setattr(
        "modules.phases.compute_satisfied_phases_for_scope",
        lambda _paths: {p.value for p in PhaseCode},
    )
    folder = tmp_path / "scope"
    folder.mkdir()
    return str(folder.resolve())


@pytest.fixture
def stub_enqueue(monkeypatch):
    """Capture submissions without touching the database."""
    calls: list[dict] = []

    def _enqueue_job(input_path, phase_code=None, job_type=None, queue_payload=None, description=None):
        calls.append({"phase_code": phase_code, "job_type": job_type})
        return 4242, 1

    def _enqueue_with_phases(input_path, phase_code, job_type, payload, description, phases, state):
        calls.append({"phase_code": phase_code, "job_type": job_type, "phases": list(phases or [])})
        return (4242, 1)

    monkeypatch.setattr("modules.db.enqueue_job", _enqueue_job)
    monkeypatch.setattr("modules.db.enqueue_job_with_phases", _enqueue_with_phases)
    monkeypatch.setattr("modules.db.create_job_phases", lambda *_a, **_k: [])
    monkeypatch.setattr(
        "modules.db.build_validation_repair_plan",
        lambda _paths, phase_values, _dry: {
            "stage_queues": {str(p): [1] for p in (phase_values or [])}
        },
    )
    monkeypatch.setattr(
        "modules.runs_autodrive.phases_with_work_from_repair_plan",
        lambda _paths, requested, **_k: list(requested or []),
    )
    return calls


def assert_vocabulary_accepted(response, surface: str, token: str):
    """The phase token was understood -- whatever else the submission then does.

    This is deliberately narrower than "the run was queued". Whether a runner is
    wired up is an environment fact, not a contract: /api/pipeline/submit answers
    "Orchestrator unavailable: Scoring runner not available" in a test app with no
    runners, and that is not a vocabulary rejection. The two rejections this gate
    exists to catch are an unrecognised stage code and a prerequisite mismatch.
    """
    assert response.status_code in (200, 400), response.text
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    message = str(body.get("message") or "") if isinstance(body, dict) else ""
    data = body.get("data") if isinstance(body, dict) else None

    assert "Invalid stage_codes" not in message, (
        f"{surface} does not recognise {token!r}: {message}"
    )
    assert "Invalid stages" not in message, (
        f"{surface} does not recognise {token!r}: {message}"
    )
    for blob in (detail, data):
        if isinstance(blob, dict):
            assert blob.get("code") != "missing_prerequisites", (
                f"{surface} gated {token!r} despite a fully satisfied scope: {blob}"
            )
            assert blob.get("code") != "invalid_stages", (
                f"{surface} does not recognise {token!r}: {blob}"
            )


@pytest.mark.parametrize("phase", [p.value for p in PhaseCode])
def test_runs_submit_accepts_every_phase_code(api_client, scope, stub_enqueue, gated_phases_enabled, phase):
    """/api/runs/submit must route every canonical phase code."""
    if phase in UNSUPPORTED_BY_DESIGN.get("runs_submit", {}):
        pytest.skip(UNSUPPORTED_BY_DESIGN["runs_submit"][phase])

    r = api_client.post(
        "/api/runs/submit",
        json={
            "scope_type": "folder_recursive",
            "scope_paths": [scope],
            "stages": [phase],
            "generate_captions": False,
        },
    )
    assert_vocabulary_accepted(r, "/api/runs/submit", phase)
    # This surface has every runner it needs stubbed, so it should reach a queued run.
    assert r.status_code == 200, f"/api/runs/submit rejected {phase!r}: {r.text}"
    assert r.json().get("success") is True


@pytest.mark.parametrize("phase", [p.value for p in PhaseCode])
def test_pipeline_submit_accepts_every_phase_code(
    api_client, scope, stub_enqueue, gated_phases_enabled, monkeypatch, phase,
):
    """/api/pipeline/submit must accept the same vocabulary /api/runs/submit does."""
    if phase in UNSUPPORTED_BY_DESIGN.get("pipeline_submit", {}):
        pytest.skip(UNSUPPORTED_BY_DESIGN["pipeline_submit"][phase])

    import modules.api as api_mod

    monkeypatch.setattr(api_mod, "validate_and_preview", lambda _req: {"preview_count": 3})

    r = api_client.post(
        "/api/pipeline/submit",
        json={"workspace_target": scope, "stage_codes": [phase]},
    )
    assert_vocabulary_accepted(r, "/api/pipeline/submit", phase)


@pytest.mark.parametrize("phase", GATED_PHASES)
def test_disabled_phase_is_rejected_by_runs_submit(api_client, scope, stub_enqueue, gated_phases_disabled, phase):
    r = api_client.post(
        "/api/runs/submit",
        json={"scope_type": "folder_recursive", "scope_paths": [scope], "stages": ["metadata", phase]},
    )
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "phase_disabled"
    assert PHASE_ENABLED_CONFIG_KEYS[phase] in detail["message"]
    assert stub_enqueue == []


@pytest.mark.parametrize("phase", GATED_PHASES)
def test_disabled_phase_is_rejected_by_pipeline_submit(
    api_client, scope, stub_enqueue, gated_phases_disabled, monkeypatch, phase,
):
    import modules.api as api_mod

    monkeypatch.setattr(api_mod, "validate_and_preview", lambda _req: {"preview_count": 3})
    r = api_client.post(
        "/api/pipeline/submit",
        json={"workspace_target": scope, "stage_codes": [phase]},
    )
    body = r.json()
    assert body["success"] is False
    assert PHASE_ENABLED_CONFIG_KEYS[phase] in body["message"]
    assert stub_enqueue == []


@pytest.mark.parametrize("alias", sorted(PHASE_CODE_ALIASES))
def test_pipeline_submit_accepts_every_legacy_alias(api_client, scope, stub_enqueue, monkeypatch, alias):
    """The legacy score/tag/cluster/bird-species spellings stay accepted."""
    import modules.api as api_mod

    monkeypatch.setattr(api_mod, "validate_and_preview", lambda _req: {"preview_count": 3})

    r = api_client.post(
        "/api/pipeline/submit",
        json={"workspace_target": scope, "stage_codes": [alias]},
    )
    assert_vocabulary_accepted(r, "/api/pipeline/submit", alias)


def test_every_phase_is_routable_end_to_end():
    """Vocabulary acceptance is worthless if the dispatcher cannot then run the phase."""
    import inspect
    import re

    from modules.job_dispatcher import JobDispatcher

    source = inspect.getsource(JobDispatcher)
    block = source[source.index("runner_map = {"):]
    block = block[: block.index("}")]
    routable = set(re.findall(r'"([^"]+)":', block))

    for phase in PhaseCode:
        job_type = PHASE_TO_JOB_TYPE[phase.value]
        assert job_type in routable, (
            f"{phase.value!r} submits as job_type {job_type!r}, which JobDispatcher "
            "cannot route"
        )
