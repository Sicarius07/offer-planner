# Offer Planner

Type a one-line business description and get a launchable Disco campaign: publishers ranked with reasons (and why the others were excluded), 3–5 personas with their reasoning, one reviewed ad per persona, and a campaign config you can download as JSON. Results stream in stage by stage. The 15 sample briefs are pre-recorded, so they replay instantly without spending tokens.

**Run it:** `cp .env.example .env` and add `ANTHROPIC_API_KEY`, then `make start` and open http://localhost:8000. Other targets: `make dev` (hot reload, UI on :5173), `make test` (49 tests, no network) and `make eval` (golden set, `N=3` for stability). All prompts are in `prompts/`.

## How it works

A fixed async DAG (`backend/pipeline/run.py`), with a FastAPI backend streaming server-sent events to a React UI:

```
understand ─┬─ score publishers (code) ─ review (LLM) ──────────────────────────┐
            └─ score personas (code) ─ pick (LLM) ─ write ×N ─ critique ─ rewrite ┴─ config (code) ─ launch summary (LLM)
```

- **Said vs. filled in.** Every profile attribute is marked stated, inferred or assumed, with a quote from the brief. Code checks that each quote really appears in the brief and downgrades the attribute if not. The UI shows the difference, and the config carries it through (an assumed price means "confirm before launch").
- **Code scores, the LLM judges, code enforces.** Code gives every publisher and persona a transparent tag-based score. The LLM reviews each one field by field and decides the final tier. A change counts only with a reason and a quote that code verifies. Competitors code finds stay excluded, and a B2B brief excludes everything. The model can flag a missed competitor, or dispute one, which sends the plan to a person.
- **Ads can only claim what the brief says.** The critique checks five points. A failing ad is rewritten once; if it fails again it's paused, not shipped.
- **Failure policy.** If a stage the plan can't do without fails, the run stops rather than showing a stand-in that looks finished. The one exception is the publisher review: the plan falls back to the computed tiers and is marked for human review.

## Why the config looks the way it does

Advertisers pay per conversion, so the bid is a **target CPA**: first-order value × an allowable ratio set by business model (0.60 subscription, 0.30 one-time), plus a max for the learning period. Core placements split the budget by fit², with caps; 15% goes to tests, each with a hypothesis, a risk and a promote-or-stop rule. Each placement runs only the ads whose persona fits its shoppers. Also included: competitor exclusions, frequency cap, attribution and holdout, and a `review` block (confidence, assumptions, warnings) so a person can approve or bounce the draft. **Every number is computed by code** and unit-tested. The one LLM step at the end writes a short launch summary; it can't change the config, and any number it states must already be in it.

## Hard vs. easy

- **Easy:** calling the model, schemas, streaming, the UI.
- **Hard:** knowing when the output is *wrong*.
  - Getting a model to stop promoting everything with a plausible story: my first version made 46 tier moves across 18 briefs, 43 of them upward. Evidence gates didn't help (a quote can always be found). A prompt that has the model evaluate each field and check each move against known failure modes did.
  - Not fooling yourself: my first prompts contained phrases from the sample briefs, so the evals partly graded memorisation. The prompts now use unrelated examples, and the eval set includes held-out briefs.
- **Where the real engineering lives:** the contract between code and model. Decide what code guarantees, what the model decides, how each model decision is verified, and what happens when a stage fails.

## Cut, on purpose

- No accounts, saved plans or plan editing. It's a planning tool, not a campaign manager.
- No real performance data, so the scoring weights and CPA ratios are reasoned defaults, not fitted values.
- Anthropic only. The provider interface is abstract; a second provider can wait until the first is stable.
- Personas are picked in parallel with the publisher review, which saves about a minute (the review is the slowest step). As a result, a persona can get an ad that no placement serves; the config warns about it instead of preventing it.

## Next week

1. **Better golden data:** go through the catalog and the outputs myself, case by case, to write more accurate expectations and add more held-out briefs. The current golden set is my quick judgment, not ground truth.
2. **Measure instability:** run each case 3× and track tier and persona agreement; some borderline calls still differ from run to run.
3. **User feedback:** let advertisers approve, reject or edit each publisher, persona and ad in the UI, and log why. Each rejection becomes an eval case.
4. **A self-improvement loop for the prompts:** a model reads eval failures, user feedback and Langfuse traces and proposes prompt changes; a change is kept only if it improves the held-out briefs without regressing the rest.
5. **Close the persona/publisher loop:** pick personas against the final plan so every ad has somewhere to run.
6. **Richer ads:** product image, brand name and logo, approved offer terms (first-order discount, free shipping) and a landing URL, in real slot sizes, with the critique checking all of them.
7. **Learn from results:** feed test-placement outcomes back into the scoring weights and use real margin/LTV for the CPA ratio.
8. **Cost and latency:** a run is about $0.55 and 85 s on Opus 5; the publisher review is half of that. Try cheaper models for critique and summary, and cache prompts.
