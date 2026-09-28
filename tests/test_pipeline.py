"""End-to-end orchestrator test with a fake provider: event order, code enforcement over
LLM output, fallbacks, and the rewrite loop. No network."""

from __future__ import annotations

import pytest

from backend.llm import registry
from backend.llm.base import LLMOutputInvalid, LLMResult, Usage
from backend.pipeline.run import run_plan
from backend.pipeline.scoring import score_publishers
from backend.schemas.campaign import LaunchSummaryDraft
from backend.schemas.creative import CreativeDraft, CritiqueDraft
from backend.schemas.events import PlanRequest
from backend.schemas.persona import PersonaSelectionDraft
from backend.schemas.profile import ProfileDraft
from backend.schemas.publisher import RerankDraft

BRIEF = ("We sell premium dog food for senior dogs, targeting owners who care about joint "
         "health and longevity. Grain-free, vet-formulated, subscription-based.")


def a(value, source="stated", quote="", note=""):
    return {"value": value, "source": source, "quote": quote, "note": note}


PROFILE = ProfileDraft.model_validate({
    "business_summary": "Premium subscription dog food for senior dogs.",
    "brand_name": "", "offering_type": "consumer_product",
    "product": a("senior dog food", quote="dog food for senior dogs"),
    "sells": ["pet_food"], "competes_with": ["pet_food", "pet_treats"],
    "interests": [{"tag": "pets", "strength": "primary"}, {"tag": "pet_health", "strength": "primary"}],
    "values": [{"tag": "science_backed", "strength": "primary"}, {"tag": "premium_quality", "strength": "primary"}],
    "occasions": [{"tag": "replenishment", "strength": "primary"}],
    "positioning": [],
    "price_tier": a("premium", quote="premium"),
    "first_order_value_usd": a(60.0, "assumed", note="typical premium bag"),
    "gender": a("any", "assumed"),
    "age_range": a("", "assumed"),
    "audience": a("owners who care about joint health", "stated",
                  quote="owners who care about joint health"),
    # An invented quote: must be dropped and downgraded.
    "business_model": a("subscription", "stated", quote="subscription-first, cancel anytime"),
    "claims": [{"claim": "vet-formulated", "quote": "vet-formulated"},
               {"claim": "vet-recommended", "quote": "recommended by vets"}],
    "clarity": "clear", "clarity_reason": "Product, audience and model are stated.",
    "assumptions": ["First order around $60."], "clarifying_questions": [],
})


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls: list[str] = []
        self.critique_calls = 0

    async def generate_structured(self, *, system, user, schema, model, effort="medium", max_tokens=16000):
        self.calls.append(schema.__name__)
        if schema is ProfileDraft:
            out = PROFILE
        elif schema is RerankDraft:
            out = RerankDraft.model_validate({"summary": "Pet competitors excluded.", "offering_type_doubt": "", "judgments": [
                # Tries to rescue a competitor, and to move a tier on an invented quote: code refuses both.
                {"publisher_id": "pub_007", "tier": "recommended", "tier_reason": "great fit",
                 "competitor_call": "agree", "competitor_reason": "",
                 "rationale": "Pawline is ideal.", "evidence": [{"field": "notes", "quote": "responsive to premium positioning"}], "risk": ""},
                {"publisher_id": "pub_018", "tier": "recommended", "tier_reason": "dogs as family",
                 "competitor_call": "agree", "competitor_reason": "",
                 "rationale": "Tailcrate reaches dog lovers.", "evidence": [{"field": "notes", "quote": "an invented note"}], "risk": ""},
                # Off-category by tags, but its notes back a move to test.
                {"publisher_id": "pub_008", "tier": "test", "tier_reason": "clean-ingredient shoppers buy premium pet food too",
                 "competitor_call": "agree", "competitor_reason": "",
                 "rationale": "Pantrygood shoppers respond to clean ingredients.",
                 "evidence": [{"field": "notes", "quote": "Responsive to clean-ingredient"}], "risk": ""},
            ]})
        elif schema is PersonaSelectionDraft:
            out = PersonaSelectionDraft.model_validate({"skipped_note": "", "picks": [
                {"persona_id": pid, "why_plausible": "fits", "lean_into": ["x"], "avoid": ["y"], "ad_angle": f"angle {pid}", "confidence": "high"}
                for pid in ("persona_004", "persona_002", "persona_001", "persona_004")
            ]})
        elif schema is CreativeDraft:
            persona = user.split("<persona>")[1][:200]
            bodies = {
                "The Pet Parent": "Grain-free, vet-formulated food made for senior dogs.",
                "The Busy Parent": "Dinner for the old dog, delivered on a schedule you set.",
                "The Wellness Optimizer": "Joint health nutrition with a label you can actually read.",
            }
            body = next(v for k, v in bodies.items() if k in persona)
            if "revision_request" in user:
                body = "Longevity starts in the bowl: food built around aging joints."
            out = CreativeDraft.model_validate({
                "angle": "a", "headline": "Joint support for older dogs",
                "body": body,
                "cta": "See the food", "claims_used": [], "offer_suggestion": "", "tone_notes": "",
            })
        elif schema is CritiqueDraft:
            self.critique_calls += 1
            import json
            cards = json.loads(user.split("<cards>")[1].split("</cards>")[0])
            reviews = []
            for c in cards:
                fail = self.critique_calls == 1 and c["persona_id"] == "persona_004"
                reviews.append({"persona_id": c["persona_id"], "fix": "be specific" if fail else "",
                                "checks": [{"name": "grounded", "passed": not fail, "reason": "r"}]})
            out = CritiqueDraft.model_validate({"reviews": reviews})
        elif schema is LaunchSummaryDraft:
            out = LaunchSummaryDraft.model_validate({
                "summary": "Most of the budget goes to Tailcrate. It should bring in 9,999 customers.",
                "uncertainties": ["The order value is assumed."],
                "questions": ["Is $60 your typical first order?", "Could you offer 37% off?"],
            })
        else:
            raise AssertionError(schema)
        return LLMResult(parsed=out, model=model, usage=Usage(10, 10), cost_usd=0.001,
                         latency_ms=1, stop_reason="end_turn")


