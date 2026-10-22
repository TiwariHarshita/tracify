import hashlib
import hmac
import math
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy import case, func, literal
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.auth import AuthRateLimit


def client_ip(request: Request) -> str:
    # Trust the ASGI server's client only, never a raw forwarded header here.
    return request.client.host if request.client else "unknown"


def hit_limit(scope: str, subject: str, limit: int, seconds: int) -> int:
    """Return retry seconds if blocked, else 0; commit independently of auth."""
    key = hmac.new(
        get_settings().session_secret.encode(),
        f"{scope}:{subject}".encode(),
        hashlib.sha256,
    ).hexdigest()
    now = func.statement_timestamp()
    expired = AuthRateLimit.window_end <= now
    new_end = now + literal(timedelta(seconds=seconds))
    stmt = insert(AuthRateLimit).values(key=key, hits=1, window_end=new_end)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AuthRateLimit.key],
        set_={
            "hits": case(
                (expired, 1),
                else_=func.least(AuthRateLimit.hits + 1, limit + 1),
            ),
            "window_end": case((expired, new_end), else_=AuthRateLimit.window_end),
        },
    ).returning(AuthRateLimit.hits, AuthRateLimit.window_end)
    with SessionLocal.begin() as db:
        row = db.execute(stmt).one()
        db_now = db.scalar(func.clock_timestamp().select())
    if row.hits <= limit:
        return 0
    return max(1, math.ceil((row.window_end - db_now).total_seconds()))


def enforce_limit(scope: str, subject: str, limit: int, seconds: int):
    retry = hit_limit(scope, subject, limit, seconds)
    if retry:
        raise HTTPException(
            429,
            "Too many attempts. Try again later.",
            headers={"Retry-After": str(retry)},
        )


def limit_login(request: Request, email: str):
    enforce_limit("login-ip", client_ip(request), 30, 900)
    enforce_limit("login-email", email, 10, 900)


def allow_email_request(request: Request, purpose: str, email: str) -> bool:
    enforce_limit(f"{purpose}-ip", client_ip(request), 20, 3600)
    # Suppress email-specific excess silently, including for nonexistent emails.
    return hit_limit(f"{purpose}-email", email, 3, 3600) == 0
