"""Locate model-quoted text inside the brief.

The model returns quotes, not offsets (models are unreliable at counting characters).
Code finds each quote. If it can't be found, the model invented it.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from backend.schemas.profile import Span

_WS = re.compile(r"\s+")
_EDGE_PUNCT = " \t\n\"'“”‘’.,;:!?()"


def _norm(s: str) -> str:
    return _WS.sub(" ", s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')).lower()


def locate(quote: str | None, text: str, *, min_ratio: float = 0.88) -> Span | None:
    """Return the span of `quote` in `text`: exact, then case/whitespace-insensitive,
    then a fuzzy window match. None if nothing is close enough."""
    if not quote:
        return None
    q = quote.strip(_EDGE_PUNCT)
    if not q:
        return None

    i = text.find(q)
    if i >= 0:
        return Span(text=text[i : i + len(q)], start=i, end=i + len(q))

    # Case- and whitespace-insensitive. Normalization keeps character count except for
    # collapsed whitespace, so search on a char-by-char normalized copy instead.
    lowered = text.lower().replace("’", "'").replace("‘", "'")
    nq = _norm(q)
    i = lowered.find(nq)
    if i >= 0:
        return Span(text=text[i : i + len(nq)], start=i, end=i + len(nq))

    # Fuzzy: best window of similar length. Catches small paraphrase or typo drift
    # ("vet formulated" vs "vet-formulated"), rejects inventions.
    n = len(q)
    best, best_i, best_len = 0.0, -1, n
    for length in {n - 2, n - 1, n, n + 1, n + 2}:
        if length <= 0 or length > len(text):
            continue
        for start in range(0, len(text) - length + 1):
            r = SequenceMatcher(None, nq, lowered[start : start + length]).ratio()
            if r > best:
                best, best_i, best_len = r, start, length
    if best >= min_ratio and best_i >= 0:
        s, e = best_i, best_i + best_len
        # Snap to word boundaries so underlines don't cut words in half.
        while s > 0 and text[s - 1].isalnum():
            s -= 1
        while e < len(text) and text[e].isalnum():
            e += 1
        return Span(text=text[s:e], start=s, end=e)
    return None
