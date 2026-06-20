# garimpo-imagens/app/coleta.py
"""Lógica pura da coleta em lote (sem rede) — testável isoladamente."""
from __future__ import annotations

import sqlite3
from typing import List

from app.licenca import ResultadoLicenca, classificar
from app.sources.base import ImageResult


def para_resolucao(r: ImageResult, res: ResultadoLicenca, *,
                   fonte: str, eixo: str, periodo: str, consulta: str) -> dict:
    return {
        "obraConfirmada": r.title,
        "autor": r.creator or "",
        "licenca": r.license,
        "acervo": r.source,
        "url": r.full_image,
        "dominioPublico": "sim" if res.estado == "livre" else ("cc" if res.estado == "atribuicao" else "nao"),
        "width": r.width,
        "height": r.height,
        "nota": "",
        "status": "coletado",
        "estadoLicenca": res.estado,
        "creditoObrigatorio": res.credito,
        "fonte": fonte,
        "eixo": eixo,
        "periodo": periodo,
        "consultaOrigem": consulta,
    }


def selecionar(candidatos: List[ImageResult], cota: int, *,
               fonte_label: dict[str, str], eixo: str = "", periodo: str = "",
               consulta: str = "", ja_no_banco: set[str] = frozenset()) -> List[dict]:
    """Seleciona até `cota` imagens fazendo ROUND-ROBIN entre as fontes.

    Os candidatos chegam concatenados por fonte (commons, depois met, depois
    europeana). Pegar os primeiros da lista faria o Commons monopolizar a cota
    e Met/Europeana quase nunca entrarem. Aqui agrupamos por fonte e pegamos uma
    imagem válida de cada fonte por rodada, até encher a cota ou esgotar tudo.
    Dentro de cada fonte preserva-se a ordem de chegada (relevância da busca).
    Descarta licença não-comercial e duplicatas (no run e contra o banco).
    """
    from collections import OrderedDict

    grupos: "OrderedDict[str, list[ImageResult]]" = OrderedDict()
    for r in candidatos:
        grupos.setdefault(r.source, []).append(r)
    filas = [iter(g) for g in grupos.values()]

    vistos: set[str] = set()
    out: list[dict] = []

    def _proximo_valido(it) -> dict | None:
        for r in it:
            chave = r.full_image or r.title
            if chave in vistos or chave in ja_no_banco:
                continue
            fonte = fonte_label.get(r.source, r.source)
            res = classificar(r.license, fonte=fonte, autor=r.creator or "")
            if res.estado == "rejeitado":
                continue
            vistos.add(chave)
            return para_resolucao(r, res, fonte=fonte, eixo=eixo, periodo=periodo, consulta=consulta)
        return None

    while len(out) < cota and filas:
        ativos = []
        for it in filas:
            if len(out) >= cota:
                break
            d = _proximo_valido(it)
            if d is not None:
                out.append(d)
                ativos.append(it)   # fonte ainda pode ter itens — segue na rotação
            # se None, a fonte esgotou (sem mais itens válidos) e sai da rotação
        filas = ativos
    return out


def carregar_urls_banco(db_path: str) -> set[str]:
    """URLs já no banco (url_commons), para pular na coleta. Vazio se db ausente."""
    import os
    if not os.path.exists(db_path):
        return set()
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT COALESCE(url_commons,'') FROM imagens").fetchall()
    except sqlite3.OperationalError:
        return set()
    finally:
        con.close()
    return {r[0] for r in rows if r[0]}
