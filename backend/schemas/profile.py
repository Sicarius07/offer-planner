"""Stage 1: reading the brief

Two layers: `ProfileDraft` is exactly what the model is asked to produce (it quotes the
brief as evidence). `AdvertiserProfile` is what the rest of the system uses, after code has
located every quote in the brief. A quote that can't be found is treated as invented:
the evidence is dropped and the attribute is downgraded to "assumed"
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from backend.schemas.catalog import PriceTier

T = TypeVar("T")

Source = Literal["stated", "inferred", "assumed"]
Strength = Literal["primary", "secondary"]
Clarity = Literal["clear", "partial", "unusable"]
OfferingType = Literal["consumer_product", "consumer_service", "b2b", "unclear"]
BusinessModel = Literal["subscription", "one_time", "mixed", "unknown"]
Gender = Literal["female", "male", "any"]

STRENGTH_WEIGHT: dict[str, float] = {"primary": 1.0, "secondary": 0.5}


# ── What the model writes ─────────────────────────────────────────────────────


class AttrDraft(BaseModel, Generic[T]):
    value: T
    source: Source = Field(
        description="stated = the brief says it; inferred = a reasonable reading of specific "
        "words; assumed = a default we chose because the brief is silent"
    )
    quote: str = Field(
        description="Exact words copied from the brief that support this. Required for "
        "stated/inferred; empty string for assumed. Copy verbatim, do not paraphrase."
    )
    note: str = Field(description="One short clause on why, for inferred/assumed; else empty")


class TextAttrDraft(AttrDraft[str]):
    pass


class NumberAttrDraft(AttrDraft[float]):
    pass


class PriceTierAttrDraft(AttrDraft[PriceTier]):
    pass


class GenderAttrDraft(AttrDraft[Gender]):
    pass


class BusinessModelAttrDraft(AttrDraft[BusinessModel]):
    pass


class TagWeight(BaseModel):
    tag: str = Field(description="A tag from the list given for this field")
    strength: Strength


class ClaimDraft(BaseModel):
    claim: str = Field(description="A factual product claim, in a few words")
    quote: str = Field(description="Exact words from the brief this claim comes from")


class ClarifyingQuestion(BaseModel):
    question: str
    why: str = Field(description="What would change in the plan with the answer")
    suggested_answers: list[str] = Field(description="2 to 4 short likely answers")


class ProfileDraft(BaseModel):
    business_summary: str = Field(description="One plain sentence in our words")
    brand_name: str = Field(description="Brand name if the brief gives one, else empty string")
    offering_type: OfferingType
    product: TextAttrDraft = Field(description="What they sell, in a few words")
    sells: list[str] = Field(description="Product tags from the products list")
    competes_with: list[str] = Field(
        description="Products a publisher would have to sell to be a direct competitor. "
        "Include `sells` plus close substitutes only."
    )
    interests: list[TagWeight]
    values: list[TagWeight]
    occasions: list[TagWeight]
    positioning: list[str] = Field(description="Positioning tags from the list, only if clearly true")
    price_tier: PriceTierAttrDraft
    first_order_value_usd: NumberAttrDraft = Field(
        description="Typical first order value in USD. Use a stated price if given, else a "
        "category-typical estimate marked assumed"
    )
    gender: GenderAttrDraft
    age_range: TextAttrDraft = Field(
        description='Target age as "min-max", e.g. "25-44". Empty value if nothing suggests an age'
    )
    audience: TextAttrDraft = Field(
        description="Who the customer is, in a short phrase. Empty value if the brief gives no hint"
    )
    business_model: BusinessModelAttrDraft
    claims: list[ClaimDraft]
    clarity: Clarity
    clarity_reason: str
    assumptions: list[str] = Field(description="Plain-language assumptions we made, shown to the user")
    clarifying_questions: list[ClarifyingQuestion]


# ── What the system uses (quotes verified and located) ────────────────────────


class Span(BaseModel):
    text: str
    start: int
    end: int


class Attr(BaseModel, Generic[T]):
    value: T
    source: Source
    evidence: Span | None
    note: str | None


class TextAttr(Attr[str]):
    pass


class NumberAttr(Attr[float]):
    pass


class PriceTierAttr(Attr[PriceTier]):
    pass


class GenderAttr(Attr[Gender]):
    pass


class BusinessModelAttr(Attr[BusinessModel]):
    pass


class Claim(BaseModel):
    claim: str
    evidence: Span


class AdvertiserProfile(BaseModel):
    brief: str
    business_summary: str
    brand_name: str | None
    offering_type: OfferingType
    product: TextAttr
    sells: list[str]
    competes_with: list[str]
    interests: dict[str, float]
    values: dict[str, float]
    occasions: dict[str, float]
    positioning: list[str]
    price_tier: PriceTierAttr
    first_order_value_usd: NumberAttr
    gender: GenderAttr
    age_range: TextAttr | None
    audience: TextAttr | None
    business_model: BusinessModelAttr
    claims: list[Claim]
    clarity: Clarity
    clarity_reason: str
    assumptions: list[str]
    clarifying_questions: list[ClarifyingQuestion]
    dropped_quotes: list[str] = Field(
        default_factory=list, description="Quotes the model gave that aren't in the brief"
    )
    dropped_tags: list[str] = Field(
        default_factory=list, description="Tags the model gave that aren't in the taxonomy"
    )
