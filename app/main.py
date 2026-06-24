"""History Image Finder — FastAPI backend.

Searches several open-access museum/archive APIs in parallel, normalizes the
results, applies an optional resolution filter, lets the teacher save chosen
images into a local library (files on disk + SQLite metadata, with tags and
collections), and serves the web UI.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import mimetypes
import os
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Body, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db
from .sources import artic, europeana, met, smithsonian, wikimedia
from .sources.base import USER_AGENT, MissingKeyError

load_dotenv()

app = FastAPI(title="Acervo de História")

log = logging.getLogger("acervo")

STATIC_DIR = Path(__file__).parent / "static"

# ---- Authentication config ----
# Auth is ON when APP_PASSWORD is set OR any user account exists. It's only OFF
# (app fully open, for local dev) when there's no APP_PASSWORD and no users yet.
# When ON, users sign in with their own e-mail/password account (see the users
# table); APP_PASSWORD additionally works as a master password so an admin always
# has a way in. SECRET_KEY signs the session cookie — set a long random value in
# production.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-change-me")

# Commit deployado, assado na imagem via `fly deploy --build-arg GIT_SHA=$(git rev-parse HEAD)`
# e servido em /version.json para o painel-projetos comparar com o HEAD local.
GIT_SHA = os.environ.get("GIT_SHA", "dev")

# Public base URL used to build absolute password-reset links. Set this in
# production: when unset we fall back to the request host, which is attacker-
# controllable (Host-header poisoning of reset links).
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

# Cache: once any account exists, auth stays required without a DB hit per
# request (users are never deleted in this app). When APP_PASSWORD is set we
# short-circuit before this even matters.
_has_users = False


def _auth_required() -> bool:
    """Whether login is enforced. True if APP_PASSWORD is set or any user exists."""
    global _has_users
    if APP_PASSWORD or _has_users:
        return True
    if db.count_users() > 0:
        _has_users = True
        return True
    return False

# Paths reachable without being logged in (auth pages + static login assets).
# /version.json stays public so the painel-projetos can read the deployed commit.
_PUBLIC_PATHS = {
    "/login", "/logout", "/register", "/forgot", "/reset",
    "/styles.css", "/theme.js", "/favicon.ico", "/version.json",
}

# Registry of available sources: key -> (label, async search function).
# NOTE: Art Institute of Chicago is temporarily disabled — its image server is
# behind Cloudflare bot-protection that blocks all automated access (thumbnails
# and downloads). To re-enable, add back:
#     "artic": ("Art Institute of Chicago", artic.search),
SOURCES: Dict[str, tuple[str, Callable]] = {
    "wikimedia": ("Wikimedia Commons", wikimedia.search),
    "met": ("The Met", met.search),
    "smithsonian": ("Smithsonian", smithsonian.search),
    "europeana": ("Europeana", europeana.search),
}
_ = artic  # connector kept for easy re-enable; see note above

# Sources that need an API key to work; used to report `ready` in /api/sources
# and to skip them gracefully when the key is absent.
REQUIRED_KEYS: Dict[str, str] = {
    "smithsonian": "SMITHSONIAN_API_KEY",
    "europeana": "EUROPEANA_API_KEY",
}

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


@app.get("/version.json")
def version_json():
    """Marcador self-report do commit deployado (público; lido pelo painel-projetos)."""
    return JSONResponse({"commit": GIT_SHA})


# ==========================================================================
# Authentication
# ==========================================================================
def _esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _auth_page(title: str, inner: str) -> str:
    """Wrap an auth form in the shared login card shell."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — Acervo de História</title>
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
    <div class="login-card">
      <div class="login-logo"><svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M10 18v-7" /><path d="M11.119 2.205a2 2 0 0 1 1.762 0l7.84 3.846A.5.5 0 0 1 20.5 7h-17a.5.5 0 0 1-.22-.949z" /><path d="M14 18v-7" /><path d="M18 18v-7" /><path d="M3 22h18" /><path d="M6 18v-7" /></svg></div>
      <h1>Acervo de História</h1>
      {inner}
    </div>
  </div>
