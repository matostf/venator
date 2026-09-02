"""Commons MediaSearch + multilingual query expansion.

Two public coroutines:
  - `search_direct(client, description, limit)` — single query, direct text search
  - `search_multilingual(client, description, limit)` — expand PT keywords to EN/FR/DE in parallel

Returns lists of `ReverseCandidate`. Dedup of titles is left to the orchestrator.
"""
from __future__ import annotations

import asyncio
import re
from typing import List

import httpx

from ..sources.base import USER_AGENT
from .models import ReverseCandidate

API = "https://commons.wikimedia.org/w/api.php"

# Lightweight PT → {EN, FR, DE} for the most common history-class vocabulary.
# Reused by `_expand()` to fan out a query. Expand opportunistically; missing
# terms just pass through.
_TERM_TRANSLATIONS = {
    "mandioca": ["manioc", "cassava", "Maniok"],
    "farinha": ["farine", "flour", "Mehl"],
    "preparação": ["preparation", "préparation"],
    "indígena": ["indigenous", "indigène", "Indianer"],
    "indígenas": ["indigenous people", "indigènes", "Indianer"],
    "índios": ["natives", "indigènes", "Eingeborene"],
    "guerra": ["war", "guerre", "Krieg"],
    "batalha": ["battle", "bataille", "Schlacht"],
    "escravo": ["slave", "esclave", "Sklave"],
    "escravidão": ["slavery", "esclavage", "Sklaverei"],
    "rei": ["king", "roi", "König"],
    "rainha": ["queen", "reine", "Königin"],
    "imperador": ["emperor", "empereur", "Kaiser"],
    "imperatriz": ["empress", "impératrice", "Kaiserin"],
    "navio": ["ship", "navire", "Schiff"],
    "templo": ["temple", "temple", "Tempel"],
    "iluminismo": ["enlightenment", "lumières", "Aufklärung"],
    "revolução": ["revolution", "révolution", "Revolution"],
    "industrial": ["industrial", "industrielle", "Industrie"],
    "fábrica": ["factory", "usine", "Fabrik"],
    "mapa": ["map", "carte", "Karte"],
    "retrato": ["portrait", "portrait", "Porträt"],
    "gravura": ["engraving", "gravure", "Stich"],
    "pintura": ["painting", "peinture", "Gemälde"],
    "século": ["century", "siècle", "Jahrhundert"],
    "antiga": ["ancient", "antique", "antiken"],
    "antigo": ["ancient", "antique", "antiken"],
    "grécia": ["greece", "grèce", "Griechenland"],
    "roma": ["rome", "rome", "Rom"],
    "egito": ["egypt", "égypte", "Ägypten"],
    "mesopotâmia": ["mesopotamia", "mésopotamie", "Mesopotamien"],
    "brasil": ["brazil", "brésil", "Brasilien"],
    "europa": ["europe", "europe", "Europa"],
}

# Public: re-used by `triangulate.py` to expand keywords for category-title matching.
TERM_TRANSLATIONS = _TERM_TRANSLATIONS

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _expand(description: str) -> List[str]:
    """Return query variants by substituting PT terms with cognates in EN/FR/DE.

    For each PT term found in description, generate one variant per language.
    Cap the number of variants to keep API usage sane.
    """
    variants = [description]
    lower = description.lower()
    for term, others in _TERM_TRANSLATIONS.items():
        if term not in lower:
            continue
        for other in others:
            variant = re.sub(re.escape(term), other, lower, flags=re.IGNORECASE)
            if variant not in variants:
                variants.append(variant)
    # Limit fan-out: original + up to 8 variants.
    return variants[:9]


async def _search_single(
    client: httpx.AsyncClient, query: str, *, limit: int = 10
) -> List[dict]:
    """Run one MediaWiki API search in namespace 6 (File:). Returns raw pages."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|mime",
        "iiurlwidth": 800,
    }
    resp = await client.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return list(((resp.json().get("query") or {}).get("pages") or {}).values())


def _candidates_from_pages(pages: list, *, strategy: str) -> List[ReverseCandidate]:
    """Normalize MediaWiki API page objects into ReverseCandidate. Skips non-images."""
    out: List[ReverseCandidate] = []
    for page in pages:
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        if not (info.get("mime") or "").startswith("image/"):
            continue
        meta = info.get("extmetadata") or {}
        license_name = _strip_html((meta.get("LicenseShortName") or {}).get("value", "")) or "See source"
        author = _strip_html((meta.get("Artist") or {}).get("value", "")) or None
        raw_date = (meta.get("DateTimeOriginal") or {}).get("value", "") or \
                   (meta.get("DateTime") or {}).get("value", "")
        date = _strip_html(raw_date) or None
        title = page.get("title", "")
        if title.startswith("File:"):
            title = title[len("File:"):]
        out.append(
            ReverseCandidate(
                file_url=info.get("descriptionurl", ""),
                thumbnail_url=info.get("thumburl") or info.get("url", ""),
                upload_url=info.get("url", ""),
                title=title,
                author=author,
                license=license_name,
                width=info.get("width"),
                height=info.get("height"),
                date=date,
                source_strategy=strategy,
                similarity_score=0.5,
            )
        )
    return out


async def search_direct(
    client: httpx.AsyncClient, description: str, *, limit: int = 10
) -> List[ReverseCandidate]:
    """Single direct MediaSearch query."""
    pages = await _search_single(client, description, limit=limit)
    return _candidates_from_pages(pages, strategy="direct")


async def search_multilingual(
    client: httpx.AsyncClient, description: str, *, limit: int = 10
) -> List[ReverseCandidate]:
    """Fan-out queries for each PT→{EN, FR, DE} variant in parallel."""
    variants = _expand(description)
    # Skip the original (already covered by search_direct upstream).
    expanded = variants[1:]
    if not expanded:
        return []
    pages_lists = await asyncio.gather(
        *[_search_single(client, v, limit=limit) for v in expanded],
        return_exceptions=True,
    )
    out: List[ReverseCandidate] = []
    for pages in pages_lists:
        if isinstance(pages, Exception):
            continue
        out.extend(_candidates_from_pages(pages, strategy="multilingual"))
    return out
