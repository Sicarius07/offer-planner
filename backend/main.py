"""HTTP layer. Thin on purpose: routes, SSE framing, rate limiting, static files."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import catalog, config
from backend.pipeline.run import run_plan
from backend.schemas.catalog import CatalogPersona, CatalogPublisher
from backend.schemas.events import PlanEvent, PlanRequest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

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


class Example(BaseModel):
    id: str
    brief: str
    cached: bool


class CachedRun(BaseModel):
    id: str
    brief: str
    events: list[PlanEvent]


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


@app.get("/api/catalog", response_model=Catalog)
def get_catalog() -> Catalog:
    pubs, ptags = catalog.publishers(), catalog.publisher_tags()
    pers, rtags = catalog.personas(), catalog.persona_tags()
    return Catalog(
        publishers=[CatalogPublisher(publisher=pubs[i], tags=ptags[i]) for i in pubs],
        personas=[CatalogPersona(persona=pers[i], tags=rtags[i]) for i in pers],
    )


@app.post("/api/plan", response_class=StreamingResponse,
          responses={200: {"content": {"text/event-stream": {}}}})
async def plan(req: PlanRequest, request: Request) -> StreamingResponse:
    _rate_limit(_client_ip(request))
    if req.model and req.model not in {m["id"] for m in config.SELECTABLE_MODELS}:
        raise HTTPException(400, f"Unknown model {req.model}")

    async def stream():
        agen = run_plan(req).__aiter__()
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
