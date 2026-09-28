"""Stage 5: build the campaign config. Pure functions, all unit-tested."""

from __future__ import annotations

from datetime import date, timedelta

from backend import catalog, config
from backend.schemas.catalog import Publisher
from backend.pipeline.scoring import persona_reach
from backend.schemas.campaign import (
    BidStrategy, Budget, CampaignConfig, CampaignMeta, CreativeRef, Demographic, Experiment,
    Flight, FrequencyCap, Measurement, Placement, Review, Targeting, TestPlan,
)
from backend.schemas.creative import Creative
from backend.schemas.persona import PersonaPlan
from backend.schemas.profile import AdvertiserProfile
from backend.schemas.publisher import PublisherPlan, PublisherResult


def bid_strategy(p: AdvertiserProfile) -> BidStrategy:
    model = p.business_model.value
    ratio = config.CPA_RATIO[model]
    fov = p.first_order_value_usd.value
    target = round(fov * ratio, 2)
    why = {
        "subscription": "subscription revenue repeats, so a first order can be bought at a larger share of its value",
        "mixed": "some revenue repeats",
        "one_time": "one-time purchase, so the first order has to pay back the acquisition",
        "unknown": "business model unclear; a middle ratio until real margins are known",
    }[model]
    src = p.first_order_value_usd.source
    return BidStrategy(
        target_cpa_usd=target,
        max_cpa_usd=round(target * config.MAX_CPA_MULTIPLIER, 2),
        allowable_cpa_ratio=ratio,
        first_order_value_usd=fov,
        first_order_value_source=src,
        learning_period_days=config.LEARNING_PERIOD_DAYS,
        rationale=(f"${fov:,.0f} first order{' (assumed)' if src == 'assumed' else ''} × {ratio:.2f} "
                   f"= ${target:,.2f} target CPA: {why}. The max CPA allows headroom while the "
                   f"campaign learns over {config.LEARNING_PERIOD_DAYS} days."),
    )


