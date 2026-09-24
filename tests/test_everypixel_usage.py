"""Unit tests for Everypixel usage accounting and spend limits (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.everypixel import (
    EverypixelBudgetExceeded,
    EverypixelClient,
    EverypixelUsageStats,
    estimated_cost_usd,
    marginal_cost_usd,
    usd_per_quality_request,
)


def test_usd_per_request_from_pricing():
    assert usd_per_quality_request() == pytest.approx(0.0006)


def test_estimated_cost_respects_free_quota_per_type():
    stats = EverypixelUsageStats(stock_requests=500, ugc_requests=100)
    assert estimated_cost_usd(stats, free_stock=500, free_ugc=500) == pytest.approx(0.0)
    stats.stock_requests = 501
    assert estimated_cost_usd(stats, free_stock=500, free_ugc=500) == pytest.approx(0.0006)


def test_marginal_cost_inside_and_outside_free_quota():
    stats = EverypixelUsageStats(stock_requests=499, ugc_requests=0)
    assert marginal_cost_usd("stock", stats, free_stock=500, free_ugc=500) == pytest.approx(0.0)
    stats.stock_requests = 500
    assert marginal_cost_usd("stock", stats, free_stock=500, free_ugc=500) == pytest.approx(0.0006)


def test_client_blocks_before_request_when_over_limit(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EVERYPIXEL_CLIENT_ID", "id")
    monkeypatch.setenv("EVERYPIXEL_SECRET_KEY", "secret")
    img = tmp_path / "a.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    stats = EverypixelUsageStats(stock_requests=16667, ugc_requests=0)
    client = EverypixelClient(
        spend_limit_usd=10.0,
        assume_free_quota_stock=0,
        assume_free_quota_ugc=0,
        usage=stats,
    )
    with pytest.raises(EverypixelBudgetExceeded):
        client.score(img, model="stock")


def test_usage_persist_roundtrip(tmp_path: Path):
    state = tmp_path / "everypixel_usage.json"
    stats = EverypixelUsageStats(stock_requests=3, ugc_requests=7)
    stats.save(state)
    loaded = EverypixelUsageStats.load(state)
    assert loaded.stock_requests == 3
    assert loaded.ugc_requests == 7


def test_ten_dollar_cap_request_count_after_free_quota():
    """After 500 free per type, ~16_666 paid calls reach ~$10 at $0.0006 each."""
    unit = usd_per_quality_request()
    paid_affordable = int(10.0 / unit)
    assert paid_affordable == 16666
    stats = EverypixelUsageStats(stock_requests=500 + paid_affordable, ugc_requests=0)
    cost = estimated_cost_usd(stats, free_stock=500, free_ugc=500)
    assert cost == pytest.approx(paid_affordable * unit, rel=1e-9)
    assert cost < 10.0
    stats.stock_requests += 1
    assert marginal_cost_usd("stock", stats, free_stock=500, free_ugc=500) == pytest.approx(unit)
    assert estimated_cost_usd(stats, free_stock=500, free_ugc=500) > 10.0 - 1e-12
