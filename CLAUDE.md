# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Garimpa** — a Portuguese-language **CLI/library to discover open-license images** (public
domain / CC) in open-access museum and archive collections, used to build history slide
decks. Two entry points:

- **`cli.reverse`** — keyword/reverse image search over Wikimedia Commons: a natural-language
  description (PT) → ranked candidates with URLs, license, and metadata.
- **`cli.coletar`** — batch collector that runs a plan of queries across several sources,
  filters by license, and writes results to feed the local `banco-imagens` vault.

It is a **library consumed by other tools**, not an app: the `decks-historia` pipeline
(`wave_workflow_so_pesquisador.js`) and the `reverse-search` skill call `cli.reverse`. It
returns URLs/metadata and does **not** download images or keep a library — the companion
`banco-imagens` project is the vault that **guarda + vê** (stores + browses); this one
**garimpa** (discovers).

> **History — Rota 1 (2026-06):** this repo used to also ship a FastAPI web app/gallery on
> Fly.io (login, accounts, SMTP, personal library). That layer was **retired**: it was idle
> (3 images, 0 users) and redundant with `banco-imagens`. Only the discovery engine +
> collector remain. The `find` engine rebuild (better PT-phrase handling, a real period
> filter, new ranking) is **paused** on branch `rota1-descoberta-commons` — see
> `docs/superpowers/specs/2026-06-24-rota1-descoberta-commons-design.md`. Default branch is
> **`master`**. (`README.md` still describes the old web app — out of date.)

## Commands

- Setup: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`
- Search: `./.venv/bin/python -m cli.reverse find "<descrição PT>" [--hint-author X] [--hint-period X] [--hint-region X] [--max N] [--json]`
  - Other subcommands: `normalize` (canonicalize a Commons URL), `hash` (pHash/dHash of an image), `dedup` (check an image against a manifest).
- Batch collect: `./.venv/bin/python -m cli.coletar --plano <plano.json> --out <dir> [--banco-db DB] [--ja-coletado FILE] [--wave N] [--limite-por-query N] [--dry]`
- Tests: `./.venv/bin/python -m pytest -q` (pytest; ~19 tests over the engine + collector). CI runs `compileall` + `pytest`.

## Architecture

- `cli/reverse.py` — the `find/normalize/hash/dedup` CLI. `find` takes a PT description +
  optional `--hint-author/--hint-period/--hint-region` and prints text or, with `--json`, a
  `candidates[]` array (fields like `file_url, thumbnail_url, title, author, license, width,
  height, date, similarity_score`). **This JSON is a contract** — `decks-historia` and the
  `reverse-search` skill parse it; keep additions backward-compatible.
- `app/reverse/` — the discovery engine behind `find`:
  - `triangulate.py` — **the live `find` engine** (Commons MediaSearch + multilingual + author
    subcategory walk + `_score_candidate`). Rota 1's replacement is not built yet, so this is
    what actually runs.
  - `commons_search.py` / `commons_categories.py` — Wikimedia Commons API access.
  - `periodo.py` — period mapper ("século XVI"/"1815" → year range + EN term); built for Rota 1,
    not yet wired into the `find` query path.
  - `hasher.py` (pHash/dHash), `dedup.py` (vs a manifest — also used by
    `acervo-didatico-historia`), `commons_normalize.py`, `models.py`.
- `cli/coletar.py` + `app/coleta.py` + `app/licenca.py` — the batch collector: runs a plan,
  searches **multiple sources**, classifies license, and writes the collected set for the
  `banco-imagens` ingest.
- `app/sources/` — one module per source, each exposing an async `search()`; consumed by the
  **collector** (`cli.coletar`). `base.py` holds the shared `USER_AGENT` / `MissingKeyError`
  (the reverse engine also imports `USER_AGENT` from here).
  - **No key needed:** `wikimedia` (Commons), `met` (The Met).
  - **Needs a key:** `smithsonian` (`SMITHSONIAN_API_KEY`), `europeana` (`EUROPEANA_API_KEY`;
    queried with `reusability=open` → PD/CC0/CC BY/CC BY-SA only) — raise `MissingKeyError`
    when absent.
  - **Disabled:** `artic` (Art Institute of Chicago — image server behind Cloudflare
    bot-protection). `acervos_adapter.py` adapts `scripts/acervos.py` to the source interface.
- `scripts/acervos.py` — stdlib-only multi-archive connectors (BnF / LoC / Walters / DPLA /
  Rijks / Harvard…).

## Environment / secrets

Copy `.env.example` to `.env`. Optional keys enable extra collector sources:
`SMITHSONIAN_API_KEY` (free at api.data.gov) and `EUROPEANA_API_KEY` (free at
pro.europeana.eu). Without them those sources are skipped; `wikimedia`/`met` need no key.
(`SECRET_KEY`, `APP_PASSWORD`, `SMTP_*` from the old web app are no longer used.)

## Data

`data/` is gitignored (local runtime/scratch). External archive dumps live under `external/`
(also gitignored — e.g. a ~43 MB Walters CSV mirror that carries its own `.git`).
