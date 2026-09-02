"""BFS of Wikimedia Commons categories.

When direct text search misses the target (common for specific historical plates),
walking the categorical structure ("Jean-Baptiste Debret" → "Indigenous peoples of
Brazil in art by Jean-Baptiste Debret") often surfaces both the original work and
thematic substitutes.

Public coroutines:
  - `list_files(category)` — files directly in a category
  - `list_subcategories(category)` — subcategories
  - `bfs_files(root, depth, max_files, filter_keywords)` — BFS with optional bias
  - `fetch_imageinfo(titles)` — batch-fetch full info for a list of File: titles
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

import httpx

from ..sources.base import USER_AGENT
from .commons_search import _candidates_from_pages
from .models import ReverseCandidate

API = "https://commons.wikimedia.org/w/api.php"


def _ensure_category_prefix(name: str) -> str:
    return name if name.startswith("Category:") else "Category:" + name


async def list_files(client: httpx.AsyncClient, category: str, *, limit: int = 50) -> List[str]:
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": _ensure_category_prefix(category),
        "cmtype": "file",
        "cmlimit": limit,
    }
    resp = await client.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return [
        m.get("title", "")
        for m in (resp.json().get("query") or {}).get("categorymembers", [])
        if m.get("title")
    ]


async def list_subcategories(
    client: httpx.AsyncClient, category: str, *, limit: int = 50
) -> List[str]:
    params = {
        "action": "query",
        "format": "json",
        "list": "categorymembers",
        "cmtitle": _ensure_category_prefix(category),
        "cmtype": "subcat",
        "cmlimit": limit,
    }
    resp = await client.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return [
        m.get("title", "")
        for m in (resp.json().get("query") or {}).get("categorymembers", [])
        if m.get("title")
    ]


async def bfs_files(
    client: httpx.AsyncClient,
    root_category: str,
    *,
    depth: int = 3,
    max_files: int = 60,
    max_categories: int = 80,
    filter_keywords: Optional[List[str]] = None,
) -> List[str]:
    """Two-phase walk: discover categories first, fetch files biased by relevance.

    Phase 1 (`category walk`): BFS the category tree up to `depth`, collecting every
    subcategory title. Capped at `max_categories` to bound fan-out (Commons
    hierarchies branch wide at depth 3+).

    Phase 2 (`file fetch`): sort discovered categories so that ones matching
    `filter_keywords` come first (descending), then by depth (deeper = more
    specific), then fetch their files in order until `max_files` is reached.

    The Wikimedia Commons author hierarchy is typically:
      Category:<Author>
        ↳ Category:Works by <Author>
            ↳ Category:<Region> in art by <Author>
                ↳ Category:<Theme> in art by <Author>   ← depth 3 from root
    so default depth=3 surfaces themed subcategories that depth=2 misses.
    """
    kws = [k.lower() for k in (filter_keywords or []) if k]
    root_category = _ensure_category_prefix(root_category)

    # Phase 1: discover categories breadth-first, capped.
    seen_cats: Set[str] = set()
    discovered: List[Tuple[str, int]] = []  # (category, depth)
    queue: List[Tuple[str, int]] = [(root_category, 0)]
    while queue and len(discovered) < max_categories:
        cat, d = queue.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        discovered.append((cat, d))
        if d < depth:
            try:
                subs = await list_subcategories(client, cat)
            except httpx.HTTPError:
                subs = []
            # Within each depth, prefer subcats that match keywords — keeps the
            # cap from being filled by unrelated branches before we reach the
            # relevant ones.
            if kws:
                subs.sort(
                    key=lambda s: sum(1 for k in kws if k in s.lower()),
                    reverse=True,
                )
            for s in subs:
                if s not in seen_cats:
                    queue.append((s, d + 1))

    # Phase 2: rank categories. Higher keyword hits first; ties broken by depth
    # descending (more specific cats first); root visited last as fallback.
    def score(entry: Tuple[str, int]) -> Tuple[int, int]:
        cat, d = entry
        cat_l = cat.lower()
        kw_hits = sum(1 for k in kws if k in cat_l) if kws else 0
        return (kw_hits, d)

    discovered.sort(key=score, reverse=True)

    # Phase 2: fetch files in ranked order.
    out_files: List[str] = []
    for cat, _d in discovered:
        if len(out_files) >= max_files:
            break
        try:
            files = await list_files(client, cat, limit=max_files - len(out_files))
        except httpx.HTTPError:
            files = []
        out_files.extend(files)

    # Order-preserving dedup.
    seen, ordered = set(), []
    for f in out_files:
        if f in seen:
            continue
        seen.add(f)
        ordered.append(f)
    return ordered[:max_files]


async def fetch_imageinfo(
    client: httpx.AsyncClient, file_titles: List[str], *, strategy: str = "subcategory_walk"
) -> List[ReverseCandidate]:
    """Batch-fetch full info for File: titles. Commons API allows 50 titles per call."""
    if not file_titles:
        return []
    out: List[ReverseCandidate] = []
    for i in range(0, len(file_titles), 50):
        batch = file_titles[i : i + 50]
        params = {
            "action": "query",
            "format": "json",
            "titles": "|".join(batch),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata|mime",
            "iiurlwidth": 800,
        }
        resp = await client.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        pages = list(((resp.json().get("query") or {}).get("pages") or {}).values())
        out.extend(_candidates_from_pages(pages, strategy=strategy))
    return out
