"""The Metropolitan Museum of Art — Open Access source.

The Met API is two-step: search returns object IDs, then each object must be
fetched for its image URLs. We fetch a bounded number of objects concurrently
and keep only public-domain items that actually have a high-res image.

No API key needed. https://metmuseum.github.io/

Rate-limit: hammering the Met endpoints in bursts returns HTTP 403, so we
retry 403/429 with exponential backoff and cap concurrent object fetches.
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
# Concorrência máxima de requests ao Met (rajada de 18 dispara 403).
_CONCORRENCIA = 5


async def _get_retry(client: httpx.AsyncClient, url: str, *, params: dict | None = None,
                     tentativas: int = 3) -> httpx.Response:
    """GET com retry em 403/429 (rate-limit do Met) com backoff exponencial."""
    atraso = 1.5
    resp = None
    for i in range(tentativas):
        resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
        if resp.status_code in (403, 429) and i < tentativas - 1:
            await asyncio.sleep(atraso)
            atraso *= 2
            continue
        break
    resp.raise_for_status()
    return resp


async def _fetch_object(client: httpx.AsyncClient, object_id: int) -> Optional[ImageResult]:
    try:
        resp = await _get_retry(client, OBJECT.format(id=object_id))
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
    resp = await _get_retry(client, SEARCH, params=params)
    data = resp.json()

    object_ids = (data.get("objectIDs") or [])[: min(limit, MAX_OBJECTS)]
    if not object_ids:
        return []

    sem = asyncio.Semaphore(_CONCORRENCIA)

    async def _um(oid: int) -> Optional[ImageResult]:
        async with sem:
            return await _fetch_object(client, oid)

    objects = await asyncio.gather(*[_um(oid) for oid in object_ids])
    return [o for o in objects if o is not None]
