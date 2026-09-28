"""Finished runs, kept for 30 days so a draft survives a reload and can be shared.

Only whole runs are stored, written once when the run ends: a reload mid-run loses it. The
id is the run's own random id, so a link is unguessable in practice but not private, and
there are no accounts.
"""

from __future__ import annotations

import json
import logging
import os

from backend import kv
from backend.schemas.events import PlanEvent

TTL_SECONDS = 30 * 24 * 3600
log = logging.getLogger(__name__)


def _key(run_id: str) -> str:
    return f"{kv.PREFIX}run:{run_id}"


def enabled() -> bool:
    """Redis keeps a run for every instance; memory only works while one process serves."""
    return kv.shared() or not os.getenv("VERCEL")


async def save(run_id: str, brief: str, events: list[PlanEvent]) -> None:
    """Best-effort: a run that can't be stored is still streamed to the user."""
    if not enabled():
        return
    body = json.dumps({"id": run_id, "brief": brief,
                       "events": [e.model_dump(mode="json") for e in events]})
    try:
        await kv.store.set(_key(run_id), body, TTL_SECONDS)
    except kv.Unavailable as e:
        log.warning("couldn't save run %s: %s", run_id, e)


async def load(run_id: str) -> str | None:
    """The stored run as JSON, or None when it's expired or never existed."""
    if not enabled():
        return None
    try:
        return await kv.store.get(_key(run_id))
    except kv.Unavailable as e:
        log.warning("couldn't read run %s: %s", run_id, e)
        return None
