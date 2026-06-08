"""Smoke test: boots the app in-process and exercises the core auth flows.

Runs without pytest — just `python tests/test_smoke.py` (exit 0 = pass). Uses
Starlette's TestClient (httpx-backed), so no network or running server needed.
Env vars are set BEFORE importing app.main because auth config is read at
import time.
"""
import os
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="acervo-ci-")
os.environ["APP_PASSWORD"] = "ci-master-password"
os.environ["SECRET_KEY"] = "ci-secret-key"
os.environ["APP_BASE_URL"] = "http://testserver"
os.environ.pop("SMITHSONIAN_API_KEY", None)
os.environ.pop("SMTP_HOST", None)

# Make the repo root importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

checks = 0


def check(cond, label):
    global checks
    if not cond:
        print(f"FAIL: {label}")
        sys.exit(1)
    checks += 1
    print(f"ok: {label}")


with TestClient(app) as client:  # context manager runs startup (init_db)
    # --- Unauthenticated: pages redirect, APIs 401 ---
    r = client.get("/", follow_redirects=False)
    check(r.status_code == 303 and r.headers["location"] == "/login", "GET / redirects to /login")
    check(client.get("/login").status_code == 200, "GET /login is 200")
    check(client.get("/register").status_code == 200, "GET /register is 200")
    check(client.get("/api/sources").status_code == 401, "GET /api/sources unauth is 401")

    # --- Registration validation ---
    bad = client.post("/register", data={"email": "x", "password": "segredo123", "password2": "segredo123"})
    check(bad.status_code == 400, "register rejects invalid e-mail")
    short = client.post("/register", data={"email": "a@b.com", "password": "123", "password2": "123"})
    check(short.status_code == 400, "register rejects short password")

    # --- Successful registration logs the client in ---
    r = client.post(
        "/register",
        data={"email": "ci@example.com", "password": "segredo123", "password2": "segredo123"},
        follow_redirects=False,
    )
    check(r.status_code == 303, "register succeeds (303)")
    check(client.get("/api/sources").status_code == 200, "authed GET /api/sources is 200")

    # Duplicate registration is rejected.
    dup = client.post(
        "/register",
        data={"email": "ci@example.com", "password": "segredo123", "password2": "segredo123"},
    )
    check(dup.status_code == 400, "duplicate e-mail rejected")

with TestClient(app) as client:
    # --- Login flows on a fresh client (no cookie) ---
    wrong = client.post("/login", data={"email": "ci@example.com", "password": "errada"})
    check(wrong.status_code == 401, "login with wrong password is 401")
    ok = client.post(
        "/login", data={"email": "ci@example.com", "password": "segredo123"}, follow_redirects=False
    )
    check(ok.status_code == 303, "login with correct password is 303")

with TestClient(app) as client:
    master = client.post(
        "/login", data={"email": "", "password": "ci-master-password"}, follow_redirects=False
    )
    check(master.status_code == 303, "master-password login is 303")

with TestClient(app) as client:
    # --- Password recovery: generic response, no link leaked, bad token rejected ---
    forgot = client.post("/forgot", data={"email": "ci@example.com"})
    check(forgot.status_code == 200, "forgot returns 200")
    check("reset?token=" not in forgot.text, "forgot never discloses the reset link in the body")
    check(client.get("/reset?token=garbage").status_code == 400, "invalid reset token is 400")

print(f"\nAll {checks} smoke checks passed.")
