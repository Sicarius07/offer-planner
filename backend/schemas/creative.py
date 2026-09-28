"""Stage 4: one post-purchase offer card per persona, then a review pass"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.catalog import PersonaId

HEADLINE_MAX, BODY_MAX, CTA_MAX = 40, 140, 18


class ClaimUse(BaseModel):
    claim: str = Field(description="The claim as it appears in the ad")
    source_quote: str = Field(description="The exact brief words that back it")


class CreativeDraft(BaseModel):
    angle: str = Field(description="The one idea this variant bets on, in a short phrase")
    headline: str = Field(max_length=HEADLINE_MAX)
    body: str = Field(max_length=BODY_MAX)
    cta: str = Field(max_length=CTA_MAX)
    claims_used: list[ClaimUse]
    offer_suggestion: str = Field(
        description="An optional incentive to test, e.g. 'first box 20% off'. A suggestion "
        "for the advertiser, never written into the copy as fact. Empty if none"
    )
    tone_notes: str = Field(description="How the copy maps to this persona's preferences")


class RubricCheck(BaseModel):
    name: Literal["grounded", "persona_fit", "specific", "placement", "publisher_safe"]
    passed: bool
    reason: str


class CreativeReviewDraft(BaseModel):
    persona_id: PersonaId
    checks: list[RubricCheck]
    fix: str = Field(description="If any check failed, the concrete change to make; else empty")


class CritiqueDraft(BaseModel):
    reviews: list[CreativeReviewDraft]


class Critique(BaseModel):
    checks: list[RubricCheck]
    code_issues: list[str]      # length, banned phrases, near-duplicates
    passed: bool
    fix: str | None


class Creative(BaseModel):
    creative_id: str
    persona_id: str
    persona_name: str
    angle: str
    headline: str
    body: str
    cta: str
    claims_used: list[ClaimUse]
    offer_suggestion: str | None
    tone_notes: str
    status: Literal["draft", "passed", "revised", "flagged"]
    critique: Critique | None = None
    revision_of: CreativeDraft | None = None
