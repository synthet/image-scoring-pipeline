"""Hermetic vexlum fixtures: token key and catalog cache live under tmp_path."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _vexlum_env(tmp_path_factory, monkeypatch):
    from modules.vexlum import policy

    cache = tmp_path_factory.getbasetemp() / "vexlum-cache"
    monkeypatch.setenv("VEXLUM_CACHE_DIR", str(cache))
    monkeypatch.setenv("VEXLUM_TOKEN_SECRET", "test-secret")
    monkeypatch.delenv("VEXLUM_ALLOW_ELEVATED", raising=False)
    policy.reset_token_key_cache()
    yield
    policy.reset_token_key_cache()
