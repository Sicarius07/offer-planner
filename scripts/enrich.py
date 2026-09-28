"""OFFLINE: tag the catalog with the controlled vocabulary (make enrich).

Writes data/enriched/*.generated.json and prints a diff against the reviewed files that the
app actually loads. A person reviews the diff and copies over what's right. At 20 rows that
review is minutes; at 20k it becomes sampling + drift alerts.
"""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from pydantic import BaseModel

from backend import catalog, taxonomy, trace
from backend.config import DATA_DIR
from backend.llm.client import generate
from backend.schemas.catalog import PriceTier
from backend.taxonomy import InterestTag, OccasionTag, PositioningTag, ProductTag, ValueTag

Level = Literal["strong", "moderate", "light"]
W = {"strong": 1.0, "moderate": 0.6, "light": 0.3}


class I(BaseModel):
    tag: InterestTag
    strength: Level


class V(BaseModel):
    tag: ValueTag
    strength: Level
    evidence: str


class O(BaseModel):
    tag: OccasionTag
    strength: Level


class PublisherTagsDraft(BaseModel):
    interests: list[I]
    values: list[V]
    occasions: list[O]
    sells: list[ProductTag]


class PersonaTagsDraft(BaseModel):
    interests: list[I]
    values: list[V]
    occasions: list[O]
    price_tiers: list[PriceTier]
    dislikes: list[PositioningTag]


VOCAB = {k: taxonomy.describe(k) for k in ("interests", "values", "occasions", "positioning", "products")}


async def tag_publisher(pub) -> dict:
    d = await generate(stage="enrich", name=f"enrich:{pub.id}", prompt="offline/enrich_publisher",
                       schema=PublisherTagsDraft, variables={**VOCAB, "record": pub.model_dump_json(indent=1)})
    return {"id": pub.id, "interests": {x.tag: W[x.strength] for x in d.interests},
            "values": {x.tag: W[x.strength] for x in d.values},
            "occasions": {x.tag: W[x.strength] for x in d.occasions}, "sells": d.sells,
            "evidence": {x.tag: x.evidence for x in d.values}, "enrichment_version": "v1-generated"}


async def tag_persona(p) -> dict:
    d = await generate(stage="enrich", name=f"enrich:{p.id}", prompt="offline/enrich_persona",
                       schema=PersonaTagsDraft, variables={**VOCAB, "record": p.model_dump_json(indent=1)})
    return {"id": p.id, "interests": {x.tag: W[x.strength] for x in d.interests},
            "values": {x.tag: W[x.strength] for x in d.values},
            "occasions": {x.tag: W[x.strength] for x in d.occasions},
            "price_tiers": d.price_tiers, "dislikes": d.dislikes, "enrichment_version": "v1-generated"}


def diff(name: str, generated: list[dict]) -> None:
    reviewed = {r["id"]: r for r in json.loads((DATA_DIR / f"enriched/{name}.json").read_text())}
    for g in generated:
        r = reviewed.get(g["id"], {})
        for field in ("interests", "values", "sells", "dislikes", "price_tiers"):
            if field not in g:
                continue
            a, b = set(r.get(field, [])), set(g[field])
            if a != b:
                print(f"{g['id']} {field}: +{sorted(b - a)} -{sorted(a - b)}")


async def main() -> None:
    sem = asyncio.Semaphore(6)

    async def lim(coro):
        async with sem:
            return await coro

    with trace.collect() as entries:
        pubs = await asyncio.gather(*(lim(tag_publisher(p)) for p in catalog.publishers().values()))
        pers = await asyncio.gather(*(lim(tag_persona(p)) for p in catalog.personas().values()))
    (DATA_DIR / "enriched/publishers.generated.json").write_text(json.dumps(pubs, indent=2))
    (DATA_DIR / "enriched/personas.generated.json").write_text(json.dumps(pers, indent=2))
    print("── differences vs reviewed ──")
    diff("publishers", pubs)
    diff("personas", pers)
    print(f"cost ${sum(e.cost_usd for e in entries):.3f}")


if __name__ == "__main__":
    asyncio.run(main())
