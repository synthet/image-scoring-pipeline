"""Explicit phase scoping of the existing one-shot missing-row repair (#166)."""

import pytest

from scripts.maintenance import repair_analyzer_gaps as repair


@pytest.mark.parametrize("phases", [[], ["bird_species"], ["culling", "bird_species"]])
def test_missing_row_repair_passes_explicit_phase_scope(monkeypatch, phases):
    args = ["repair_analyzer_gaps.py", "--missing-rows", "--dry-run",
            "--missing-rows-folder", "/photos", "--limit", "25"]
    for phase in phases:
        args += ["--missing-rows-phase", phase]
    monkeypatch.setattr("sys.argv", args)
    calls = []
    monkeypatch.setattr(repair.db, "init_db", lambda: None)

    def backfill(**kwargs):
        calls.append(kwargs)
        return {"matched": 0, "inserted": 0, "by_phase": {}}

    monkeypatch.setattr(repair.db, "backfill_missing_phase_rows", backfill)
    repair.main()

    assert calls == [{
        "folder_path": "/photos", "phase_codes": phases or None,
        "limit": 25, "dry_run": True,
    }]


def test_missing_row_repair_rejects_unknown_phase_before_initialization(monkeypatch):
    monkeypatch.setattr("sys.argv", ["repair_analyzer_gaps.py", "--missing-rows",
                                     "--missing-rows-phase", "bogus"])
    monkeypatch.setattr(repair.db, "init_db", lambda: pytest.fail("invalid scope initialized DB"))
    with pytest.raises(SystemExit) as exc:
        repair.main()
    assert exc.value.code == 2
