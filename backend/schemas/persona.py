"""Stage 3: which shoppers to talk to"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.catalog import PersonaId


class PersonaScore(BaseModel):
    persona_id: str
    score: int
    affinity: int
    values: int
    price: int
    reach: int
    conflicts: list[str]       # positioning traits this persona dislikes that the brand has
    reach_publishers: list[str]
    detail: str


class PersonaPickDraft(BaseModel):
    persona_id: PersonaId
    why_plausible: str = Field(description="Two sentences max, citing the brief and persona fields")
    lean_into: list[str] = Field(description="Messaging to use, from the persona's preferences")
    avoid: list[str] = Field(description="Messaging to avoid for this persona and this brand")
    ad_angle: str = Field(
        description="The single idea this persona's ad should lead with. Every pick's angle must "
        "be clearly different from the others"
    )
    confidence: Literal["high", "medium", "low"]


class PersonaSelectionDraft(BaseModel):
    picks: list[PersonaPickDraft]
    skipped_note: str = Field(
        description="If fewer than 3 are genuinely plausible, say why instead of padding; else empty"
    )


class PersonaPick(BaseModel):
    persona_id: str
    name: str
    score: int
    why_plausible: str
    lean_into: list[str]
    avoid: list[str]
    ad_angle: str = ""
    confidence: Literal["high", "medium", "low"]
    reached_via: list[str]
    conflicts: list[str]


class PersonaPlan(BaseModel):
    picks: list[PersonaPick]
    candidates: list[PersonaScore]
    skipped_note: str | None
