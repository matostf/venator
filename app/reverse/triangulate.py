"""Compose strategies to find the best candidates for a description.

Pipeline:
  1. **direct**       — MediaSearch on the literal description
  2. **multilingual** — re-run with PT→EN/FR/DE term substitutions (parallel)
  3. **subcategory_walk** — if `hints.author` is set, BFS from `Category:<Author>`
                            biased toward subcats matching description keywords

Each candidate is dedup'd by title and scored with a small heuristic. The
returned list is sorted descending by score and capped at `max_results`.
"""
from __future__ import annotations

import asyncio
import re
from typing import List, Optional

import httpx

from ..sources.base import USER_AGENT
from .commons_categories import bfs_files, fetch_imageinfo
from .commons_search import TERM_TRANSLATIONS, search_direct, search_multilingual
from .models import ReverseCandidate, ReverseQuery, ReverseResponse


def _author_to_category(author: str) -> str:
    """Best-effort guess at the Commons category for an author name."""
    return f"Category:{author.replace(' ', '_')}"


_STOPWORDS_PT = {
    "de", "da", "do", "das", "dos", "e", "ou", "para", "com", "em",
    "no", "na", "nos", "nas", "um", "uma", "o", "a", "os", "as", "se", "por",
}


def _keywords(text: str) -> List[str]:
    """Cheap keyword extraction: lowercase, strip stopwords + short tokens."""
    words = re.findall(r"\w+", (text or "").lower(), flags=re.UNICODE)
    return [w for w in words if len(w) >= 4 and w not in _STOPWORDS_PT]


def _expand_for_category_match(keywords: List[str]) -> List[str]:
    """Wikimedia category names are mostly English. Expand PT keywords with cognates
    so BFS bias actually fires on `Indigenous peoples...`, `Slavery...`, etc."""
    out = list(keywords)
    for kw in keywords:
        for other in TERM_TRANSLATIONS.get(kw, []):
            out.append(other.lower())
    return out


def _score_candidate(c: ReverseCandidate, query: ReverseQuery) -> float:
    """Heuristic 0..1 score: keyword overlap + author hint matches."""
    score = c.similarity_score
    title_l = c.title.lower()
    author_l = (c.author or "").lower()

    for kw in _keywords(query.description):
        if kw in title_l:
            score += 0.08

    if query.hints.author:
        ah = query.hints.author.lower()
        if ah in author_l or ah.replace(" ", "_") in title_l:
            score += 0.25
        # Catch surname-only matches in the title.
        surname = ah.split()[-1] if ah else ""
        if surname and len(surname) >= 4 and surname in title_l:
            score += 0.15

    if query.hints.region:
        if query.hints.region.lower() in title_l:
            score += 0.05

    if query.hints.period:
        if query.hints.period.lower() in title_l:
            score += 0.05

    # Slight bonus for direct-strategy hits.
    if c.source_strategy == "direct":
        score += 0.05

    return min(1.0, max(0.0, score))


async def run(query: ReverseQuery, *, client: Optional[httpx.AsyncClient] = None) -> ReverseResponse:
    """Execute the triangulation pipeline and return ranked candidates."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT})

    try:
        all_candidates: List[ReverseCandidate] = []
        strategies_used: List[str] = []

        # Run direct + multilingual concurrently — same set of API endpoints, no contention.
        direct_task = search_direct(client, query.description, limit=query.max_results)
        multi_task = search_multilingual(client, query.description, limit=query.max_results)

        direct, multi = await asyncio.gather(direct_task, multi_task, return_exceptions=True)

        if isinstance(direct, list) and direct:
            all_candidates.extend(direct)
            strategies_used.append("direct")
        if isinstance(multi, list) and multi:
            all_candidates.extend(multi)
            strategies_used.append("multilingual")

        # If we have an author hint, walk subcategories.
        if query.hints.author:
            root = _author_to_category(query.hints.author)
            kws = _keywords(query.description)
            if query.hints.region:
                kws.append(query.hints.region.lower())
            if query.hints.period:
                kws.append(query.hints.period.lower())
            # Expand PT keywords to cognates so EN/FR category titles match.
            kws = _expand_for_category_match(kws)

            try:
                titles = await bfs_files(
                    client,
                    root,
                    depth=3,
                    max_files=60,
                    max_categories=80,
                    filter_keywords=kws,
                )
                if titles:
                    cands = await fetch_imageinfo(client, titles, strategy="subcategory_walk")
                    if cands:
                        all_candidates.extend(cands)
                        strategies_used.append("subcategory_walk")
            except httpx.HTTPError:
                pass

        # Dedup by title, score, sort.
        seen, unique = set(), []
        for c in all_candidates:
            key = c.title
            if key in seen:
                continue
            seen.add(key)
            c.similarity_score = _score_candidate(c, query)
            unique.append(c)

        unique.sort(key=lambda x: x.similarity_score, reverse=True)
        unique = unique[: query.max_results]

        return ReverseResponse(
            query=query,
            candidates=unique,
            strategies_used=strategies_used,
        )
    finally:
        if own_client:
            await client.aclose()
