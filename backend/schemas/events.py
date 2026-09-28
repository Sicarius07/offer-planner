"""Server-sent events for POST /api/plan. The frontend state is a reducer over these"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from backend.schemas.campaign import CampaignConfig
from backend.schemas.creative import Creative
from backend.schemas.persona import PersonaPlan
from backend.schemas.profile import AdvertiserProfile, ClarifyingQuestion
from backend.schemas.publisher import PublisherPlan

StageName = Literal["understand", "publishers", "personas", "creative", "campaign"]


class PlanRequest(BaseModel):
    brief: str
    monthly_budget_usd: float | None = None
    flight_days: int | None = None
    model: str | None = None
    force: bool = Field(False, description="Draft even if the brief is too vague")
    allow_competitors: bool = Field(
        False, description="Flag publishers that sell the same products instead of excluding them"
    )


class StageTrace(BaseModel):
    stage: str
    name: str                 # e.g. "creative:persona_004"
    model: str | None = None
    prompt: str | None = None
    prompt_version: str | None = None
    ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    retries: int = 0
    ok: bool = True
    error: str | None = None


class StageEvent(BaseModel):
    type: Literal["stage"] = "stage"
    stage: StageName
    status: Literal["started", "done", "failed", "skipped"]
    ms: int | None = None


class ProfileEvent(BaseModel):
    type: Literal["profile"] = "profile"
    profile: AdvertiserProfile


class NeedsInputEvent(BaseModel):
    type: Literal["needs_input"] = "needs_input"
    reason: str
    questions: list[ClarifyingQuestion]


class PublishersEvent(BaseModel):
    type: Literal["publishers"] = "publishers"
    plan: PublisherPlan


class PersonasEvent(BaseModel):
    type: Literal["personas"] = "personas"
    plan: PersonaPlan


class CreativeEvent(BaseModel):
    type: Literal["creative"] = "creative"
    creative: Creative


class ConfigEvent(BaseModel):
    type: Literal["config"] = "config"
    config: CampaignConfig


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    run_id: str
    total_ms: int
    cost_usd: float
    trace: list[StageTrace]


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    stage: str
    message: str
    retryable: bool = True


PlanEvent = Annotated[
    StageEvent | ProfileEvent | NeedsInputEvent | PublishersEvent | PersonasEvent | CreativeEvent | ConfigEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]
