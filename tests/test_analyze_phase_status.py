"""Regression tests for missing-row coverage in the phase-status audit (#166)."""

import json

import pytest

from scripts.analysis import analyze_phase_status as audit


@pytest.fixture
def image():
    return {
        "id": 42,
        "file_path": "/photos/frame.jpg",
        "folder_path": "/photos",
        **{signal: False for signal in audit.DATA_SIGNAL.values()},
    }


@pytest.mark.parametrize("phase", ["scoring", "culling", "keywords"])
def test_missing_row_is_reported_without_phase_data(image, phase):
    issues = audit.analyze_image(image, {}, [phase])

    assert len(issues) == 1
    assert issues[0]["type"] == "ips_missing"
    assert issues[0]["phase"] == phase
    assert issues[0]["ips_status"] is None
    assert issues[0]["data_present"] is False


def test_missing_row_with_data_keeps_existing_report_type(image):
    image["data_culling"] = True

    issues = audit.analyze_image(image, {}, ["culling"])

    assert [issue["type"] for issue in issues] == ["ips_missing_has_data"]


def test_existing_not_started_row_is_not_a_missing_row(image):
    assert audit.analyze_image(image, {42: {"culling": {"status": "not_started"}}}, ["culling"]) == []


def test_default_audit_omits_optional_phases_without_data_signals(image):
    assert audit.PHASES == ["indexing", "metadata", "scoring", "culling", "keywords"]
    assert len(audit.analyze_image(image, {}, audit.PHASES)) == 5


@pytest.mark.parametrize("phase", ["localization", "bird_species"])
def test_explicit_optional_phase_reports_missing_row_without_inventing_data(image, phase):
    issues = audit.analyze_image(image, {}, [phase])

    assert len(issues) == 1
    assert issues[0]["type"] == "ips_missing"
    assert issues[0]["data_present"] is None
    assert audit.analyze_image(image, {42: {phase: {"status": "done"}}}, [phase]) == []


def test_missing_row_appears_in_report_and_repair_guidance(image, capsys):
    phases = ["culling"]
    issues = audit.analyze_image(image, {}, phases)
    audit.print_report(
        [image], issues, {"stale": [], "flag_mismatches": []},
        {"legacy_only": [], "junction_only": []}, phases, {}, verbose=True,
    )

    report = capsys.readouterr().out
    assert "miss/no-row" in report
    assert "[GAP-J] 1" in report
    assert "--missing-rows" in report
    assert "null!N" in report


@pytest.mark.parametrize("phase", ["localization", "bird_species"])
def test_optional_phase_can_be_selected_on_cli(monkeypatch, phase):
    monkeypatch.setattr("sys.argv", ["analyze_phase_status.py", "--phase", phase])
    assert audit.parse_args().phase == phase


def test_cli_exports_rowless_images_in_issue_counts(image, monkeypatch, tmp_path):
    output = tmp_path / "audit.json"
    monkeypatch.setattr("sys.argv", ["analyze_phase_status.py", "--output", str(output)])

    class Connection:
        def close(self):
            pass

    monkeypatch.setattr(audit.db, "get_db", Connection)
    monkeypatch.setattr(audit, "load_images", lambda *a, **kw: [image])
    monkeypatch.setattr(audit, "load_ips", lambda *a, **kw: {})
    monkeypatch.setattr(audit, "check_keywords_sync", lambda *a, **kw: {
        "legacy_only": [], "junction_only": [],
    })
    monkeypatch.setattr(audit, "check_folder_caches", lambda *a, **kw: {
        "stale": [], "flag_mismatches": [],
    })
    monkeypatch.setattr(audit, "check_bird_species", lambda *a, **kw: {
        "birds_no_species": [], "species_no_birds": [],
    })
    monkeypatch.setattr(audit, "check_stuck_running", lambda *a, **kw: [])

    audit.main()

    report = json.loads(output.read_text())
    assert report["summary"]["total_issues"] == 5
    assert {issue["phase"] for issue in report["issues_by_type"]["ips_missing"]} == set(audit.PHASES)


@pytest.mark.parametrize("phase", ["localization", "bird_species"])
def test_optional_phase_verbose_report_handles_unknown_data(image, capsys, phase):
    audit.print_report(
        [image], [], {"stale": [], "flag_mismatches": []},
        {"legacy_only": [], "junction_only": []}, [phase],
        {42: {phase: {"status": "done"}}}, verbose=True,
    )
    report = capsys.readouterr().out
    assert "done|?" in report
    assert "DONE!" not in report
