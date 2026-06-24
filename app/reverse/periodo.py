"""Mapeia uma expressão de período histórico (PT) para século/intervalo + termo EN
usável na busca do Commons. Função pura, sem rede."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_ROMANOS = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8,
    "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
    "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20, "xxi": 21,
}
_ERAS_NOMEADAS = {
    "antiguidade": ("ancient", -3000, 476),
    "idade média": ("medieval", 476, 1453),
    "idade media": ("medieval", 476, 1453),
}
_ORDINAL_EN = {
    1: "1st", 2: "2nd", 3: "3rd", 21: "21st",
}


@dataclass(frozen=True)
class Periodo:
    rotulo: str
    ano_inicio: int
    ano_fim: int
    termo_en: str


def _ordinal(n: int) -> str:
    return _ORDINAL_EN.get(n, f"{n}th")


def _seculo_para_periodo(rotulo: str, seculo: int) -> Periodo:
    inicio = (seculo - 1) * 100
    return Periodo(rotulo=rotulo, ano_inicio=inicio, ano_fim=inicio + 99,
                   termo_en=f"{_ordinal(seculo)}-century")


def mapear_periodo(texto: Optional[str]) -> Optional[Periodo]:
    if not texto:
        return None
    low = texto.lower().strip()

    for nome, (termo, ini, fim) in _ERAS_NOMEADAS.items():
        if nome in low:
            return Periodo(rotulo=nome, ano_inicio=ini, ano_fim=fim, termo_en=termo)

    m = re.search(r"s[ée]culo\s+([ivxl]+)", low)
    if m and m.group(1) in _ROMANOS:
        sec = _ROMANOS[m.group(1)]
        return _seculo_para_periodo(f"século {m.group(1).upper()}", sec)

    m = re.search(r"\b(\d{3,4})\b", low)
    if m:
        ano = int(m.group(1))
        sec = ano // 100 + 1
        return _seculo_para_periodo(texto.strip(), sec)

    return None
