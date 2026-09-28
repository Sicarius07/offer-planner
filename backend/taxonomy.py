"""Loads data/taxonomy.yaml and exposes the tag vocabularies as runtime Literal types

Because the Literals feed the Pydantic schemas, they become enums in the JSON Schema the
model is constrained to: the LLM physically cannot emit a tag that isn't in the taxonomy
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import yaml

from backend.config import DATA_DIR


@lru_cache
def load() -> dict:
    return yaml.safe_load((DATA_DIR / "taxonomy.yaml").read_text())


_T = load()

INTERESTS: dict[str, str] = _T["interests"]
VALUES: dict[str, str] = _T["values"]
OCCASIONS: dict[str, str] = _T["occasions"]
PRODUCTS: dict[str, str] = _T["products"]
POSITIONING: dict[str, str] = _T["positioning"]

InterestTag = Literal[tuple(INTERESTS)]  # type: ignore[valid-type]
ValueTag = Literal[tuple(VALUES)]  # type: ignore[valid-type]
OccasionTag = Literal[tuple(OCCASIONS)]  # type: ignore[valid-type]
ProductTag = Literal[tuple(PRODUCTS)]  # type: ignore[valid-type]
PositioningTag = Literal[tuple(POSITIONING)]  # type: ignore[valid-type]


def _symmetric(raw: dict[str, dict[str, float]]) -> dict[tuple[str, str], float]:
    sim: dict[tuple[str, str], float] = {}
    for a, row in (raw or {}).items():
        for b, w in row.items():
            sim[(a, b)] = max(sim.get((a, b), 0.0), w)
            sim[(b, a)] = max(sim.get((b, a), 0.0), w)
    return sim


INTEREST_SIM = _symmetric(_T.get("adjacency", {}))
VALUE_SIM = _symmetric(_T.get("values_adjacency", {}))


def similarity(a: str, b: str, table: dict[tuple[str, str], float]) -> float:
    return 1.0 if a == b else table.get((a, b), 0.0)


def describe(section: str) -> str:
    """Taxonomy section rendered for prompts: `tag: description` per line"""
    items = _T[section]
    if isinstance(items, list):
        return ", ".join(items)
    return "\n".join(f"- {k}: {v}" for k, v in items.items())
