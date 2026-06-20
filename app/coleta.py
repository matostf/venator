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
    vistos: set[str] = set()
    out: list[dict] = []
    for r in candidatos:
        if len(out) >= cota:
            break
        chave = r.full_image or r.title
        if chave in vistos or chave in ja_no_banco:
            continue
        fonte = fonte_label.get(r.source, r.source)
        res = classificar(r.license, fonte=fonte, autor=r.creator or "")
        if res.estado == "rejeitado":
            continue
        vistos.add(chave)
        out.append(para_resolucao(r, res, fonte=fonte, eixo=eixo, periodo=periodo, consulta=consulta))
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