def allocate(core: list[PublisherResult], test: list[PublisherResult],
             total: float) -> list[tuple[PublisherResult, str, float]]:
    """Split `total` across publishers. Returns (publisher, role, share).

    Test tier: a fixed share, split evenly; any publisher whose slice is under the minimum is
    dropped. Core: the rest, proportional to fit² (strong fits dominate), each share clamped to
    [CORE_MIN_SHARE, CORE_MAX_SHARE] with the excess redistributed.
    """
    out: list[tuple[PublisherResult, str, float]] = []
    test_share = config.TEST_TIER_SHARE if test else 0.0
    if test:
        # Keep as many of the best test publishers as can each get the minimum budget.
        k = min(len(test), int(total * test_share // config.TEST_MIN_BUDGET_USD))
        if k:
            out += [(t, "test", test_share / k) for t in test[:k]]
        else:
            test_share = 0.0
    if not core:
        # No strong fits: everything goes to test-tier publishers, evenly.
        if out:
            n = len(out)
            return [(pub, role, 1.0 / n) for pub, role, _ in out]
        return []

    core_total = 1.0 - test_share
    shares = _capped_proportional([c.fit ** 2 for c in core], core_total,
                                  config.CORE_MAX_SHARE, config.CORE_MIN_SHARE)
    kept = [(c, s) for c, s in zip(core, shares, strict=True) if s > 0]
    return [(c, "core", s) for c, s in kept] + out


def _capped_proportional(weights: list[float], total: float, cap: float, floor: float) -> list[float]:
    """Proportional split of `total` with a per-item cap and floor. Items below the floor
    are dropped and the split recomputed. If the cap can't be honored (too few items), the
    cap is relaxed to an even split."""
    n = len(weights)
    active = [w > 0 for w in weights]
    while True:
        idx = [i for i in range(n) if active[i]]
        if not idx:
            return [0.0] * n
        eff_cap = max(cap, total / len(idx))
        shares = [0.0] * n
        fixed: set[int] = set()
        remaining = total
        # Water-filling: repeatedly cap items that exceed the cap.
        while True:
            free = [i for i in idx if i not in fixed]
            wsum = sum(weights[i] for i in free)
            changed = False
            for i in free:
                s = remaining * weights[i] / wsum if wsum else 0
                if s > eff_cap + 1e-12:
                    shares[i] = eff_cap
                    fixed.add(i)
                    changed = True
            if not changed:
                for i in free:
                    shares[i] = remaining * weights[i] / wsum if wsum else 0
                break
            remaining = total - sum(shares[i] for i in fixed)
        low = [i for i in idx if shares[i] < floor - 1e-12]
        if not low or len(idx) == 1:
            return shares
        active[min(low, key=lambda i: shares[i])] = False


def ads_for(pub: Publisher, ads: list[Creative]) -> list[Creative]:
    """The ads whose persona this publisher's audience fits (same test as persona reach)."""
    personas = catalog.personas()
    return [c for c in ads if persona_reach(personas[c.persona_id], [pub])[1]]


def test_plan(pub: PublisherResult, bid: BidStrategy) -> TestPlan:
    days = config.LEARNING_PERIOD_DAYS
    return TestPlan(
        hypothesis=pub.rationale,
        risk=pub.risk,
        promote_if=f"CPA at or below the ${bid.target_cpa_usd:,.2f} target after {days} days: move it to core.",
        cut_if=f"CPA above the ${bid.max_cpa_usd:,.2f} maximum, or no conversions after {days} days: stop it.",
    )


def build_config(p: AdvertiserProfile, pubs: PublisherPlan, personas: PersonaPlan,
                 creatives: list[Creative], monthly_budget: float, flight_days: int,
                 start: date | None = None) -> CampaignConfig:
    start = start or date.today() + timedelta(days=7)
    total = round(monthly_budget * flight_days / 30, 2)
    bid = bid_strategy(p)
    catalog_pubs = catalog.publishers()

    placements: list[Placement] = []
    warnings: list[str] = []
    active = [c for c in creatives if c.status != "flagged"]
    unmatched: list[str] = []
    for pub, role, share in allocate(pubs.recommended, pubs.test, total):
        budget = round(total * share, 2)
        est = round(budget / bid.target_cpa_usd, 1) if bid.target_cpa_usd else 0.0
        imps = catalog_pubs[pub.publisher_id].monthly_impressions * flight_days / 30
        ceiling = imps * config.CAPACITY_CONVERSION_CEILING
        note = None
        if est > ceiling:
            note = (f"{est:.0f} conversions would exceed ~{ceiling:.0f} this publisher can likely "
                    "deliver; expect under-delivery or raise the CPA")
            warnings.append(f"{pub.name}: {note}.")
        ads = ads_for(catalog_pubs[pub.publisher_id], active)
        if active and not ads:
            unmatched.append(pub.name)
        placements.append(Placement(
            publisher_id=pub.publisher_id, publisher_name=pub.name, category=pub.category,
            role=role, fit_score=pub.fit, allocation_pct=round(100 * share, 1),
            budget_usd=budget, est_conversions=est, capacity_note=note,
            creative_ids=[c.creative_id for c in (ads or active)], personas_matched=bool(ads),
            test_plan=test_plan(pub, bid) if role == "test" else None,
        ))
    if unmatched:
        warnings.append(f"No chosen persona fits the audience at {', '.join(unmatched)}, so every ad "
                        "rotates there. Consider writing an ad for that audience.")
    placed = {cid for pl in placements for cid in pl.creative_ids}
    idle = [c for c in active if c.creative_id not in placed]
    if placements and idle:
        warnings.append(f"The ad{'s' if len(idle) > 1 else ''} for {', '.join(c.persona_name for c in idle)} "
                        f"won't run: no placement's shoppers fit {'those personas' if len(idle) > 1 else 'that persona'}.")

    plan_pubs = [catalog_pubs[x.publisher_id] for x in placements]
    geos = sorted({g for pub in plan_pubs for g in pub.audience.top_geos})
    if "nationwide" in geos or not geos:
        geos = ["US (nationwide)"]

    def demo(attr) -> Demographic | None:
        if attr is None or attr.value in (None, "any"):
            return None
        return Demographic(value=str(attr.value), source=attr.source)

    targeting = Targeting(
        personas=[x.persona_id for x in personas.picks],
        gender=demo(p.gender),
        age_range=demo(p.age_range),
        geo=geos,
        contextual_interests=sorted(p.interests, key=lambda k: -p.interests[k]),
        exclusions=sorted(set(p.competes_with) - {"other"}),
    )

    usable = [c for c in creatives if c.status != "flagged"] or creatives
    weight = round(1 / len(usable), 3) if usable else 0.0
    creative_refs = [CreativeRef(creative_id=c.creative_id, persona_id=c.persona_id,
                                 weight=weight if c in usable else 0.0, status=c.status)
                     for c in creatives]

    flagged = [c for c in creatives if c.status == "flagged"]
    if flagged and p.clarity == "unusable":
        warnings.append("The brief doesn't say what's being sold, so the ads can't pass review and are "
                        "paused. They're shown as drafts; answer the questions to get launchable ads.")
    elif flagged:
        warnings.append(f"{len(flagged)} creative(s) failed review twice and are paused: "
                        + ", ".join(c.persona_name for c in flagged) + ".")
    if not pubs.explained:
        warnings.append("Publisher review was unavailable, so placements come from computed scores "
                        "alone, without explanations or a check of the tiers. Check them before launch.")
    disputed = [r for r in pubs.excluded if r.competitor_dispute]
    for r in disputed:
        warnings.append(f"{r.name} was excluded as a competitor, but the review disagrees: "
                        f"{r.competitor_dispute} Decide whether it should run.")
    if pubs.offering_type_doubt:
        warnings.append(f"The review questions whether this is a B2B or consumer business: "
                        f"{pubs.offering_type_doubt}")
    if not placements:
        warnings.append("No publisher in this catalog is a good fit; nothing would run.")
    elif not pubs.recommended:
        warnings.append("No publisher cleared the recommended bar, so the whole budget is a test. "
                        "Treat results as exploratory.")
    if p.clarity == "unusable" and creatives:
        warnings.append("The brief doesn't say what's being sold, so the ads are generic placeholders. "
                        "Rewrite them once the product is known.")
    if p.first_order_value_usd.source == "assumed":
        warnings.append("Target CPA is based on an assumed order value. Confirm price before launch.")

    assumptions = list(p.assumptions)
    assumptions.append(f"Allowable CPA is {bid.allowable_cpa_ratio:.0%} of first order value "
                       f"({p.business_model.value.replace('_', ' ')}); replace with real margin and LTV.")
    confidence = ("low" if p.clarity == "unusable" or not placements
                  else "medium" if p.clarity == "partial" or warnings else "high")
    needs_review = (p.clarity != "clear" or bool(flagged) or not pubs.recommended
                    or not pubs.explained or bool(disputed) or bool(pubs.offering_type_doubt))

    product = p.product.value if p.product.source != "assumed" else "new advertiser"
    return CampaignConfig(
        campaign=CampaignMeta(
            name=f"{p.brand_name or product.capitalize()} · post-purchase launch",
            flight=Flight(start=start.isoformat(),
                          end=(start + timedelta(days=flight_days - 1)).isoformat(), days=flight_days),
        ),
        budget=Budget(total_usd=total, monthly_usd=monthly_budget,
                      daily_cap_usd=round(total / flight_days, 2)),
        bid_strategy=bid,
        placements=placements,
        targeting=targeting,
        creatives=creative_refs,
        frequency_cap=FrequencyCap(
            **config.FREQUENCY_CAP,
            rationale="Offers appear once, right after checkout; repeating them reads as spam.",
        ),
        measurement=Measurement(
            attribution_window_days=config.ATTRIBUTION_WINDOW_DAYS,
            kpis=["conversions", "cpa", "conversion_rate", "revenue_per_impression"],
            holdout_pct=5.0,
        ),
        experiment=Experiment(
            test_budget_pct=round(sum(x.allocation_pct for x in placements if x.role == "test"), 1),
            graduate_rule=(f"After {config.LEARNING_PERIOD_DAYS} days, move a test publisher to core if "
                           "its CPA is at or below target; cut any placement above max CPA."),
            notes="Creatives rotate evenly until each has enough conversions to compare.",
        ),
        review=Review(needs_human_review=needs_review, confidence=confidence,
                      assumptions=assumptions, warnings=warnings),
    )
