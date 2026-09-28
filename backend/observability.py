"""Optional Langfuse tracing.

On only when LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL are all set
(LANGFUSE_TRACING_ENVIRONMENT is read by the SDK itself). Otherwise every helper here is a
no-op and Langfuse is never imported. Tracing errors are logged and swallowed: an
observability outage must never fail a user's run
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any
from collections.abc import Iterator

log = logging.getLogger(__name__)

import backend.config  # noqa: E402,F401  (loads .env before the check below)

_REQUIRED = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
ENABLED = all(os.getenv(k) for k in _REQUIRED)


class _Obs:
    """Wraps a Langfuse observation (or nothing) so `.update()` can never raise."""

    def __init__(self, inner: Any = None) -> None:
        self._inner = inner

    def update(self, **kw: Any) -> None:
        if self._inner is None:
            return
        try:
            self._inner.update(**kw)
        except Exception:  # noqa: BLE001
            log.warning("langfuse update failed", exc_info=True)


def _client():
    from langfuse import get_client

    return get_client()


@contextmanager
def observe(name: str, as_type: str = "span", **kw: Any) -> Iterator[_Obs]:
    """Context manager for a span/generation. Nested calls nest in the trace (contextvars,
    so parallel asyncio tasks each get the right parent)."""
    if not ENABLED:
        yield _Obs()
        return
    try:
        cm = _client().start_as_current_observation(name=name, as_type=as_type, **kw)
        inner = cm.__enter__()
    except Exception:  # noqa: BLE001
        log.warning("langfuse start failed", exc_info=True)
        yield _Obs()
        return
    try:
        yield _Obs(inner)
    except BaseException as e:
        _safe_exit(cm, e)
        raise
    else:
        _safe_exit(cm, None)


def _safe_exit(cm: Any, e: BaseException | None) -> None:
    try:
        if e is None:
            cm.__exit__(None, None, None)
        else:
            cm.__exit__(type(e), e, e.__traceback__)
    except Exception:  # noqa: BLE001
        log.warning("langfuse end failed", exc_info=True)


@contextmanager
def trace_attributes(**kw: Any) -> Iterator[None]:
    """Trace-level attributes (session_id, tags, metadata) for everything inside."""
    if not ENABLED:
        yield
        return
    try:
        from langfuse import propagate_attributes

        cm = propagate_attributes(**kw)
        cm.__enter__()
    except Exception:  # noqa: BLE001
        log.warning("langfuse attributes failed", exc_info=True)
        yield
        return
    try:
        yield
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


def flush() -> None:
    if not ENABLED:
        return
    try:
        _client().flush()
    except Exception:  # noqa: BLE001
        log.warning("langfuse flush failed", exc_info=True)
