"""The one key-value store: Upstash Redis when configured, else this process's memory.

Serverless instances share nothing, so anything that must be one number or one record for
every visitor (the spending limit, a saved run) needs Redis. Memory is the local fallback.
"""

from __future__ import annotations

import time

import httpx

from backend import config

PREFIX = "offer-planner:"


class Unavailable(Exception):
    """The store can't be reached."""


class _Memory:
    """Per-process fallback. Expiry is honoured so behaviour matches Redis in tests."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    def _live(self, key: str) -> str | None:
        if (hit := self._data.get(key)) and (hit[1] is None or hit[1] > time.time()):
            return hit[0]
        self._data.pop(key, None)
        return None

    async def get(self, key: str) -> str | None:
        return self._live(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._data[key] = (value, time.time() + ttl_seconds if ttl_seconds else None)

    async def add_float(self, key: str, delta: float) -> float:
        total = float(self._live(key) or 0) + delta
        await self.set(key, repr(total))
        return total


class _Redis:
    """Upstash's REST API: one POST per command, so there's no connection to keep warm."""

    def __init__(self, url: str, token: str) -> None:
        self.url, self.headers = url.rstrip("/"), {"Authorization": f"Bearer {token}"}

    async def _cmd(self, *args: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(self.url, headers=self.headers, json=list(args))
                r.raise_for_status()
                return r.json()["result"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise Unavailable(str(e)) from e

    async def get(self, key: str) -> str | None:
        return await self._cmd("GET", key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        args = ("SET", key, value) + (("EX", str(ttl_seconds)) if ttl_seconds else ())
        await self._cmd(*args)

    async def add_float(self, key: str, delta: float) -> float:
        return float(await self._cmd("INCRBYFLOAT", key, f"{delta:.6f}"))


_shared = bool(config.REDIS_URL and config.REDIS_TOKEN)
store: _Redis | _Memory = (_Redis(config.REDIS_URL, config.REDIS_TOKEN) if _shared else _Memory())


def shared() -> bool:
    """True when the store is Redis, so every instance sees the same data."""
    return _shared
