"""History Image Finder — FastAPI backend.

Searches several open-access museum/archive APIs in parallel, normalizes the
results, applies an optional resolution filter, lets the teacher save chosen
images into a local library (files on disk + SQLite metadata, with tags and
collections), and serves the web UI.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import mimetypes
import os
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import db
from .sources import artic, met, smithsonian, wikimedia
from .sources.base import USER_AGENT
from .sources.smithsonian import MissingKeyError

load_dotenv()

app = FastAPI(title="Acervo de História")

STATIC_DIR = Path(__file__).parent / "static"

# ---- Authentication config ----
# Set APP_PASSWORD to require a login. If it's empty (local dev), auth is OFF.
# SECRET_KEY signs the session cookie — set a long random value in production.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-change-me")

# Paths reachable without being logged in (the login page + its assets).
_PUBLIC_PATHS = {"/login", "/logout", "/styles.css", "/theme.js", "/favicon.ico"}

# Registry of available sources: key -> (label, async search function).
# NOTE: Art Institute of Chicago is temporarily disabled — its image server is
# behind Cloudflare bot-protection that blocks all automated access (thumbnails
# and downloads). To re-enable, add back:
#     "artic": ("Art Institute of Chicago", artic.search),
SOURCES: Dict[str, tuple[str, Callable]] = {
    "wikimedia": ("Wikimedia Commons", wikimedia.search),
    "met": ("The Met", met.search),
    "smithsonian": ("Smithsonian", smithsonian.search),
}
_ = artic  # connector kept for easy re-enable; see note above

# content-type -> file extension, for naming downloaded files.
_CT_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "image/tiff": ".tif",
}


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


# ==========================================================================
# Authentication
# ==========================================================================
def _login_html(error: bool = False) -> str:
    msg = (
        '<p class="login-error">Senha incorreta. Tente novamente.</p>' if error else ""
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Entrar — Acervo de História</title>
  <script>
    (function () {{
      var t = localStorage.getItem("theme") || "dark";
      document.documentElement.setAttribute("data-theme", t);
    }})();
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Spectral:ital,wght@0,400;0,500;0,600;1,400&display=swap" />
  <link rel="stylesheet" href="/styles.css" />
</head>
<body>
  <div class="login-wrap">
    <form class="login-card" method="post" action="/login">
      <div class="login-logo">🏛️</div>
      <h1>Acervo de História</h1>
      <p class="login-sub">Digite a senha para acessar sua biblioteca.</p>
      {msg}
      <input type="password" name="password" placeholder="Senha" autofocus required />
      <button type="submit" class="btn">Entrar</button>
    </form>
  </div>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if not APP_PASSWORD or request.session.get("auth"):
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse(_login_html())


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, password: str = Form(...)):
    if APP_PASSWORD and password == APP_PASSWORD:
        request.session["auth"] = True
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse(_login_html(error=True), status_code=401)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ==========================================================================
# Search
# ==========================================================================
@app.get("/api/sources")
async def list_sources() -> dict:
    """Report which sources exist and whether they're ready to use."""
    return {
        "sources": [
            {
                "key": key,
                "label": label,
                "ready": key != "smithsonian" or bool(os.environ.get("SMITHSONIAN_API_KEY")),
            }
            for key, (label, _fn) in SOURCES.items()
        ]
    }


