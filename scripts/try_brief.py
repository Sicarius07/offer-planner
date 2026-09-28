"""Run one brief end to end and print a readable summary (dev tool).

    uv run python -m scripts.try_brief "We sell ..." [--model anthropic:claude-sonnet-5]
"""

from __future__ import annotations

import argparse
import asyncio
import time

from backend.pipeline.run import run_plan
from backend.schemas.events import PlanRequest


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("--model")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dump", help="write all events as JSON to this path")
    args = ap.parse_args()
    t = time.time()
    dumped = []
    async for e in run_plan(PlanRequest(brief=args.brief, model=args.model, force=args.force)):
        dumped.append(e.model_dump(mode="json"))
        at = f"{time.time() - t:5.1f}s"
        if e.type == "stage":
            print(at, "stage", e.stage, e.status, e.ms or "")
        elif e.type == "profile":
            p = e.profile
            print(at, "PROFILE", p.clarity, "|", p.business_summary)
            for k in ("product", "audience", "price_tier", "first_order_value_usd", "gender", "age_range", "business_model"):
                a = getattr(p, k)
                if a:
                    print(f"      {k}: {a.value} [{a.source}] {repr(a.evidence.text) if a.evidence else ''} {a.note or ''}")
            print("      sells", p.sells, "competes", p.competes_with, "positioning", p.positioning)
            print("      interests", p.interests, "values", p.values, "occasions", p.occasions)
            print("      claims", [c.claim for c in p.claims], "dropped", p.dropped_quotes)
            print("      assumptions", p.assumptions)
            print("      questions", [q.question for q in p.clarifying_questions])
        elif e.type == "publishers":
            pl = e.plan
            print(at, "PUBLISHERS", pl.summary)
            for g in ("recommended", "test", "excluded"):
                for r in getattr(pl, g):
                    moved = f" (was {r.computed_tier}: {r.tier_reason[:60]})" if r.tier_reason else ""
                    print(f"      {g[:4]} {r.name:18} {r.base_fit:>3} → {r.fit:>3} {r.exclusion_reason or ''}{moved} | {r.rationale[:110]}")
        elif e.type == "personas":
            print(at, "PERSONAS", e.plan.skipped_note or "")
            for p in e.plan.picks:
                print(f"      {p.name} ({p.confidence}) {p.why_plausible[:120]}")
        elif e.type == "creative":
            c = e.creative
            print(at, "CREATIVE", c.persona_name, c.status, "|", c.headline, "|", c.body, "|", c.cta)
            if c.critique and not c.critique.passed:
                print("      fix:", c.critique.fix)
        elif e.type == "config":
            cfg = e.config
            print(at, "CONFIG target CPA", cfg.bid_strategy.target_cpa_usd,
                  [(x.publisher_name, x.role, x.allocation_pct) for x in cfg.placements])
            print("      review", cfg.review.needs_human_review, cfg.review.warnings)
        elif e.type == "needs_input":
            print(at, "NEEDS INPUT", e.reason, [q.question for q in e.questions])
        elif e.type == "error":
            print(at, "ERROR", e.stage, e.message)
        elif e.type == "done":
            print(at, f"DONE {e.total_ms / 1000:.1f}s ${e.cost_usd:.3f}")
            for x in e.trace:
                if x.model:
                    print(f"      {x.name:32} {x.ms / 1000:5.1f}s in={x.input_tokens:>6} out={x.output_tokens:>5} ${x.cost_usd:.4f} retries={x.retries} {x.error or ''}")
    if args.dump:
        import json
        with open(args.dump, "w") as f:
            json.dump(dumped, f, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
