"""A finished run is stored whole, so a reload or a shared link replays it."""

from __future__ import annotations

import json

import httpx
import pytest

from backend import config, kv, runs
from backend.main import app
from tests.test_pipeline import BRIEF, fake  # noqa: F401  (fake is a fixture)


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(kv, "store", kv._Memory())
    monkeypatch.setattr(config, "SELECTABLE_MODELS",
                        [*config.SELECTABLE_MODELS, {"id": "fake:test", "label": "Fake"}])
    return kv.store


async def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_a_finished_run_can_be_replayed_from_its_link(store, fake):  # noqa: F811
    async with await client() as c:
        async with c.stream("POST", "/api/plan", json={"brief": BRIEF, "model": "fake:test"}) as r:
            assert r.status_code == 200
            live = [json.loads(line[6:]) async for line in r.aiter_lines() if line.startswith("data: ")]

        run_id = next(e["run_id"] for e in live if e["type"] == "done")
        saved = (await c.get(f"/api/runs/{run_id}")).json()

    assert saved["brief"] == BRIEF
    assert [e["type"] for e in saved["events"]] == [e["type"] for e in live]
    assert saved["events"][-1]["cost_usd"] == pytest.approx(live[-1]["cost_usd"])


async def test_an_unknown_or_expired_link_says_so(store):
    async with await client() as c:
        r = await c.get("/api/runs/deadbeef99")
    assert r.status_code == 404 and "expired" in r.json()["detail"]


async def test_the_ui_is_told_whether_runs_are_saved(store):
    async with await client() as c:
        assert (await c.get("/api/meta")).json()["saved_runs"] is True


async def test_serverless_without_redis_does_not_pretend_to_save(store, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(kv, "shared", lambda: False)
    assert not runs.enabled()
    await runs.save("abc123", "a brief", [])
    assert await runs.load("abc123") is None
