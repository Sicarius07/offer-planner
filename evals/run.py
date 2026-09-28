"""Golden-set evals (make eval, N=3 for stability)

Deterministic checks on the structured output, a grounding check on ad copy, and rank
stability across repeats. Writes a markdown report to evals/reports/.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import time
from datetime import datetime
from pathlib import Path

import yaml

from backend import catalog
from backend.pipeline.run import run_plan
from backend.schemas.events import PlanRequest

HERE = Path(__file__).parent


def collect(events) -> dict:
    out: dict = {"creatives": {}, "errors": []}
    for e in events:
        if e.type == "profile":
            out["profile"] = e.profile
        elif e.type == "publishers":
            out["publishers"] = e.plan
        elif e.type == "personas":
            out["personas"] = e.plan
        elif e.type == "creative":
            out["creatives"][e.creative.persona_id] = e.creative
        elif e.type == "error":
            out["errors"].append(e.message)
        elif e.type == "done":
            out["done"] = e
        elif e.type == "needs_input":
            out["needs_input"] = e
    return out


def check(r: dict, exp: dict) -> list[tuple[str, bool, str]]:
    res: list[tuple[str, bool, str]] = []
    p = r.get("profile")
    pubs = r.get("publishers")
    pers = r.get("personas")
    add = lambda name, ok, detail="": res.append((name, bool(ok), detail))  # noqa: E731

    if p is None:
        return [("profile produced", False, "; ".join(r["errors"]))]
    if "clarity" in exp:
        add("clarity", p.clarity in exp["clarity"], p.clarity)
    if "offering_type" in exp:
        add("offering_type", p.offering_type == exp["offering_type"], p.offering_type)
    if "gender" in exp:
        add("gender", p.gender.value == exp["gender"], p.gender.value)
    if "first_order_min" in exp:
        v = p.first_order_value_usd.value
        add("first order value", v >= exp["first_order_min"], f"${v:,.0f}")
    if "positioning_includes" in exp:
        add("positioning", set(exp["positioning_includes"]) <= set(p.positioning), ",".join(p.positioning))
    if "min_questions" in exp:
        add("clarifying questions", len(p.clarifying_questions) >= exp["min_questions"], str(len(p.clarifying_questions)))
    add("no invented quotes", not p.dropped_quotes, "; ".join(p.dropped_quotes))

    if pubs:
        excl = {x.publisher_id: x for x in pubs.excluded}
        rec = {x.publisher_id for x in pubs.recommended}
        ok_ids = rec | {x.publisher_id for x in pubs.test}
        for pid in exp.get("exclude_as_competitor", []):
            x = excl.get(pid)
            add(f"competitor excluded {pid}", x is not None and x.exclusion_reason == "competitor",
                x.exclusion_reason if x else "not excluded")
        everyone = {x.publisher_id: x for x in pubs.recommended + pubs.test + pubs.excluded}
        for pid in exp.get("conflict_flagged", []):
            x = everyone.get(pid)
            add(f"conflict flagged {pid}", x is not None and (x.exclusion_reason == "competitor" or x.adjacent_conflict))
        for pid in exp.get("must_not_recommend", []):
            add(f"not recommended {pid}", pid not in rec)
        if "recommend_or_test_any" in exp:
            add("key publisher in plan", ok_ids & set(exp["recommend_or_test_any"]), ",".join(sorted(ok_ids)))
        if "max_recommended" in exp:
            add("max recommended", len(rec) <= exp["max_recommended"], str(len(rec)))
    elif any(k in exp for k in ("exclude_as_competitor", "recommend_or_test_any")) and p.clarity != "unusable":
        add("publishers produced", False)

    if pers:
        ids = {x.persona_id for x in pers.picks}
        if "personas_include_any" in exp:
            add("persona included", ids & set(exp["personas_include_any"]), ",".join(sorted(ids)))
        for pid in exp.get("personas_exclude", []):
            add(f"persona not picked {pid}", pid not in ids)
        add("3-5 personas or explained", 3 <= len(ids) <= 5 or bool(pers.skipped_note), str(len(ids)))

    cards = list(r["creatives"].values())
    if cards:
        text = " ".join(f"{c.headline} {c.body} {c.cta}".lower() for c in cards)
        bad = [w for w in exp.get("creative_must_not_contain", []) if w.lower() in text]
        add("no forbidden claims", not bad, ",".join(bad))
        brief = p.brief.lower()
        ungrounded = [u.source_quote for c in cards for u in c.claims_used
                      if u.source_quote.lower().strip(" .\"'") not in brief]
        add("claims trace to brief", not ungrounded, "; ".join(ungrounded[:3]))
        add("no ad flagged", all(c.status != "flagged" for c in cards),
            ",".join(c.persona_id for c in cards if c.status == "flagged"))
    add("no stage errors", not r["errors"], "; ".join(r["errors"])[:200])
    return res


def kendall_tau(a: list[str], b: list[str]) -> float:
    common = [x for x in a if x in b]
    if len(common) < 2:
        return 1.0
    pos = {x: i for i, x in enumerate(b)}
    conc = disc = 0
    for x, y in itertools.combinations(common, 2):
        s = (pos[x] - pos[y])
        if s < 0:
            conc += 1
        else:
            disc += 1
    return (conc - disc) / (conc + disc)


def ranking(r: dict) -> list[str]:
    p = r.get("publishers")
    return [x.publisher_id for x in (p.recommended + p.test + p.excluded)] if p else []


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--model")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--save-cache", action="store_true",
                    help="also save sample runs (first repeat) as the UI's instant-replay cache")
    args = ap.parse_args()

    cases = yaml.safe_load((HERE / "golden.yaml").read_text())
    briefs = catalog.example_briefs()
    for c in cases:
        if "brief" not in c:
            c["brief"] = briefs[int(c["id"][2:]) - 1]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]

    sem = asyncio.Semaphore(4)

    async def run_case(c, k):
        async with sem:
            evs = [e async for e in run_plan(PlanRequest(brief=c["brief"], model=args.model))]
            if args.save_cache and k == 0 and c["id"].startswith("ex"):
                from backend import config
                from backend.main import CachedRun
                config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (config.CACHE_DIR / f"{c['id']}.json").write_text(
                    CachedRun(id=c["id"], brief=c["brief"], events=evs).model_dump_json(indent=1))
            return c["id"], k, collect(evs)

    t = time.time()
    results = await asyncio.gather(*(run_case(c, k) for c in cases for k in range(args.repeats)))
    by_case: dict[str, list[dict]] = {}
    for cid, _, r in results:
        by_case.setdefault(cid, []).append(r)

    lines = [f"# Eval report {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Model: {args.model or 'default per stage'}; repeats: {args.repeats}; "
             f"wall time {time.time() - t:.0f}s", "",
             "| case | pass | failed checks | τ (rank stability) | cost | time |", "|---|---|---|---|---|---|"]
    total = passed = 0
    cost = 0.0
    raw = {}
    for c in cases:
        runs = by_case[c["id"]]
        fails: list[str] = []
        n_ok = n = 0
        for r in runs:
            for name, ok, detail in check(r, c.get("expect", {})):
                n += 1
                n_ok += ok
                if not ok:
                    fails.append(f"{name} ({detail})" if detail else name)
        taus = [kendall_tau(ranking(a), ranking(b)) for a, b in itertools.combinations(runs, 2)]
        tau = f"{sum(taus) / len(taus):.2f}" if taus else "—"
        c_cost = sum(r["done"].cost_usd for r in runs if "done" in r)
        c_ms = sum(r["done"].total_ms for r in runs if "done" in r) / max(1, len(runs))
        cost += c_cost
        total += n
        passed += n_ok
        lines.append(f"| {c['id']} | {n_ok}/{n} | {'<br>'.join(sorted(set(fails)))[:400] or ''} | {tau} | "
                     f"${c_cost:.3f} | {c_ms / 1000:.0f}s |")
        raw[c["id"]] = [{"ranking": ranking(r), "personas": [p.persona_id for p in r["personas"].picks] if r.get("personas") else [],
                         "errors": r["errors"]} for r in runs]
    lines += ["", f"**{passed}/{total} checks passed ({100 * passed / max(1, total):.0f}%). Total cost ${cost:.2f}.**"]
    report = "\n".join(lines)
    out = HERE / "reports" / f"{datetime.now():%Y%m%d-%H%M}.md"
    out.write_text(report)
    (HERE / "reports" / "latest.json").write_text(json.dumps(raw, indent=1))
    print(report)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
