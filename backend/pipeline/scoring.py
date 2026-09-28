"""Deterministic scoring: publishers and personas

Pure functions of (profile, catalog, config). No I/O, no LLM. Every number comes with a
sentence explaining it, because the UI shows both
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend import catalog, config
from backend.schemas.catalog import Persona, PersonaTags, Publisher, PublisherTags
from backend.schemas.persona import PersonaScore
from backend.schemas.profile import AdvertiserProfile
from backend.schemas.publisher import ScoredPublisher, Signal
from backend.taxonomy import INTEREST_SIM, VALUE_SIM, similarity

INCOME_RANK = {"mid": 1, "mid-high": 2, "high": 3}
# The lowest publisher income tier that comfortably buys at each price tier.
INCOME_NEEDED = {"value": 0, "mid": 1, "premium": 2, "luxury": 3}


# ── Small helpers ─────────────────────────────────────────────────────────────


def parse_age(s: str | None) -> tuple[int, int] | None:
    if not s:
        return None
    try:
        a, b = s.replace("–", "-").split("-")[:2]
        lo, hi = int(a.strip()), int(b.strip().rstrip("+"))
        return (lo, hi) if lo <= hi else (hi, lo)
    except (ValueError, IndexError):
        return None


def age_overlap(target: tuple[int, int], audience: tuple[int, int]) -> float:
    """Share of the target age range that the audience range covers."""
    lo, hi = max(target[0], audience[0]), min(target[1], audience[1])
    return max(0, hi - lo) / max(1, target[1] - target[0])


@dataclass
class Match:
    score: float                      # 0..1
    hits: list[tuple[str, str, float]]  # (advertiser tag, matched tag, contribution)


def tag_match(want: dict[str, float], have: dict[str, float], sim: dict) -> Match:
    """How well `have` covers what `want` asks for. Each wanted tag takes its best match
    (exact = 1.0, adjacent = partial credit), weighted by how much the advertiser wants it."""
    total = sum(want.values())
    if total <= 0:
        return Match(0.0, [])
    got, hits = 0.0, []
    for tag, w in want.items():
        best, best_tag = 0.0, ""
        for other, strength in have.items():
            v = similarity(tag, other, sim) * strength
            if v > best:
                best, best_tag = v, other
        if best > 0:
            hits.append((tag, best_tag, best))
        got += w * best
    hits.sort(key=lambda h: -h[2])
    return Match(got / total, hits)


def _hits_text(m: Match, limit: int = 3) -> str:
    parts = []
    for want, have, _ in m.hits[:limit]:
        parts.append(want if want == have else f"{want}≈{have}")
    return ", ".join(parts)


def _clip(x: float) -> int:
    return int(round(max(0.0, min(100.0, x))))


# ── Publisher signals ─────────────────────────────────────────────────────────


def category_signal(p: AdvertiserProfile, t: PublisherTags) -> Signal:
    want = {**p.interests, **{k: v * 0.5 for k, v in p.occasions.items()}}
    have = {**t.interests, **{k: v * 0.5 for k, v in t.occasions.items()}}
    m = tag_match(want, have, INTEREST_SIM)
    score = _clip(100 * m.score)
    detail = f"matches {_hits_text(m)}" if m.hits else "no shared interests"
    return Signal(name="category", score=score, detail=detail)


def audience_signal(p: AdvertiserProfile, pub: Publisher) -> Signal:
    parts: list[tuple[float, str]] = []
    if p.gender.value != "any" and p.gender.source != "assumed":
        share = pub.audience.gender_split.get(p.gender.value, 0.0)
        parts.append((100 * min(1.0, share / 0.75), f"{share:.0%} {p.gender.value}"))
    target_age = parse_age(p.age_range.value) if p.age_range and p.age_range.source != "assumed" else None
    pub_age = parse_age(pub.audience.age_skew)
    if target_age and pub_age:
        ov = age_overlap(target_age, pub_age)
        parts.append((100 * ov, f"ages {pub.audience.age_skew} cover {ov:.0%} of {target_age[0]}–{target_age[1]}"))
    need = INCOME_NEEDED[p.price_tier.value]
    have = INCOME_RANK[pub.audience.income_tier]
    income_score = 100 if have >= need else max(0, 100 - 35 * (need - have))
    if p.price_tier.source != "assumed" or need >= 2:
        parts.append((income_score, f"{pub.audience.income_tier} income for {p.price_tier.value} price"))
    if not parts:
        return Signal(name="audience", score=config.NEUTRAL_SCORE, neutral=True,
                      detail="brief doesn't narrow the audience")
    score = _clip(sum(s for s, _ in parts) / len(parts))
    return Signal(name="audience", score=score, detail="; ".join(d for _, d in parts))


def price_signal(p: AdvertiserProfile, pub: Publisher) -> Signal:
    price = p.first_order_value_usd.value
    aov = pub.avg_order_value_usd
    if not price or price <= 0:
        return Signal(name="price", score=config.NEUTRAL_SCORE, neutral=True, detail="no price signal")
    r = price / aov
    lo, hi = config.PRICE_BAND
    if lo <= r <= hi:
        score = 100.0
    elif r > hi:
        score = 100 - config.PRICE_FALLOFF_PER_DOUBLING * math.log2(r / hi)
    else:
        # Much cheaper than the basket is an easy add-on after checkout, so it costs little.
        score = 100 - config.PRICE_FALLOFF_CHEAPER_PER_DOUBLING * math.log2(lo / r)
    tag = "" if p.first_order_value_usd.source != "assumed" else " (price assumed)"
    return Signal(name="price", score=_clip(score),
                  detail=f"${price:,.0f} vs ${aov:,.0f} typical order ({r:.1f}×){tag}")


def values_signal(p: AdvertiserProfile, t: PublisherTags) -> Signal:
    if not p.values:
        return Signal(name="values", score=config.NEUTRAL_SCORE, neutral=True,
                      detail="brief states no values")
    m = tag_match(p.values, t.values, VALUE_SIM)
    detail = f"shares {_hits_text(m)}" if m.hits else "no shared values"
    return Signal(name="values", score=_clip(100 * m.score), detail=detail)


def reach_signal(pub: Publisher, lo: int, hi: int) -> Signal:
    x = (math.log10(pub.monthly_impressions) - math.log10(lo)) / max(1e-9, math.log10(hi) - math.log10(lo))
    return Signal(name="reach", score=_clip(20 + 80 * x),
                  detail=f"{pub.monthly_impressions / 1e6:.1f}M monthly impressions")


# ── Publisher scoring ─────────────────────────────────────────────────────────


def conflicts(p: AdvertiserProfile, t: PublisherTags) -> tuple[str | None, str | None]:
    """(direct, adjacent). Direct: publisher sells what the advertiser sells → excluded.
    Adjacent: publisher sells a close substitute → flagged, capped at test tier."""
    sells = set(p.sells) - {"other"}
    direct = sorted(sells & set(t.sells))
    if direct:
        return f"sells {', '.join(direct)}, like you", None
    adjacent = sorted((set(p.competes_with) - sells - {"other"}) & set(t.sells))
    if adjacent:
        return None, f"sells {', '.join(adjacent)}, a close substitute"
    return None, None


def score_publisher(p: AdvertiserProfile, pub: Publisher, t: PublisherTags,
                    reach_bounds: tuple[int, int], allow_competitors: bool = False) -> ScoredPublisher:
    signals = [
        category_signal(p, t),
        audience_signal(p, pub),
        price_signal(p, pub),
        values_signal(p, t),
        reach_signal(pub, *reach_bounds),
    ]
    by = {s.name: s for s in signals}
    fit = _clip(sum(config.PUBLISHER_WEIGHTS[s.name] * s.score for s in signals))
    direct, adjacent = conflicts(p, t)
    if direct and allow_competitors:
        # Some publishers accept adjacent brands; the advertiser opted in. Flag, don't exclude.
        direct, adjacent = None, f"{direct} (allowed by your settings)"

    if p.offering_type == "b2b":
        # Every publisher here is consumer checkout traffic; no score makes a B2B buyer appear.
        return ScoredPublisher(publisher_id=pub.id, signals=signals, base_fit=fit, tier="excluded",
                               exclusion_reason="off_category",
                               reason="B2B product: this network reaches consumers at checkout, not businesses.")
    if direct:
        return ScoredPublisher(publisher_id=pub.id, signals=signals, base_fit=fit, tier="excluded",
                               exclusion_reason="competitor", conflict=direct,
                               reason=f"Competitor: {direct}. Offers only run on non-competing brands.")
    if by["category"].score < config.OFF_CATEGORY_BELOW:
        return ScoredPublisher(publisher_id=pub.id, signals=signals, base_fit=fit, tier="excluded",
                               exclusion_reason="off_category",
                               reason=f"Off-category: shoppers here buy {pub.category.replace('_', ' ')}, "
                                      "with little overlap with what you sell.")
    tier, reason_code = tier_for(fit, adjacent is not None)
    if tier == "excluded":
        weakest = min((s for s in signals if s.name != "reach"), key=lambda s: s.score)
        reason = f"Weak fit ({fit}); weakest signal is {weakest.name}: {weakest.detail}."
    elif adjacent:
        reason = f"Fit {fit}, but {adjacent}; limited to a test budget."
    else:
        strongest = max((s for s in signals if not s.neutral and s.name != "reach"),
                        key=lambda s: s.score, default=by["category"])
        reason = f"Fit {fit}; strongest signal is {strongest.name}: {strongest.detail}."
    return ScoredPublisher(publisher_id=pub.id, signals=signals, base_fit=fit, tier=tier,
                           exclusion_reason=reason_code, adjacent_conflict=adjacent, reason=reason)


def tier_for(fit: int, adjacent_conflict: bool = False):
    if fit >= config.RECOMMEND_AT and not adjacent_conflict:
        return "recommended", None
    if fit >= config.TEST_AT:
        return "test", None
    return "excluded", "weak_fit"


def score_publishers(p: AdvertiserProfile, allow_competitors: bool = False) -> list[ScoredPublisher]:
    pubs, tags = catalog.publishers(), catalog.publisher_tags()
    imps = [x.monthly_impressions for x in pubs.values()]
    bounds = (min(imps), max(imps))
    scored = [score_publisher(p, pub, tags[pid], bounds, allow_competitors) for pid, pub in pubs.items()]
    return sorted(scored, key=lambda s: -s.base_fit)


# ── Persona scoring ───────────────────────────────────────────────────────────


def persona_gender_ok(persona: Persona, pub: Publisher) -> float:
    skew = persona.gender_skew
    female = pub.audience.gender_split.get("female", 0.5)
    if skew == "female":
        return min(1.0, female / 0.7)
    if skew == "female-leaning":
        return min(1.0, female / 0.55)
    if skew == "male":
        return min(1.0, (1 - female) / 0.7)
    return 1.0 - max(0.0, abs(female - 0.5) - 0.3)  # balanced: fine unless very one-sided


def persona_reach(persona: Persona, pubs: list[Publisher]) -> tuple[float, list[str]]:
    """Impression-weighted share of `pubs` whose audience fits this persona, and the ids of
    the ones that fit (best first)."""
    p_age = parse_age(persona.age_range)
    num = den = 0.0
    via: list[tuple[float, str]] = []
    for pub in pubs:
        a = parse_age(pub.audience.age_skew)
        fit = persona_gender_ok(persona, pub) * (age_overlap(p_age, a) if p_age and a else 0.5)
        w = math.log10(pub.monthly_impressions)
        num += w * fit
        den += w
        if fit >= 0.5:
            via.append((fit, pub.id))
    return (100 * num / den if den else 0.0), [pid for _, pid in sorted(via, reverse=True)]


def score_persona(p: AdvertiserProfile, persona: Persona, t: PersonaTags,
                  reachable: list[Publisher]) -> PersonaScore:
    want = {**p.interests, **p.occasions}
    have = {**t.interests, **t.occasions}
    aff = tag_match(want, have, INTEREST_SIM)
    val = tag_match(p.values, t.values, VALUE_SIM) if p.values else None
    price_ok = p.price_tier.value in t.price_tiers
    dislikes = sorted(set(t.dislikes) & set(p.positioning))

    reach, via = persona_reach(persona, reachable)

    affinity = 100 * aff.score
    values = 100 * val.score if val else config.NEUTRAL_SCORE
    price = 100 if price_ok else 30
    w = config.PERSONA_WEIGHTS
    raw = (w["affinity"] * affinity + w["values"] * values + w["price"] * price + w["reach"] * reach
           - config.PERSONA_CONFLICT_PENALTY * len(dislikes))

    bits = []
    if aff.hits:
        bits.append(f"shops {_hits_text(aff)}")
    if val and val.hits:
        bits.append(f"responds to {_hits_text(val, 2)}")
    if not price_ok:
        bits.append(f"price-mismatched for {p.price_tier.value}")
    if dislikes:
        bits.append(f"dislikes {', '.join(dislikes)}")
    return PersonaScore(
        persona_id=persona.id, score=_clip(raw), affinity=_clip(affinity), values=_clip(values),
        price=price, reach=_clip(reach), conflicts=dislikes,
        reach_publishers=via,
        detail="; ".join(bits) or "little overlap",
    )


def score_personas(p: AdvertiserProfile, plan_publisher_ids: list[str]) -> list[PersonaScore]:
    pubs = catalog.publishers()
    reachable = [pubs[i] for i in plan_publisher_ids if i in pubs]
    tags = catalog.persona_tags()
    scored = [score_persona(p, persona, tags[pid], reachable) for pid, persona in catalog.personas().items()]
    return sorted(scored, key=lambda s: -s.score)
