"""Smithsonian Open Access source.

Requires a free API key from https://api.data.gov/signup/ — set it in the
environment as SMITHSONIAN_API_KEY (or in a .env file). When no key is present
this source is simply skipped, and the API layer surfaces a friendly note.

https://edan.si.edu/openaccess/apidocs/
"""
from __future__ import annotations

import os
from typing import List, Optional

import httpx

from .base import ImageResult, USER_AGENT

SEARCH = "https://api.si.edu/openaccess/api/v1.0/search"


class MissingKeyError(RuntimeError):
    """Raised when no Smithsonian API key is configured."""


def _best_image(media_item: dict) -> Optional[str]:
    """Pick the highest-resolution image URL from a media record."""
    resources = media_item.get("resources") or []
    # 'resources' lists derivatives; prefer the largest by label heuristics.
    preferred_order = ["High-resolution JPEG", "Screen Image", "Thumbnail Image"]
    by_label = {r.get("label"): r.get("url") for r in resources if r.get("url")}
    for label in preferred_order:
        if by_label.get(label):
            return by_label[label]
    # Fall back to the primary content URL.
    return media_item.get("content")


async def search(client: httpx.AsyncClient, query: str, limit: int = 24) -> List[ImageResult]:
    api_key = os.environ.get("SMITHSONIAN_API_KEY")
    if not api_key:
        raise MissingKeyError(
            "No SMITHSONIAN_API_KEY set. Get a free key at "
            "https://api.data.gov/signup/ and add it to your .env file."
        )

    params = {
        "api_key": api_key,
        "q": f"{query} AND online_media_type:Images",
        "rows": limit,
    }
    resp = await client.get(SEARCH, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    rows = ((data.get("response") or {}).get("rows")) or []
    results: List[ImageResult] = []
    for row in rows:
        content = row.get("content") or {}
        descriptive = content.get("descriptiveNonRepeating") or {}
        online_media = (descriptive.get("online_media") or {}).get("media") or []
        if not online_media:
            continue

        media_item = online_media[0]
        full = _best_image(media_item)
        thumb = media_item.get("thumbnail") or full
        if not full:
            continue

        # Smithsonian Open Access images are CC0, but double-check the flag.
        rights = (
            (content.get("indexedStructured") or {}).get("usage_flag") or []
        )
        license_name = "CC0" if ("CC0" in rights or not rights) else ", ".join(rights)

        freetext = content.get("freetext") or {}
        names = freetext.get("name") or []
        creator = names[0].get("content") if names else None

        results.append(
            ImageResult(
                id=f"smithsonian:{row.get('id')}",
                source="Smithsonian",
                title=row.get("title") or "Untitled",
                thumbnail=thumb,
                full_image=full,
                source_url=descriptive.get("record_link", ""),
                license=license_name,
                creator=creator,
                width=None,
                height=None,
            )
        )
    return results
