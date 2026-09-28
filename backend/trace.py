"""Per-run trace: one StageTrace per LLM call or code stage. Shown in the UI's run drawer,
printed as JSON to stdout (so hosted logs capture it), and mirrored to Langfuse if enabled"""

from __future__ import annotations

import contextvars
import json
import logging
import time
from contextlib import contextmanager
from collections.abc import Iterator

from backend.schemas.events import StageTrace

log = logging.getLogger("trace")
_current: contextvars.ContextVar[list[StageTrace] | None] = contextvars.ContextVar("trace", default=None)


@contextmanager
def collect() -> Iterator[list[StageTrace]]:
    entries: list[StageTrace] = []
    token = _current.set(entries)
    try:
        yield entries
    finally:
        _current.reset(token)


def record(entry: StageTrace) -> None:
    entries = _current.get()
    if entries is not None:
        entries.append(entry)
    log.info(json.dumps({"trace": entry.model_dump()}))


@contextmanager
def timed_stage(stage: str, name: str) -> Iterator[None]:
    """For code-only stages (scoring, config), so they show up in the timeline too."""
    t = time.perf_counter()
    ok, err = True, None
    try:
        yield
    except Exception as e:
        ok, err = False, str(e)
        raise
    finally:
        record(StageTrace(stage=stage, name=name, ms=int((time.perf_counter() - t) * 1000), ok=ok, error=err))
