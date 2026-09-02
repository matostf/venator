"""CLI front-end for `app.reverse`.

Run from the project root:

    python -m cli.reverse "preparação de farinha de mandioca por indígenas" \
        --hint-author "Jean-Baptiste Debret" --max 10

Outputs a human-readable ranked list. Use `--json` to pipe into other tools.
The CLI calls the library functions directly — no HTTP server needed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from app.reverse import (
    ReverseHint,
    ReverseQuery,
    dedup_path,
    dedup_url,
    hash_from_path,
    hash_from_url,
    load_manifest,
    normalize_url,
    run_reverse,
)


def _format_text(response: Any) -> str:
    lines = [
        f"Estratégias usadas: {', '.join(response.strategies_used) or '(nenhuma)'}",
        f"Candidatos: {len(response.candidates)}",
        "",
    ]
    for i, c in enumerate(response.candidates, 1):
        dims = f"{c.width}×{c.height}px" if (c.width and c.height) else "?"
        lines.append(
            f"{i:2d}. [{c.source_strategy:18s} score={c.similarity_score:.2f}] {c.title}"
        )
        lines.append(f"    autor: {c.author or '(anônimo)'}  ·  licença: {c.license or '?'}  ·  {dims}")
        lines.append(f"    {c.file_url}")
        lines.append("")
    return "\n".join(lines)


async def cmd_find(args: argparse.Namespace) -> int:
    query = ReverseQuery(
        description=args.description,
        hints=ReverseHint(
            author=args.hint_author,
            period=args.hint_period,
            region=args.hint_region,
        ),
        max_results=args.max,
    )
    response = await run_reverse(query)
    if args.json:
        print(json.dumps(response.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(_format_text(response))
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    result = normalize_url(args.url)
    if not result:
        print(f"ERRO: URL não é um arquivo do Wikimedia Commons:\n  {args.url}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for k, v in result.items():
            print(f"{k:>16s}: {v}")
    return 0


async def cmd_hash(args: argparse.Namespace) -> int:
    import httpx

    if args.url:
        async with httpx.AsyncClient() as client:
            hashes = await hash_from_url(client, args.url)
    else:
        hashes = hash_from_path(args.path)

    if args.json:
        print(json.dumps(hashes.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"  phash:  {hashes.phash}")
        print(f"  dhash:  {hashes.dhash}")
        print(f"  size:   {hashes.width}×{hashes.height}")
    return 0


async def cmd_dedup(args: argparse.Namespace) -> int:
    try:
        entries = load_manifest(args.manifest)
    except FileNotFoundError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2
    if not entries:
        print(f"AVISO: manifesto vazio ou sem entradas com 'phash': {args.manifest}", file=sys.stderr)

    if args.url:
        verdict = await dedup_url(args.url, entries, threshold=args.threshold)
    else:
        verdict = dedup_path(args.path, entries, threshold=args.threshold)

    if args.json:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
        return 0 if not verdict["is_duplicate"] else 3

    # Human-readable summary.
    cand = verdict["candidate_hashes"]
    print(f"Candidato: phash={cand['phash']} dhash={cand['dhash']}")
    print(f"Manifesto: {len(entries)} entradas | limite de distância pHash: {verdict['threshold']}")
    if verdict["best_match"]:
        b = verdict["best_match"]
        label = b.get("id") or b.get("slug") or b.get("title") or "?"
        print(f"\nMais próximo: {label}")
        print(f"  pHash distância: {b['distance']}  ·  dHash distância: {b.get('distance_dhash','?')}")
    print()
    if verdict["is_duplicate"]:
        print("⚠ DUPLICATA detectada (distância ≤ limite).")
    else:
        print("✓ Não é duplicata.")
    if verdict["near_matches"]:
        print(f"\n{len(verdict['near_matches'])} match(es) próximo(s):")
        for m in verdict["near_matches"]:
            label = m.get("id") or m.get("slug") or m.get("title") or "?"
            print(f"  · {label}  (distância pHash {m['distance']})")
    return 0 if not verdict["is_duplicate"] else 3


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="cli.reverse",
        description="Reverse image search no Wikimedia Commons (modo CLI).",
    )
    sub = ap.add_subparsers(dest="command")

    # `find` is the default if the first arg is not a known subcommand.
    p_find = sub.add_parser("find", help="Buscar candidatos para uma descrição")
    p_find.add_argument("description", help="Descrição em linguagem natural (PT)")
    p_find.add_argument("--hint-author", help="Pista: nome do autor (ex.: 'Jean-Baptiste Debret')")
    p_find.add_argument("--hint-period", help="Pista: período (ex.: 'século XIX')")
    p_find.add_argument("--hint-region", help="Pista: região (ex.: 'Brasil')")
    p_find.add_argument("--max", type=int, default=10, help="Máximo de candidatos (default: 10)")
    p_find.add_argument("--json", action="store_true", help="Sai em JSON em vez de texto")
    p_find.set_defaults(func=lambda a: asyncio.run(cmd_find(a)))

    p_norm = sub.add_parser("normalize", help="Normalizar uma URL do Commons")
    p_norm.add_argument("url", help="URL (qualquer formato Commons)")
    p_norm.add_argument("--json", action="store_true", help="Sai em JSON em vez de texto")
    p_norm.set_defaults(func=cmd_normalize)

    p_hash = sub.add_parser("hash", help="Calcular pHash + dHash de uma imagem")
    g_h = p_hash.add_mutually_exclusive_group(required=True)
    g_h.add_argument("--url", help="URL da imagem")
    g_h.add_argument("--path", help="Caminho local da imagem")
    p_hash.add_argument("--json", action="store_true", help="Sai em JSON em vez de texto")
    p_hash.set_defaults(func=lambda a: asyncio.run(cmd_hash(a)))

    p_dedup = sub.add_parser("dedup", help="Verificar duplicata contra um manifesto")
    g_d = p_dedup.add_mutually_exclusive_group(required=True)
    g_d.add_argument("--url", help="URL da imagem a verificar")
    g_d.add_argument("--path", help="Caminho local da imagem a verificar")
    p_dedup.add_argument("--manifest", required=True, help="Caminho do MANIFESTO.json com entradas {phash, dhash, id, ...}")
    p_dedup.add_argument(
        "--threshold",
        type=int,
        default=6,
        help="Distância pHash máxima para considerar duplicata (default: 6)",
    )
    p_dedup.add_argument("--json", action="store_true", help="Sai em JSON em vez de texto")
    p_dedup.set_defaults(func=lambda a: asyncio.run(cmd_dedup(a)))

    # Shorthand: if first arg is not a subcommand, treat it as `find <args>`.
    KNOWN = {"find", "normalize", "hash", "dedup", "-h", "--help"}
    if len(sys.argv) > 1 and sys.argv[1] not in KNOWN:
        sys.argv.insert(1, "find")

    args = ap.parse_args()
    if not args.command:
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
