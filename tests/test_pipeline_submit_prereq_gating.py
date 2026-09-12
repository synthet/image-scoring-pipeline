"""POST /api/pipeline/submit — stage vocabulary and prerequisite gating (issue #346).

This router had no test file. Before localization stage 1 it accepted its own
five-token vocabulary (``indexing|metadata|score|tag|cluster``) and never called
``assert_prereqs_for_scope``, so it was the one submission path that could queue a
downstream stage over an unprepared folder.

No PostgreSQL required: ``compute_satisfied_phases_for_scope``, the selector preview
and ``db.enqueue_job`` are all stubbed.
"""

from __future__ import annotations

import pytest

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda *_a, **_kw: None)
    from modules import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.create_api_router())
    with TestClient(app) as client:
        yield client


@pytest.fixture(name="satisfied")
def stub_satisfied_phases(monkeypatch):
    """Controlled satisfied-phase set; mutate it in a test to prepare the scope."""
    satisfied: set[str] = set()
    monkeypatch.setattr(
        "modules.phases.compute_satisfied_phases_for_scope",
        lambda _scope_paths: set(satisfied),
    )
    return satisfied


@pytest.fixture(autouse=True)
def stub_preview(monkeypatch):
    """Selector preview always resolves images, so gating is what fails (or does not)."""
    monkeypatch.setattr(
        "modules.api.validate_and_preview",
        lambda _selector_request: {"preview_count": 5},
    )


@pytest.fixture(autouse=True)
def stub_runners(monkeypatch):
    """Install idle stub runners.

    Without these the router short-circuits on "Orchestrator unavailable" before it
    ever reaches the routing branches under test.

    Patched on ``modules.api``, not ``modules.api.state``. ``modules.api`` normally
    forwards ``_*_runner`` to ``state`` through a module ``__getattr__``, but any test
    that does ``monkeypatch.setattr(api, "_clustering_runner", ...)`` — several in
    ``tests/test_api_queue.py`` do — leaves a real module attribute behind on undo,
    which shadows that forwarding for the rest of the session. Patching the same level
    works whether or not the shadow is already there.
    """
    class _IdleRunner:
        is_running = False

    for attr in (
        "_indexing_runner",
        "_metadata_runner",
        "_scoring_runner",
        "_tagging_runner",
        "_clustering_runner",
        "_selection_runner",
        "_bird_species_runner",
    ):
        monkeypatch.setattr(f"modules.api.{attr}", _IdleRunner(), raising=False)


@pytest.fixture(name="enqueued", autouse=True)
def stub_enqueue(monkeypatch):
    """Capture ``db.enqueue_job`` kwargs instead of touching the queue.

    Autouse so no test in this file can reach a live Postgres (see issue #336).
    """
    calls: list[dict] = []

    def _fake(input_path, **kwargs):
        calls.append({"input_path": input_path, **kwargs})
        return (4242, 1)

    def _fake_phases(job_id, phase_codes, **_kw):
        return [
            {"phase_order": i, "phase_code": code, "state": "pending"}
            for i, code in enumerate(phase_codes)
        ]

    monkeypatch.setattr("modules.db.enqueue_job", _fake)
    # The router persists the phase plan straight after enqueueing; without this the
    # stubbed job_id hits a real FK against ``jobs``.
    monkeypatch.setattr("modules.db.create_job_phases", _fake_phases)
    return calls


def _submit(client, folder=None, stages=("score",), **extra):
    body: dict = {"stage_codes": list(stages), **extra}
    if folder is not None:
        body["workspace_target"] = folder
    return client.post("/api/pipeline/submit", json=body)


def _folder(tmp_path, name="scope"):
    p = tmp_path / name
    p.mkdir()
    return str(p.resolve())


