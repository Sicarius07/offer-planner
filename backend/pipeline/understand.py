"""Stage 0–1: guard the input, read the brief, verify every quote the model gave."""

from __future__ import annotations

import logging
import re

from backend import config, taxonomy
from backend.llm.client import generate
from backend.pipeline.scoring import parse_age
from backend.pipeline.spans import locate
from backend.schemas.profile import (
    STRENGTH_WEIGHT, AdvertiserProfile, AttrDraft, Claim, ProfileDraft,
)

log = logging.getLogger(__name__)


class BriefRejected(ValueError):
    pass


def guard(brief: str) -> str:
    # Tidy spaces within each line but keep line breaks: an answers block (one answer per
    # line, appended by the UI) has to stay readable as a list.
    lines = [" ".join(line.split()) for line in brief.splitlines()]
    brief = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if not brief:
        raise BriefRejected("Describe what you sell in a sentence or two.")
    if len(brief) > config.MAX_BRIEF_CHARS:
        raise BriefRejected(f"Keep the description under {config.MAX_BRIEF_CHARS} characters.")
    return brief


async def understand(brief: str, model: str | None = None) -> AdvertiserProfile:
    draft = await generate(
        stage="understand", name="understand_brief", prompt="understand_brief",
        schema=ProfileDraft, model=model,
        variables={
            "brief": brief,
            "interests": taxonomy.describe("interests"),
            "values": taxonomy.describe("values"),
            "occasions": taxonomy.describe("occasions"),
            "positioning": taxonomy.describe("positioning"),
            "products": taxonomy.describe("products"),
        },
    )
    return to_profile(draft, brief)


def _weights(items, vocab, dropped: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for it in items:
        tag = it.tag.strip().lower()
        if tag not in vocab:
            dropped.append(tag)
            continue
        out[tag] = max(out.get(tag, 0.0), STRENGTH_WEIGHT[it.strength])
    return out


def _known(tags: list[str], vocab, dropped: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = t.strip().lower()
        if t in vocab:
            out.append(t)
        else:
            dropped.append(t)
    return list(dict.fromkeys(out))


def to_profile(d: ProfileDraft, brief: str) -> AdvertiserProfile:
    """Locate every quote in the brief. Unfound quotes are treated as invented: the
    evidence is dropped, the attribute becomes 'assumed', and the quote is reported."""
    dropped: list[str] = []
    bad_tags: list[str] = []

    def verify(a: AttrDraft | None):
        if a is None or (isinstance(a.value, str) and not a.value.strip()):
            return None
        span = locate(a.quote or None, brief) if a.source != "assumed" else None
        source, note = a.source, a.note or None
        if a.source != "assumed" and span is None:
            if a.quote:
                dropped.append(a.quote)
            source = "assumed"
            note = note or "no supporting words found in the brief"
        return {"value": a.value, "source": source, "evidence": span, "note": note}

    claims = []
    for c in d.claims:
        span = locate(c.quote, brief)
        if span:
            claims.append(Claim(claim=c.claim, evidence=span))
        else:
            dropped.append(c.quote)

    age = verify(d.age_range)
    if age and not parse_age(str(age["value"])):
        age = None
    if dropped:
        log.warning("dropped unverifiable quotes: %s", dropped)
    if bad_tags:
        log.warning("dropped unknown tags: %s", bad_tags)

    return AdvertiserProfile(
        brief=brief,
        business_summary=d.business_summary,
        brand_name=d.brand_name.strip() or None,
        offering_type=d.offering_type,
        product=verify(d.product),
        sells=_known(d.sells, taxonomy.PRODUCTS, bad_tags) or ["other"],
        competes_with=_known([*d.sells, *d.competes_with], taxonomy.PRODUCTS, bad_tags) or ["other"],
        interests=_weights(d.interests, taxonomy.INTERESTS, bad_tags),
        values=_weights(d.values, taxonomy.VALUES, bad_tags),
        occasions=_weights(d.occasions, taxonomy.OCCASIONS, bad_tags),
        positioning=_known(d.positioning, taxonomy.POSITIONING, bad_tags),
        price_tier=verify(d.price_tier),
        first_order_value_usd=verify(d.first_order_value_usd),
        gender=verify(d.gender),
        age_range=age,
        audience=verify(d.audience),
        business_model=verify(d.business_model),
        claims=claims,
        clarity=d.clarity,
        clarity_reason=d.clarity_reason,
        assumptions=d.assumptions,
        clarifying_questions=d.clarifying_questions,
        dropped_quotes=dropped,
        dropped_tags=list(dict.fromkeys(bad_tags)),
    )
