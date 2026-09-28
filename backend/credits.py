"""A shared spending limit for live runs.

A run holds RUN_RESERVE_USD before it starts, so parallel runs can't overshoot the limit
together, and is charged its real cost when it finishes. A run the user abandons keeps its
hold, since its real cost isn't known. The total lives in Upstash Redis when configured
(shared by every serverless instance), otherwise in this process.
"""

from __future__ import annotations

import httpx

from backend import config

KEY = "offer-planner:spent_usd"


class OutOfCredits(Exception):
    pass


class CreditsUnavailable(Exception):
    """The store can't be reached. Runs are refused rather than spent without a limit."""


class _Memory:
    def __init__(self) -> None:
        self.spent = 0.0

    async def add(self, usd: float) -> float:
        self.spent += usd
        return self.spent

    async def get(self) -> float:
        return self.spent


class _Redis:
    def __init__(self, url: str, token: str) -> None:
        self.url, self.headers = url.rstrip("/"), {"Authorization": f"Bearer {token}"}

    async def _cmd(self, *args: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.post(self.url, headers=self.headers, json=list(args))
                r.raise_for_status()
                return r.json()["result"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise CreditsUnavailable(str(e)) from e

    async def add(self, usd: float) -> float:
        return float(await self._cmd("INCRBYFLOAT", KEY, f"{usd:.6f}"))

    async def get(self) -> float:
        return float(await self._cmd("GET", KEY) or 0)


_store = (_Redis(config.REDIS_URL, config.REDIS_TOKEN) if config.REDIS_URL and config.REDIS_TOKEN
          else _Memory())


def enabled() -> bool:
    return config.SPEND_LIMIT_USD is not None


async def status() -> tuple[float, float] | None:
    """(limit, spent), or None when there's no limit."""
    if not enabled():
        return None
    return config.SPEND_LIMIT_USD, await _store.get()


async def reserve() -> float:
    """Hold the reserve for one run. Returns the amount held (0 when there's no limit)."""
    if not enabled():
        return 0.0
    held = config.RUN_RESERVE_USD
    if await _store.add(held) > config.SPEND_LIMIT_USD:
        await _store.add(-held)
        raise OutOfCredits("The demo credit for live runs is used up. The sample briefs still work.")
    return held


async def settle(held: float, cost_usd: float) -> None:
    """Swap the hold for the run's real cost."""
    if held:
        await _store.add(cost_usd - held)
