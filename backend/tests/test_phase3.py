"""Essential multi-user checks. Requires a PostgreSQL test URL.

Run: TRACE_AUTH_TEST_DATABASE_URL=postgresql+psycopg://... uv run python -m pytest -q tests/test_phase3.py
Each test uses its own schema; public application tables are untouched.
"""
import hashlib
import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

TEST_URL = os.getenv("TRACE_AUTH_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.skip("Set TRACE_AUTH_TEST_DATABASE_URL to run Phase 3 checks", allow_module_level=True)
os.environ.setdefault("DATABASE_URL", TEST_URL)
os.environ.setdefault("SESSION_SECRET", "phase-three-test-only-secret-012345678901234567")

from app.api.dependencies import get_current_user
from app.api.v1.routes.workspace import router
from app.db.base import Base
from app.db.session import get_db
from app.models.auth import User
from app.models.workspace import Dataset
from app.services import workspace


@pytest.fixture()
def env(monkeypatch, tmp_path):
    schema = "trace_phase3_test_" + uuid.uuid4().hex
    admin = create_engine(TEST_URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(TEST_URL)
    @event.listens_for(engine, "connect")
    def set_schema(connection, _):
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        connection.commit()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        first = User(id=uuid.uuid4(), email="first@example.com", name="First", email_verified=True)
        second = User(id=uuid.uuid4(), email="second@example.com", name="Second", email_verified=True)
        db.add_all([first, second])
    state = SimpleNamespace(current=first)
    monkeypatch.setattr(workspace, "STORAGE_ROOT", tmp_path)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: state.current
    with TestClient(app, base_url="http://localhost") as client:
        yield SimpleNamespace(client=client, db=factory, state=state, first=first, second=second, app=app, storage=tmp_path)
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def write(env, method, path, **kwargs):
    return env.client.request(method, "/api/v1" + path, headers={"X-Trace-Client":"web"}, **kwargs)


def sample(env):
    response = write(env, "POST", "/datasets/sample")
    assert response.status_code == 200
    return response.json()


def test_sample_is_public_real_and_import_is_idempotent(env):
    first = sample(env)
    again = sample(env)
    assert first["id"] == again["id"]
    assert first["row_count"] == 244
    assert first["column_count"] == 7
    assert first["source_url"] == workspace.SOURCE_URL
    assert first["sha256"] == hashlib.sha256(workspace.SAMPLE_FILE.read_bytes()).hexdigest()
    assert "storage_key" not in first
    assert len(list(env.storage.glob("*.csv"))) == 1


def test_datasets_and_physical_copies_are_separate_per_user(env):
    first = sample(env)
    env.state.current = env.second
    assert env.client.get("/api/v1/datasets").json() == []
    assert env.client.get("/api/v1/datasets/" + first["id"]).status_code == 404
    assert write(env, "DELETE", "/datasets/" + first["id"]).status_code == 404
    second = sample(env)
    assert second["id"] != first["id"]
    assert len(list(env.storage.glob("*.csv"))) == 2
    assert len(env.client.get("/api/v1/datasets").json()) == 1


def test_cannot_attach_another_users_dataset_or_supply_owner(env):
    first = sample(env)
    env.state.current = env.second
    assert write(env, "POST", "/reports", json={"title":"Attack", "dataset_id":first["id"]}).status_code == 404
    assert write(env, "POST", "/reports", json={"title":"Attack", "dataset_id":first["id"], "owner_id":str(env.first.id)}).status_code == 422


def test_report_ownership_covers_read_rename_delete_and_listing(env):
    dataset = sample(env)
    response = write(env, "POST", "/reports", json={"title":"  Tips report  ", "dataset_id":dataset["id"]})
    assert response.status_code == 201
    report = response.json()
    assert report["title"] == "Tips report"
    env.state.current = env.second
    assert env.client.get("/api/v1/reports").json() == []
    assert env.client.get("/api/v1/reports/" + report["id"]).status_code == 404
    assert write(env, "PATCH", "/reports/" + report["id"], json={"title":"Stolen"}).status_code == 404
    assert write(env, "DELETE", "/reports/" + report["id"]).status_code == 404
    env.state.current = env.first
    assert write(env, "PATCH", "/reports/" + report["id"], json={"title":"Renamed"}).json()["title"] == "Renamed"
    assert env.client.get("/api/v1/reports/" + report["id"]).json()["title"] == "Renamed"


def test_used_dataset_cannot_be_deleted_and_unused_file_is_removed(env):
    dataset = sample(env)
    report = write(env, "POST", "/reports", json={"title":"Tips", "dataset_id":dataset["id"]}).json()
    assert write(env, "DELETE", "/datasets/" + dataset["id"]).status_code == 409
    assert len(list(env.storage.glob("*.csv"))) == 1
    assert write(env, "DELETE", "/reports/" + report["id"]).status_code == 204
    assert write(env, "DELETE", "/datasets/" + dataset["id"]).status_code == 204
    assert list(env.storage.iterdir()) == []


def test_protection_headers_validation_and_anonymous_requests(env):
    assert env.client.post("/api/v1/datasets/sample").status_code == 403
    dataset = sample(env)
    assert write(env, "POST", "/reports", json={"title":"   ", "dataset_id":dataset["id"]}).status_code == 422
    assert env.client.get("/api/v1/datasets?limit=101").status_code == 422
    del env.app.dependency_overrides[get_current_user]
    assert env.client.get("/api/v1/datasets").status_code == 401
    assert write(env, "POST", "/datasets/sample").status_code == 401