@pytest.fixture
def fake(monkeypatch):
    p = FakeProvider()
    monkeypatch.setitem(registry._FACTORIES, "fake", lambda: p)
    registry._instances.pop("fake", None)
    return p


async def collect(req):
    return [e async for e in run_plan(req)]


async def test_full_run_event_sequence_and_enforcement(fake):
    events = await collect(PlanRequest(brief=BRIEF, model="fake:test"))
    types = [e.type for e in events]
    assert types[0] == "stage" and types[-1] == "done"
    for t in ("profile", "publishers", "personas", "creative", "config"):
        assert t in types, t
    assert "error" not in types

    profile = next(e for e in events if e.type == "profile").profile
    # Invented quote → downgraded; invented claim → dropped.
    assert profile.business_model.source == "assumed"
    assert [c.claim for c in profile.claims] == ["vet-formulated"]
    assert "recommended by vets" in profile.dropped_quotes
    assert profile.audience.evidence.start == BRIEF.index("owners who care")

    plan = next(e for e in events if e.type == "publishers").plan
    pawline = next(r for r in plan.excluded if r.publisher_id == "pub_007")
    assert pawline.exclusion_reason == "competitor" and pawline.tier_reason is None
    tailcrate = next(r for r in plan.recommended + plan.test + plan.excluded if r.publisher_id == "pub_018")
    assert tailcrate.tier == "test" and tailcrate.tier_reason is None  # no checked quote, no move
    assert tailcrate.evidence == []               # invented quote dropped
    pantry = next(r for r in plan.test if r.publisher_id == "pub_008")
    assert pantry.computed_tier == "excluded" and pantry.exclusion_reason is None
    assert pantry.fit == 50 and pantry.base_fit < 50

    personas = next(e for e in events if e.type == "personas").plan
    assert [p.persona_id for p in personas.picks] == ["persona_004", "persona_002", "persona_001"]

    final = {}
    for e in events:
        if e.type == "creative":
            final[e.creative.persona_id] = e.creative
    assert final["persona_004"].status == "revised"
    assert final["persona_004"].revision_of is not None
    assert final["persona_002"].status == "passed"

    configs = [e.config for e in events if e.type == "config"]
    assert configs[0].review.launch_summary is None  # the config streams before its summary
    cfg = configs[-1]
    assert sum(p.allocation_pct for p in cfg.placements) == pytest.approx(100, abs=0.2)
    # Numbers the config doesn't contain are dropped from the summary.
    ls = cfg.review.launch_summary
    assert ls.summary == "Most of the budget goes to Tailcrate."
    assert ls.questions == ["Is $60 your typical first order?"]
    for p in cfg.placements:
        assert p.creative_ids
        assert (p.test_plan is not None) == (p.role == "test")
    # The value survives the downgrade; only its source changes (and the UI shows it amber).
    assert cfg.bid_strategy.allowable_cpa_ratio == 0.60
    done = events[-1]
    assert done.cost_usd > 0 and any(t.name == "understand_brief" for t in done.trace)


async def test_unusable_brief_stops_with_questions(fake, monkeypatch):
    vague = ProfileDraft.model_validate({**PROFILE.model_dump(), "clarity": "unusable", "clarifying_questions": [
        {"question": "What do you sell?", "why": "everything depends on it", "suggested_answers": ["A", "B"]}]})

    async def gen(**kw):
        return LLMResult(parsed=vague, model="m", usage=Usage(), cost_usd=0, latency_ms=1, stop_reason="end_turn")
    monkeypatch.setattr(fake, "generate_structured", gen)
    events = await collect(PlanRequest(brief="idk just try it", model="fake:test"))
    types = [e.type for e in events]
    assert "needs_input" in types and "publishers" not in types and types[-1] == "done"


