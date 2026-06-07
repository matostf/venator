# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Acervo de História** — a FastAPI web app for a history teacher to search open-access
museum/archive APIs, preview results, and save chosen images into a personal library
(files on disk + SQLite metadata, with tags, notes, and collections). UI is in Portuguese.

> Recovered Jun 2026 from the running Fly.io machine (`acervo-historia-matostf`); the
> original source was not on this machine. `Dockerfile` and `fly.toml` were reconstructed
> from `fly config show` and the running container.

## Commands

- Setup: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`
- Run locally: `DATA_DIR=./data ./.venv/bin/uvicorn app.main:app --reload --port 8099`
  - With no `APP_PASSWORD` set, auth is OFF (login bypassed) — convenient for local dev.
- Deploy: `fly deploy` (uses `Dockerfile` + `fly.toml`).

No test suite or linter is configured.

## Architecture

- `app/main.py` — all FastAPI routes and app logic. Auth is a session cookie
  (`SessionMiddleware`, signed with `SECRET_KEY`); when `APP_PASSWORD` is set, every path
  except `_PUBLIC_PATHS` (`/login`, `/logout`, `/styles.css`, `/theme.js`, `/favicon.ico`)
  requires login. Searches all sources in parallel via `asyncio` + `httpx`.
- `app/db.py` — SQLite access. `DATA_DIR` (env, defaults to `./data`) holds `library.db`,
  `images/`, and `thumbs/`. On Fly this is the persistent volume `acervo_data` at `/data`.
- `app/sources/` — one module per source, each exposing an async `search()` returning
  normalized results. Registered in the `SOURCES` dict in `main.py`:
  - **Active:** `wikimedia` (Wikimedia Commons), `met` (The Met), `smithsonian`.
  - **Disabled:** `artic` (Art Institute of Chicago) — its image server is behind
    Cloudflare bot-protection. Re-enable by adding it back to `SOURCES`.
  - `base.py` holds the shared `USER_AGENT`. `smithsonian` needs `SMITHSONIAN_API_KEY`
    (free at api.data.gov); without it the source reports `ready: false`.
- `app/static/` — frontend (no build step): `index.html`/`app.js` (search), `library.html`/
  `library.js` (saved library), `styles.css`, `theme.js` (dark mode).

## Key routes

`/login` `/logout`; `/api/sources`; `/api/search`; `/api/download`; library CRUD under
`/api/library*` (save, list, refs, get/delete by id, tags, notes, view/file/thumb);
`/api/tags`; `/api/collections` (+ add/remove images).

## Environment / secrets

Local: copy `.env.example` to `.env`. Production secrets are set on Fly
(`fly secrets set`): `SECRET_KEY`, `APP_PASSWORD` (both already Deployed). Set
`SMITHSONIAN_API_KEY` similarly to enable that source.

## Data

`data/` is gitignored (it's the runtime volume). The recovered copy — `library.db` plus the
saved `images/` and `thumbs/` — is kept locally as a backup but not committed.
