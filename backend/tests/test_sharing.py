"""Frozen, public sharing checks. Uses the isolated PostgreSQL fixture."""
import os
from datetime import datetime, timedelta, timezone

import pytest

TEST_URL = os.getenv("TRACE_AUTH_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.skip("Set TRACE_AUTH_TEST_DATABASE_URL for isolated PostgreSQL checks", allow_module_level=True)
os.environ.setdefault("DATABASE_URL", TEST_URL)
os.environ.setdefault("SESSION_SECRET", "share-test-only-secret-012345678901234567")

from app.api.v1.routes.report_editor import router as editor_router
from app.api.v1.routes.sharing import private, public
from app.models.workspace import ReportShareLink
from test_csv_api import env, upload

HEADERS = {"X-Trace-Client": "web"}


def setup(env):
    env.app.include_router(editor_router, prefix="/api/v1")
    env.app.include_router(private, prefix="/api/v1")
    env.app.include_router(public, prefix="/api/v1")
    dataset = upload(env, b"amount,day\n1,Sun\n2,Sat\n3,Sun\n").json()
    report = env.client.post("/api/v1/reports", headers=HEADERS,
        json={"title": "Frozen report", "dataset_id": dataset["id"]}).json()
    definition = {"version": 1, "filters": [], "blocks": [
        {"id": "total", "type": "metric", "title": "Total", "operation": "sum", "column": "c0"},
        {"id": "note", "type": "note", "title": "Context", "text": "Snapshot note"},
    ]}
    saved = env.client.patch(f"/api/v1/reports/{report['id']}/editor", headers=HEADERS,
        json={"title": "Frozen report", "definition": definition, "expected_revision": 1,
              "expected_sha256": dataset["sha256"]})
    assert saved.status_code == 200, saved.text
    return report, dataset


def share(env, report, dataset, **changes):
    return env.client.post(f"/api/v1/reports/{report['id']}/share-links", headers=HEADERS,
        json={"expected_revision": 2, "expected_sha256": dataset["sha256"], "expires_at": None} | changes)


def test_public_link_returns_only_frozen_server_output_and_survives_later_edits(env):
    report, dataset = setup(env)
    response = share(env, report, dataset)
    assert response.status_code == 201, response.text
    issued = response.json()
    public_response = env.client.get("/api/v1/public/shares/" + issued["url_token"])
    assert public_response.status_code == 200
    payload = public_response.json()
    assert payload["title"] == "Frozen report"
    assert payload["results"][0]["result"]["rows"][0]["value"] == "6"
    assert "storage_key" not in str(payload) and "source_url" not in str(payload)
    assert public_response.headers["cache-control"] == "no-store"
    listing = env.client.get(f"/api/v1/reports/{report['id']}/share-links").json()
    assert listing[0]["id"] == issued["id"] and "token_hash" not in listing[0] and "url_token" not in listing[0]
    # Editing the draft after publication cannot mutate the frozen viewer result.
    env.client.patch(f"/api/v1/reports/{report['id']}/editor", headers=HEADERS,
        json={"title": "Changed draft", "definition": {"version": 1, "filters": [], "blocks": []},
              "expected_revision": 2, "expected_sha256": dataset["sha256"]})
    assert env.client.get("/api/v1/public/shares/" + issued["url_token"]).json()["title"] == "Frozen report"
    with env.db() as db:
        stored = db.get(ReportShareLink, issued["id"])
        assert stored.token_hash != issued["url_token"]


def test_revoke_and_other_owner_access_are_denied(env):
    report, dataset = setup(env)
    issued = share(env, report, dataset).json()
    env.state.current = env.second
    assert env.client.get(f"/api/v1/reports/{report['id']}/share-links").status_code == 404
    assert env.client.delete(f"/api/v1/reports/{report['id']}/share-links/{issued['id']}", headers=HEADERS).status_code == 404
    env.state.current = env.first
    assert env.client.delete(f"/api/v1/reports/{report['id']}/share-links/{issued['id']}", headers=HEADERS).status_code == 204
    assert env.client.get("/api/v1/public/shares/" + issued["url_token"]).status_code == 404


def test_expired_link_cannot_be_opened(env):
    report, dataset = setup(env)
    issued = share(env, report, dataset).json()
    with env.db() as db:
        link = db.get(ReportShareLink, issued["id"])
        link.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    response = env.client.get("/api/v1/public/shares/" + issued["url_token"])
    assert response.status_code == 404
