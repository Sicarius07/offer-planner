from datetime import date

import pytest

from backend import config
from backend.pipeline.campaign import _capped_proportional, allocate, bid_strategy, build_config
from backend.schemas.persona import PersonaPlan
from backend.schemas.publisher import PublisherPlan, PublisherResult


def pr(pid, fit, tier="recommended"):
    return PublisherResult(
        publisher_id=pid, name=pid, category="pet", signals=[], base_fit=fit, fit=fit,
        computed_tier=tier, tier=tier, tier_reason=None, exclusion_reason=None, conflict=None,
        adjacent_conflict=None, rationale="", evidence=[], risk=None,
    )


def test_bid_strategy_subscription_ratio(dog_food):
    b = bid_strategy(dog_food)
    assert b.allowable_cpa_ratio == config.CPA_RATIO["subscription"]
    assert b.target_cpa_usd == pytest.approx(36.0)
    assert b.max_cpa_usd == pytest.approx(46.8)


def test_capped_proportional_respects_cap_and_sums():
    shares = _capped_proportional([100, 10, 10, 10], 1.0, 0.4, 0.05)
    assert sum(shares) == pytest.approx(1.0)
    assert max(shares) <= 0.4 + 1e-9


def test_capped_proportional_drops_below_floor():
    shares = _capped_proportional([100, 100, 1], 1.0, 0.6, 0.05)
    assert shares[2] == 0.0 and sum(shares) == pytest.approx(1.0)


def test_allocation_sums_to_one_and_test_tier_share():
    core = [pr("pub_a", 90), pr("pub_b", 80), pr("pub_c", 72)]
    test = [pr("pub_t1", 60, "test"), pr("pub_t2", 55, "test")]
    out = allocate(core, test, 10_000)
    assert sum(s for *_, s in out) == pytest.approx(1.0)
    assert sum(s for _, role, s in out if role == "test") == pytest.approx(config.TEST_TIER_SHARE)


def test_small_budget_drops_test_publishers():
    out = allocate([pr("pub_a", 90)], [pr("t1", 60, "test"), pr("t2", 55, "test")], 1_000)
    tests = [x for x in out if x[1] == "test"]
    assert len(tests) == 0  # 15% of $1,000 = $150 < $250 minimum
    assert sum(s for *_, s in out) == pytest.approx(1.0)


def test_only_test_tier_splits_evenly():
    out = allocate([], [pr("t1", 60, "test"), pr("t2", 55, "test")], 10_000)
    assert [s for *_, s in out] == [0.5, 0.5]


def test_build_config_end_to_end(dog_food):
    pubs = PublisherPlan(summary="", recommended=[pr("pub_018", 80)], test=[], excluded=[])
    cfg = build_config(dog_food, pubs, PersonaPlan(picks=[], candidates=[], skipped_note=None),
                       [], 10_000, 30, start=date(2026, 10, 1))
    assert cfg.budget.total_usd == 10_000
    assert cfg.placements[0].allocation_pct == 100.0
    assert cfg.campaign.flight.end == "2026-10-30"
    assert "pet_food" in cfg.targeting.exclusions
    assert any("assumed order value" in w for w in cfg.review.warnings)


def test_ads_run_only_where_their_persona_shops():
    from types import SimpleNamespace

    from backend import catalog
    from backend.pipeline.campaign import ads_for
    pubs = catalog.publishers()
    gen_z, parent = SimpleNamespace(persona_id="persona_003"), SimpleNamespace(persona_id="persona_002")
    assert ads_for(pubs["pub_005"], [gen_z, parent]) == []        # ages 50-70: neither fits
    assert ads_for(pubs["pub_015"], [gen_z, parent]) == [parent]  # family households


def test_an_ad_no_placement_can_use_is_called_out(dog_food):
    from backend.schemas.creative import Creative
    cards = [Creative(creative_id=f"c_{pid}", persona_id=pid, persona_name=name, angle="a", headline="h",
                      body="b", cta="c", claims_used=[], offer_suggestion=None, tone_notes="",
                      status="passed")
             for pid, name in (("persona_002", "The Busy Parent"), ("persona_003", "The Gen Z Aesthete"))]
    pubs = PublisherPlan(summary="", recommended=[pr("pub_015", 80)], test=[], excluded=[])
    cfg = build_config(dog_food, pubs, PersonaPlan(picks=[], candidates=[], skipped_note=None), cards,
                       10_000, 30, start=date(2026, 1, 1))
    assert cfg.placements[0].creative_ids == ["c_persona_002"]
    assert any("The Gen Z Aesthete won't run" in w for w in cfg.review.warnings)
