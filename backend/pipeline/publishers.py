"""Stage 2: code scores every publisher; the LLM explains and nudges; code enforces limits"""

from __future__ import annotations

import json

from backend import catalog, config
from backend.llm.client import generate
from backend.pipeline.scoring import tier_for
from backend.pipeline.spans import locate
from backend.schemas.profile import AdvertiserProfile
from backend.schemas.publisher import (
    EvidenceRef, PublisherJudgmentDraft, PublisherPlan, PublisherResult, RerankDraft, ScoredPublisher,
)


def profile_for_prompt(p: AdvertiserProfile) -> str:
    """Compact profile JSON for downstream prompts (no offsets, no clutter)"""
    def a(x):
        return None if x is None else {"value": x.value, "source": x.source}
    return json.dumps({
        "brief": p.brief,
        "summary": p.business_summary,
        "brand_name": p.brand_name,
        "offering_type": p.offering_type,
        "product": a(p.product),
        "sells": p.sells,
        "interests": p.interests,
        "values": p.values,
        "occasions": p.occasions,
        "positioning": p.positioning,
        "price_tier": a(p.price_tier),
        "first_order_value_usd": a(p.first_order_value_usd),
        "gender": a(p.gender),
        "age_range": a(p.age_range),
        "audience": a(p.audience),
        "business_model": a(p.business_model),
        "claims": [c.claim for c in p.claims],
        "clarity": p.clarity,
    }, indent=1)


def publishers_for_prompt(scored: list[ScoredPublisher]) -> str:
    pubs, tags = catalog.publishers(), catalog.publisher_tags()
    rows = []
    for s in scored:
        pub = pubs[s.publisher_id]
        rows.append({
            "publisher_id": pub.id, "name": pub.name, "category": pub.category,
            "subcategories": pub.subcategories, "notes": pub.notes,
            "avg_order_value_usd": pub.avg_order_value_usd,
            "monthly_impressions": pub.monthly_impressions,
            "audience": pub.audience.model_dump(),
            "sells": tags[pub.id].sells,
            "computed_fit": s.base_fit, "tier": s.tier, "exclusion_reason": s.exclusion_reason,
            "signals": {x.name: {"score": x.score, "detail": x.detail} for x in s.signals},
            "code_reason": s.reason,
        })
    return json.dumps(rows, indent=1)


async def rerank(p: AdvertiserProfile, scored: list[ScoredPublisher],
                 model: str | None = None) -> PublisherPlan:
    draft = await generate(
        stage="rerank", name="rerank_publishers", prompt="rerank_publishers",
        schema=RerankDraft, model=model,
        variables={"profile": profile_for_prompt(p), "publishers": publishers_for_prompt(scored)},
    )
    return merge(p, scored, draft)


def _verify_evidence(refs: list[EvidenceRef], pub_id: str, brief: str) -> list[EvidenceRef]:
    pub = catalog.publishers()[pub_id]
    texts = {
        "notes": pub.notes, "category": pub.category, "subcategories": " ".join(pub.subcategories),
        "audience": json.dumps(pub.audience.model_dump()),
        "avg_order_value_usd": str(pub.avg_order_value_usd),
        "monthly_impressions": str(pub.monthly_impressions), "brief": brief,
    }
    out = []
    for r in refs:
        field_text = texts.get(r.field, "")
        if r.field in ("avg_order_value_usd", "monthly_impressions", "audience", "category", "subcategories"):
            out.append(r)  # structured fields: the model paraphrases numbers; keep, they're checkable
        elif locate(r.quote, field_text):
            out.append(EvidenceRef(field=r.field, quote=locate(r.quote, field_text).text))
    return out


def merge(p: AdvertiserProfile, scored: list[ScoredPublisher], draft: RerankDraft | None) -> PublisherPlan:
    """Combine code scores with LLM judgments. Code has the last word:
    adjustments are clamped, competitors stay excluded, tiers are recomputed from the final fit."""
    pubs = catalog.publishers()
    judgments: dict[str, PublisherJudgmentDraft] = {}
    if draft:
        for j in draft.judgments:
            judgments.setdefault(j.publisher_id, j)

    results: list[PublisherResult] = []
    for s in scored:
        pub = pubs[s.publisher_id]
        j = judgments.get(s.publisher_id)
        adj = 0
        if j and s.exclusion_reason != "competitor":
            adj = max(-config.MAX_LLM_ADJUSTMENT, min(config.MAX_LLM_ADJUSTMENT, j.adjustment))
            if adj and not (j.adjustment_reason or "").strip():
                adj = 0  # an unexplained nudge doesn't count
        fit = max(0, min(100, s.base_fit + adj))

        tier, reason = s.tier, s.exclusion_reason
        if s.exclusion_reason == "competitor":
            pass
        elif s.exclusion_reason == "off_category":
            # The model can argue an off-category publisher into a small test, never further.
            if adj > 0 and fit >= config.TEST_AT:
                tier, reason = "test", None
        else:
            tier, reason = tier_for(fit, s.adjacent_conflict is not None)

        results.append(PublisherResult(
            publisher_id=pub.id, name=pub.name, category=pub.category, signals=s.signals,
            base_fit=s.base_fit, adjustment=adj,
            adjustment_reason=(j.adjustment_reason or None) if (j and adj) else None,
            fit=fit, tier=tier, exclusion_reason=reason, conflict=s.conflict,
            adjacent_conflict=s.adjacent_conflict,
            rationale=(j.rationale if j else s.reason),
            evidence=_verify_evidence(j.evidence, pub.id, p.brief) if j else [],
            risk=(j.risk or None) if j else None,
        ))

    results.sort(key=lambda r: -r.fit)
    summary = draft.summary if draft else _fallback_summary(results)
    return PublisherPlan(
        summary=summary,
        explained=draft is not None,
        recommended=[r for r in results if r.tier == "recommended"],
        test=[r for r in results if r.tier == "test"],
        excluded=[r for r in results if r.tier == "excluded"],
    )


def _fallback_summary(results: list[PublisherResult]) -> str:
    rec = sum(r.tier == "recommended" for r in results)
    test = sum(r.tier == "test" for r in results)
    return f"{rec} recommended and {test} to test, from computed fit scores."
