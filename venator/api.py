"""A porta de entrada do venator para outros programas (librarius).

`garimpar(termos) -> {termo: [candidato, ...]}` — busca reversa no Wikimedia
Commons (rede, sem chave) usando o mesmo motor do `cli.reverse find`. Cada
candidato é um dict com `title`, `file_url`, `upload_url`, `license`, `author`,
`width`, `height`, `source_strategy`. Lista vazia = nada achado; erro de rede vira
`[{"erro": "..."}]` em vez de exceção, porque quem chama está no meio de uma
compilação e quer saber o que falhou, não parar.
"""
from __future__ import annotations

import asyncio

from .app.reverse import ReverseHint, ReverseQuery, run_reverse


async def _garimpar_async(termos: list[str], *, max_por_termo: int, dica: ReverseHint) -> dict:
    saida: dict[str, list[dict]] = {}
    for termo in termos:
        try:
            resp = await run_reverse(ReverseQuery(description=termo, hints=dica, max_results=max_por_termo))
            saida[termo] = [c.model_dump() for c in resp.candidates]
        except Exception as exc:  # noqa: BLE001 — a compilação decide o que fazer
            saida[termo] = [{"erro": f"{type(exc).__name__}: {exc}"}]
    return saida


def garimpar(imagens: list[str], *, max_por_termo: int = 5, periodo: str | None = None,
             autor: str | None = None, regiao: str | None = None) -> dict[str, list[dict]]:
    """Candidatos do Commons para cada termo; exige rede, não exige chave."""
    dica = ReverseHint(author=autor, period=periodo, region=regiao)
    return asyncio.run(_garimpar_async(list(imagens), max_por_termo=max_por_termo, dica=dica))
