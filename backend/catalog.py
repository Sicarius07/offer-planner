"""Loads the data pack and the committed enrichment into memory, once"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from backend.config import DATA_DIR
from backend.schemas.catalog import Persona, PersonaTags, Publisher, PublisherTags


def _load(path: str) -> list[dict]:
    return json.loads((DATA_DIR / path).read_text())


@lru_cache
def publishers() -> dict[str, Publisher]:
    return {p["id"]: Publisher(**p) for p in _load("publishers.json")}


@lru_cache
def personas() -> dict[str, Persona]:
    return {p["id"]: Persona(**p) for p in _load("shopper_personas.json")}


@lru_cache
def publisher_tags() -> dict[str, PublisherTags]:
    tags = {t["id"]: PublisherTags(**t) for t in _load("enriched/publishers.json")}
    missing = set(publishers()) - set(tags)
    if missing:
        raise RuntimeError(f"publishers without enrichment: {sorted(missing)} (run make enrich)")
    return tags


@lru_cache
def persona_tags() -> dict[str, PersonaTags]:
    tags = {t["id"]: PersonaTags(**t) for t in _load("enriched/personas.json")}
    missing = set(personas()) - set(tags)
    if missing:
        raise RuntimeError(f"personas without enrichment: {sorted(missing)} (run make enrich)")
    return tags


def example_briefs() -> list[str]:
    lines = (DATA_DIR / "example_advertisers.txt").read_text().splitlines()
    out = []
    for line in lines:
        head, _, rest = line.partition(". ")
        if head.strip().isdigit() and rest:
            out.append(rest.strip())
    return out


# Enums of real IDs: used in LLM output schemas so the model can't invent a publisher.
PublisherId = Literal[tuple(publishers())]  # type: ignore[valid-type]
PersonaId = Literal[tuple(personas())]  # type: ignore[valid-type]
