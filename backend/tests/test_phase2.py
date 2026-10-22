"""Phase 2 routing checks with provider and DB boundaries stubbed.

These do not contact Google/GitHub. Run: uv run python -m pytest -q tests/test_phase2.py
"""
import ast
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from authlib.integrations.base_client import OAuthError
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from app.api.dependencies import get_current_user
from app.api.v1.routes import oauth as routes
from app.core.frontend import FrontendSettings, get_frontend_settings
from app.db.session import get_db
from app.models.auth import User
from app.services.auth.security import hash_token
from scripts.apply_phase2 import expose_retry_after, refactor_current_user


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(routes, "get_frontend_settings", lambda: SimpleNamespace(frontend_url="http://localhost:5173"))
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(backend_url="http://localhost:8000"))
    fake = SimpleNamespace(result=None, statement=None)
    def scalar(statement):
        fake.statement = statement
        return fake.result
    fake.scalar = scalar
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="phase-two-test-secret-not-for-production")
    app.include_router(routes.router, prefix="/api/v1")
    def db():
        yield fake
    app.dependency_overrides[get_db] = db

    @app.get("/private")
    def private(user: User = Depends(get_current_user)):
        return {"email": user.email}

    with TestClient(app, base_url="http://localhost", follow_redirects=False) as client:
        yield SimpleNamespace(client=client, db=fake)


class FakeProvider:
    def __init__(self, error=None):
        self.error = error
        self.options = None
        self.callback = None
    async def authorize_redirect(self, request, callback, **options):
        self.options = options
        self.callback = callback
        request.session["transaction"] = "saved"
        return RedirectResponse("https://provider.example/authorize")
    async def authorize_access_token(self, request):
        if self.error:
            raise self.error
        return {"userinfo": {"sub": "stable-subject", "email": "member@example.com", "name": "Member", "email_verified": True}}


def test_session_dependency_rejects_missing_cookie(env):
    assert env.client.get("/private").status_code == 401
    assert env.db.statement is None


def test_session_dependency_hashes_cookie_and_queries_verified_unexpired_session(env):
    env.db.result = User(id=uuid.uuid4(), email="member@example.com", name="Member", email_verified=True)
    env.client.cookies.set("trace_session", "random-token")
    response = env.client.get("/private")
    assert response.status_code == 200
    compiled = env.db.statement.compile()
    assert hash_token("random-token") in compiled.params.values()
    sql = str(compiled)
    assert "sessions.expires_at >" in sql
    assert "users.email_verified IS true" in sql


def test_session_dependency_rejects_invalid_database_session(env):
    env.client.cookies.set("trace_session", "invalid-token")
    assert env.client.get("/private").status_code == 401


