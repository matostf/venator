"""Wikimedia Commons source.

Uses the MediaWiki API to search the File namespace and pull image info
(full URL, dimensions, license, author) in a single request. No API key needed.
"""
from __future__ import annotations

import re
from typing import List

import httpx

from .base import ImageResult, USER_AGENT

API = "https://commons.wikimedia.org/w/api.php"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return _TAG_RE.sub("", text).strip()


async def search(client: httpx.AsyncClient, query: str, limit: int = 24) -> List[ImageResult]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,          # File namespace
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|mime",
        "iiurlwidth": 500,          # ask for a 500px-wide thumbnail
    }
    resp = await client.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    pages = (data.get("query") or {}).get("pages") or {}
    results: List[ImageResult] = []
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]

        mime = info.get("mime", "")
        if not mime.startswith("image/"):
            continue

        meta = info.get("extmetadata") or {}
        license_name = _strip_html((meta.get("LicenseShortName") or {}).get("value", "")) or "See source"
        author = _strip_html((meta.get("Artist") or {}).get("value", "")) or None

        title = page.get("title", "File:")
        if title.startswith("File:"):
            title = title[len("File:"):]

        results.append(
            ImageResult(
                id=f"wikimedia:{page.get('pageid')}",
                source="Wikimedia Commons",
                title=title,
                thumbnail=info.get("thumburl") or info.get("url", ""),
                full_image=info.get("url", ""),
                source_url=info.get("descriptionurl", ""),
                license=license_name,
                creator=author,
                width=info.get("width"),
                height=info.get("height"),
            )
        )
    return results
