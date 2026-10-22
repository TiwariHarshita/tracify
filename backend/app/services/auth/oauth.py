from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.auth import AuthIdentity, LoginSession, User
from app.services.auth.security import hash_token, new_session_token


def finish_oauth_login(
    provider: str, subject: str, email: str, name: str,
    old_session_token: str | None,
) -> str:
    token, expires = new_session_token()
    try:
        with SessionLocal.begin() as db:
            identity = db.scalar(select(AuthIdentity).where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_subject == subject,
            ))
            if identity is not None:
                user = db.scalar(select(User).where(
                    User.id == identity.user_id
                ).with_for_update())
                if user is None:
                    raise HTTPException(401, "Account unavailable")
                # Current verified provider email can verify the stored address
                # only if it matches. Never silently change the stored email.
                if email == user.email:
                    user.email_verified = True
            else:
                existing_user = db.scalar(select(User).where(User.email == email))
                if existing_user is not None:
                    raise HTTPException(
                        409, "An account already uses this email. Sign in using its existing method. Linking requires a separate authenticated flow."
                    )
                # Callback already required Google's email_verified or
                # GitHub's primary AND verified email before calling us.
                user = User(
                    email=email, name=name, password_hash=None, email_verified=True
                )
                db.add(user)
                db.flush()
                db.add(AuthIdentity(
                    user_id=user.id, provider=provider, provider_subject=subject
                ))
            if old_session_token:
                db.execute(delete(LoginSession).where(
                    LoginSession.token_hash == hash_token(old_session_token)
                ))
            db.add(LoginSession(
                user_id=user.id, token_hash=hash_token(token), expires_at=expires
            ))
        return token
    except IntegrityError:
        raise HTTPException(409, "Account creation conflicted. Try signing in again.") from None
