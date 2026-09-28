"""Stage 2: scoring publishers (code) and explaining them (LLM)"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.catalog import PublisherId

SignalName = Literal["category", "audience", "price", "values", "reach"]
Tier = Literal["recommended", "test", "excluded"]
ExclusionReason = Literal["competitor", "off_category", "weak_fit"]


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


class PublisherJudgmentDraft(BaseModel):
    publisher_id: PublisherId
    adjustment: int = Field(
        description="Nudge to the computed fit, between -15 and 15. 0 unless the tags "
        "clearly missed something."
    )
    adjustment_reason: str = Field(description="Required when adjustment is not 0, else empty")
    rationale: str = Field(description="One or two sentences citing specific evidence")
    evidence: list[EvidenceRef]
    risk: str = Field(description="What could make this placement underperform; empty if nothing specific")


class RerankDraft(BaseModel):
    judgments: list[PublisherJudgmentDraft]
    summary: str = Field(description="One sentence on the overall shape of the recommendation")


class PublisherResult(BaseModel):
    """What the UI shows per publisher: code score + LLM judgment, merged and enforced."""

    publisher_id: str
    name: str
    category: str
    signals: list[Signal]
    base_fit: int
    adjustment: int
    adjustment_reason: str | None
    fit: int
    tier: Tier
    exclusion_reason: ExclusionReason | None
    conflict: str | None
    adjacent_conflict: str | None
    rationale: str
    evidence: list[EvidenceRef]
    risk: str | None


class PublisherPlan(BaseModel):
    summary: str
    explained: bool = Field(True, description="False when the LLM review failed and these are computed scores only")
    recommended: list[PublisherResult]
    test: list[PublisherResult]
    excluded: list[PublisherResult]
