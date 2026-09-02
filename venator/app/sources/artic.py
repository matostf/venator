"""Art Institute of Chicago source.

Single search request returns everything we need; images are served over IIIF,
so we build URLs ourselves (a medium thumbnail and a high-res download). Only
public-domain artworks with an image are kept. No API key needed.

https://api.artic.edu/docs/
"""
from __future__ import annotations

from typing import List

import httpx

from .base import ImageResult, USER_AGENT

SEARCH = "https://api.artic.edu/api/v1/artworks/search"
# IIIF image server; documented default in the API config.
IIIF = "https://www.artic.edu/iiif/2"


def _thumb_url(image_id: str) -> str:
    return f"{IIIF}/{image_id}/full/600,/0/default.jpg"


def _full_url(image_id: str) -> str:
    # 1686px is the Art Institute's recommended max-quality width.
    return f"{IIIF}/{image_id}/full/1686,/0/default.jpg"


async def search(client: httpx.AsyncClient, query: str, limit: int = 24) -> List[ImageResult]:
    params = {
        "q": query,
        "limit": limit,
        "fields": "id,title,image_id,artist_display,is_public_domain,date_display",
    }
    resp = await client.get(SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    results: List[ImageResult] = []
    for item in data.get("data", []):
        image_id = item.get("image_id")
        if not image_id or not item.get("is_public_domain"):
            continue

        artist = item.get("artist_display") or None
        if artist:
            # artist_display is often multi-line; collapse to the first line.
            artist = artist.split("\n")[0].strip() or None

        results.append(
            ImageResult(
                id=f"artic:{item.get('id')}",
                source="Art Institute of Chicago",
                title=item.get("title") or "Untitled",
                thumbnail=_thumb_url(image_id),
                full_image=_full_url(image_id),
                source_url=f"https://www.artic.edu/artworks/{item.get('id')}",
                license="Public Domain (CC0)",
                creator=artist,
                width=None,
                height=None,
            )
        )
    return results
