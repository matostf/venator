"""Europeana — aggregator of European cultural-heritage collections.

Search API v2. Requires a free API key (EUROPEANA_API_KEY) from
https://pro.europeana.eu/page/get-api. We query with ``reusability=open`` so the
API only returns openly-reusable items (Public Domain / CC0 / CC BY / CC BY-SA),
matching this project's license rule — then we still validate the ``rights`` URI
per item and drop anything that isn't clearly PD/CC, since the credit line is
pasted straight into the teacher's slides.

https://pro.europeana.eu/page/search
"""
from __future__ import annotations

import os
from typing import List, Optional

import httpx

from .base import ImageResult, USER_AGENT, MissingKeyError

SEARCH = "https://api.europeana.eu/record/v2/search.json"


def _first(value):
    """Europeana returns most fields as lists; take the first non-empty value."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _license_name(rights_uri: Optional[str]) -> Optional[str]:
    """Map a rights URI to a short, paste-ready license name.

    Returns None for anything that isn't reusable for sold material (NC/ND or
    rights-reserved), so those items are dropped.
    """
    if not rights_uri:
        return None
    u = rights_uri.lower()
    if "publicdomain/zero" in u:
        return "CC0"
    if "publicdomain/mark" in u or "/publicdomain/" in u:
        return "Domínio Público"
    if "/licenses/by-sa/" in u:
        return "CC BY-SA"
    if "/licenses/by/" in u:
        return "CC BY"
    return None


async def search(client: httpx.AsyncClient, query: str, limit: int = 24) -> List[ImageResult]:
    api_key = os.environ.get("EUROPEANA_API_KEY")
    if not api_key:
        raise MissingKeyError(
            "No EUROPEANA_API_KEY set. Get a free key at "
            "https://pro.europeana.eu/page/get-api and add it to your .env file."
        )

    params = {
        "wskey": api_key,
        "query": query,
        "reusability": "open",   # PD / CC0 / CC BY / CC BY-SA only
        "media": "true",          # must have a usable media resource
        "qf": "TYPE:IMAGE",       # images only (not text/sound/video)
        "rows": limit,
    }
    resp = await client.get(SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    results: List[ImageResult] = []
    for item in data.get("items") or []:
        full = _first(item.get("edmIsShownBy"))
        thumb = _first(item.get("edmPreview")) or full
        if not full:
            continue
        license_name = _license_name(_first(item.get("rights")))
        if not license_name:  # keep only clearly PD/CC-reusable items
            continue

        results.append(
            ImageResult(
                id=f"europeana:{item.get('id')}",
                source="Europeana",
                title=_first(item.get("title")) or "Untitled",
                thumbnail=thumb,
                full_image=full,
                source_url=item.get("guid") or "",
                license=license_name,
                creator=_first(item.get("dcCreator")),
                width=None,
                height=None,
            )
        )
    return results
