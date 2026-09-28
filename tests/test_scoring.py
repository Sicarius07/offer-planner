from backend.pipeline.scoring import (
    age_overlap, parse_age, score_personas, score_publishers, tag_match,
)
from backend.taxonomy import INTEREST_SIM
from tests.conftest import make_profile


def by_id(scored):
    return {s.publisher_id: s for s in scored}


def test_parse_age():
    assert parse_age("25-44") == (25, 44)
    assert parse_age("50–70") == (50, 70)
    assert parse_age("garbage") is None
    assert age_overlap((30, 50), (40, 60)) == 0.5


def test_tag_match_adjacency_gives_partial_credit():
    exact = tag_match({"fitness": 1.0}, {"fitness": 1.0}, INTEREST_SIM).score
    near = tag_match({"fitness": 1.0}, {"activewear": 1.0}, INTEREST_SIM).score
    none = tag_match({"fitness": 1.0}, {"kitchen": 1.0}, INTEREST_SIM).score
    assert exact == 1.0 and 0 < near < 1 and none == 0


def test_dog_food_excludes_pet_food_competitors(dog_food):
    s = by_id(score_publishers(dog_food))
    for pid in ("pub_007", "pub_009"):   # Pawline, Ruffco sell pet food
        assert s[pid].tier == "excluded" and s[pid].exclusion_reason == "competitor"
    # Tailcrate sells treats: a close substitute, flagged but not excluded.
    assert s["pub_018"].adjacent_conflict and s["pub_018"].tier != "recommended"
    # Beauty and wellness-services audiences are off-category for dog food.
    assert s["pub_013"].tier == "excluded"
    assert s["pub_003"].tier == "excluded"


def test_activewear_excludes_movewell_and_cloudfoot(activewear):
    s = by_id(score_publishers(activewear))
    assert s["pub_002"].exclusion_reason == "competitor"   # Movewell sells activewear
    assert s["pub_017"].exclusion_reason == "competitor"   # Cloudfoot sells activewear
    # Women's apparel publishers are close substitutes: flagged, never "recommended".
    assert s["pub_004"].adjacent_conflict


def test_luxury_handbags_price_mismatch_everywhere(handbags):
    scored = score_publishers(handbags)
    prices = [next(x for x in s.signals if x.name == "price").score for s in scored]
    assert max(prices) <= 40, "a $1,200 bag should not look price-compatible with ≤$198 AOVs"
    assert not [s for s in scored if s.tier == "recommended"]


def test_b2b_has_no_fits(dental_saas):
    scored = score_publishers(dental_saas)
    assert all(s.tier == "excluded" for s in scored)
    assert all(s.exclusion_reason == "off_category" for s in scored)


def test_unstated_dimensions_are_neutral():
    p = make_profile(interests={"pets": 1.0})
    s = score_publishers(p)[0]
    audience = next(x for x in s.signals if x.name == "audience")
    values = next(x for x in s.signals if x.name == "values")
    assert audience.neutral and values.neutral


def test_scores_are_deterministic(dog_food):
    assert score_publishers(dog_food) == score_publishers(dog_food)


def test_persona_scoring_prefers_pet_parent_for_dog_food(dog_food):
    plan = [s.publisher_id for s in score_publishers(dog_food) if s.tier != "excluded"]
    ranked = score_personas(dog_food, plan)
    assert ranked[0].persona_id == "persona_004"


def test_persona_conflicts_penalize(handbags):
    ranked = {p.persona_id: p for p in score_personas(handbags, ["pub_004", "pub_005"])}
    # Value-Conscious Shopper dislikes luxury positioning.
    assert "luxury_positioning" in ranked["persona_008"].conflicts
    assert ranked["persona_005"].score > ranked["persona_008"].score


def test_allow_competitors_flags_instead_of_excluding(dog_food):
    s = by_id(score_publishers(dog_food, allow_competitors=True))
    assert s["pub_007"].tier != "excluded"
    assert "allowed by your settings" in s["pub_007"].adjacent_conflict


def test_b2b_never_places_even_with_overlapping_tags(dental_saas):
    p = dental_saas.model_copy(update={"interests": {"convenience": 1.0}, "values": {"convenience_speed": 1.0}})
    assert all(s.tier == "excluded" for s in score_publishers(p))



def test_cheap_add_on_is_not_punished_like_an_expensive_offer():
    from backend import catalog
    from backend.pipeline.scoring import price_signal
    pub = catalog.publishers()["pub_014"]  # $198 typical order
    cheap = price_signal(make_profile(first_order_value_usd=(18.0, "stated")), pub)
    pricey = price_signal(make_profile(first_order_value_usd=(2178.0, "stated")), pub)  # 11× the basket
    assert cheap.score >= 70 and pricey.score <= 10
