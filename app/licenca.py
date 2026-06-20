"""Classificador de licença em 3 estados para uso comercial (material vendido).

Regra central: checar NC/ND ANTES de casar BY, senão "CC BY-NC" casaria com
"cc by". Fail-closed: licença vazia/desconhecida → rejeitado.
"""
from __future__ import annotations

from dataclasses import dataclass

_REJEITA = ("-nc", "noncommercial", "non-commercial", "/by-nc",
            "-nd", "noderiv", "/by-nd",
            "all rights reserved", "rights reserved", "see source", "unknown")


@dataclass(frozen=True)
class ResultadoLicenca:
    estado: str       # "livre" | "atribuicao" | "rejeitado"
    categoria: str    # "Domínio público" | "CC0" | "CC BY" | "CC BY-SA" | "rejeitado"
    credito: str      # texto de atribuição; "" quando livre/rejeitado


def _credito(categoria: str, fonte: str, autor: str) -> str:
    quem = (autor or "").strip() or "Autor desconhecido"
    onde = (fonte or "").strip()
    base = f"{quem}, {categoria}"
    return f"{base}, via {onde}" if onde else base


def classificar(licenca: str, *, fonte: str = "", autor: str = "") -> ResultadoLicenca:
    l = (licenca or "").strip().lower()
    if not l:
        return ResultadoLicenca("rejeitado", "rejeitado", "")
    # 1) NC/ND/reservado primeiro — fail-closed
    if any(t in l for t in _REJEITA):
        return ResultadoLicenca("rejeitado", "rejeitado", "")
    # 2) livres
    if "cc0" in l or "publicdomain/zero" in l:
        return ResultadoLicenca("livre", "CC0", "")
    if ("public domain" in l or "domínio público" in l or "dominio publico" in l
            or "publicdomain/mark" in l or "/publicdomain/" in l):
        return ResultadoLicenca("livre", "Domínio público", "")
    # 3) atribuição (crédito obrigatório)
    if "by-sa" in l or "/licenses/by-sa/" in l:
        return ResultadoLicenca("atribuicao", "CC BY-SA", _credito("CC BY-SA", fonte, autor))
    if "cc by" in l or "cc-by" in l or "/licenses/by/" in l:
        return ResultadoLicenca("atribuicao", "CC BY", _credito("CC BY", fonte, autor))
    # 4) qualquer outra coisa — fail-closed
    return ResultadoLicenca("rejeitado", "rejeitado", "")
