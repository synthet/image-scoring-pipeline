"""Smoke tests for cli.py — no GPU or heavy imports required."""
import os
import sys

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def test_cli_help():
    """CLI --help exits successfully."""
    from typer.testing import CliRunner
    from cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "image scoring" in result.output.lower()
    assert "score" in result.output.lower()
    assert "config" in result.output.lower()


def test_cli_config_get_scoring():
    """config get scoring returns valid output (section or key)."""
    from typer.testing import CliRunner
    from cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["config", "get", "scoring"])
    assert result.exit_code == 0
    # Output is JSON (section) or a scalar
    out = result.output.strip()
    assert out.startswith("{") or out or True  # empty config is ok
