"""Stage 2: code scores every publisher; the LLM reviews and can move tiers with evidence; code keeps the hard rules"""

from __future__ import annotations

import json

from backend import catalog, config
from backend.llm.client import generate
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
        "competes_with": p.competes_with,
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
            "computed_fit": s.base_fit, "computed_tier": s.tier, "exclusion_reason": s.exclusion_reason,
            "adjacent_conflict": s.adjacent_conflict,
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
    """Keep only quotes that appear in the cited field. Numbers and the audience record are
    structured, so the model paraphrases them; those are kept as they're checkable at a glance."""
    pub = catalog.publishers()[pub_id]
    labels = lambda *xs: " ".join(xs) + " " + " ".join(xs).replace("_", " ")  # noqa: E731
    texts = {
        "notes": pub.notes, "category": labels(pub.category), "subcategories": labels(*pub.subcategories),
        "brief": brief,
    }
    out = []
    for r in refs:
        if r.field in ("avg_order_value_usd", "monthly_impressions", "audience"):
            out.append(r)
        elif span := locate(r.quote, texts.get(r.field, "")):
            out.append(EvidenceRef(field=r.field, quote=span.text))
    return out


def _fit_in_tier(fit: int, tier: str) -> int:
    """A publisher the review moved gets a fit inside its new tier's band, so budget
    allocation (which weights by fit) treats it like the tier it's in."""
    if tier == "recommended":
        return max(fit, config.RECOMMEND_AT)
    if tier == "test":
        return min(max(fit, config.TEST_AT), config.RECOMMEND_AT - 1)
    return min(fit, config.TEST_AT - 1)


def merge(p: AdvertiserProfile, scored: list[ScoredPublisher], draft: RerankDraft | None) -> PublisherPlan:
    """Combine code scores with the review's judgments.

    The review decides the final tier, but a move only counts with a reason and at least one
    quote that checks out. Code keeps the rules that must never break: a competitor it found
    stays excluded (the review can only dispute it, which sends the plan to a human), and a
    B2B brief excludes everything. The review can add a competitor code missed, citing the
    publisher's own fields."""
    pubs = catalog.publishers()
    judgments: dict[str, PublisherJudgmentDraft] = {}
    if draft:
        for j in draft.judgments:
            judgments.setdefault(j.publisher_id, j)

    results: list[PublisherResult] = []
    for s in scored:
        pub = pubs[s.publisher_id]
        j = judgments.get(s.publisher_id)
        evidence = _verify_evidence(j.evidence, pub.id, p.brief) if j else []
        tier, reason, conflict = s.tier, s.exclusion_reason, s.conflict
        tier_reason = dispute = None
        locked = p.offering_type == "b2b" or s.exclusion_reason == "competitor"

        if j and s.exclusion_reason == "competitor" and j.competitor_call == "not_a_competitor":
            dispute = j.competitor_reason.strip() or None
        elif j and not locked:
            own_fields = [e for e in evidence if e.field != "brief"]
            if j.competitor_call == "missed_competitor" and j.competitor_reason.strip() and own_fields:
                tier, reason, conflict = "excluded", "competitor", j.competitor_reason.strip()
                tier_reason = f"Review found a competitor the tags missed: {conflict}"
            elif j.tier != s.tier and j.tier_reason.strip() and evidence:
                tier, tier_reason = j.tier, j.tier_reason.strip()
                reason = "review" if tier == "excluded" else None

        results.append(PublisherResult(
            publisher_id=pub.id, name=pub.name, category=pub.category, signals=s.signals,
            base_fit=s.base_fit, fit=_fit_in_tier(s.base_fit, tier) if tier != s.tier else s.base_fit,
            computed_tier=s.tier, tier=tier, tier_reason=tier_reason,
            exclusion_reason=reason, conflict=conflict, adjacent_conflict=s.adjacent_conflict,
            rationale=(j.rationale if j else s.reason), evidence=evidence,
            risk=(j.risk or None) if j else None, competitor_dispute=dispute,
        ))

    results.sort(key=lambda r: -r.fit)
    summary = draft.summary if draft else _fallback_summary(results)
    return PublisherPlan(
        summary=summary,
        explained=draft is not None,
        recommended=[r for r in results if r.tier == "recommended"],
        test=[r for r in results if r.tier == "test"],
        excluded=[r for r in results if r.tier == "excluded"],
        offering_type_doubt=((draft.offering_type_doubt or "").strip() or None) if draft else None,
    )


def _fallback_summary(results: list[PublisherResult]) -> str:
    rec = sum(r.tier == "recommended" for r in results)
    test = sum(r.tier == "test" for r in results)
    return f"{rec} recommended and {test} to test, from computed fit scores."
