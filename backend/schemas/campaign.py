"""Stage 5: a draft campaign an ad server could launch and a human could approve.

The advertiser pays per conversion, so the objective is conversions and the bid strategy is target CPA; everything else is
what's needed to launch, measure, and review.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Flight(BaseModel):
    start: str          # ISO date
    end: str
    days: int


class CampaignMeta(BaseModel):
    name: str
    status: Literal["draft"] = "draft"
    objective: Literal["conversions"] = "conversions"
    flight: Flight


class Budget(BaseModel):
    total_usd: float
    monthly_usd: float
    daily_cap_usd: float
    pacing: Literal["even"] = "even"
    currency: Literal["USD"] = "USD"


class BidStrategy(BaseModel):
    type: Literal["target_cpa"] = "target_cpa"
    target_cpa_usd: float
    max_cpa_usd: float
    allowable_cpa_ratio: float
    first_order_value_usd: float
    first_order_value_source: Literal["stated", "inferred", "assumed"]
    learning_period_days: int
    rationale: str


class Placement(BaseModel):
    publisher_id: str
    publisher_name: str
    category: str
    role: Literal["core", "test"]
    fit_score: int
    allocation_pct: float
    budget_usd: float
    est_conversions: float
    capacity_note: str | None = None


class Demographic(BaseModel):
    value: str
    source: Literal["stated", "inferred", "assumed"]


class Targeting(BaseModel):
    personas: list[str]
    gender: Demographic | None
    age_range: Demographic | None
    geo: list[str]
    contextual_interests: list[str]
    exclusions: list[str]          # competitor product categories: the non-compete rule, as config


class CreativeRef(BaseModel):
    creative_id: str
    persona_id: str
    weight: float
    status: str


class FrequencyCap(BaseModel):
    impressions: int
    per_days: int
    rationale: str


class Measurement(BaseModel):
    conversion_event: Literal["purchase"] = "purchase"
    attribution_window_days: int
    kpis: list[str]
    holdout_pct: float


class Experiment(BaseModel):
    creative_rotation: Literal["even_then_optimize"] = "even_then_optimize"
    test_budget_pct: float
    graduate_rule: str
    notes: str


class Review(BaseModel):
    needs_human_review: bool
    confidence: Literal["high", "medium", "low"]
    assumptions: list[str]
    warnings: list[str]


class CampaignConfig(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    campaign: CampaignMeta
    budget: Budget
    bid_strategy: BidStrategy
    placements: list[Placement]
    targeting: Targeting
    creatives: list[CreativeRef]
    frequency_cap: FrequencyCap
    measurement: Measurement
    experiment: Experiment
    review: Review
