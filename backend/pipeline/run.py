"""The orchestrator: a fixed DAG!

    understand ─┬─ score_publishers ─ rerank (LLM) ──────────────────────────────────────┐
                │                                                                          ├─ config ─ launch summary (LLM)
                └─ score_personas ─ select (LLM) ─ write × N (LLM) ─ critique ─ rewrite ──┘

Publishers and personas run in parallel. Each ad starts the moment personas are picked, and
review starts as soon as the ads exist: it needs the candidate publishers, not the reranked
explanations, so it doesn't wait on the publisher branch. Config waits for both.
The publisher review decides final tiers, but a move needs a reason and a quote that checks
out, and code keeps the hard rules (competitors it found stay excluded, B2B excludes all).
Personas are picked against the computed tiers, so "reached through" is recomputed from the
final publisher plan once both branches finish.

Every LLM call is already retried (network errors by the SDK, invalid output once with the
error fed back). If a stage still fails:
- reading the brief, choosing personas, writing every ad, or reviewing the ads stops the run.
  Without them there's nothing safe to launch, and a code-only stand-in would look finished.
- the publisher review falls back to the computed scores and tiers, and the config is marked
  for review.
- the launch summary is skipped. It only explains the config, which is complete without it.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator

from pydantic import BaseModel

from backend import config, observability, trace
from backend.llm.base import LLMError
from backend.pipeline import campaign, creative, launch, personas, publishers
from backend.pipeline.scoring import score_publishers
from backend.pipeline.understand import BriefRejected, guard, understand
from backend.schemas.creative import Creative
from backend.schemas.events import (
    ConfigEvent, CreativeEvent, DoneEvent, ErrorEvent, NeedsInputEvent, PersonasEvent,
    PlanRequest, ProfileEvent, PublishersEvent, StageEvent,
)
from backend.schemas.persona import PersonaPlan
from backend.schemas.publisher import PublisherPlan

log = logging.getLogger(__name__)


class StageFailed(Exception):
    """A stage the run can't do without failed after retries. Stops the run."""

    def __init__(self, stage: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.stage, self.retryable = stage, retryable


async def run_plan(req: PlanRequest) -> AsyncIterator[BaseModel]:
    """Yields events. Never raises: errors become ErrorEvents"""
    queue: asyncio.Queue[BaseModel | None] = asyncio.Queue()
    run_id = uuid.uuid4().hex[:10]
    task = asyncio.create_task(_run(req, run_id, queue.put_nowait))
    task.add_done_callback(lambda _: queue.put_nowait(None))
    try:
        while (ev := await queue.get()) is not None:
            yield ev
    finally:
        if not task.done():  # client disconnected: stop spending tokens
            task.cancel()


async def _run(req: PlanRequest, run_id: str, emit) -> None:
    started = time.perf_counter()
    with trace.collect() as entries, observability.trace_attributes(
        trace_name="plan", session_id=run_id, tags=["plan"],
        metadata={"model": req.model or config.DEFAULT_MODEL},
    ), observability.observe("plan", input={"brief": req.brief}) as root:
        try:
            await _pipeline(req, run_id, emit)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # last-resort guard; stages handle their own errors
            log.exception("run %s failed", run_id)
            emit(ErrorEvent(stage="run", message=f"Unexpected error: {e}", retryable=True))
        total_ms = int((time.perf_counter() - started) * 1000)
        cost = round(sum(x.cost_usd for x in entries), 4)
        root.update(output={"run_id": run_id, "cost_usd": cost, "ms": total_ms})
        emit(DoneEvent(run_id=run_id, total_ms=total_ms, cost_usd=cost, trace=list(entries)))
    await asyncio.to_thread(observability.flush)


async def _pipeline(req: PlanRequest, run_id: str, emit) -> None:
    model = req.model
    budget = req.monthly_budget_usd or config.DEFAULT_MONTHLY_BUDGET_USD
    flight = req.flight_days or config.DEFAULT_FLIGHT_DAYS

    # ── 1. Understand ───────────────────────────────────────────────────────
    emit(StageEvent(stage="understand", status="started"))
    t = time.perf_counter()
    try:
        brief = guard(req.brief)
        with observability.observe("understand"):
            profile = await understand(brief, model, draft_anyway=req.force)
    except BriefRejected as e:
        emit(StageEvent(stage="understand", status="failed"))
        emit(ErrorEvent(stage="understand", message=str(e), retryable=False))
        return
    except LLMError as e:
        emit(StageEvent(stage="understand", status="failed"))
        emit(ErrorEvent(stage="understand", message=f"Couldn't read the brief: {e}",
                        retryable=e.retryable))
        return
    emit(ProfileEvent(profile=profile))
    emit(StageEvent(stage="understand", status="done", ms=_ms(t)))

    if profile.clarity == "unusable" and not req.force:
        emit(NeedsInputEvent(reason=profile.clarity_reason, questions=profile.clarifying_questions))
        for s in ("publishers", "personas", "creative", "campaign"):
            emit(StageEvent(stage=s, status="skipped"))
        return

    # ── 2 + 3. Publishers and personas, in parallel ─────────────────────────
    with trace.timed_stage("publishers", "score_publishers"):
        scored = score_publishers(profile, req.allow_competitors)
    candidate_ids = [s.publisher_id for s in scored if s.tier != "excluded"]
    if not candidate_ids and profile.offering_type != "b2b":
        # Code found no fit, but the review may still promote some, so the audience work
        # can't be skipped. Use the closest non-competitors as the stand-in plan.
        candidate_ids = [s.publisher_id for s in scored if s.exclusion_reason != "competitor"][:5]

    emit(StageEvent(stage="publishers", status="started"))
    t_pub = time.perf_counter()

    async def publisher_branch() -> PublisherPlan:
        try:
            with observability.observe("publishers"):
                plan = await publishers.rerank(profile, scored, model)
        except LLMError as e:
            emit(ErrorEvent(stage="publishers",
                            message=f"Explanations unavailable, showing computed scores only: {e}"))
            plan = publishers.merge(profile, scored, None)
        emit(PublishersEvent(plan=plan))
        emit(StageEvent(stage="publishers", status="done", ms=_ms(t_pub)))
        return plan

    async def persona_branch() -> tuple[PersonaPlan | None, list[Creative]]:
        if not candidate_ids:
            for s in ("personas", "creative"):
                emit(StageEvent(stage=s, status="skipped"))
            return None, []
        emit(StageEvent(stage="personas", status="started"))
        t_per = time.perf_counter()
        try:
            with observability.observe("personas"):
                pplan = await personas.select(profile, candidate_ids, model)
        except LLMError as e:
            emit(StageEvent(stage="personas", status="failed"))
            emit(StageEvent(stage="creative", status="skipped"))
            raise StageFailed("personas", f"Couldn't choose who to reach: {e}", e.retryable) from e
        emit(PersonasEvent(plan=pplan))
        emit(StageEvent(stage="personas", status="done", ms=_ms(t_per)))

        emit(StageEvent(stage="creative", status="started"))
        picks = pplan.picks

        async def one(pick) -> Creative | None:
            try:
                with observability.observe(f"creative:{pick.persona_id}"):
                    d = await creative.write(profile, pick, [x for x in picks if x is not pick],
                                             candidate_ids, model)
            except LLMError as e:
                emit(ErrorEvent(stage="creative",
                                message=f"Couldn't write the ad for {pick.name}: {e}"))
                return None
            c = creative.to_creative(d, pick, run_id)
            emit(CreativeEvent(creative=c))
            return c

        results = await asyncio.gather(*(one(p) for p in picks))
        cards = [c for c in results if c]

        # 4b. Review, rewrite once, review again. Runs as soon as the ads exist, without
        # waiting for publisher explanations: it only needs the candidate publishers' notes.
        if not cards:
            emit(StageEvent(stage="creative", status="failed"))
            raise StageFailed("creative", "Couldn't write any of the ads.")
        try:
            cards = await _review(profile, pplan, cards, candidate_ids, model, run_id, emit)
        except StageFailed:
            emit(StageEvent(stage="creative", status="failed"))
            raise
        emit(StageEvent(stage="creative", status="done", ms=_ms(t_per)))
        return pplan, cards

    pub_task = asyncio.create_task(publisher_branch())
    try:
        persona_plan, cards = await persona_branch()
        pub_plan = await pub_task
    except StageFailed as e:
        # Stop spending: the publisher explanations can't become a campaign without ads.
        if not pub_task.done():
            pub_task.cancel()
            emit(StageEvent(stage="publishers", status="skipped"))
        emit(StageEvent(stage="campaign", status="skipped"))
        emit(ErrorEvent(stage="run", message=f"{e} Nothing was drafted; try again.", retryable=e.retryable))
        return
    finally:
        if not pub_task.done():  # client disconnected mid-run
            pub_task.cancel()

    if persona_plan:
        # "Reached through" came from the computed tiers; the review may have moved some.
        persona_plan = personas.reach_final(persona_plan, pub_plan)
        emit(PersonasEvent(plan=persona_plan))

    # ── 5. Campaign config ──────────────────────────────────────────────────
    emit(StageEvent(stage="campaign", status="started"))
    t = time.perf_counter()
    with trace.timed_stage("campaign", "build_config"):
        cfg = campaign.build_config(
            profile, pub_plan, persona_plan or PersonaPlan(picks=[], candidates=[], skipped_note=None),
            cards, budget, flight,
        )
    emit(ConfigEvent(config=cfg))

    # 5b. The launch summary explains the finished config; the config doesn't depend on it,
    # so a failure here leaves the campaign intact without one.
    if persona_plan and cfg.placements:
        try:
            with observability.observe("launch_summary"):
                summary = await launch.summarize(profile, cfg, pub_plan, persona_plan, model)
            cfg = cfg.model_copy(update={"review": cfg.review.model_copy(update={"launch_summary": summary})})
            emit(ConfigEvent(config=cfg))
        except LLMError as e:
            emit(ErrorEvent(stage="campaign", message=f"Couldn't write the launch summary: {e}"))
    emit(StageEvent(stage="campaign", status="done", ms=_ms(t)))


async def _review(profile, persona_plan: PersonaPlan, cards: list[Creative], plan_ids: list[str],
                  model, run_id: str, emit) -> list[Creative]:
    picks = {p.persona_id: p for p in persona_plan.picks}
    try:
        with observability.observe("critique"):
            reviews = await creative.critique(profile, cards, plan_ids, model)
    except LLMError as e:
        raise StageFailed("creative", f"Couldn't review the ads: {e}", e.retryable) from e

    final: dict[str, Creative] = {}
    failed: list[Creative] = []
    for c in cards:
        r = reviews[c.persona_id]
        c = c.model_copy(update={"critique": r, "status": "passed" if r.passed else "draft"})
        final[c.persona_id] = c
        if r.passed:
            emit(CreativeEvent(creative=c))
        elif profile.clarity == "unusable" and any(x.name == "specific" and not x.passed for x in r.checks):
            # No rewrite can name a product nobody has described: pause it now.
            final[c.persona_id] = c.model_copy(update={"status": "flagged"})
            emit(CreativeEvent(creative=final[c.persona_id]))
        else:
            failed.append(c)

    async def rewrite(c: Creative) -> Creative:
        pick = picks[c.persona_id]
        prev = _as_draft(c)
        try:
            taken = [x for x in final.values() if x.persona_id != c.persona_id]
            d = await creative.write(profile, pick, [], plan_ids, model, fix=c.critique.fix,
                                     previous=prev, taken=taken)
        except LLMError:
            return c.model_copy(update={"status": "flagged"})
        return creative.to_creative(d, pick, run_id).model_copy(
            update={"revision_of": prev, "critique": c.critique})

    if failed:
        rewritten = await asyncio.gather(*(rewrite(c) for c in failed))
        to_check = [c for c in rewritten if c.status != "flagged"]
        second: dict = {}
        if to_check:
            try:
                others = [c for c in final.values() if c.persona_id not in {x.persona_id for x in to_check}]
                second = await creative.critique(profile, to_check + others, plan_ids, model)
            except LLMError:
                second = {}  # the rewrites stay unreviewed, so they're paused below
        for c in rewritten:
            r = second.get(c.persona_id)
            if c.status == "flagged" or r is None:
                c = c.model_copy(update={"status": "flagged"})
            else:
                c = c.model_copy(update={"critique": r, "status": "revised" if r.passed else "flagged"})
            final[c.persona_id] = c
            emit(CreativeEvent(creative=c))
    return [final[c.persona_id] for c in cards]


def _as_draft(c: Creative):
    from backend.schemas.creative import CreativeDraft
    return CreativeDraft(angle=c.angle, headline=c.headline[:40], body=c.body[:140], cta=c.cta[:18],
                         claims_used=c.claims_used, offer_suggestion=c.offer_suggestion or "",
                         tone_notes=c.tone_notes)


def _ms(t: float) -> int:
    return int((time.perf_counter() - t) * 1000)
