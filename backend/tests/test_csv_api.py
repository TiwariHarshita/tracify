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
from app.api.v1.routes.csv_upload import router as csv_router
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
    app.include_router(csv_router, prefix="/api/v1")
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


from app.services.csv_ingestion import artifact_path
from app.services.csv_parser import MAX_BYTES


def upload(env, data, delimiter=",", filename="public-data.csv"):
    return env.client.post("/api/v1/datasets/upload", headers={"X-Trace-Client":"web"},
        files={"file":(filename,data,"text/csv")},data={"delimiter":delimiter})


def test_upload_profile_and_original_bytes_preserved_and_bad_records_block_reports(env):
    data=b"amount,date,group\n1,2026-10-20,A\n2,2026-10-21,B\n3,missing-field\n"
    response=upload(env,data)
    assert response.status_code==200
    item=response.json()
    profile=env.client.get(f"/api/v1/datasets/{item['id']}/profile").json()
    assert profile["total_records"]==3 and profile["readable_rows"]==2 and profile["unreadable_rows"]==1
    assert profile["analysis_ready"] is False
    assert env.client.get(f"/api/v1/datasets/{item['id']}/raw").content==data
    report=env.client.post("/api/v1/reports",headers={"X-Trace-Client":"web"},json={"dataset_id":item["id"],"title":"Blocked"})
    assert report.status_code==422
    assert "unreadable" in report.json()["detail"]


def test_all_csv_endpoints_enforce_owner_and_anonymous_access(env):
    item=upload(env,b"a,b\n1,2\n").json()
    env.state.current=env.second
    for suffix in ["profile","preview","errors","raw"]:
        assert env.client.get(f"/api/v1/datasets/{item['id']}/{suffix}").status_code==404
    del env.app.dependency_overrides[get_current_user]
    assert upload(env,b"a,b\n1,2\n").status_code==401


def test_all_errors_are_pageable_not_dropped_after_first_page(env):
    item=upload(env,b"a,b\n"+b"only-one-field\n"*61).json()
    first=env.client.get(f"/api/v1/datasets/{item['id']}/errors?limit=50").json()
    second=env.client.get(f"/api/v1/datasets/{item['id']}/errors?offset=50&limit=50").json()
    assert first["total"]==second["total"]==61
    assert len(first["items"])==50 and len(second["items"])==11
    assert [x["record_number"] for x in first["items"]+second["items"]]==list(range(1,62))


def test_legacy_public_sample_is_profiled_and_ready_without_a_migration(env):
    item=env.client.post("/api/v1/datasets/sample",headers={"X-Trace-Client":"web"}).json()
    profile=env.client.get(f"/api/v1/datasets/{item['id']}/profile")
    assert profile.status_code==200
    assert profile.json()["readable_rows"]==244
    assert profile.json()["error_count"]==0
    assert profile.json()["columns"][0]["type"]=="number"


def test_rejected_files_leave_no_dataset_or_files(env):
    for data in [b"",b"\xff",b"a,a\n1,2\n",b"x"*(MAX_BYTES+1)]:
        assert upload(env,data).status_code in {400,413}
    with env.db() as db:
        assert db.scalar(select(Dataset)) is None
    assert list(env.storage.iterdir())==[]


def test_semicolon_config_survives_cache_rebuild_and_cannot_be_silently_changed(env):
    data=b"name;amount\nA;12\n"
    item=upload(env,data,";").json()
    assert upload(env,data,";").json()["id"]==item["id"]
    assert upload(env,data,",").status_code==409
    with env.db() as db:
        dataset=db.get(Dataset,uuid.UUID(item["id"]))
        artifact_path(dataset,"rows.jsonl").unlink()
    rebuilt=env.client.get(f"/api/v1/datasets/{item['id']}/profile").json()
    assert rebuilt["delimiter"]==";" and len(rebuilt["columns"])==2


def test_delete_removes_source_and_all_sidecars(env):
    item=upload(env,b"a,b\n1,2\n").json()
    assert len(list(env.storage.iterdir()))==4
    result=env.client.delete(f"/api/v1/datasets/{item['id']}",headers={"X-Trace-Client":"web"})
    assert result.status_code==204
    assert list(env.storage.iterdir())==[]


def test_upload_write_protection_and_preview_limit(env):
    assert env.client.post("/api/v1/datasets/upload",files={"file":("data.csv",b"a\n1\n","text/csv")}).status_code==403
    item=upload(env,b"a\n1\n").json()
    assert env.client.get(f"/api/v1/datasets/{item['id']}/preview?limit=101").status_code==422


def test_source_hash_is_checked_even_when_profile_is_cached(env):
    item=upload(env,b"a,b\n1,2\n").json()
    with env.db() as db:
        dataset=db.get(Dataset,uuid.UUID(item["id"]))
        workspace.private_path(dataset.storage_key).write_bytes(b"a,b\n99,100\n")
    for suffix in ["profile","preview","errors","raw"]:
        assert env.client.get(f"/api/v1/datasets/{item['id']}/{suffix}").status_code==409
