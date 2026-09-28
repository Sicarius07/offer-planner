"""Stage 3: code scores all personas; the LLM picks 3–5 distinct, plausible ones."""

from __future__ import annotations

import json

from backend import catalog, config
from backend.llm.client import generate
from backend.pipeline.publishers import profile_for_prompt
from backend.pipeline.scoring import score_personas
from backend.schemas.persona import PersonaPick, PersonaPlan, PersonaScore, PersonaSelectionDraft
from backend.schemas.profile import AdvertiserProfile


def candidates_for_prompt(cands: list[PersonaScore]) -> str:
    personas = catalog.personas()
    return json.dumps([
        {**personas[c.persona_id].model_dump(),
         "computed": {"score": c.score, "affinity": c.affinity, "values": c.values,
                      "price": c.price, "reach": c.reach, "conflicts": c.conflicts,
                      "detail": c.detail}}
        for c in cands
    ], indent=1)


async def select(p: AdvertiserProfile, plan_publisher_ids: list[str],
                 model: str | None = None) -> PersonaPlan:
    scored = score_personas(p, plan_publisher_ids)
    cands = scored[: config.PERSONA_CANDIDATES]
    draft = await generate(
        stage="personas", name="select_personas", prompt="select_personas",
        schema=PersonaSelectionDraft, model=model,
        variables={"profile": profile_for_prompt(p), "candidates": candidates_for_prompt(cands)},
    )
    return merge(scored, draft)


def merge(scored: list[PersonaScore], draft: PersonaSelectionDraft | None) -> PersonaPlan:
    personas = catalog.personas()
    by_id = {s.persona_id: s for s in scored}
    allowed = {s.persona_id for s in scored[: config.PERSONA_CANDIDATES]}
    picks: list[PersonaPick] = []
    seen: set[str] = set()
    for d in (draft.picks if draft else []):
        if d.persona_id in seen or d.persona_id not in allowed:
            continue
        seen.add(d.persona_id)
        s = by_id[d.persona_id]
        picks.append(PersonaPick(
            persona_id=d.persona_id, name=personas[d.persona_id].name, score=s.score,
            why_plausible=d.why_plausible, lean_into=d.lean_into, avoid=d.avoid,
            ad_angle=d.ad_angle, confidence=d.confidence, reached_via=s.reach_publishers[:4], conflicts=s.conflicts,
        ))
    picks = picks[: config.PERSONAS_MAX]
    if not picks:  # model failed or picked nothing valid: fall back to the top scores
        for s in scored[: config.PERSONAS_MIN]:
            persona = personas[s.persona_id]
            picks.append(PersonaPick(
                persona_id=s.persona_id, name=persona.name, score=s.score,
                why_plausible=f"Highest computed fit: {s.detail}.",
                lean_into=persona.messaging_preferences[:2], avoid=persona.disinterested_in[:2],
                confidence="low", reached_via=s.reach_publishers[:4], conflicts=s.conflicts,
            ))
    return PersonaPlan(picks=picks, candidates=scored,
                       skipped_note=(draft.skipped_note or None) if draft else None)
