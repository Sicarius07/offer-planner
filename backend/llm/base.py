"""Provider-neutral interface. Pipeline code depends on this, never on a vendor SDK"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
Effort = Literal["low", "medium", "high"]


@dataclass
class Usage:
    input_tokens: int = 0            # uncached input only
    output_tokens: int = 0           # includes thinking_tokens
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    thinking_tokens: int = 0         # informational: already inside output_tokens


@dataclass
class LLMResult(Generic[T]):
    parsed: T
    model: str
    usage: Usage
    cost_usd: float
    latency_ms: int
    stop_reason: str | None
    raw: Any = field(default=None, repr=False)


class LLMError(Exception):
    """Base class. `retryable` tells the orchestrator whether a retry could help."""

    retryable = True


class LLMRefusal(LLMError):
    retryable = False


class LLMOutputInvalid(LLMError):
    """The response didn't validate against the schema (after the SDK's own parsing)."""


class LLMProvider(Protocol):
    name: str

    async def generate_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        effort: Effort = "medium",
        max_tokens: int = 16000,
    ) -> LLMResult[T]: ...
