"""HTTP layer. Thin on purpose: routes, SSE framing, rate limiting, static files."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from backend import catalog, config, credits, runs
from backend.pipeline.run import run_plan
from backend.schemas.catalog import CatalogPersona, CatalogPublisher
from backend.schemas.events import DoneEvent, PlanEvent, PlanRequest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Offer Planner", version="0.1.0")

KEEPALIVE_SECONDS = 15


# ── Models for the read-only endpoints ────────────────────────────────────────


class ModelOption(BaseModel):
    id: str
    label: str


class Meta(BaseModel):
    models: list[ModelOption]
    default_model: str
    default_monthly_budget_usd: float
    default_flight_days: int
    max_brief_chars: int
    saved_runs: bool


class Example(BaseModel):
    id: str
    brief: str
    cached: bool


class CachedRun(BaseModel):
    id: str
    brief: str
    events: list[PlanEvent]


class Credits(BaseModel):
    limit_usd: float
    spent_usd: float
    remaining_usd: float
    run_reserve_usd: float


class Catalog(BaseModel):
    publishers: list[CatalogPublisher]
    personas: list[CatalogPersona]


# ── Rate limiting (best-effort; per instance on serverless) ───────────────────

_hits: dict[str, deque[float]] = defaultdict(deque)

# Behind Vercel's proxy every request arrives from the proxy's address, so the caller's IP
# is only in X-Forwarded-For, which Vercel sets itself. Anywhere else a caller can write that
# header, so we ignore it and use the socket address.
_BEHIND_PROXY = bool(os.getenv("VERCEL"))


def _client_ip(request: Request) -> str:
    if _BEHIND_PROXY and (fwd := request.headers.get("x-forwarded-for")):
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _rate_limit(ip: str) -> None:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_HOUR:
        raise HTTPException(429, "Too many drafts from this address. Try an example, or wait an hour.")
    q.append(now)


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/meta", response_model=Meta)
def meta() -> Meta:
    return Meta(
        models=[ModelOption(**m) for m in config.SELECTABLE_MODELS],
        default_model=config.DEFAULT_MODEL,
        default_monthly_budget_usd=config.DEFAULT_MONTHLY_BUDGET_USD,
        default_flight_days=config.DEFAULT_FLIGHT_DAYS,
        max_brief_chars=config.MAX_BRIEF_CHARS,
        saved_runs=runs.enabled(),
    )


def _example_id(i: int) -> str:
    return f"ex{i + 1:02d}"


@app.get("/api/examples", response_model=list[Example])
def examples() -> list[Example]:
    return [Example(id=_example_id(i), brief=b, cached=(config.CACHE_DIR / f"{_example_id(i)}.json").exists())
            for i, b in enumerate(catalog.example_briefs())]


@app.get("/api/examples/{example_id}", response_model=CachedRun)
def example_run(example_id: str) -> CachedRun:
    path = config.CACHE_DIR / f"{example_id}.json"
    if not path.exists() or "/" in example_id:
        raise HTTPException(404, "No cached run for this example.")
    return CachedRun.model_validate_json(path.read_text())


@app.get("/api/runs/{run_id}", response_model=CachedRun)
async def saved_run(run_id: str) -> Response:
    """A finished live run, in the same shape as a cached example so the UI replays it."""
    body = await runs.load(run_id) if run_id.isalnum() else None
    if body is None:
        raise HTTPException(404, "That draft has expired or was never saved. Drafts are kept for 30 days.")
    return Response(body, media_type="application/json")


@app.get("/api/catalog", response_model=Catalog)
def get_catalog() -> Catalog:
    pubs, ptags = catalog.publishers(), catalog.publisher_tags()
    pers, rtags = catalog.personas(), catalog.persona_tags()
    return Catalog(
        publishers=[CatalogPublisher(publisher=pubs[i], tags=ptags[i]) for i in pubs],
        personas=[CatalogPersona(persona=pers[i], tags=rtags[i]) for i in pers],
    )


@app.get("/api/credits", response_model=Credits | None)
async def get_credits() -> JSONResponse:
    """How much of the live-run spending limit is left; null when there's no limit."""
    try:
        s = await credits.status()
    except credits.CreditsUnavailable:
        raise HTTPException(503, "Can't check the spending limit right now.") from None
    body = None if s is None else Credits(
        limit_usd=s[0], spent_usd=round(s[1], 2), remaining_usd=round(max(s[0] - s[1], 0), 2),
        run_reserve_usd=config.RUN_RESERVE_USD,
    ).model_dump()
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


@app.post("/api/plan", response_class=StreamingResponse,
          responses={200: {"content": {"text/event-stream": {}}}})
async def plan(req: PlanRequest, request: Request) -> StreamingResponse:
    _rate_limit(_client_ip(request))
    if req.model and req.model not in {m["id"] for m in config.SELECTABLE_MODELS}:
        raise HTTPException(400, f"Unknown model {req.model}")
    try:
        held = await credits.reserve()
    except credits.OutOfCredits as e:
        raise HTTPException(402, str(e)) from None
    except credits.CreditsUnavailable:
        raise HTTPException(503, "Can't check the spending limit right now. Try again shortly.") from None

    async def stream():
        agen = run_plan(req).__aiter__()
        seen: list[PlanEvent] = []
        pending: asyncio.Task | None = None
        try:
            while True:
                pending = pending or asyncio.ensure_future(agen.__anext__())
                done, _ = await asyncio.wait({pending}, timeout=KEEPALIVE_SECONDS)
                if not done:
                    yield ": keepalive\n\n"
                    continue
                try:
                    ev = pending.result()
                except StopAsyncIteration:
                    break
                pending = None
                seen.append(ev)
                if isinstance(ev, DoneEvent):
                    await runs.save(ev.run_id, req.brief, seen)
                    # Charge the real cost. If the user leaves before this, the hold stays.
                    try:
                        await credits.settle(held, ev.cost_usd)
                    except credits.CreditsUnavailable:
                        log.warning("couldn't settle run %s; its hold stays", ev.run_id)
                yield f"data: {ev.model_dump_json()}\n\n"
        finally:
            if pending and not pending.done():
                pending.cancel()
            await agen.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Frontend (built Vite app), when present ───────────────────────────────────
# app.frontend serves web/dist with an index.html fallback for client routes; API routes
# always win. On Vercel the files are promoted to the CDN at build time.

_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.exists():
    app.frontend("/", directory=_DIST, fallback="index.html")
