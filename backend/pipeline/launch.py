"""Stage 5b: a short launch summary written from the finished config.

The config is already final; this only explains it. Any number the model writes must appear
in the config or the brief (a sentence or item with an unknown number is dropped), because a
summary that misquotes the budget is worse than none.
"""

from __future__ import annotations

import json
import logging
import re

from backend import catalog
from backend.llm.client import generate
from backend.pipeline.publishers import profile_for_prompt
from backend.schemas.campaign import CampaignConfig, LaunchSummary, LaunchSummaryDraft
from backend.schemas.persona import PersonaPlan
from backend.schemas.profile import AdvertiserProfile
from backend.schemas.publisher import PublisherPlan

log = logging.getLogger(__name__)

_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out


def _known(x: float, allowed: set[float]) -> bool:
    # Plain rounding is fine ("$36" for 36.0, "12%" for 12.4); a nearby number isn't.
    return any(x in (a, round(a), round(a, 1), round(a, 2)) for a in allowed)


def _checked(text: str, allowed: set[float]) -> bool:
    return all(_known(x, allowed) for x in _numbers(text))


def config_for_prompt(cfg: CampaignConfig) -> str:
    d = cfg.model_dump(exclude={"review": {"launch_summary"}})
    # Totals a reader would want, computed here so the model can quote rather than add up.
    core = [p for p in cfg.placements if p.role == "core"]
    test = [p for p in cfg.placements if p.role == "test"]
    d["totals"] = {
        "est_conversions": round(sum(p.est_conversions for p in cfg.placements)),
        "core_budget_usd": round(sum(p.budget_usd for p in core), 2),
        "core_pct": round(sum(p.allocation_pct for p in core), 1),
        "test_budget_usd": round(sum(p.budget_usd for p in test), 2),
        "test_pct": round(sum(p.allocation_pct for p in test), 1),
        "core_publishers": len(core), "test_publishers": len(test),
    }
    return json.dumps(d, indent=1)


def verify(draft: LaunchSummaryDraft, cfg: CampaignConfig, brief: str) -> LaunchSummary:
    allowed = set(_numbers(config_for_prompt(cfg) + " " + brief))
    kept = [s for s in _SENTENCE.split(draft.summary.strip()) if _checked(s, allowed)]
    items = lambda xs: [x for x in xs if _checked(x, allowed)]  # noqa: E731
    out = LaunchSummary(summary=" ".join(kept), uncertainties=items(draft.uncertainties),
                        questions=items(draft.questions))
    dropped = (len(_SENTENCE.split(draft.summary.strip())) - len(kept)
               + len(draft.uncertainties) - len(out.uncertainties) + len(draft.questions) - len(out.questions))
    if dropped:
        log.warning("launch summary: dropped %d line(s) with numbers not in the config", dropped)
    return out


async def summarize(p: AdvertiserProfile, cfg: CampaignConfig, pubs: PublisherPlan,
                    personas: PersonaPlan, model: str | None = None) -> LaunchSummary:
    names = catalog.personas()
    draft = await generate(
        stage="campaign", name="summarize_launch", prompt="summarize_launch",
        schema=LaunchSummaryDraft, model=model,
        variables={
            "profile": profile_for_prompt(p),
            "publisher_summary": pubs.summary,
            "personas": json.dumps([{"persona_id": x.persona_id, "name": names[x.persona_id].name,
                                     "ad_angle": x.ad_angle} for x in personas.picks], indent=1),
            "config": config_for_prompt(cfg),
        },
    )
    return verify(draft, cfg, p.brief)
