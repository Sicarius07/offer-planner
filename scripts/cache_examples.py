"""Run the 15 sample briefs live and save their event streams (make cache).

The UI replays these so reviewers can click through instantly without spending tokens.
"""

from __future__ import annotations

import argparse
import asyncio

from backend import catalog, config
from backend.main import CachedRun
from backend.pipeline.run import run_plan
from backend.schemas.events import PlanRequest


async def one(i: int, brief: str, model: str | None) -> None:
    ex_id = f"ex{i + 1:02d}"
    events = [e async for e in run_plan(PlanRequest(brief=brief, model=model))]
    errors = [e.message for e in events if e.type == "error"]
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (config.CACHE_DIR / f"{ex_id}.json").write_text(
        CachedRun(id=ex_id, brief=brief, events=events).model_dump_json(indent=1))
    done = events[-1]
    print(f"{ex_id} {done.total_ms / 1000:.0f}s ${done.cost_usd:.3f} errors={errors}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="example ids like ex01 ex06")
    ap.add_argument("--model")
    args = ap.parse_args()
    sem = asyncio.Semaphore(4)
    briefs = catalog.example_briefs()

    async def lim(i, b):
        async with sem:
            await one(i, b, args.model)

    await asyncio.gather(*(lim(i, b) for i, b in enumerate(briefs)
                           if not args.only or f"ex{i + 1:02d}" in args.only))


if __name__ == "__main__":
    asyncio.run(main())
