"""A shared spending limit for live runs.

A run holds RUN_RESERVE_USD before it starts, so parallel runs can't overshoot the limit
together, and is charged its real cost when it finishes. A run the user abandons keeps its
hold, since its real cost isn't known.
"""

from __future__ import annotations

from backend import config, kv

KEY = kv.PREFIX + "spent_usd"


class OutOfCredits(Exception):
    pass


class CreditsUnavailable(Exception):
    """The store can't be reached. Runs are refused rather than spent without a limit."""


def enabled() -> bool:
    return config.SPEND_LIMIT_USD is not None


async def status() -> tuple[float, float] | None:
    """(limit, spent), or None when there's no limit."""
    if not enabled():
        return None
    try:
        return config.SPEND_LIMIT_USD, float(await kv.store.get(KEY) or 0)
    except kv.Unavailable as e:
        raise CreditsUnavailable(str(e)) from e


async def reserve() -> float:
    """Hold the reserve for one run. Returns the amount held (0 when there's no limit)."""
    if not enabled():
        return 0.0
    held = config.RUN_RESERVE_USD
    try:
        total = await kv.store.add_float(KEY, held)
    except kv.Unavailable as e:
        raise CreditsUnavailable(str(e)) from e
    if total > config.SPEND_LIMIT_USD:
        await kv.store.add_float(KEY, -held)
        raise OutOfCredits("The demo credit for live runs is used up. The sample briefs still work.")
    return held


async def settle(held: float, cost_usd: float) -> None:
    """Swap the hold for the run's real cost."""
    if held:
        try:
            await kv.store.add_float(KEY, cost_usd - held)
        except kv.Unavailable as e:
            raise CreditsUnavailable(str(e)) from e