def test_provider_start_preserves_pkce_nonce_and_backend_callback(env, monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(routes, "get_provider_client", lambda _: provider)
    response = env.client.get("/api/v1/auth/oauth/google/login")
    assert response.status_code == 307
    assert response.headers["location"] == "https://provider.example/authorize"
    assert provider.callback == "http://localhost:8000/api/v1/auth/oauth/google/callback"
    assert len(provider.options["code_verifier"]) >= 43
    assert provider.options["nonce"]


def test_success_sets_cookie_and_uses_fixed_frontend_app_url(env, monkeypatch):
    monkeypatch.setattr(routes, "get_provider_client", lambda _: FakeProvider())
    calls = []
    def finish(*args):
        calls.append(args)
        return "new-session-token"
    monkeypatch.setattr(routes, "finish_oauth_login", finish)
    response = env.client.get("/api/v1/auth/oauth/google/callback?next=https://wrong.example")
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/app"
    assert "trace_session=new-session-token" in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert calls[0][:4] == ("google", "stable-subject", "member@example.com", "Member")


def test_provider_unavailable_returns_safe_frontend_error(env, monkeypatch):
    def unavailable(_):
        raise HTTPException(503, "A private configuration error")
    monkeypatch.setattr(routes, "get_provider_client", unavailable)
    response = env.client.get("/api/v1/auth/oauth/github/login")
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/login?auth_error=provider_unavailable&provider=github"
    assert "private" not in response.headers["location"]


def test_collision_is_preserved_and_returns_frontend_error(env, monkeypatch):
    monkeypatch.setattr(routes, "get_provider_client", lambda _: FakeProvider())
    def conflict(*args):
        raise HTTPException(409, "Do not merge accounts")
    monkeypatch.setattr(routes, "finish_oauth_login", conflict)
    response = env.client.get("/api/v1/auth/oauth/google/callback")
    assert "auth_error=account_exists" in response.headers["location"]
    assert "trace_session=" not in response.headers.get("set-cookie", "")


def test_provider_cancelled_maps_to_a_known_frontend_code(env, monkeypatch):
    monkeypatch.setattr(routes, "get_provider_client", lambda _: FakeProvider(OAuthError(error="access_denied")))
    response = env.client.get("/api/v1/auth/oauth/google/callback")
    assert "auth_error=oauth_cancelled" in response.headers["location"]


def test_unverified_google_email_never_creates_an_app_session(env, monkeypatch):
    provider = FakeProvider()
    async def invalid(_):
        return {"userinfo":{"sub":"subject","email":"member@example.com","email_verified":False}}
    provider.authorize_access_token = invalid
    monkeypatch.setattr(routes, "get_provider_client", lambda _: provider)
    calls = []
    monkeypatch.setattr(routes, "finish_oauth_login", lambda *args: calls.append(args))
    response = env.client.get("/api/v1/auth/oauth/google/callback")
    assert "auth_error=oauth_invalid" in response.headers["location"]
    assert calls == []


@pytest.mark.parametrize("origin", [
    "https://trace.example/app", "https://user:password@trace.example",
    "https://trace.example?next=bad", "//wrong.example", "http://public.example",
])
def test_frontend_origin_rejects_paths_credentials_and_unsafe_origins(origin):
    with pytest.raises(ValidationError):
        FrontendSettings(frontend_url=origin, _env_file=None)


def test_frontend_origin_accepts_local_origin():
    assert FrontendSettings(frontend_url="http://localhost:5173/", _env_file=None).frontend_url == "http://localhost:5173"


def test_me_refactor_preserves_other_handlers_and_is_idempotent():
    original = '''from __future__ import annotations
from fastapi import Depends
@router.post("/password/reset")
def reset_password(body, request):
    consume_email_action(body.token, "reset_password", body.new_password)
@router.get("/me", response_model=UserResponse)
def current_user(request, db=Depends(get_db)):
    return old_lookup(request, db)
'''
    updated = refactor_current_user(original)
    before = next(node for node in ast.parse(original).body if isinstance(node, ast.FunctionDef) and node.name == "reset_password")
    after = next(node for node in ast.parse(updated).body if isinstance(node, ast.FunctionDef) and node.name == "reset_password")
    assert ast.dump(before) == ast.dump(after)
    assert refactor_current_user(updated) == updated
    assert updated.startswith("from __future__ import annotations")


def test_cors_patch_preserves_allowed_origins_credentials_and_existing_exposed_headers():
    source = 'app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, expose_headers=["X-Request-ID"])\n'
    updated = expose_retry_after(source)
    call = ast.parse(updated).body[0].value
    values = {item.arg: ast.dump(item.value) for item in call.keywords}
    assert values['allow_credentials'] == ast.dump(ast.Constant(value=True))
    assert 'allowed_origins' in values['allow_origins']
    assert 'X-Request-ID' in values['expose_headers']
    assert 'Retry-After' in values['expose_headers']
    assert expose_retry_after(updated) == updated


def test_cors_patch_adds_exposed_header_when_absent():
    source = '''app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
)'''
    updated = expose_retry_after(source)
    assert 'expose_headers=["Retry-After"]' in updated
    assert expose_retry_after(updated) == updated