async def test_rerank_failure_falls_back_to_scores(fake, monkeypatch):
    orig = fake.generate_structured

    async def gen(**kw):
        if kw["schema"] is RerankDraft:
            raise LLMOutputInvalid("bad")
        return await orig(**kw)
    monkeypatch.setattr(fake, "generate_structured", gen)
    events = await collect(PlanRequest(brief=BRIEF, model="fake:test"))
    assert any(e.type == "error" and e.stage == "publishers" for e in events)
    plan = next(e for e in events if e.type == "publishers").plan
    assert not plan.explained
    cfg = next(e for e in events if e.type == "config").config
    assert cfg.review.needs_human_review
    assert any("Publisher review was unavailable" in w for w in cfg.review.warnings)


def _failing(fake, monkeypatch, schema):
    orig = fake.generate_structured

    async def gen(**kw):
        if kw["schema"] is schema:
            raise LLMOutputInvalid("bad")
        return await orig(**kw)
    monkeypatch.setattr(fake, "generate_structured", gen)


def _stops(events, failed_stage):
    types = [e.type for e in events]
    assert "config" not in types and types[-1] == "done"
    assert any(e.type == "stage" and e.stage == failed_stage and e.status == "failed" for e in events)
    assert any(e.type == "stage" and e.stage == "campaign" and e.status == "skipped" for e in events)
    assert any(e.type == "error" and e.stage == "run" and "Nothing was drafted" in e.message for e in events)


async def test_persona_failure_stops_the_run(fake, monkeypatch):
    _failing(fake, monkeypatch, PersonaSelectionDraft)
    events = await collect(PlanRequest(brief=BRIEF, model="fake:test"))
    _stops(events, "personas")
    assert not any(e.type == "creative" for e in events)


async def test_review_failure_stops_the_run(fake, monkeypatch):
    _failing(fake, monkeypatch, CritiqueDraft)
    events = await collect(PlanRequest(brief=BRIEF, model="fake:test"))
    _stops(events, "creative")


async def test_no_ads_written_stops_the_run(fake, monkeypatch):
    _failing(fake, monkeypatch, CreativeDraft)
    events = await collect(PlanRequest(brief=BRIEF, model="fake:test"))
    _stops(events, "creative")


async def test_empty_brief_rejected(fake):
    events = await collect(PlanRequest(brief="   ", model="fake:test"))
    assert any(e.type == "error" and not e.retryable for e in events)


def test_unknown_tags_are_dropped_not_trusted():
    from backend.pipeline.understand import to_profile
    d = PROFILE.model_copy(update={
        "interests": [*PROFILE.interests, {"tag": "crypto", "strength": "primary"}],
        "sells": ["pet_food", "dog_chow"],
    })
    d = ProfileDraft.model_validate(d.model_dump())
    p = to_profile(d, BRIEF)
    assert "crypto" not in p.interests and "crypto" in p.dropped_tags
    assert p.sells == ["pet_food"] and "dog_chow" in p.dropped_tags


def test_code_review_catches_claims_not_in_brief():
    from backend.pipeline.creative import code_issues
    from backend.schemas.creative import ClaimUse, Creative
    c = Creative(creative_id="x", persona_id="persona_004", persona_name="P", angle="a",
                 headline="h", body="b", cta="c", tone_notes="", status="draft", offer_suggestion=None,
                 claims_used=[ClaimUse(claim="vet-formulated", source_quote="vet-formulated"),
                              ClaimUse(claim="vet-recommended", source_quote="recommended by vets")])
    issues = code_issues(c, [c], BRIEF)
    assert len(issues) == 1 and "recommended by vets" in issues[0]


def test_guard_keeps_the_answers_block_as_lines():
    from backend.pipeline.understand import guard
    raw = "We sell   candles.\n\n\n\nAnswers to your questions:\n-  What do you sell?  Soy candles \n- Who buys? Women"
    assert guard(raw) == ("We sell candles.\n\nAnswers to your questions:\n"
                          "- What do you sell? Soy candles\n- Who buys? Women")


async def test_audience_work_runs_even_when_code_excludes_every_publisher(fake, monkeypatch):
    from backend.pipeline import run as run_mod

    def nothing_fits(profile, allow):
        return [s.model_copy(update={"tier": "excluded", "exclusion_reason": s.exclusion_reason or "weak_fit"})
                for s in score_publishers(profile, allow)]
    monkeypatch.setattr(run_mod, "score_publishers", nothing_fits)
    events = await collect(PlanRequest(brief=BRIEF, model="fake:test"))
    types = [e.type for e in events]
    assert "personas" in types and "creative" in types


async def test_launch_summary_failure_keeps_the_config(fake, monkeypatch):
    _failing(fake, monkeypatch, LaunchSummaryDraft)
    events = await collect(PlanRequest(brief=BRIEF, model="fake:test"))
    cfg = [e for e in events if e.type == "config"][-1].config
    assert cfg.placements and cfg.review.launch_summary is None
    assert any(e.type == "error" and "launch summary" in e.message for e in events)
    assert any(e.type == "stage" and e.stage == "campaign" and e.status == "done" for e in events)