# ---------------------------------------------------------------------------
# Stage vocabulary (issue #346 defect 4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("legacy", ["score", "tag", "cluster"])
def test_legacy_stage_tokens_still_resolve(api_client, tmp_path, satisfied, enqueued, legacy):
    """Backward compatibility: the pre-#346 vocabulary must not start 400-ing."""
    satisfied.update({"indexing", "metadata", "scoring", "culling", "keywords"})
    r = _submit(api_client, _folder(tmp_path), [legacy])
    assert r.status_code == 200, r.text
    assert "Invalid stage_codes" not in (r.json().get("message") or "")


@pytest.mark.parametrize("code", ["scoring", "culling", "keywords", "bird_species"])
def test_canonical_phase_codes_are_accepted(api_client, tmp_path, satisfied, enqueued, code):
    """The widened vocabulary: every PhaseCode value, not just the five aliases."""
    satisfied.update({"indexing", "metadata", "scoring", "culling", "keywords"})
    r = _submit(api_client, _folder(tmp_path), [code])
    assert r.status_code == 200, r.text
    assert "Invalid stage_codes" not in (r.json().get("message") or "")


def test_unknown_stage_token_is_rejected_with_the_widened_valid_list(api_client, tmp_path, satisfied):
    r = _submit(api_client, _folder(tmp_path), ["localization"])
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    message = body["message"]
    assert "Invalid stage_codes" in message
    assert "localization" in message
    # The advertised vocabulary now covers canonical codes and the legacy aliases.
    for token in ("bird_species", "keywords", "culling", "score", "tag", "cluster"):
        assert token in message


def test_empty_stage_codes_rejected(api_client, tmp_path, satisfied):
    r = _submit(api_client, _folder(tmp_path), [])
    assert r.json()["success"] is False
    assert "At least one stage_code" in r.json()["message"]


# ---------------------------------------------------------------------------
# Prerequisite gate — the breaking change
# ---------------------------------------------------------------------------

def test_culling_over_unscored_folder_is_rejected(api_client, tmp_path, satisfied, enqueued):
    """BREAKING: this submission used to be accepted and queued.

    ``{"stage_codes": ["cluster"]}`` against a folder with no scoring done now fails
    the same DAG check ``/api/runs/submit`` enforces.
    """
    satisfied.update({"indexing", "metadata"})  # scoring NOT satisfied
    r = _submit(api_client, _folder(tmp_path), ["cluster"])

    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "missing_prerequisites"
    assert body["data"]["missing"] == {"culling": ["scoring"]}
    assert enqueued == []


def test_bird_species_over_untagged_folder_is_rejected(api_client, tmp_path, satisfied, enqueued):
    satisfied.update({"indexing", "metadata", "scoring", "culling"})
    r = _submit(api_client, _folder(tmp_path), ["bird_species"])

    assert r.json()["data"]["missing"] == {"bird_species": ["keywords"]}
    assert enqueued == []


def test_co_requested_prerequisite_passes_the_gate(api_client, tmp_path, satisfied, enqueued):
    """A prerequisite supplied in the same call satisfies the gate."""
    satisfied.update({"indexing"})
    r = _submit(api_client, _folder(tmp_path), ["metadata", "score"])

    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert len(enqueued) == 1


def test_co_requested_prerequisite_after_its_consumer_is_rejected(api_client, tmp_path, satisfied, enqueued):
    """BREAKING (issue #351): accepted before, when the gate only checked membership.

    This router resolves ``stage_codes`` one token at a time to preserve the client's
    order, so ``["tag", "score"]`` really would run ``keywords`` first.
    """
    satisfied.update({"indexing", "metadata"})  # scoring NOT satisfied
    r = _submit(api_client, _folder(tmp_path), ["tag", "score"])

    body = r.json()
    assert body["success"] is False
    assert body["data"]["code"] == "missing_prerequisites"
    assert body["data"]["missing"] == {"keywords": ["scoring"]}
    assert enqueued == []


