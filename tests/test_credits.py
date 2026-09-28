"""The spending limit holds a reserve per run, charges the real cost, and refuses runs past it."""

from __future__ import annotations

import httpx
import pytest

from backend import config, credits
from backend.main import app


@pytest.fixture
def limit(monkeypatch):
    monkeypatch.setattr(config, "SPEND_LIMIT_USD", 2.5)
    monkeypatch.setattr(credits, "_store", credits._Memory())


async def test_a_run_holds_the_reserve_then_pays_its_real_cost(limit):
    held = await credits.reserve()
    assert await credits.status() == (2.5, config.RUN_RESERVE_USD)
    await credits.settle(held, 0.55)
    assert await credits.status() == (2.5, pytest.approx(0.55))


async def test_runs_past_the_limit_are_refused_and_hold_nothing(limit):
    await credits.reserve()
    await credits.reserve()
    with pytest.raises(credits.OutOfCredits):
        await credits.reserve()  # 3 × $1 holds > $2.50
    assert (await credits.status())[1] == pytest.approx(2 * config.RUN_RESERVE_USD)


async def test_no_limit_means_no_accounting(monkeypatch):
    monkeypatch.setattr(config, "SPEND_LIMIT_USD", None)
    assert await credits.reserve() == 0.0 and await credits.status() is None


async def test_api_reports_what_is_left_and_refuses_when_used_up(limit):
    await credits._store.add(2.0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        left = (await c.get("/api/credits")).json()
        assert (left["limit_usd"], left["remaining_usd"]) == (2.5, 0.5)
        r = await c.post("/api/plan", json={"brief": "handmade candles, $30"})
        assert r.status_code == 402 and "used up" in r.json()["detail"]
