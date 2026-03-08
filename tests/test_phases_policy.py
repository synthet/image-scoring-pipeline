from modules.phases import PhaseCode, PhaseExecutor, PhaseRegistry
from modules import phases_policy


def test_policy_runs_when_status_missing(monkeypatch):
    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", lambda image_id: {})
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_phase_status"


def test_policy_skips_when_done_same_version(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "done", "executor_version": "1.2.3"}},
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.SCORING, executor_version="1.2.3"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"


def test_policy_runs_when_done_but_version_changed(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"keywords": {"status": "done", "executor_version": "1.0.0"}},
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.KEYWORDS, executor_version="2.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.KEYWORDS)
    assert decision["should_run"] is True
    assert decision["reason"] == "executor_version_changed"
