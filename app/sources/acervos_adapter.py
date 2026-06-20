"""Adapta os conectores síncronos de scripts/acervos.py à interface async
search() usada pelo coletor. Itens sem URL de imagem direta são descartados."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import List

import httpx

from app.sources.base import ImageResult

# scripts/ não é um pacote — injeta no path e importa o módulo
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
import acervos  # noqa: E402

_SOURCES = dict(acervos.SOURCES)  # {"bnf": bnf_search, "loc": ..., ...}


def _para_result(d: dict, acervo: str, i: int) -> ImageResult | None:
    img = (d.get("image") or "").strip()
    if not img:
        return None  # sem imagem direta → não dá pra baixar; descarta
    return ImageResult(
        id=f"{acervo}:{i}:{abs(hash(img)) % 10_000_000}",
        source=d.get("source") or acervo,
        title=d.get("title") or "",
        thumbnail=img,
        full_image=img,
        source_url=d.get("url") or img,
        license=d.get("license") or "",
        creator=d.get("creator") or None,
    )


async def search(client: httpx.AsyncClient, query: str, limit: int = 10, *, acervo: str) -> List[ImageResult]:
    fn = _SOURCES.get(acervo)
    if fn is None:
        return []
    brutos = await asyncio.to_thread(fn, query, limit)
    out: list[ImageResult] = []
    for i, d in enumerate(brutos or []):
        r = _para_result(d, acervo, i)
        if r is not None:
            out.append(r)
    return out
