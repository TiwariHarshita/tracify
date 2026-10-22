import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Response
from pwdlib import PasswordHash

from app.core.config import get_settings


password_hasher = PasswordHash.recommended()
dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))

COOKIE_NAME = "trace_session"
SESSION_SECONDS = 7 * 24 * 60 * 60


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session_token():
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(
        seconds=SESSION_SECONDS
    )
    return token, expires


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/api",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/api",
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
    )
