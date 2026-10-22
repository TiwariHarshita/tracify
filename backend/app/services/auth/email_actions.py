import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.auth import EmailActionToken, LoginSession, User
from app.services.auth.mailer import send_email
from app.services.auth.security import hash_token, password_hasher

logger = logging.getLogger(__name__)
TTL_SECONDS = {"verify_email": 24 * 3600, "reset_password": 30 * 60}


def issue_email_action(email: str, purpose: str):
    """Background task: same public response whether eligible or not."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    try:
        with SessionLocal.begin() as db:
            user = db.scalar(select(User).where(User.email == email).with_for_update())
            if user is None or user.password_hash is None:
                return
            if purpose == "verify_email" and user.email_verified:
                return
            now = db.scalar(select(func.clock_timestamp()))
            db.add(EmailActionToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=token_hash,
                expires_at=now + timedelta(seconds=TTL_SECONDS[purpose]),
            ))
        path = "verify-email" if purpose == "verify_email" else "reset-password"
        # The fragment is not sent to the backend in a GET request/access log.
        link = (
            f"{get_settings().backend_url.rstrip('/')}/api/v1/auth/{path}"
            f"#{urlencode({'token': raw_token})}"
        )
        if purpose == "verify_email":
            subject = "Verify your Trace email"
            body = f"Open this link and choose Verify email:\n\n{link}\n\nIt expires in 24 hours. If you did not request it, ignore this email."
        else:
            subject = "Reset your Trace password"
            body = f"Open this link to choose a new password:\n\n{link}\n\nIt expires in 30 minutes. If you did not request it, ignore this email."
        send_email(email, subject, body)
    except Exception:
        # No raw tokens, message contents, recipient, or exception text in logs.
        logger.warning("Email action delivery failed: %s", purpose)
        try:
            with SessionLocal.begin() as db:
                db.execute(delete(EmailActionToken).where(
                    EmailActionToken.token_hash == token_hash
                ))
        except Exception:
            logger.warning("Email action cleanup failed")


def consume_email_action(raw_token: str, purpose: str, new_password: str | None = None):
    # Expensive hashing happens before taking locks; this endpoint is IP limited.
    new_hash = password_hasher.hash(new_password) if new_password is not None else None
    with SessionLocal.begin() as db:
        user_id = db.scalar(select(EmailActionToken.user_id).where(
            EmailActionToken.token_hash == hash_token(raw_token),
            EmailActionToken.purpose == purpose,
        ))
        if user_id is None:
            raise HTTPException(400, "Link is invalid or expired")
        # All account mutations/login use this lock first. Token is rechecked
        # after the lock, so simultaneous redemption can only succeed once.
        user = db.scalar(select(User).where(User.id == user_id).with_for_update())
        action = db.scalar(select(EmailActionToken).where(
            EmailActionToken.token_hash == hash_token(raw_token),
            EmailActionToken.purpose == purpose,
        ).with_for_update())
        now = db.scalar(select(func.clock_timestamp()))
        if user is None or action is None or action.expires_at <= now:
            raise HTTPException(400, "Link is invalid or expired")
        if purpose == "verify_email":
            user.email_verified = True
        else:
            if user.password_hash is None or new_hash is None:
                raise HTTPException(400, "Link is invalid or expired")
            user.password_hash = new_hash
            # A reset signs every browser out; never automatically logs in.
            db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        # Consume this and all outstanding tokens of the same purpose.
        db.execute(delete(EmailActionToken).where(
            EmailActionToken.user_id == user.id,
            EmailActionToken.purpose == purpose,
        ))
        recipient = user.email
    return recipient


def notify_password_changed(email: str):
    try:
        send_email(
            email,
            "Your Trace password was changed",
            "Your Trace password was changed and all existing sessions were signed out. "
            "If this was not you, use password recovery immediately.",
        )
    except Exception:
        logger.warning("Password change notification delivery failed")
