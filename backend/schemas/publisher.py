"""Stage 2: scoring publishers (code) and explaining them (LLM)"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.catalog import PublisherId

SignalName = Literal["category", "audience", "price", "values", "reach"]
Tier = Literal["recommended", "test", "excluded"]
ExclusionReason = Literal["competitor", "off_category", "weak_fit", "review"]


class Signal(BaseModel):
    name: SignalName
    score: int                 # 0..100
    neutral: bool = False      # the brief didn't specify this dimension
    detail: str                # human-readable explanation of the number


class ScoredPublisher(BaseModel):
    """Output of the deterministic scorer. No LLM involved."""

    publisher_id: str
    signals: list[Signal]
    base_fit: int
    tier: Tier
    exclusion_reason: ExclusionReason | None = None
    conflict: str | None = None           # "sells pet_food, like you"
    adjacent_conflict: str | None = None  # related but not identical products: flagged, not excluded
    reason: str                           # one line, code-written


EvidenceField = Literal[
    "notes", "category", "subcategories", "audience", "avg_order_value_usd",
    "monthly_impressions", "brief",
]


class EvidenceRef(BaseModel):
    field: EvidenceField
    quote: str = Field(description="Exact text of that field (or of the brief) being cited")


CompetitorCall = Literal["agree", "missed_competitor", "not_a_competitor"]


class PublisherJudgmentDraft(BaseModel):
    publisher_id: PublisherId
    tier: Tier = Field(
        description="Final tier. Keep the computed tier unless the tags clearly got it wrong"
    )
    tier_reason: str = Field(
        description="Required when tier differs from the computed tier: what the scores missed, "
        "backed by the evidence quotes. Else empty"
    )
    competitor_call: CompetitorCall = Field(
        description="missed_competitor: not excluded as a competitor, but it sells what the "
        "advertiser sells. not_a_competitor: excluded as a competitor, but it isn't one. "
        "Else agree"
    )
    competitor_reason: str = Field(description="Required unless competitor_call is agree, else empty")
    rationale: str = Field(description="One or two sentences citing specific evidence")
    evidence: list[EvidenceRef]
    risk: str = Field(description="What could make this placement underperform; empty if nothing specific")


class RerankDraft(BaseModel):
    judgments: list[PublisherJudgmentDraft]
    summary: str = Field(description="One sentence on the overall shape of the recommendation")
    offering_type_doubt: str = Field(
        description="If the profile's offering_type (b2b vs consumer) looks wrong, say why. Else empty"
    )


class PublisherResult(BaseModel):
    """What the UI shows per publisher: code score + LLM judgment, merged and enforced."""

    publisher_id: str
    name: str
    category: str
    signals: list[Signal]
    base_fit: int                         # computed by code, never changed
    fit: int                              # base_fit, moved into the final tier's band if the review moved it
    computed_tier: Tier
    tier: Tier
    tier_reason: str | None               # why the review moved it; None when it kept the computed tier
    exclusion_reason: ExclusionReason | None
    conflict: str | None
    adjacent_conflict: str | None
    rationale: str
    evidence: list[EvidenceRef]
    risk: str | None
    competitor_dispute: str | None = None  # the review thinks a code-excluded competitor isn't one


class PublisherPlan(BaseModel):
    summary: str
    explained: bool = Field(True, description="False when the LLM review failed and these are computed scores only")
    recommended: list[PublisherResult]
    test: list[PublisherResult]
    excluded: list[PublisherResult]
    offering_type_doubt: str | None = None
