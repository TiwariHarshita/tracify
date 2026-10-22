"""PostgreSQL integration checks; each test uses a fresh isolated schema.

Run from backend with TRACE_AUTH_TEST_DATABASE_URL set to a test PostgreSQL
database URL. No application tables in public are created, dropped, or read.
"""
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, func, select, text, update
from sqlalchemy.orm import sessionmaker

TEST_URL = os.getenv("TRACE_AUTH_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.skip("Set TRACE_AUTH_TEST_DATABASE_URL to run PostgreSQL checks", allow_module_level=True)
if not TEST_URL.startswith("postgresql+psycopg://"):
    raise RuntimeError("Use a postgresql+psycopg:// test URL")
os.environ.setdefault("DATABASE_URL", TEST_URL)
os.environ.setdefault("SESSION_SECRET", "trace-test-only-secret-01234567890123456789")

from app.api.v1.routes.auth import router
from app.db.base import Base
from app.db.session import get_db
from app.models.auth import AuthIdentity, AuthRateLimit, EmailActionToken, LoginSession, User
from app.services.auth import email_actions, oauth, rate_limit
from app.services.auth.security import hash_token, password_hasher

HEADERS = {"X-Trace-Client": "web"}
PASSWORD = "Trace-test-password-2026!"
NEW_PASSWORD = "Trace-replacement-2026!"


@pytest.fixture()
def env(monkeypatch):
    schema = "trace_auth_test_" + uuid.uuid4().hex
    admin = create_engine(TEST_URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(TEST_URL, connect_args={"options": f"-csearch_path={schema}"})
    @event.listens_for(engine, "connect")
    def set_schema(connection, _):
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        connection.commit()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    for module in (email_actions, rate_limit, oauth):
        monkeypatch.setattr(module, "SessionLocal", factory)
    messages = []
    monkeypatch.setattr(email_actions, "send_email", lambda *args: messages.append(args))
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def test_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    client = TestClient(app, base_url="http://localhost")
    yield SimpleNamespace(db=factory, client=client, messages=messages, app=app)
    client.close()
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def add_user(env, verified=True, local=True, email="member@example.com"):
    with env.db.begin() as db:
        user = User(
            email=email, name="Trace Tester", email_verified=verified,
            password_hash=password_hasher.hash(PASSWORD) if local else None,
        )
        db.add(user)
        db.flush()
        return user.id


def post(env, path, data):
    return env.client.post("/api/v1/auth" + path, json=data, headers=HEADERS)


def mailed_token(env):
    return re.search(r"#token=([A-Za-z0-9_-]{43})", env.messages[-1][2]).group(1)


def test_registration_requires_verification_and_consumes_once(env):
    registered = post(env, "/register", {
        "email": "New@Example.com", "name": "New Member", "password": PASSWORD,
    })
    assert registered.status_code == 201
    assert registered.json()["email_verified"] is False
    assert "password_hash" not in registered.json()
    token = mailed_token(env)
    with env.db() as db:
        assert db.scalar(select(EmailActionToken.token_hash)) == hash_token(token)
    denied = post(env, "/login", {"email": "new@example.com", "password": PASSWORD})
    assert denied.status_code == 403
    assert post(env, "/email/verify", {"token": token}).status_code == 200
    assert post(env, "/email/verify", {"token": token}).status_code == 400
    assert post(env, "/login", {"email": "new@example.com", "password": PASSWORD}).status_code == 200
    assert env.client.get("/api/v1/auth/me").status_code == 200


def test_reset_revokes_all_sessions_and_does_not_login(env):
    user_id = add_user(env)
    assert post(env, "/login", {"email": "member@example.com", "password": PASSWORD}).status_code == 200
    cookie = env.client.cookies.get("trace_session")
    with env.db.begin() as db:
        db.add(LoginSession(
            user_id=user_id, token_hash=hash_token("another-browser"),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        ))
    assert post(env, "/password/forgot", {"email": "member@example.com"}).status_code == 202
    token = mailed_token(env)
    assert post(env, "/password/reset", {"token": token, "new_password": NEW_PASSWORD}).status_code == 200
    with env.db() as db:
        assert db.scalar(select(func.count()).select_from(LoginSession)) == 0
    env.client.cookies.set("trace_session", cookie)
    assert env.client.get("/api/v1/auth/me").status_code == 401
    assert post(env, "/password/reset", {"token": token, "new_password": NEW_PASSWORD}).status_code == 400
    assert post(env, "/login", {"email": "member@example.com", "password": PASSWORD}).status_code == 401
    assert post(env, "/login", {"email": "member@example.com", "password": NEW_PASSWORD}).status_code == 200


def test_reset_is_not_a_provider_password_creation_flow(env):
    add_user(env, local=False)
    response = post(env, "/password/forgot", {"email": "member@example.com"})
    other = post(env, "/password/forgot", {"email": "absent@example.com"})
    assert response.status_code == other.status_code == 202
    assert response.json() == other.json()
    assert not env.messages


def test_expired_and_wrong_purpose_tokens_are_rejected(env):
    add_user(env, verified=False)
    email_actions.issue_email_action("member@example.com", "reset_password")
    token = mailed_token(env)
    assert post(env, "/email/verify", {"token": token}).status_code == 400
    with env.db.begin() as db:
        db.execute(update(EmailActionToken).values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
        ))
    assert post(env, "/password/reset", {"token": token, "new_password": NEW_PASSWORD}).status_code == 400


def test_get_pages_do_not_consume_tokens(env):
    add_user(env, verified=False)
    email_actions.issue_email_action("member@example.com", "verify_email")
    token = mailed_token(env)
    for page in ("verify-email", "reset-password"):
        response = env.client.get(f"/api/v1/auth/{page}#token={token}")
        assert response.status_code == 200
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    with env.db() as db:
        assert db.scalar(select(func.count()).select_from(EmailActionToken)) == 1
        assert db.scalar(select(User.email_verified)) is False


def test_login_email_limit_survives_failed_auth_transactions(env):
    add_user(env)
    for _ in range(10):
        assert post(env, "/login", {"email": "member@example.com", "password": "wrong"}).status_code == 401
    response = post(env, "/login", {"email": "MEMBER@example.com", "password": PASSWORD})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_login_ip_limit_spans_different_emails(env):
    for index in range(30):
        assert post(env, "/login", {"email": f"missing{index}@example.com", "password": "wrong"}).status_code == 401
    assert post(env, "/login", {"email": "another@example.com", "password": "wrong"}).status_code == 429


def test_email_cooldown_is_generic_and_does_not_send_excess(env):
    add_user(env)
    for _ in range(4):
        assert post(env, "/password/forgot", {"email": "member@example.com"}).status_code == 202
    assert len(env.messages) == 3
    for _ in range(4):
        assert post(env, "/password/forgot", {"email": "absent@example.com"}).status_code == 202
    assert len(env.messages) == 3


def test_window_expires_without_process_restart(env):
    assert rate_limit.hit_limit("test", "subject", 1, 900) == 0
    assert rate_limit.hit_limit("test", "subject", 1, 900) > 0
    with env.db.begin() as db:
        db.execute(update(AuthRateLimit).values(
            window_end=datetime.now(timezone.utc) - timedelta(seconds=1)
        ))
    assert rate_limit.hit_limit("test", "subject", 1, 900) == 0


def test_mail_failure_returns_generic_response_without_live_token(env, monkeypatch):
    add_user(env)
    def fail(*args):
        raise OSError("simulated SMTP failure")
    monkeypatch.setattr(email_actions, "send_email", fail)
    assert post(env, "/password/forgot", {"email": "member@example.com"}).status_code == 202
    with env.db() as db:
        assert db.scalar(select(func.count()).select_from(EmailActionToken)) == 0


def test_csrf_header_origin_and_password_length(env):
    add_user(env)
    assert env.client.post("/api/v1/auth/password/forgot", json={"email": "member@example.com"}).status_code == 403
    assert env.client.post("/api/v1/auth/password/forgot", json={"email": "member@example.com"}, headers={**HEADERS, "Origin": "https://wrong.example"}).status_code == 403
    assert post(env, "/password/reset", {"token": "a"*43, "new_password": "short"}).status_code == 422


def test_oauth_new_account_is_verified_and_collision_still_blocked(env):
    token = oauth.finish_oauth_login("github", "12345", "oauth@example.com", "OAuth", None)
    with env.db() as db:
        user = db.scalar(select(User).where(User.email == "oauth@example.com"))
        assert user.email_verified is True
        assert user.password_hash is None
        original_id = user.id
    oauth.finish_oauth_login("github", "12345", "changed@example.com", "OAuth", token)
    with env.db() as db:
        user = db.get(User, original_id)
        assert user.email == "oauth@example.com"
    with pytest.raises(HTTPException) as conflict:
        oauth.finish_oauth_login("google", "other", "oauth@example.com", "Other", None)
    assert conflict.value.status_code == 409


native_pg = pytest.mark.skipif(
    os.getenv("TRACE_AUTH_EMBEDDED_DB") == "1",
    reason="Requires native multi-connection PostgreSQL row-lock semantics",
)


@native_pg
def test_parallel_token_redemption_succeeds_once(env):
    add_user(env)
    email_actions.issue_email_action("member@example.com", "reset_password")
    token = mailed_token(env)
    def attempt(_):
        try:
            email_actions.consume_email_action(token, "reset_password", NEW_PASSWORD)
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [200, 400]


@native_pg
def test_parallel_limiter_does_not_lose_updates(env):
    def attempt(_):
        return rate_limit.hit_limit("parallel", "same-subject", 5, 900) == 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(20))) == 5


@native_pg
def test_old_password_login_cannot_survive_concurrent_reset(env):
    user_id = add_user(env)
    email_actions.issue_email_action("member@example.com", "reset_password")
    token = mailed_token(env)
    def login_attempt():
        with TestClient(env.app, base_url="http://localhost") as client:
            return client.post(
                "/api/v1/auth/login",
                json={"email": "member@example.com", "password": PASSWORD},
                headers=HEADERS,
            ).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        login_future = pool.submit(login_attempt)
        reset_future = pool.submit(
            email_actions.consume_email_action, token, "reset_password", NEW_PASSWORD
        )
        assert login_future.result() in {200, 401}
        reset_future.result()
    with env.db() as db:
        assert db.scalar(select(func.count()).select_from(LoginSession).where(
            LoginSession.user_id == user_id
        )) == 0