def test_the_same_stages_in_canonical_order_are_accepted(api_client, tmp_path, satisfied, enqueued):
    """Mirror of the case above: only the order differs."""
    satisfied.update({"indexing", "metadata"})
    r = _submit(api_client, _folder(tmp_path), ["score", "tag"])

    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert enqueued[0]["phase_code"] == "scoring"


@pytest.mark.parametrize("stages", [("cluster", "tag"), ("tag", "cluster")])
def test_sibling_stages_are_accepted_in_either_order(api_client, tmp_path, satisfied, enqueued, stages):
    """``culling`` and ``keywords`` are siblings under ``scoring``, not ordered pairwise."""
    satisfied.update({"indexing", "metadata", "scoring"})
    r = _submit(api_client, _folder(tmp_path), list(stages))

    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert len(enqueued) == 1


def test_satisfied_scope_passes_the_gate(api_client, tmp_path, satisfied, enqueued):
    satisfied.update({"indexing", "metadata"})
    r = _submit(api_client, _folder(tmp_path), ["score"])

    assert r.json()["success"] is True
    assert enqueued[0]["phase_code"] == "scoring"
    assert enqueued[0]["job_type"] == "scoring"


def test_indexing_is_never_blocked(api_client, tmp_path, satisfied, enqueued):
    """The root phase has no prerequisites, so an empty scope must not block it."""
    r = _submit(api_client, _folder(tmp_path), ["indexing"])
    assert r.json()["success"] is True


def test_folder_paths_selector_is_gated(api_client, tmp_path, satisfied, enqueued):
    """The gate reads ``folder_paths`` too, not only ``workspace_target``."""
    satisfied.update({"indexing", "metadata"})
    r = api_client.post(
        "/api/pipeline/submit",
        json={"folder_paths": [_folder(tmp_path)], "stage_codes": ["cluster"]},
    )
    assert r.json()["data"]["code"] == "missing_prerequisites"


def test_folder_ids_selector_is_gated(api_client, satisfied, enqueued, monkeypatch):
    """``folder_ids`` is a folder scope, so it must be gated like ``folder_paths``.

    The router already counts ``folder_ids`` as a folder selector for the culling check
    further down, but the gate only ever looked at ``workspace_target`` and
    ``folder_paths``.  That made the whole DAG opt-out: submit the same folder by id and
    every stage order was accepted.
    """
    monkeypatch.setattr("modules.db.get_folder_by_id", lambda fid: "/mnt/d/Photos/scope")
    satisfied.update({"indexing", "metadata"})  # scoring NOT satisfied
    r = api_client.post(
        "/api/pipeline/submit",
        json={"folder_ids": [12], "stage_codes": ["cluster"]},
    )

    body = r.json()
    assert body["success"] is False
    assert body["data"]["missing"] == {"culling": ["scoring"]}
    assert enqueued == []


def test_folder_ids_selector_gates_stage_order(api_client, satisfied, enqueued, monkeypatch):
    """The issue #351 ordering rule has to hold on this selector form too."""
    monkeypatch.setattr("modules.db.get_folder_by_id", lambda fid: "/mnt/d/Photos/scope")
    satisfied.update({"indexing", "metadata"})
    r = api_client.post(
        "/api/pipeline/submit",
        json={"folder_ids": [12], "stage_codes": ["tag", "score"]},
    )

    assert r.json()["data"]["missing"] == {"keywords": ["scoring"]}
    assert enqueued == []


def test_folder_ids_selector_passes_a_prepared_scope(api_client, satisfied, enqueued, monkeypatch):
    """Resolving the ids must not turn into a blanket rejection."""
    monkeypatch.setattr("modules.db.get_folder_by_id", lambda fid: "/mnt/d/Photos/scope")
    satisfied.update({"indexing", "metadata", "scoring"})
    r = api_client.post(
        "/api/pipeline/submit",
        json={"folder_ids": [12], "stage_codes": ["cluster"]},
    )

    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    assert len(enqueued) == 1


