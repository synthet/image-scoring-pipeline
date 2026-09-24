"""The SPA's prerequisite table is a hand-mirrored copy of the backend's — keep them equal.

``frontend/src/constants/pipeline.ts`` declares ``STAGE_PREREQUISITES`` so the New Run
dialog can grey out stages whose prerequisites are unmet, and it has to agree with
``modules.phases.PHASE_PREREQUISITES`` or the UI offers submissions the API now rejects.
Adding the ``localization`` phase (rollout stage 4) touches exactly these two tables.

Parsed with a regex rather than a TS toolchain: the block is a flat object literal and
this must run in the plain pytest subset with no Node available.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from modules.phases import PHASE_ENABLED_CONFIG_KEYS, PHASE_PREREQUISITES

PIPELINE_TS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "constants" / "pipeline.ts"

_BLOCK_RE = re.compile(
    r"STAGE_PREREQUISITES\s*:\s*Record<[^>]*>\s*=\s*\{(?P<body>.*?)\n\}",
    re.DOTALL,
)
_ENTRY_RE = re.compile(r"^\s*(?P<key>\w+)\s*:\s*\[(?P<vals>[^\]]*)\]\s*,?\s*$")


def _parse_frontend_prerequisites() -> dict[str, tuple[str, ...]]:
    source = PIPELINE_TS.read_text(encoding="utf-8")
    block = _BLOCK_RE.search(source)
    assert block, f"STAGE_PREREQUISITES object literal not found in {PIPELINE_TS}"

    parsed: dict[str, tuple[str, ...]] = {}
    for line in block.group("body").splitlines():
        entry = _ENTRY_RE.match(line)
        if not entry:
            continue
        values = tuple(
            v.strip().strip("'\"")
            for v in entry.group("vals").split(",")
            if v.strip()
        )
        parsed[entry.group("key")] = values
    assert parsed, "parsed STAGE_PREREQUISITES but found no entries"
    return parsed


@pytest.fixture(scope="module")
def frontend_prereqs() -> dict[str, tuple[str, ...]]:
    if not PIPELINE_TS.exists():
        pytest.skip(f"frontend constants not present: {PIPELINE_TS}")
    return _parse_frontend_prerequisites()


# Config-gated phases stay out of the SPA until the slice that enables them (#387
# decision 1): the New Run dialog must not offer a stage every submit surface rejects.
_GATED = set(PHASE_ENABLED_CONFIG_KEYS)


def test_every_backend_phase_appears_in_the_frontend_table(frontend_prereqs):
    missing = sorted(set(PHASE_PREREQUISITES) - set(frontend_prereqs) - _GATED)
    assert not missing, (
        f"phases missing from {PIPELINE_TS.name}: {missing}. "
        "Add them to STAGE_PREREQUISITES or the New Run dialog will not gate them."
    )


def test_prerequisites_agree_for_every_backend_phase(frontend_prereqs):
    mismatches = {
        code: {"backend": expected, "frontend": frontend_prereqs[code]}
        for code, expected in PHASE_PREREQUISITES.items()
        if code not in _GATED and frontend_prereqs.get(code) != expected
    }
    assert not mismatches, f"backend/frontend prerequisite drift: {mismatches}"


def test_frontend_extras_are_not_backend_phases(frontend_prereqs):
    """The TS table may carry UI-only stages (``maintenance``) with no backend phase.

    They are allowed, but must not claim a prerequisite the backend never enforces.
    """
    for code, prereqs in frontend_prereqs.items():
        if code in PHASE_PREREQUISITES:
            continue
        assert prereqs == (), (
            f"UI-only stage {code!r} declares prerequisites {prereqs} that no backend "
            "phase enforces"
        )