def _passes_resolution(item_dict: dict, min_res: int) -> bool:
    """Keep an item if it meets min_res, OR if its size is unknown.

    Most museum APIs don't expose pixel dimensions, so we don't want the filter
    to hide them — unknown-size items always pass, known-size items are checked.
    """
    if min_res <= 0:
        return True
    w, h = item_dict.get("width"), item_dict.get("height")
    if not w or not h:
        return True
    return max(w, h) >= min_res


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=1, description="Search terms"),
    sources: str = Query("wikimedia,met,artic,smithsonian"),
    min_res: int = Query(0, ge=0, description="Minimum width/height in pixels"),
) -> dict:
    requested = [s.strip() for s in sources.split(",") if s.strip() in SOURCES]
    if not requested:
        requested = list(SOURCES)

    notes: List[str] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def run(key: str):
            label, fn = SOURCES[key]
            try:
                return key, await fn(client, q)
            except MissingKeyError as exc:
                notes.append(str(exc))
                return key, []
            except Exception as exc:  # one bad source shouldn't kill the search
                notes.append(f"{label} could not be reached ({type(exc).__name__}).")
                return key, []

        gathered = await asyncio.gather(*(run(k) for k in requested))

    results: List[dict] = []
    per_source: Dict[str, int] = {}
    for key, items in gathered:
        kept = [i.to_dict() for i in items if _passes_resolution(i.to_dict(), min_res)]
        per_source[key] = len(kept)
        results.extend(kept)

    return {
        "query": q,
        "count": len(results),
        "per_source": per_source,
        "notes": notes,
        "results": results,
    }


# ==========================================================================
# Download proxy (search results, remote)
# ==========================================================================
@app.get("/api/download")
async def download(url: str = Query(...), filename: str = Query("image")):
    """Stream a remote image through the server so the browser saves it cleanly."""
    async def stream():
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream(
                "GET", url, headers={"User-Agent": USER_AGENT}, timeout=60
            ) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes():
                    yield chunk

    ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
    disposition = f'attachment; filename="{_safe_name(filename)}{ext}"'
    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


# ==========================================================================
# Library (local storage)
# ==========================================================================
def _safe_name(name: str) -> str:
    safe = "".join(c for c in (name or "") if c.isalnum() or c in " -_").strip()
    return safe or "image"


def _ext_for(url: str, content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _CT_EXT:
        return _CT_EXT[ct]
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    return suffix if suffix else ".jpg"


async def _fetch_bytes(client: httpx.AsyncClient, url: str) -> tuple[bytes, str]:
    r = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=90)
    r.raise_for_status()
    return r.content, _ext_for(url, r.headers.get("content-type", ""))


@app.get("/api/library")
def library_list(
    tag: Optional[str] = None,
    collection_id: Optional[int] = None,
    q: Optional[str] = None,
) -> dict:
    items = db.list_images(tag=tag, collection_id=collection_id, q=q)
    return {"count": len(items), "results": items}


@app.get("/api/library/refs")
def library_refs() -> dict:
    """source_refs already saved, so the search page can mark them."""
    return {"refs": db.list_saved_refs()}


@app.post("/api/library/save")
async def library_save(payload: dict = Body(...)) -> dict:
    """Save a search result into the local library.

    Body: the search-result object, plus optional ``tags`` (list[str]) and
    ``collection_ids`` (list[int]). Downloads the full image (and a thumbnail)
    to disk unless this item is already saved.
    """
    full_url = payload.get("full_image")
    if not full_url:
        raise HTTPException(status_code=400, detail="Missing full_image URL.")

    tags = payload.get("tags") or []
    collection_ids = payload.get("collection_ids") or []

    # Skip the download entirely if we already have this item.
    if payload.get("id") and db.find_by_ref(payload["id"]):
        saved = db.save_image(
            payload, b"", ".jpg", None, None, tags, collection_ids, _now()
        )
        return {"saved": saved, "already_existed": True}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            full_bytes, full_ext = await _fetch_bytes(client, full_url)
        except httpx.HTTPError:
            raise HTTPException(
                status_code=502,
                detail=(
                    "A fonte bloqueou o download automático desta imagem "
                    "(proteção anti-robô). Tente baixar pela página da fonte "
                    "ou use outra fonte."
                ),
            )

        thumb_bytes = thumb_ext = None
        thumb_url = payload.get("thumbnail")
        if thumb_url and thumb_url != full_url:
            try:
                thumb_bytes, thumb_ext = await _fetch_bytes(client, thumb_url)
            except httpx.HTTPError:
                thumb_bytes = thumb_ext = None  # thumbnail is optional

    saved = db.save_image(
        payload, full_bytes, full_ext, thumb_bytes, thumb_ext,
        tags, collection_ids, _now(),
    )
    return {"saved": saved, "already_existed": False}


