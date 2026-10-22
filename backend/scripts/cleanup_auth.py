"""Run from backend: uv run python -m scripts.cleanup_auth"""
from sqlalchemy import delete, func

from app.db.session import SessionLocal
from app.models.auth import AuthRateLimit, EmailActionToken, LoginSession


def main():
    with SessionLocal.begin() as db:
        for model, expiry in [
            (EmailActionToken, EmailActionToken.expires_at),
            (LoginSession, LoginSession.expires_at),
            (AuthRateLimit, AuthRateLimit.window_end),
        ]:
            db.execute(delete(model).where(expiry <= func.clock_timestamp()))
    print("Expired auth records removed.")


if __name__ == "__main__":
    main()
