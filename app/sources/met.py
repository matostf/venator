"""The Metropolitan Museum of Art — Open Access source.

The Met API is two-step: search returns object IDs, then each object must be
fetched for its image URLs. We fetch a bounded number of objects concurrently
and keep only public-domain items that actually have a high-res image.

No API key needed. https://metmuseum.github.io/
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

import httpx

from .base import ImageResult, USER_AGENT

SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"

# The Met object endpoint requires one request per object, so cap how many we
# resolve to keep searches fast.
MAX_OBJECTS = 18


async def _fetch_object(client: httpx.AsyncClient, object_id: int) -> Optional[ImageResult]:
    try:
        resp = await client.get(
            OBJECT.format(id=object_id),
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        obj = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not obj.get("isPublicDomain"):
        return None
    full = obj.get("primaryImage")
    if not full:
        return None

    return ImageResult(
        id=f"met:{object_id}",
        source="The Met",
        title=obj.get("title") or "Untitled",
        thumbnail=obj.get("primaryImageSmall") or full,
        full_image=full,
        source_url=obj.get("objectURL", ""),
        license="Public Domain (CC0)",
        creator=obj.get("artistDisplayName") or None,
        # The Met API does not expose pixel dimensions; left as None.
        width=None,
        height=None,
    )


async def search(client: httpx.AsyncClient, query: str, limit: int = 18) -> List[ImageResult]:
    params = {"q": query, "hasImages": "true"}
    resp = await client.get(SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    object_ids = (data.get("objectIDs") or [])[: min(limit, MAX_OBJECTS)]
    if not object_ids:
        return []

    tasks = [_fetch_object(client, oid) for oid in object_ids]
    objects = await asyncio.gather(*tasks)
    return [o for o in objects if o is not None]
