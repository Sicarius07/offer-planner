"""Every tunable number in one place. Scoring weights, thresholds, models per stage.

These are hand-set for the prototype; in production the scoring weights would be learned
from conversion data.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
PROMPTS_DIR = ROOT / "prompts"
CACHE_DIR = DATA_DIR / "cache" / "examples"

# ── Models ────────────────────────────────────────────────────────────────────
# "provider:model". Each stage can use a different model; the UI can override all of them.
DEFAULT_MODEL = os.getenv("MODEL_DEFAULT", "anthropic:claude-opus-5")
STAGE_MODELS: dict[str, str] = {
    "understand": os.getenv("MODEL_UNDERSTAND", DEFAULT_MODEL),
    "rerank": os.getenv("MODEL_RERANK", DEFAULT_MODEL),
    "personas": os.getenv("MODEL_PERSONAS", DEFAULT_MODEL),
    "creative": os.getenv("MODEL_CREATIVE", DEFAULT_MODEL),
    "critique": os.getenv("MODEL_CRITIQUE", DEFAULT_MODEL),
    "campaign": os.getenv("MODEL_CAMPAIGN", DEFAULT_MODEL),
    "enrich": os.getenv("MODEL_ENRICH", DEFAULT_MODEL),
}
# How hard the model thinks per stage. The publisher review makes the final tier call across
# every publisher, so it gets the most; critique is a checklist.
STAGE_EFFORT: dict[str, str] = {
    "understand": "medium",
    "rerank": "high",
    "personas": "medium",
    "creative": "medium",
    "critique": "low",
    "campaign": "low",
    "enrich": "medium",
}
SELECTABLE_MODELS = [
    {"id": "anthropic:claude-opus-5", "label": "Claude Opus 5"},
    {"id": "anthropic:claude-sonnet-5", "label": "Claude Sonnet 5"},
    {"id": "anthropic:claude-haiku-4-5", "label": "Claude Haiku 4.5"},
]
# USD per million tokens, for every model in SELECTABLE_MODELS (a test enforces it).
# Output includes thinking tokens: Anthropic bills them as output and counts them in
# `output_tokens`. Input excludes cached tokens, which are billed at their own rates.
PRICING: dict[str, dict[str, float]] = {
    "claude-opus-5":    {"input": 5.0, "output": 25.0, "cache_write_5m": 6.25, "cache_write_1h": 10.0, "cache_read": 0.5},
    "claude-sonnet-5":  {"input": 3.0, "output": 15.0, "cache_write_5m": 3.75, "cache_write_1h": 6.0,  "cache_read": 0.3},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0,  "cache_write_5m": 1.25, "cache_write_1h": 2.0,  "cache_read": 0.1},
}

# ── Publisher scoring ────────────────────────────────────────────────────────
PUBLISHER_WEIGHTS = {
    "category": 0.40,
    "audience": 0.20,
    "price": 0.15,
    "values": 0.15,
    "reach": 0.10,
}
NEUTRAL_SCORE = 60          # a dimension the brief didn't specify: neither helps nor hurts much
OFF_CATEGORY_BELOW = 15     # category fit under this → excluded as irrelevant
RECOMMEND_AT = 70           # fit ≥ this → recommended
TEST_AT = 50                # fit in [TEST_AT, RECOMMEND_AT) → small test budget
PRICE_BAND = (0.5, 2.0)     # advertiser price / publisher AOV inside this band = full price fit
PRICE_FALLOFF_PER_DOUBLING = 45          # per doubling above the band: a hard sell after checkout
PRICE_FALLOFF_CHEAPER_PER_DOUBLING = 10  # per halving below it: a cheap add-on is still easy

# ── Persona scoring ──────────────────────────────────────────────────────────
PERSONA_WEIGHTS = {"affinity": 0.40, "values": 0.20, "price": 0.15, "reach": 0.25}
PERSONA_CONFLICT_PENALTY = 25   # per positioning trait the persona dislikes
PERSONAS_MIN, PERSONAS_MAX = 3, 5

# ── Campaign config ──────────────────────────────────────────────────────────
DEFAULT_MONTHLY_BUDGET_USD = 10_000
DEFAULT_FLIGHT_DAYS = 30
CPA_RATIO = {"subscription": 0.60, "mixed": 0.45, "one_time": 0.30, "unknown": 0.35}
MAX_CPA_MULTIPLIER = 1.3
LEARNING_PERIOD_DAYS = 14
TEST_TIER_SHARE = 0.15
TEST_MIN_BUDGET_USD = 250
CORE_MAX_SHARE = 0.40
CORE_MIN_SHARE = 0.05
# Rough ceiling used only to warn when a budget is large relative to a publisher's reach.
CAPACITY_CONVERSION_CEILING = 0.0005   # ≤0.05% of monthly impressions converting
FREQUENCY_CAP = {"impressions": 1, "per_days": 7}
ATTRIBUTION_WINDOW_DAYS = 7

# ── Guardrails ────────────────────────────────────────────────────────────────
MAX_BRIEF_CHARS = 1000
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "20"))
# Total spend allowed on live runs, across all users (unset = no limit). Each run holds
# RUN_RESERVE_USD up front and is charged its real cost when it finishes; a typical run is
# about $0.55. Shared across instances when Upstash Redis is configured, else per process.
SPEND_LIMIT_USD = float(os.getenv("SPEND_LIMIT_USD") or 0) or None
RUN_RESERVE_USD = 1.00
REDIS_URL = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