def test_unresolvable_folder_id_leaves_the_submission_ungated(api_client, satisfied, enqueued, monkeypatch):
    """An id with no folder row yields no gate path, which must not reject the run.

    Same reasoning as the image-id case below: an empty scope reports every non-root
    phase unsatisfied, so gating on nothing would fail legitimate work.
    """
    monkeypatch.setattr("modules.db.get_folder_by_id", lambda fid: None)
    r = api_client.post(
        "/api/pipeline/submit",
        json={"folder_ids": [999], "stage_codes": ["cluster"]},
    )

    body = r.json()
    assert body["success"] is True
    assert (body.get("data") or {}).get("code") != "missing_prerequisites"


def test_folder_id_lookup_failure_does_not_500(api_client, satisfied, enqueued, monkeypatch):
    """A DB hiccup resolving one id degrades to ungated, not to a 500."""
    def _boom(_fid):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("modules.db.get_folder_by_id", _boom)
    r = api_client.post(
        "/api/pipeline/submit",
        json={"folder_ids": [12], "stage_codes": ["cluster"]},
    )

    assert r.status_code == 200, r.text
    assert r.json()["success"] is True


def test_image_id_selector_is_not_gated(api_client, satisfied, enqueued):
    """Image-scoped submissions stay ungated on purpose.

    ``compute_satisfied_phases_for_scope`` aggregates per-folder summaries; with no
    folder in scope it reports every non-root phase unsatisfied, which would reject
    legitimate image-id work. Only folder scopes can be gated meaningfully.
    """
    r = api_client.post(
        "/api/pipeline/submit",
        json={"image_ids": [101, 102], "stage_codes": ["score"]},
    )
    body = r.json()
    assert body["success"] is True
    assert (body.get("data") or {}).get("code") != "missing_prerequisites"


# ---------------------------------------------------------------------------
# Routing (issue #346 defect 7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("stage", "phase_code", "job_type"),
    [
        ("indexing", "indexing", "indexing"),
        ("metadata", "metadata", "metadata"),
        ("score", "scoring", "scoring"),
        ("tag", "keywords", "tagging"),
        # NOTE: culling here enters the *clustering* runner, not SelectionRunner —
        # this legacy endpoint has always done so, while PHASE_TO_JOB_TYPE maps
        # culling -> "selection" for /api/runs/submit and auto-drive. The dispatcher
        # accepts both spellings. Pinned as-is; changing it is a behaviour change
        # outside issue #346.
        ("cluster", "culling", "clustering"),
    ],
)
def test_first_stage_selects_the_right_entry_runner(
    api_client, tmp_path, satisfied, enqueued, stage, phase_code, job_type,
):
    satisfied.update({"indexing", "metadata", "scoring", "culling", "keywords"})
    r = _submit(api_client, _folder(tmp_path), [stage])

    assert r.status_code == 200, r.text
    assert len(enqueued) == 1
    assert enqueued[0]["phase_code"] == phase_code
    assert enqueued[0]["job_type"] == job_type


def test_bird_species_routes_to_its_own_runner_not_clustering(api_client, tmp_path, satisfied, enqueued):
    """``bird_species`` used to fall through the ``else`` branch into clustering."""
    satisfied.update({"indexing", "metadata", "scoring", "culling", "keywords"})
    r = _submit(api_client, _folder(tmp_path), ["bird_species"])

    assert r.status_code == 200, r.text
    assert len(enqueued) == 1
    assert enqueued[0]["phase_code"] == "bird_species"
    assert enqueued[0]["job_type"] == "bird_species"


def test_clustering_requires_a_folder_selector(api_client, satisfied, enqueued):
    r = api_client.post(
        "/api/pipeline/submit",
        json={"image_ids": [101], "stage_codes": ["cluster"]},
    )
    body = r.json()
    assert body["success"] is False
    assert "folder selector" in body["message"]
