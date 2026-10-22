from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auth import LoginSession, User
from app.services.auth.security import COOKIE_NAME, hash_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Reusable verified-session dependency for every future private API."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 128:
        raise HTTPException(401, "Not signed in")
    user = db.scalar(
        select(User).join(LoginSession, LoginSession.user_id == User.id).where(
            LoginSession.token_hash == hash_token(token),
            LoginSession.expires_at > datetime.now(timezone.utc),
            User.email_verified.is_(True),
        )
    )
    if user is None:
        raise HTTPException(401, "Session expired or invalid")
    return user
