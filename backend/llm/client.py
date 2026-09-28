"""The one function pipeline stages call to use an LLM.

Loads + renders the prompt, resolves the model for the stage, calls the provider, retries
once with the validation error on bad output, and records the call in the run trace and
(optionally) Langfuse.
"""

from __future__ import annotations

import logging
import time

from pydantic import BaseModel

from backend import config, observability, prompts, trace
from backend.llm.base import LLMError, LLMOutputInvalid, T
from backend.llm.registry import resolve
from backend.schemas.events import StageTrace

log = logging.getLogger(__name__)


async def generate(
    *,
    stage: str,
    name: str,
    prompt: str,
    schema: type[T],
    variables: dict[str, object],
    model: str | None = None,
    max_tokens: int = 16000,
) -> T:
    p = prompts.load(prompt)
    system, user = p.render(**variables)
    spec = model or config.STAGE_MODELS[stage]
    provider, model_id = resolve(spec)
    effort = config.STAGE_EFFORT.get(stage, "medium")

    started = time.perf_counter()
    retries = 0
    tokens_in = tokens_out = 0
    cost = 0.0
    with observability.observe(
        name, as_type="generation", model=model_id, input={"system": system, "user": user},
        metadata={"prompt": p.name, "prompt_version": p.version, "stage": stage, "effort": effort},
        version=p.version,
    ) as gen:
        attempt_user = user
        while True:
            try:
                result = await provider.generate_structured(
                    system=system, user=attempt_user, schema=schema, model=model_id,
                    effort=effort, max_tokens=max_tokens,
                )
                tokens_in += result.usage.input_tokens
                tokens_out += result.usage.output_tokens
                cost += result.cost_usd
                break
            except LLMOutputInvalid as e:
                if retries >= 1:
                    _record(stage, name, spec, p, started, tokens_in, tokens_out, cost, retries, str(e))
                    gen.update(level="ERROR", status_message=str(e)[:500])
                    raise
                retries += 1
                log.warning("repairing %s after invalid output: %s", name, e)
                attempt_user = (
                    f"{user}\n\n<previous_attempt_error>\nYour previous answer failed validation:\n"
                    f"{str(e)[:2000]}\nFix these problems and answer again.\n</previous_attempt_error>"
                )
            except LLMError as e:
                _record(stage, name, spec, p, started, tokens_in, tokens_out, cost, retries, str(e))
                gen.update(level="ERROR", status_message=str(e)[:500])
                raise
            except Exception as e:  # SDK / network errors, already retried by the SDK
                _record(stage, name, spec, p, started, tokens_in, tokens_out, cost, retries, str(e))
                gen.update(level="ERROR", status_message=str(e)[:500])
                raise LLMError(f"{type(e).__name__}: {e}") from e

        gen.update(
            output=result.parsed.model_dump(mode="json") if isinstance(result.parsed, BaseModel) else None,
            usage_details={"input": tokens_in, "output": tokens_out},
            cost_details={"total": cost},
        )
    _record(stage, name, spec, p, started, tokens_in, tokens_out, cost, retries, None)
    return result.parsed


def _record(stage, name, spec, p, started, tin, tout, cost, retries, error) -> None:
    trace.record(StageTrace(
        stage=stage, name=name, model=spec, prompt=p.name, prompt_version=p.version,
        ms=int((time.perf_counter() - started) * 1000), input_tokens=tin, output_tokens=tout,
        cost_usd=round(cost, 6), retries=retries, ok=error is None, error=error,
    ))
