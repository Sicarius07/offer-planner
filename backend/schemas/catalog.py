"""The given data pack, plus the offline enrichment layered on top of it"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

IncomeTier = Literal["mid", "mid-high", "high"]
PriceTier = Literal["value", "mid", "premium", "luxury"]


class Audience(BaseModel):
    age_skew: str
    gender_split: dict[str, float]
    top_geos: list[str]
    income_tier: IncomeTier


class Publisher(BaseModel):
    id: str
    name: str
    category: str
    subcategories: list[str]
    monthly_impressions: int
    avg_order_value_usd: float
    audience: Audience
    notes: str


class PublisherTags(BaseModel):
    id: str
    interests: dict[str, float]
    values: dict[str, float]
    occasions: dict[str, float]
    sells: list[str]
    evidence: dict[str, str] = {}
    enrichment_version: str = ""


class Persona(BaseModel):
    id: str
    name: str
    age_range: str
    gender_skew: str
    description: str
    category_affinities: list[str]
    price_sensitivity: str
    messaging_preferences: list[str]
    disinterested_in: list[str]
    typical_aov_usd: float


class PersonaTags(BaseModel):
    id: str
    interests: dict[str, float]
    values: dict[str, float]
    occasions: dict[str, float]
    price_tiers: list[PriceTier]
    dislikes: list[str]
    enrichment_version: str = ""


class CatalogPublisher(BaseModel):
    """Publisher row as the API serves it: raw fields plus tags."""

    publisher: Publisher
    tags: PublisherTags


class CatalogPersona(BaseModel):
    persona: Persona
    tags: PersonaTags
