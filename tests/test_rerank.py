"""The publisher review moves tiers only with a checked quote; code keeps the hard rules."""

from __future__ import annotations

from datetime import date



from backend import catalog
from backend.pipeline import personas, publishers
from backend.pipeline.campaign import build_config
from backend.pipeline.scoring import score_publishers
from backend.schemas.persona import PersonaPlan, PersonaSelectionDraft
from backend.schemas.publisher import RerankDraft
from tests.conftest import dog_food_profile, make_profile


def j(pid, tier, reason="", evidence=(), call="agree", call_reason="", fit=None):
    return {"publisher_id": pid, "tier": tier, "tier_reason": reason, "fit": fit, "competitor_call": call,
            "competitor_reason": call_reason, "rationale": "r", "risk": "",
            "evidence": [{"field": f, "quote": q} for f, q in evidence]}


def review(*judgments, doubt=""):
    return RerankDraft.model_validate({"summary": "s", "offering_type_doubt": doubt, "judgments": list(judgments)})


def by_id(plan):
    return {r.publisher_id: r for r in plan.recommended + plan.test + plan.excluded}


def config_for(p, plan):
    return build_config(p, plan, PersonaPlan(picks=[], candidates=[], skipped_note=None), [],
                        10_000, 30, start=date(2026, 1, 1))


def test_promotion_with_a_checked_quote_counts():
    p = dog_food_profile()
    plan = publishers.merge(p, score_publishers(p), review(
        j("pub_008", "recommended", "clean-label shoppers buy premium pet food",
          [("notes", "Responsive to clean-ingredient")])))
    r = by_id(plan)["pub_008"]
    assert (r.computed_tier, r.tier, r.exclusion_reason) == ("excluded", "recommended", None)
    assert r.fit == 70 and r.base_fit < 70  # placed at the bottom of its new tier, for budget
    assert r.tier_reason
    assert any(x.publisher_id == "pub_008" for x in config_for(p, plan).placements)


def test_reviews_fit_for_a_moved_publisher_sets_its_budget_weight():
    p = dog_food_profile()
    quote = [("notes", "Responsive to clean-ingredient")]
    plan = publishers.merge(p, score_publishers(p), review(
        j("pub_008", "recommended", "strong fit", quote, fit=88),
        j("pub_012", "recommended", "weaker fit", [("notes", "Science-forward wellness")], fit=40),
    ))
    assert by_id(plan)["pub_008"].fit == 88
    assert by_id(plan)["pub_012"].fit == 70  # out of its band: pulled into it
    shares = {x.publisher_id: x.allocation_pct for x in config_for(p, plan).placements}
    assert shares["pub_008"] > shares["pub_012"]


def test_move_without_a_quote_or_reason_is_ignored():
    p = dog_food_profile()
    plan = publishers.merge(p, score_publishers(p), review(
        j("pub_008", "recommended", "great fit", [("notes", "loves dogs")]),  # invented quote
        j("pub_012", "test", "", [("notes", "Science-forward wellness")]),   # no reason
    ))
    assert by_id(plan)["pub_008"].tier == "excluded"
    assert by_id(plan)["pub_012"].tier == "excluded"


def test_demotion_is_marked_as_the_reviews_call():
    p = dog_food_profile()
    plan = publishers.merge(p, score_publishers(p), review(
        j("pub_018", "excluded", "playful voice clashes with a clinical senior-dog brand",
          [("notes", "Fun, playful brand voice converts best")])))
    r = by_id(plan)["pub_018"]
    assert (r.tier, r.exclusion_reason) == ("excluded", "review") and r.fit < 50


def test_competitor_stays_excluded_but_a_dispute_goes_to_a_human():
    p = dog_food_profile()
    plan = publishers.merge(p, score_publishers(p), review(
        j("pub_007", "recommended", "complementary", [("notes", "Subscription-heavy")],
          call="not_a_competitor", call_reason="Pawline mostly sells supplies.")))
    r = by_id(plan)["pub_007"]
    assert (r.tier, r.exclusion_reason) == ("excluded", "competitor")
    assert r.competitor_dispute == "Pawline mostly sells supplies."
    review_ = config_for(p, plan).review
    assert review_.needs_human_review and any("review disagrees" in w for w in review_.warnings)


def test_review_can_add_a_competitor_the_tags_missed():
    # A sunglasses brand: `other`, so code has nothing to compare.
    p = make_profile(sells=["other"], competes_with=["other"], interests={"apparel_women": 1.0})
    scored = score_publishers(p)
    assert by_id(publishers.merge(p, scored, None))["pub_004"].tier == "recommended"
    plan = publishers.merge(p, scored, review(
        j("pub_004", "recommended", call="missed_competitor", call_reason="sells sunglasses too",
          evidence=[("notes", "Older affluent women")]),
        # Only the brief as evidence: not enough to call a publisher a competitor.
        j("pub_006", "recommended", call="missed_competitor", call_reason="sells sunglasses",
          evidence=[("brief", "test brief")]),
    ))
    assert (by_id(plan)["pub_004"].tier, by_id(plan)["pub_004"].exclusion_reason) == ("excluded", "competitor")
    assert by_id(plan)["pub_006"].tier == "recommended"


def test_b2b_stays_excluded_and_a_doubt_is_surfaced():
    p = make_profile(offering_type="b2b", interests={"groceries": 1.0})
    plan = publishers.merge(p, score_publishers(p), review(
        j("pub_001", "recommended", "restaurants order here", [("notes", "High-frequency purchasers")]),
        doubt="Sounds like a consumer app."))
    assert not plan.recommended and not plan.test
    review_ = config_for(p, plan).review
    assert review_.needs_human_review and any("B2B or consumer" in w for w in review_.warnings)


def test_any_persona_can_be_picked_and_reach_follows_the_final_plan():
    p = dog_food_profile()
    scored_pubs = score_publishers(p)
    candidate_ids = [s.publisher_id for s in scored_pubs if s.tier != "excluded"]
    scored = personas.score_personas(p, candidate_ids)
    last = scored[-1].persona_id
    draft = PersonaSelectionDraft.model_validate({"skipped_note": "", "picks": [
        {"persona_id": pid, "why_plausible": "w", "lean_into": [], "avoid": [], "ad_angle": pid, "confidence": "low"}
        for pid in (scored[0].persona_id, last)]})
    plan = personas.merge(scored, draft)
    assert [pk.rank for pk in plan.picks] == [1, len(catalog.personas())]

    pub_plan = publishers.merge(p, scored_pubs, review(
        j("pub_008", "recommended", "clean-label shoppers", [("notes", "Responsive to clean-ingredient")])))
    final_ids = {r.publisher_id for r in pub_plan.recommended + pub_plan.test}
    for pk in personas.reach_final(plan, pub_plan).picks:
        assert set(pk.reached_via) <= final_ids
