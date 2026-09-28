"""Hand-built profiles for the tricky sample briefs, so scoring is tested without an LLM."""

from __future__ import annotations

import os

# Tests never trace or call real APIs. Set before backend imports: dotenv won't override.
for _k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
    os.environ[_k] = ""

import pytest  # noqa: E402

from backend.schemas.profile import AdvertiserProfile  # noqa: E402


def attr(value, source="stated"):
    return {"value": value, "source": source, "evidence": None, "note": None}


def make_profile(**kw) -> AdvertiserProfile:
    base = dict(
        brief="test brief",
        business_summary="test",
        brand_name=None,
        offering_type="consumer_product",
        product=attr("thing"),
        sells=[],
        competes_with=[],
        interests={},
        values={},
        occasions={},
        positioning=[],
        price_tier=attr("mid", "assumed"),
        first_order_value_usd=attr(50.0, "assumed"),
        gender=attr("any", "assumed"),
        age_range=None,
        audience=None,
        business_model=attr("unknown", "assumed"),
        claims=[],
        clarity="clear",
        clarity_reason="",
        assumptions=[],
        clarifying_questions=[],
    )
    for k, v in kw.items():
        base[k] = attr(*v) if isinstance(v, tuple) else v
    return AdvertiserProfile(**base)


def dog_food_profile():
    return make_profile(
        product=("senior dog food",),
        sells=["pet_food"], competes_with=["pet_food", "pet_treats"],
        interests={"pets": 1.0, "pet_health": 1.0},
        values={"science_backed": 1.0, "premium_quality": 1.0, "clean_ingredients": 0.5},
        occasions={"replenishment": 1.0},
        price_tier=("premium", "stated"),
        first_order_value_usd=(60.0, "assumed"),
        business_model=("subscription", "stated"),
    )


def activewear_profile():
    return make_profile(
        product=("sustainable women's activewear",),
        sells=["activewear"], competes_with=["activewear", "womens_apparel"],
        interests={"activewear": 1.0, "fitness": 0.5, "apparel_women": 0.5},
        values={"sustainability": 1.0},
        price_tier=("premium", "inferred"),
        first_order_value_usd=(95.0, "inferred"),
        gender=("female", "stated"),
        business_model=("one_time", "assumed"),
    )


def handbags_profile():
    return make_profile(
        product=("custom Italian leather handbags",),
        sells=["handbags_leather_goods"], competes_with=["handbags_leather_goods"],
        interests={"luxury_fashion": 1.0, "apparel_women": 0.5},
        values={"premium_quality": 1.0, "heritage": 1.0},
        positioning=["luxury_positioning", "slow_fulfillment"],
        price_tier=("luxury", "stated"),
        first_order_value_usd=(1200.0, "stated"),
        gender=("female", "inferred"),
        business_model=("one_time", "inferred"),
    )


def dental_saas_profile():
    return make_profile(
        offering_type="b2b",
        product=("dental practice software",),
        sells=["b2b_software"], competes_with=["b2b_software"],
        price_tier=("mid", "assumed"),
        first_order_value_usd=(300.0, "assumed"),
    )


dog_food = pytest.fixture(dog_food_profile, name="dog_food")
activewear = pytest.fixture(activewear_profile, name="activewear")
handbags = pytest.fixture(handbags_profile, name="handbags")
dental_saas = pytest.fixture(dental_saas_profile, name="dental_saas")
