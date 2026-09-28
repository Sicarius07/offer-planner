"""Stage 4: one offer card per persona (parallel), a batched review, one rewrite on failure."""

from __future__ import annotations

import json
import re

from backend import catalog
from backend.llm.client import generate
from backend.pipeline.spans import locate
from backend.schemas.creative import (
    BODY_MAX, CTA_MAX, HEADLINE_MAX, Creative, CreativeDraft, Critique, CritiqueDraft,
)
from backend.schemas.persona import PersonaPick
from backend.schemas.profile import AdvertiserProfile

BANNED = [
    "elevate", "unleash", "game-changer", "game changer", "revolutionary", "look no further",
    "you deserve", "unlock", "next level", "next-level", "seamless", "synergy", "must-have",
    "act now", "limited time", "don't miss",
]
DUPLICATE_THRESHOLD = 0.6


def advertiser_for_prompt(p: AdvertiserProfile) -> str:
    return json.dumps({
        "brief": p.brief, "brand_name": p.brand_name, "product": p.product.value,
        "summary": p.business_summary, "price_tier": p.price_tier.value,
        "business_model": p.business_model.value,
    }, indent=1)


def claims_for_prompt(p: AdvertiserProfile) -> str:
    if not p.claims:
        return "(none beyond describing what the product is)"
    return "\n".join(f'- {c.claim} (brief: "{c.evidence.text}")' for c in p.claims)


def placements_for_prompt(publisher_ids: list[str]) -> str:
    pubs = catalog.publishers()
    return "\n".join(f"- {pubs[i].name} ({pubs[i].category}): {pubs[i].notes}"
                     for i in publisher_ids if i in pubs) or "(not decided yet)"


def persona_for_prompt(pick: PersonaPick) -> str:
    persona = catalog.personas()[pick.persona_id]
    return json.dumps({**persona.model_dump(), "why_chosen": pick.why_plausible,
                       "lean_into": pick.lean_into, "avoid": pick.avoid,
                       "assigned_angle": pick.ad_angle}, indent=1)


async def write(p: AdvertiserProfile, pick: PersonaPick, others: list[PersonaPick],
                publisher_ids: list[str], model: str | None = None,
                fix: str | None = None, previous: CreativeDraft | None = None,
                taken: list[Creative] | None = None) -> CreativeDraft:
    other = ""
    if taken:
        other += ("\nOther cards in this campaign already say the following; yours must use a "
                  "different headline and a different angle:\n"
                  + "\n".join(f'- {c.persona_name}: "{c.headline}" / "{c.body}"' for c in taken))
    elif others:
        other = ("\nOther cards in this campaign target: "
                 + ", ".join(o.name for o in others) + ". Take a clearly different angle.")
    if fix and previous:
        other += ("\n\n<revision_request>\nA reviewer rejected this earlier card:\n"
                  + previous.model_dump_json(indent=1)
                  + f"\nRequired fix: {fix}\nWrite a corrected card.\n</revision_request>")
    return await generate(
        stage="creative", name=f"{'rewrite' if fix else 'write'}_creative:{pick.persona_id}",
        prompt="write_creative", schema=CreativeDraft, model=model,
        variables={
            "advertiser": advertiser_for_prompt(p), "claims": claims_for_prompt(p),
            "persona": persona_for_prompt(pick), "placements": placements_for_prompt(publisher_ids),
            "other_angles": other,
        },
    )


_ESCAPED = re.compile(r"\\u([0-9a-fA-F]{4})")


def _clean(s: str) -> str:
    """Models occasionally double-escape inside JSON, leaving a literal \u2014 in copy."""
    return _ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), s).strip()


def to_creative(d: CreativeDraft, pick: PersonaPick, run_id: str) -> Creative:
    return Creative(
        creative_id=f"{run_id}-{pick.persona_id}", persona_id=pick.persona_id,
        persona_name=pick.name, angle=d.angle, headline=_clean(d.headline), body=_clean(d.body),
        cta=_clean(d.cta),
        claims_used=d.claims_used, offer_suggestion=d.offer_suggestion or None, tone_notes=d.tone_notes,
        status="draft",
    )


# ── Code checks ──────────────────────────────────────────────────────────────


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z']+", s.lower())) - {"a", "an", "the", "and", "or", "for", "to", "of", "your", "you", "with"}


def code_issues(c: Creative, others: list[Creative], brief: str = "") -> list[str]:
    issues = []
    if brief:
        # Grounding, enforced in code: every claim must cite words that are really in the brief.
        missing = [u.source_quote for u in c.claims_used if not locate(u.source_quote, brief)]
        if missing:
            issues.append("claims cite words that aren't in the brief: " + "; ".join(f'"{m}"' for m in missing))
    if len(c.headline) > HEADLINE_MAX:
        issues.append(f"headline is {len(c.headline)} characters (max {HEADLINE_MAX})")
    if len(c.body) > BODY_MAX:
        issues.append(f"body is {len(c.body)} characters (max {BODY_MAX})")
    if len(c.cta) > CTA_MAX:
        issues.append(f"CTA is {len(c.cta)} characters (max {CTA_MAX})")
    text = f"{c.headline} {c.body} {c.cta}".lower()
    hits = [b for b in BANNED if b in text]
    if hits:
        issues.append("cliché: " + ", ".join(hits))
    mine = _words(f"{c.headline} {c.body}")
    for o in others:
        if o.persona_id == c.persona_id:
            continue
        theirs = _words(f"{o.headline} {o.body}")
        if mine and theirs and len(mine & theirs) / len(mine | theirs) > DUPLICATE_THRESHOLD:
            issues.append(f"too similar to the {o.persona_name} card")
    return issues


# ── Review ───────────────────────────────────────────────────────────────────


async def critique(p: AdvertiserProfile, cards: list[Creative], publisher_ids: list[str],
                   model: str | None = None) -> dict[str, Critique]:
    payload = json.dumps([
        {"persona_id": c.persona_id, "persona": persona_for_prompt_short(c.persona_id),
         "headline": c.headline, "body": c.body, "cta": c.cta,
         "claims_used": [x.model_dump() for x in c.claims_used]}
        for c in cards
    ], indent=1)
    draft: CritiqueDraft = await generate(
        stage="critique", name="critique_creative", prompt="critique_creative",
        schema=CritiqueDraft, model=model,
        variables={"brief": p.brief, "claims": claims_for_prompt(p),
                   "placements": placements_for_prompt(publisher_ids), "cards": payload},
    )
    by_persona = {r.persona_id: r for r in draft.reviews}
    out: dict[str, Critique] = {}
    for c in cards:
        r = by_persona.get(c.persona_id)
        issues = code_issues(c, cards, p.brief)
        checks = r.checks if r else []
        passed = all(x.passed for x in checks) and not issues
        fix = (r.fix or None) if r else None
        if issues:
            fix = "; ".join(filter(None, [fix, *issues]))
        out[c.persona_id] = Critique(checks=checks, code_issues=issues, passed=passed, fix=fix)
    return out


def persona_for_prompt_short(persona_id: str) -> dict:
    persona = catalog.personas()[persona_id]
    return {"name": persona.name, "messaging_preferences": persona.messaging_preferences,
            "disinterested_in": persona.disinterested_in}