</body>
</html>"""


def _alert(msg: str, kind: str = "error") -> str:
    cls = "login-error" if kind == "error" else "login-success"
    return f'<p class="{cls}">{msg}</p>' if msg else ""


def _login_inner(error: str = "", info: str = "") -> str:
    return f"""
      <p class="login-sub">Entre com sua conta para acessar a biblioteca.</p>
      {_alert(error)}{_alert(info, "success")}
      <form method="post" action="/login">
        <input type="email" name="email" placeholder="E-mail" autocomplete="username" autofocus required />
        <input type="password" name="password" placeholder="Senha" autocomplete="current-password" required />
        <button type="submit" class="btn">Entrar</button>
      </form>
      <p class="login-links">
        <a href="/forgot">Esqueci minha senha</a> · <a href="/register">Criar conta</a>
      </p>"""


def _register_inner(error: str = "", name: str = "", email: str = "") -> str:
    return f"""
      <p class="login-sub">Crie sua conta para acessar o acervo.</p>
      {_alert(error)}
      <form method="post" action="/register">
        <input type="text" name="name" placeholder="Nome (opcional)" autocomplete="name" value="{_esc(name)}" />
        <input type="email" name="email" placeholder="E-mail" autocomplete="username" value="{_esc(email)}" required />
        <input type="password" name="password" placeholder="Senha (mínimo 8 caracteres)" autocomplete="new-password" minlength="8" required />
        <input type="password" name="password2" placeholder="Repita a senha" autocomplete="new-password" minlength="8" required />
        <button type="submit" class="btn">Criar conta</button>
      </form>
      <p class="login-links"><a href="/login">Já tenho conta — entrar</a></p>"""


def _is_valid_email(email: str) -> bool:
    email = (email or "").strip()
    return "@" in email and "." in email.split("@")[-1] and len(email) <= 254


def _enter(request: Request, uid: Optional[int], email: str, is_admin: bool = False, sv: int = 0):
    """Start a logged-in session and redirect home. ``uid`` is the integer
    users.id for a real account, or None for the master-password admin (tracked
    separately via ``is_admin`` so the session never mixes id types). ``sv`` is
    the account's session_version, checked per request so a password reset can
    invalidate this session."""
    request.session.clear()
    request.session["auth"] = True
    request.session["uid"] = uid
    request.session["email"] = email
    request.session["is_admin"] = is_admin
    request.session["sv"] = sv
    return RedirectResponse(url="/", status_code=303)


def _session_valid(request: Request) -> bool:
    """Whether an authenticated session is still good. The master-password admin
    is always valid; a real account is valid only while its stored session_version
    still matches the current one (a password reset bumps it, logging out every
    existing session)."""
    if request.session.get("is_admin"):
        return True
    uid = request.session.get("uid")
    if not isinstance(uid, int):
        return False
    current = db.get_session_version(uid)
    return current is not None and current == request.session.get("sv")


def _reset_base(request: Request) -> str:
    """Base URL for reset links. Prefer APP_BASE_URL (trusted); fall back to the
    request's scheme+host only when it isn't set. The fallback is vulnerable to
    Host-header poisoning, so warn loudly when auth is enforced without it.
    """
    if APP_BASE_URL:
        return APP_BASE_URL
    if _auth_required():
        log.warning(
            "APP_BASE_URL não definido: links de redefinição usam o Host da "
            "requisição e podem ser forjados. Defina APP_BASE_URL em produção."
        )
    u = request.url
    return f"{u.scheme}://{u.netloc}"


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if not _auth_required() or request.session.get("auth"):
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse(_auth_page("Entrar", _login_inner()))


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(""), password: str = Form(...)):
    user = db.get_user_by_email(email) if email else None
    if user and auth.verify_password(password, user["password_hash"]):
        return _enter(request, user["id"], user["email"], sv=user["session_version"])

    # Master password fallback (admin always has a way in). Constant-time compare.
    if auth.secret_matches(password, APP_PASSWORD):
        return _enter(request, None, email or "admin", is_admin=True)

    return HTMLResponse(
        _auth_page("Entrar", _login_inner(error="E-mail ou senha incorretos.")),
        status_code=401,
    )


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if request.session.get("auth"):
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse(_auth_page("Criar conta", _register_inner()))


@app.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(""),
    name: str = Form(""),
):
    def fail(msg: str):
        return HTMLResponse(
            _auth_page("Criar conta", _register_inner(error=msg, name=name, email=email)),
            status_code=400,
        )

    if not _is_valid_email(email):
        return fail("Informe um e-mail válido.")
    if len(password) < 8:
        return fail("A senha precisa ter pelo menos 8 caracteres.")
    if password != password2:
        return fail("As senhas não coincidem.")

    # create_user does INSERT OR IGNORE and returns None on a duplicate e-mail,
    # so it's the single source of truth — no separate existence check needed.
    user = db.create_user(email, name, auth.hash_password(password), _now())
    if not user:
        return fail("Já existe uma conta com este e-mail.")

    global _has_users
    _has_users = True  # auth is now required even without APP_PASSWORD
    return _enter(request, user["id"], user["email"], sv=user["session_version"])


@app.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    if not _auth_required() or request.session.get("auth"):
        return RedirectResponse(url="/", status_code=303)
    inner = """
      <p class="login-sub">Informe seu e-mail e enviaremos um link para redefinir a senha.</p>
      <form method="post" action="/forgot">
        <input type="email" name="email" placeholder="E-mail" autocomplete="username" autofocus required />
        <button type="submit" class="btn">Enviar link</button>
      </form>
      <p class="login-links"><a href="/login">Voltar ao login</a></p>"""
    return HTMLResponse(_auth_page("Recuperar senha", inner))


@app.post("/forgot", response_class=HTMLResponse)
def forgot_submit(request: Request, background: BackgroundTasks, email: str = Form(...)):
    # Generate the reset link only for a real account. We never disclose the link
    # in the HTTP response (that would allow account takeover); when SMTP is
    # unconfigured, send_reset_email logs it to the server console so an admin can
    # still recover an account from the logs (e.g. `fly logs`). The (potentially
    # slow) send runs as a background task AFTER the response is returned, so the
    # response time doesn't reveal whether the account exists (no enumeration).
    user = db.get_user_by_email(email)
    if user:
        token = auth.new_reset_token()
        expires = _dt.datetime.now() + _dt.timedelta(hours=auth.RESET_TOKEN_TTL_HOURS)
        db.create_reset_token(user["id"], token, expires.isoformat(timespec="seconds"), _now())
        reset_url = f"{_reset_base(request)}/reset?token={token}"
        background.add_task(auth.send_reset_email, user["email"], reset_url)

    # Same generic response whether or not the account exists.
    inner = """
      <p class="login-sub">Se houver uma conta com esse e-mail, enviamos um link para
      redefinir a senha. Verifique sua caixa de entrada (e o spam).</p>
      <p class="login-links"><a href="/login">Voltar ao login</a></p>"""
    return HTMLResponse(_auth_page("Recuperar senha", inner))


def _valid_reset(token: str):
    """Return the reset row if the token exists, is unused and not expired."""
    row = db.get_reset_token(token) if token else None
    if not row or row["used"]:
        return None
    try:
        if _dt.datetime.fromisoformat(row["expires_at"]) < _dt.datetime.now():
            return None
    except (ValueError, TypeError):
        return None
    return row


def _reset_form_inner(token: str, error: str = "") -> str:
    return f"""
      <p class="login-sub">Crie uma nova senha para sua conta.</p>
      {_alert(error)}
      <form method="post" action="/reset">
        <input type="hidden" name="token" value="{_esc(token)}" />
        <input type="password" name="password" placeholder="Nova senha (mínimo 8 caracteres)" autocomplete="new-password" minlength="8" autofocus required />
        <input type="password" name="password2" placeholder="Repita a nova senha" autocomplete="new-password" minlength="8" required />
        <button type="submit" class="btn">Redefinir senha</button>
      </form>"""


def _invalid_token_page() -> HTMLResponse:
    inner = """
      <p class="login-sub">Este link de redefinição é inválido ou expirou.</p>
      <p class="login-links"><a href="/forgot">Solicitar um novo link</a></p>"""
    return HTMLResponse(_auth_page("Link inválido", inner), status_code=400)


@app.get("/reset", response_class=HTMLResponse)
def reset_page(request: Request, token: str = Query("")):
    if not _valid_reset(token):
        return _invalid_token_page()
    return HTMLResponse(_auth_page("Redefinir senha", _reset_form_inner(token)))


@app.post("/reset", response_class=HTMLResponse)
def reset_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password2: str = Form(""),
):
    row = _valid_reset(token)
    if not row:
        return _invalid_token_page()

    def fail(msg: str):
        return HTMLResponse(
            _auth_page("Redefinir senha", _reset_form_inner(token, msg)), status_code=400
        )

    if len(password) < 8:
        return fail("A senha precisa ter pelo menos 8 caracteres.")
    if password != password2:
        return fail("As senhas não coincidem.")

    # Consume the token first (fail-closed): if anything below fails, the link is
    # already spent rather than left replayable.
    db.consume_reset_token(token)
    db.set_user_password(row["user_id"], auth.hash_password(password))
    info = "Senha redefinida com sucesso. Faça login com sua nova senha."
    return HTMLResponse(_auth_page("Entrar", _login_inner(info=info)))


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

    def _ready(key: str) -> bool:
        env = REQUIRED_KEYS.get(key)
        return env is None or bool(os.environ.get(env))

    return {
        "sources": [
            {"key": key, "label": label, "ready": _ready(key)}
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
    sources: str = Query("wikimedia,met,smithsonian,europeana"),
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
# Reverse image search on Wikimedia Commons.
# - POST /api/reverse/find       — description+hints → ranked Commons candidates
# - GET  /api/reverse/normalize  — any Commons URL → canonical filename + URLs
# - POST /api/reverse/hash       — image URL → pHash + dHash
# - POST /api/reverse/dedup      — image (URL or hash) + manifest → duplicate verdict
# ==========================================================================
from .reverse import (  # noqa: E402
    DedupRequest,
    HashRequest,
    ImageHashes,
    ReverseQuery,
    dedup_against,
    hash_from_url,
    load_manifest,
    normalize_url,
    run_reverse,
)


@app.post("/api/reverse/find")
async def api_reverse_find(query: ReverseQuery) -> dict:
    response = await run_reverse(query)
    return response.model_dump()


@app.get("/api/reverse/normalize")
def api_reverse_normalize(url: str = Query(..., description="Any Commons-related image URL")) -> dict:
    result = normalize_url(url)
    if not result:
        raise HTTPException(status_code=400, detail="URL não é um arquivo do Wikimedia Commons")
    return result


@app.post("/api/reverse/hash")
async def api_reverse_hash(req: HashRequest) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            hashes = await hash_from_url(client, req.url)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Falha ao baixar imagem: {e}")
    return hashes.to_dict()


@app.post("/api/reverse/dedup")
async def api_reverse_dedup(req: DedupRequest) -> dict:
    # Resolve the candidate hash: either inline or by downloading the URL.
    if req.phash:
        candidate = ImageHashes(
            phash=req.phash,
            dhash=req.dhash or req.phash,  # fall back if caller only has phash
            width=0,
            height=0,
        )
    elif req.url:
        async with httpx.AsyncClient() as client:
            try:
                candidate = await hash_from_url(client, req.url)
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=f"Falha ao baixar imagem: {e}")
    else:
        raise HTTPException(status_code=400, detail="Forneça `url` ou (`phash` + `dhash`)")

    # Resolve manifest entries.
    if req.manifest is not None:
        entries = [e for e in req.manifest if isinstance(e, dict) and e.get("phash")]
    elif req.manifest_path:
        try:
            entries = load_manifest(req.manifest_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"manifest não encontrado: {req.manifest_path}")
    else:
        raise HTTPException(status_code=400, detail="Forneça `manifest_path` ou `manifest`")

    return dedup_against(candidate, entries, threshold=req.threshold)


# ==========================================================================
# Middleware (added LAST so SessionMiddleware is outermost and runs first,
# making request.session available to the auth guard below it).
# ==========================================================================
@app.middleware("http")
async def auth_guard(request: Request, call_next):
    # No password configured and no accounts yet → app is open (local dev).
    if not _auth_required():
        return await call_next(request)

    path = request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)
    if request.session.get("auth") and _session_valid(request):
        return await call_next(request)

    # Not logged in (or the session was invalidated, e.g. after a password
    # reset): drop the cookie, give APIs a clean 401 and pages a login redirect.
    request.session.clear()
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Não autenticado."}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 14)

# Serve the web UI at the root (mounted LAST so /api routes win).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
