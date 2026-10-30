"""Maintenance commands cannot target the wrong database or activate authority."""
from types import SimpleNamespace

import pytest

from scripts.maintenance import localization_authority as cli


@pytest.mark.parametrize("expected", [None, "different_database"])
def test_mutations_require_verified_database_identity(monkeypatch, expected):
    calls = []
    store = SimpleNamespace(conn=SimpleNamespace(query_one=lambda _: {"name": "image_scoring_test"}),
                            set_mode=lambda mode: calls.append(mode))
    monkeypatch.setattr(cli, "AuthorityStore", lambda: store)
    argv = ["set-mode", "shadow"]
    if expected:
        argv = ["--expect-database", expected, *argv]
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2 and calls == []


def test_active_mode_is_not_exposed_by_the_cli():
    with pytest.raises(SystemExit) as error:
        cli.main(["set-mode", "active"])
    assert error.value.code == 2


@pytest.mark.parametrize('argv',[
    ['activate','--policy-hash','p','--receipt-sha256','r'],
    ['set-freshness','on'],
    ['approve-policy','--policy-hash','p','--receipt','x','--receipt-sha256','r','--actor','test'],
])
def test_effectful_rollout_commands_require_separate_confirmation(argv):
    with pytest.raises(SystemExit) as error:
        cli.main(argv)
    assert error.value.code == 2


def test_verified_shadow_mode_is_an_explicit_operator_action(monkeypatch, capsys):
    calls = []
    store = SimpleNamespace(conn=SimpleNamespace(query_one=lambda _: {"name": "image_scoring_test"}),
                            set_mode=lambda mode: calls.append(mode), diagnostics=lambda: {"mode": "shadow"})
    monkeypatch.setattr(cli, "AuthorityStore", lambda: store)
    assert cli.main(["--expect-database", "image_scoring_test", "set-mode", "shadow"]) == 0
    assert calls == ["shadow"] and '"database": "image_scoring_test"' in capsys.readouterr().out
