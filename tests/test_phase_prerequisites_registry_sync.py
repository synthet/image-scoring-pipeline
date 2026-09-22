"""Ensure PHASE_PREREQUISITES matches PhaseExecutor.depends_on from phase_executors."""

import pytest

from modules.phase_executors import register_all
from modules.phases import PHASE_PREREQUISITES, PhaseCode, PhaseRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    PhaseRegistry._executors.clear()
    yield
    PhaseRegistry._executors.clear()


def test_phase_prerequisites_match_registered_executors():
    """Drift guard: registry depends_on must match PHASE_PREREQUISITES."""

    class _StubRunner:
        def start_batch(self, *_a, **_kw):
            return "ok"

    register_all(
        indexing_runner=_StubRunner(),
        metadata_runner=_StubRunner(),
        scoring_runner=_StubRunner(),
        tagging_runner=_StubRunner(),
        clustering_runner=_StubRunner(),
        selection_runner=_StubRunner(),
        bird_species_runner=_StubRunner(),
    )

    for code_str, expected_tuple in PHASE_PREREQUISITES.items():
        ex = PhaseRegistry._executors.get(PhaseCode(code_str))
        assert ex is not None, f"no executor registered for {code_str!r}"
        deps = tuple(
            d.value if isinstance(d, PhaseCode) else str(d)
            for d in (ex.depends_on or [])
        )
        assert deps == expected_tuple, (
            f"mismatch for {code_str}: registry={deps} PHASE_PREREQUISITES={expected_tuple}"
        )


def test_registry_lookup_accepts_string_and_enum():
    """``PhaseRegistry`` is written with enum members and read with strings.

    Both spellings must resolve to the same executor.  This holds today only because
    ``PhaseCode``'s ``str`` mixin supplies ``__hash__``/``__eq__``; ``PhaseRegistry._key``
    normalizes so the guarantee does not depend on that.
    """
    from modules.phases import PhaseExecutor

    PhaseRegistry.register(
        PhaseExecutor(code=PhaseCode.SCORING, executor_version="1.0.0", depends_on=[])
    )

    by_enum = PhaseRegistry.get(PhaseCode.SCORING)
    by_string = PhaseRegistry.get("scoring")
    assert by_enum is not None
    assert by_enum is by_string
    assert PhaseRegistry.is_registered("scoring")
    assert PhaseRegistry.is_registered(PhaseCode.SCORING)


def test_registry_lookup_of_unknown_and_blank_codes_is_none():
    assert PhaseRegistry.get("localization") is None
    assert PhaseRegistry.get("") is None
    assert PhaseRegistry.get(None) is None
    assert not PhaseRegistry.is_registered("localization")


def test_every_pipeline_phase_has_a_prerequisite_entry():
    """A new PhaseCode without a PHASE_PREREQUISITES row would KeyError in
    ``phase_executors._prereqs`` at import time — catch it here instead."""
    assert set(PHASE_PREREQUISITES) == {p.value for p in PhaseCode}


# ---------------------------------------------------------------------------
# Preferred-before (advisory) edges — issue #364
# ---------------------------------------------------------------------------

def test_preferred_before_matches_registered_executors():
    """Same drift guard as depends_on, for the advisory table."""
    from modules.phases import PHASE_PREFERRED_BEFORE

    class _StubRunner:
        def start_batch(self, *_a, **_kw):
            return "ok"

    register_all(
        indexing_runner=_StubRunner(),
        metadata_runner=_StubRunner(),
        scoring_runner=_StubRunner(),
        tagging_runner=_StubRunner(),
        clustering_runner=_StubRunner(),
        selection_runner=_StubRunner(),
        bird_species_runner=_StubRunner(),
    )

    for code in PhaseCode:
        ex = PhaseRegistry._executors.get(code)
        assert ex is not None, f"no executor registered for {code.value!r}"
        preferred = tuple(str(p) for p in (ex.preferred_before or []))
        assert preferred == PHASE_PREFERRED_BEFORE.get(code.value, ())


def test_preferred_before_keys_are_known_phases():
    """An advisory edge naming a phase that does not exist is a typo, not a feature."""
    from modules.phases import PHASE_PREFERRED_BEFORE

    known = {p.value for p in PhaseCode}
    for source, consumers in PHASE_PREFERRED_BEFORE.items():
        assert source in known, f"unknown preferred-before source {source!r}"
        for consumer in consumers:
            assert consumer in known, f"unknown preferred-before consumer {consumer!r}"


def test_a_preferred_edge_never_becomes_a_prerequisite(monkeypatch):
    """The whole point of the split: an advisory edge must not gate its consumer.

    ``PHASE_PREFERRED_BEFORE`` is empty until ``localization`` lands, so inject the
    Stage-4 shape and assert the gate ignores it.  Were ``missing_prerequisites`` to
    consult the advisory table, a detector failure would block scoring.
    """
    from modules import phases

    monkeypatch.setitem(phases.PHASE_PREFERRED_BEFORE, "localization", ("scoring",))

    # scoring requested alone, with only its real prerequisite satisfied
    assert phases.missing_prerequisites(["scoring"], ["metadata"]) == {}
    # and co-requesting the advisory source in the "wrong" order is still fine
    assert phases.missing_prerequisites(["scoring", "localization"], ["metadata"]) == {}


def test_a_preferred_edge_never_enters_the_phase_prefix(monkeypatch):
    """``pipeline_prefix_through`` enqueues hard prerequisites; advisory edges are not."""
    from modules import phases

    monkeypatch.setitem(phases.PHASE_PREFERRED_BEFORE, "localization", ("keywords",))

    assert "localization" not in phases.pipeline_prefix_through("keywords")
    assert phases.pipeline_prefix_through("keywords") == [
        "indexing", "metadata", "scoring", "keywords",
    ]
