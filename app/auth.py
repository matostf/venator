"""Authentication helpers: password hashing, reset tokens, and e-mail delivery.

Kept dependency-free on purpose (stdlib only) so the app runs with the same
``requirements.txt`` as before:

* Passwords are hashed with PBKDF2-HMAC-SHA256 and a per-user random salt,
  stored as ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.
* Password-reset tokens are random URL-safe strings; only their value is mailed
  to the user, and they expire after ``RESET_TOKEN_TTL_HOURS``.
* Reset links are sent over SMTP when it's configured (see the ``SMTP_*`` env
  vars). When it isn't, the link is logged to the server console as a fallback
  so a local/dev admin can still recover an account.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("acervo.auth")

_PBKDF2_ITERATIONS = 240_000
_PBKDF2_ALGO = "pbkdf2_sha256"

RESET_TOKEN_TTL_HOURS = 2


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return a self-describing hash string for ``password``."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def secret_matches(candidate: str, secret: str) -> bool:
    """Constant-time comparison for fixed secrets (e.g. the master password)."""
    if not secret:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), secret.encode("utf-8"))


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored hash string."""
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        iterations = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


# --------------------------------------------------------------------------
# Reset tokens
# --------------------------------------------------------------------------
def new_reset_token() -> str:
    return secrets.token_urlsafe(32)


# --------------------------------------------------------------------------
# E-mail delivery (SMTP)
# --------------------------------------------------------------------------
def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def _smtp_from() -> str:
    return os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "no-reply@localhost"


def send_reset_email(to_email: str, reset_url: str) -> bool:
    """Best-effort delivery of a password-reset link.

    Returns True if an e-mail was actually sent. When SMTP isn't configured the
    link is logged instead and False is returned — callers should still show the
    user the same generic confirmation either way (don't leak whether an account
    exists).
    """
    subject = "Redefinição de senha — Acervo de História"
    body = (
        "Olá,\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no Acervo de "
        "História. Para criar uma nova senha, acesse o link abaixo "
        f"(válido por {RESET_TOKEN_TTL_HOURS} horas):\n\n"
        f"{reset_url}\n\n"
        "Se você não solicitou isso, pode ignorar este e-mail com segurança.\n"
    )

    if not smtp_configured():
        log.warning(
            "SMTP não configurado; link de redefinição para %s: %s", to_email, reset_url
        )
        return False

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    use_ssl = os.environ.get("SMTP_SSL", "").lower() in ("1", "true", "yes")
    use_starttls = os.environ.get("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _smtp_from()
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
                if user:
                    s.login(user, password or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as s:
                if use_starttls:
                    s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, password or "")
                s.send_message(msg)
        log.info("Reset e-mail enviado para %s", to_email)
        return True
    except Exception:  # noqa: BLE001 — never let mail failures break the flow
        log.exception("Falha ao enviar e-mail de redefinição para %s", to_email)
        return False
