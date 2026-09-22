"""The phase <-> job_type mapping has one home: modules.phases.

Before the localization control-plane consolidation this mapping existed in four
places (db_legacy.job_type_for_phase_dispatch, electron_run_helpers._phase_code_map,
and two tables in job_dispatcher). Adding a seventh phase meant editing all of them,
and nothing failed if one was missed -- which is how bird_species ended up routable
by fallthrough rather than registration.

These tests pin the round trip and guard the one table that is still hand-written
(the dispatcher's job_type -> runner-instance map, which cannot be derived from the
registry because it binds live runner objects). See issue #366.
"""

import pytest

from modules.phases import (
    PHASE_CODE_ALIASES,
    PHASE_TO_JOB_TYPE,
    PhaseCode,
    job_type_for_phase,
    phase_for_job_type,
)


@pytest.mark.parametrize("phase", list(PhaseCode))
def test_phase_job_type_round_trip(phase):
    assert phase_for_job_type(job_type_for_phase(phase)) == phase.value


def test_every_phase_has_a_job_type():
    assert set(PHASE_TO_JOB_TYPE) == {p.value for p in PhaseCode}


def test_phase_for_job_type_resolves_legacy_spellings():
    assert phase_for_job_type("tagging") == "keywords"
    assert phase_for_job_type("clustering") == "culling"
    assert phase_for_job_type("selection") == "culling"
    assert phase_for_job_type("bird-species") == "bird_species"


def test_phase_for_job_type_passes_through_phase_codes():
    """Callers hand it either vocabulary; a phase code must not be remapped."""
    for phase in PhaseCode:
        assert phase_for_job_type(phase.value) == phase.value


def test_phase_for_job_type_falls_back_for_unknown_and_blank():
    assert phase_for_job_type(None) == "scoring"
    assert phase_for_job_type("") == "scoring"
    assert phase_for_job_type("   ") == "scoring"
    assert phase_for_job_type("maintenance") == "scoring"
    assert phase_for_job_type("maintenance", default="maintenance") == "maintenance"


def test_dispatch_mapping_matches_the_registry():
    """db_legacy.job_type_for_phase_dispatch must agree with PHASE_TO_JOB_TYPE."""
    from modules.db_legacy import job_type_for_phase_dispatch

    for phase, job_type in PHASE_TO_JOB_TYPE.items():
        assert job_type_for_phase_dispatch(phase) == job_type

    # `cluster` / `clustering` are the legacy ClusteringRunner job type, not phase
    # codes -- the dispatcher accepts them alongside `selection`, so they pass through.
    assert job_type_for_phase_dispatch("cluster") == "cluster"
    assert job_type_for_phase_dispatch("clustering") == "clustering"
    assert job_type_for_phase_dispatch("") == "scoring"


def test_every_phase_vocabulary_spelling_is_routable_by_the_dispatcher():
    """Drift guard for the one map that stays hand-written.

    A new PhaseCode whose job_type is absent from JobDispatcher.runner_map is silently
    unroutable: `_start_job_for_phase` logs "Unknown queued job_type" and returns False.
    Assert every spelling the rest of the control plane can produce has an entry.
    """
    import inspect
    import re

    from modules.job_dispatcher import JobDispatcher

    source = inspect.getsource(JobDispatcher)
    block = source[source.index("runner_map = {"):]
    block = block[: block.index("}")]
    routable = set(re.findall(r'"([^"]+)":', block))

    expected = (
        {p.value for p in PhaseCode}
        | set(PHASE_TO_JOB_TYPE.values())
        | set(PHASE_CODE_ALIASES)
    )
    missing = sorted(expected - routable)
    assert not missing, f"not routable by JobDispatcher.runner_map: {missing}"
