"""job_phases accepts the canonical ``cancelled`` spelling (STATUS_VOCABULARY.md).

Cancelling a running run mapped the job status to phase state ``cancelled``, but the
transition table only listed the legacy ``canceled``, so the phase row stayed
``running`` and the run page showed a stuck stage.
"""

from __future__ import annotations

import pytest

from modules import db_legacy


class _FakeTx:
    def __init__(self, state: str) -> None:
        self.state = state
        self.updates: list[tuple[str, list]] = []

    def query_one(self, sql, params):
        if sql.lstrip().startswith("SELECT id, state FROM job_phases"):
            return {"id": 7, "state": self.state}
        return None

    def execute(self, sql, params):
        self.updates.append((sql, list(params)))


@pytest.mark.parametrize("old_state", ["running", "paused", "queued", "pending", "cancel_requested"])
@pytest.mark.parametrize("new_state", ["cancelled", "canceled"])
def test_cancel_spellings_are_valid_transitions(old_state, new_state):
    tx = _FakeTx(old_state)
    assert db_legacy.set_job_phase_state(6839, "maintenance", new_state, tx=tx) is True
    assert tx.updates and tx.updates[0][1][0] == new_state


@pytest.mark.parametrize("terminal", ["cancelled", "canceled"])
def test_cancelled_phase_is_terminal(terminal):
    with pytest.raises(ValueError, match="Invalid job phase transition"):
        db_legacy.set_job_phase_state(6839, "maintenance", "running", tx=_FakeTx(terminal))
