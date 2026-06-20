# garimpo-imagens/cli/coletar.py
"""Coleta em lote: plano-coleta.json -> wave-N.json (descobre + verifica licença).

Uso:
  python -m cli.coletar --plano plano-coleta.json --out data/coleta/wave-3.json \
      --banco-db ~/Projetos/banco-imagens/data/library.db [--dry] [--limite-por-query N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

from app import coleta
from app.sources import acervos_adapter, europeana, met, smithsonian, wikimedia
from app.sources.base import MissingKeyError

# fonte slug -> (label exibido pelo conector, função search async)
ASYNC_SOURCES = {
    "commons": ("Wikimedia Commons", wikimedia.search),
    "met": ("The Met", met.search),
    "smithsonian": ("Smithsonian", smithsonian.search),
    "europeana": ("Europeana", europeana.search),
}
ACERVOS = {"bnf", "loc", "dpla", "openlib", "walters"}
FONTE_LABEL = {lbl: slug for slug, (lbl, _) in ASYNC_SOURCES.items()}


async def _buscar(client, fonte: str, query: str, limit: int):
    if fonte in ASYNC_SOURCES:
        return await ASYNC_SOURCES[fonte][1](client, query, limit)
    if fonte in ACERVOS:
        return await acervos_adapter.search(client, query, limit, acervo=fonte)
    return []


async def run(args) -> int:
    plano = json.loads(Path(os.path.expanduser(args.plano)).read_text(encoding="utf-8"))
    out_path = Path(os.path.expanduser(args.out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prog_path = out_path.with_suffix(".progress.json")
    progresso = json.loads(prog_path.read_text()) if prog_path.exists() else {"feitas": []}

    ja_no_banco = coleta.carregar_urls_banco(os.path.expanduser(args.banco_db)) if args.banco_db else set()
    resultados: list[dict] = []
    if out_path.exists():
        resultados = json.loads(out_path.read_text(encoding="utf-8")).get("results", [])

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for q in plano["queries"]:
            chave = q["consulta"] + "|" + q["eixo"]
            if chave in progresso["feitas"]:
                continue
            cand = []
            limit_q = args.limite_por_query or q.get("overfetch", q["cota"] * 2)
            for fonte in q.get("fontes", ["commons"]):
                try:
                    cand += await _buscar(client, fonte, q["consulta"], limit_q)
                except MissingKeyError as e:
                    print(f"  [pulado] {fonte}: {e}", file=sys.stderr)
                except (httpx.HTTPError, asyncio.TimeoutError) as e:
                    print(f"  [erro] {fonte}: {e}", file=sys.stderr)
                await asyncio.sleep(0.4)  # rate-limit cortês
            sel = coleta.selecionar(
                cand, q["cota"], fonte_label=FONTE_LABEL,
                eixo=q["eixo"], periodo=q["periodo"], consulta=q["consulta"],
                ja_no_banco=ja_no_banco,
            )
            if args.dry:
                print(f"{q['consulta']}: {len(sel)}/{q['cota']} ({len(cand)} candidatos)")
            else:
                resultados.append({"aulaId": chave, "era": q["periodo"],
                                   "roteiro": {"slides": []},
                                   "resolucoes": [{"slideN": i + 1, "resolucao": r}
                                                  for i, r in enumerate(sel)]})
                progresso["feitas"].append(chave)
                out_path.write_text(json.dumps(
                    {"wave": args.wave, "bloco": "coleta-1000", "results": resultados},
                    ensure_ascii=False, indent=2), encoding="utf-8")
                prog_path.write_text(json.dumps(progresso), encoding="utf-8")
                print(f"{q['consulta']}: +{len(sel)} (checkpoint salvo)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="cli.coletar")
    ap.add_argument("--plano", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--banco-db", default="")
    ap.add_argument("--wave", type=int, default=3)
    ap.add_argument("--limite-por-query", type=int, default=0)
    ap.add_argument("--dry", action="store_true")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
