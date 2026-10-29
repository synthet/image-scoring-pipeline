"""Worker lifecycle and default-off isolation without a database."""
from types import SimpleNamespace

from modules.localization_authority_worker import ShadowAuthorityWorker


def test_worker_polls_metadata_independently_of_gpu_activity():
    events = []
    store = SimpleNamespace(
        control=lambda: {"mode": "shadow", "revision": 1},
        scan_batch=lambda size: events.append(("scan", size)) or [],
        claim_next=lambda: None,
        diagnostics=lambda: {"mode": "shadow"},
    )
    worker = ShadowAuthorityWorker(store)
    worker.poll_once()
    assert events == [("scan", 100)]


def test_off_mode_never_scans_or_claims():
    store = SimpleNamespace(control=lambda: {"mode": "off", "revision": 0},
                            diagnostics=lambda: {"mode": "off"})
    assert ShadowAuthorityWorker(store).poll_once() == 0


def test_dispatcher_owns_worker_lifecycle_even_while_gpu_runner_is_busy(monkeypatch):
    from modules.job_dispatcher import JobDispatcher

    calls = []
    worker = SimpleNamespace(start=lambda: calls.append("start"), stop=lambda: calls.append("stop"))
    dispatcher = JobDispatcher(authority_worker=worker)
    monkeypatch.setattr(dispatcher, "_any_runner_busy", lambda: True)
    monkeypatch.setattr(dispatcher, "_run_loop", lambda: None)
    dispatcher.start()
    dispatcher.stop()
    assert calls == ["start", "stop"]


def test_diagnostic_snapshots_do_not_expose_shared_mutable_state():
    from modules.localization_authority_worker import get_diagnostic_state

    state = get_diagnostic_state()
    state["test_mutation"] = True
    assert "test_mutation" not in get_diagnostic_state()


def test_drive_status_adds_cached_authority_diagnostics_without_database_work(monkeypatch):
    from modules import localization_authority_worker, runs_autodrive

    expected = {"availability": "available", "mode": "off", "authority_granted": False}
    monkeypatch.setattr(runs_autodrive, "get_drive_state", lambda: {"last_result": None})
    monkeypatch.setattr(localization_authority_worker, "get_diagnostic_state", lambda: expected)
    response = runs_autodrive.get_drive_status_with_outstanding()
    assert response["localization_authority"] == expected
    assert {"state", "outstanding", "localization_lane"} <= response.keys()


def test_documented_drive_contract_includes_optional_authority_diagnostics():
    from pathlib import Path
    import yaml

    path = Path(__file__).resolve().parents[1] / "docs/reference/api/openapi.yaml"
    spec = yaml.safe_load(path.read_text())
    model = spec["components"]["schemas"]["RunsDriveStatus"]
    assert model["properties"]["localization_authority"]["type"] == "object"
    assert "localization_authority" not in model.get("required", [])