@app.delete("/api/library/{image_id}")
def library_delete(image_id: int) -> dict:
    if not db.delete_image(image_id):
        raise HTTPException(status_code=404, detail="Image not found.")
    return {"deleted": image_id}


@app.get("/api/library/{image_id}")
def library_get(image_id: int) -> dict:
    img = db.get_image(image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found.")
    return {"image": img}


@app.put("/api/library/{image_id}/tags")
def library_set_tags(image_id: int, payload: dict = Body(...)) -> dict:
    if not db.get_image(image_id):
        raise HTTPException(status_code=404, detail="Image not found.")
    db.set_tags(image_id, payload.get("tags") or [])
    return {"image": db.get_image(image_id)}


@app.put("/api/library/{image_id}/notes")
def library_set_notes(image_id: int, payload: dict = Body(...)) -> dict:
    if not db.get_image(image_id):
        raise HTTPException(status_code=404, detail="Image not found.")
    db.set_notes(image_id, payload.get("notes") or "")
    return {"image": db.get_image(image_id)}


@app.get("/api/library/{image_id}/view")
def library_view(image_id: int):
    """Serve the full image inline (for the lightbox), not as a download."""
    img = db.get_image(image_id)
    if not img or not img.get("file_path"):
        raise HTTPException(status_code=404, detail="File not found.")
    path = db.DATA_DIR / img["file_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk.")
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return FileResponse(path, media_type=media_type)


@app.get("/api/library/{image_id}/file")
def library_file(image_id: int):
    img = db.get_image(image_id)
    if not img or not img.get("file_path"):
        raise HTTPException(status_code=404, detail="File not found.")
    path = db.DATA_DIR / img["file_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk.")
    ext = path.suffix or ".jpg"
    return FileResponse(
        path,
        filename=f"{_safe_name(img['title'])}{ext}",
        media_type="application/octet-stream",
    )


@app.get("/api/library/{image_id}/thumb")
def library_thumb(image_id: int):
    img = db.get_image(image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Not found.")
    rel = img.get("thumb_path") or img.get("file_path")
    if not rel:
        raise HTTPException(status_code=404, detail="No image on disk.")
    path = db.DATA_DIR / rel
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk.")
    return FileResponse(path)


# ---- Tags ----
@app.get("/api/tags")
def tags_list() -> dict:
    return {"tags": db.list_tags()}


# ---- Collections ----
@app.get("/api/collections")
def collections_list() -> dict:
    return {"collections": db.list_collections()}


@app.post("/api/collections")
def collections_create(payload: dict = Body(...)) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Collection name is required.")
    return {"collection": db.create_collection(name, payload.get("description", ""), _now())}


@app.delete("/api/collections/{collection_id}")
def collections_delete(collection_id: int) -> dict:
    db.delete_collection(collection_id)
    return {"deleted": collection_id}


@app.post("/api/collections/{collection_id}/images/{image_id}")
def collections_add_image(collection_id: int, image_id: int) -> dict:
    db.add_to_collection(collection_id, image_id, _now())
    return {"ok": True}


@app.delete("/api/collections/{collection_id}/images/{image_id}")
def collections_remove_image(collection_id: int, image_id: int) -> dict:
    db.remove_from_collection(collection_id, image_id)
    return {"ok": True}


# ==========================================================================
# Middleware (added LAST so SessionMiddleware is outermost and runs first,
# making request.session available to the auth guard below it).
# ==========================================================================
@app.middleware("http")
async def auth_guard(request: Request, call_next):
    # No password configured → app is open (local development).
    if not APP_PASSWORD:
        return await call_next(request)

    path = request.url.path
    if path in _PUBLIC_PATHS or request.session.get("auth"):
        return await call_next(request)

    # Not logged in: APIs get a clean 401, pages get redirected to login.
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Não autenticado."}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 14)

# Serve the web UI at the root (mounted LAST so /api routes win).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
