"""Anthropic adapter: native structured outputs via `messages.parse`"""

from __future__ import annotations

import logging
import time

import anthropic
from pydantic import ValidationError

from backend.config import PRICING
from backend.llm.base import Effort, LLMOutputInvalid, LLMRefusal, LLMResult, T, Usage

log = logging.getLogger(__name__)

# Models that take adaptive thinking + the effort parameter. Others get a plain request.
_ADAPTIVE = ("claude-opus-5", "claude-opus-5-5", "claude-sonnet-5", "claude-fable-5")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:  # lazy: importing the app shouldn't require a key
            self._client = anthropic.AsyncAnthropic(max_retries=3)
        return self._client

    async def generate_structured(
        self, *, system: str, user: str, schema: type[T], model: str,
        effort: Effort = "medium", max_tokens: int = 16000,
    ) -> LLMResult[T]:
        extra: dict = {}
        if model.startswith(_ADAPTIVE):
            extra = {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}

        started = time.perf_counter()
        try:
            resp = await self.client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                **extra,
            )
        except ValidationError as e:
            raise LLMOutputInvalid(str(e)) from e
        latency = int((time.perf_counter() - started) * 1000)

        if resp.stop_reason == "refusal":
            raise LLMRefusal("The model declined to answer this request.")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            raise LLMOutputInvalid(f"Response incomplete (stop_reason={resp.stop_reason}).")

        u = resp.usage
        cw = u.cache_creation
        usage = Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            # The split is missing on some responses; then all writes count as 5-minute writes.
            cache_write_5m_tokens=cw.ephemeral_5m_input_tokens if cw else (u.cache_creation_input_tokens or 0),
            cache_write_1h_tokens=cw.ephemeral_1h_input_tokens if cw else 0,
            thinking_tokens=u.output_tokens_details.thinking_tokens if u.output_tokens_details else 0,
        )
        return LLMResult(
            parsed=resp.parsed_output, model=model, usage=usage,
            cost_usd=cost(model, usage), latency_ms=latency,
            stop_reason=resp.stop_reason, raw=resp,
        )


def cost(model: str, u: Usage) -> float:
    # Longest prefix wins, so dated IDs ("claude-haiku-4-5-20251001") find their base model.
    key = next((k for k in sorted(PRICING, key=len, reverse=True) if model.startswith(k)), None)
    if key is None:
        log.warning("no pricing for %s; reporting its cost as $0", model)
        return 0.0
    r = PRICING[key]
    return round((u.input_tokens * r["input"] + u.output_tokens * r["output"]
                  + u.cache_read_tokens * r["cache_read"]
                  + u.cache_write_5m_tokens * r["cache_write_5m"]
                  + u.cache_write_1h_tokens * r["cache_write_1h"]) / 1e6, 6)
