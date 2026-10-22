import os
import uuid

import pytest

TEST_URL = os.getenv("TRACE_AUTH_TEST_DATABASE_URL")
if not TEST_URL:
    pytest.skip("Set TRACE_AUTH_TEST_DATABASE_URL to run the isolated PostgreSQL API checks", allow_module_level=True)
os.environ.setdefault("DATABASE_URL", TEST_URL)
os.environ.setdefault("SESSION_SECRET", "phase-five-test-only-secret-012345678901234567")

from app.api.v1.routes.analytics import router as analytics_router
from app.api.dependencies import get_current_user
from app.models.workspace import Dataset
from app.services import analytics, workspace
from app.services.csv_ingestion import artifact_path
from test_csv_api import env, upload  # Reuse Phase 4's isolated PostgreSQL fixture.


def setup(env, data=b"amount,group\n0.1,A\n0.2,B\n"):
    env.app.include_router(analytics_router,prefix="/api/v1")
    return upload(env,data).json()


def evaluate(env,item,**changes):
    body={"expected_sha256":item["sha256"],"calculations":[{"id":"total","type":"metric","operation":"sum","column":"c0"}]}
    return env.client.post(f"/api/v1/datasets/{item['id']}/evaluate",headers={"X-Trace-Client":"web"},json=body|changes)


def test_evaluate_returns_exact_value_receipt_and_no_store(env):
    item=setup(env)
    response=evaluate(env,item)
    assert response.status_code==200,response.text
    assert response.headers["cache-control"]=="no-store"
    output=response.json()["results"][0]
    assert output["result"]["rows"][0]["value"]=="0.3"
    assert output["receipt"]["dataset_id"]==item["id"]
    assert output["receipt"]["included_rows"]==2


def test_owner_anonymous_and_request_header_enforced(env):
    item=setup(env)
    env.state.current=env.second
    assert evaluate(env,item).status_code==404
    env.state.current=env.first
    assert env.client.post(f"/api/v1/datasets/{item['id']}/evaluate",json={"expected_sha256":item["sha256"],"calculations":[{"id":"n","type":"metric","operation":"count"}]}).status_code==403
    del env.app.dependency_overrides[get_current_user]
    assert evaluate(env,item).status_code==401


def test_wrong_version_and_modified_original_rejected(env):
    item=setup(env)
    assert evaluate(env,item,expected_sha256="0"*64).status_code==409
    with env.db() as db:
        dataset=db.get(Dataset,uuid.UUID(item["id"]))
        workspace.private_path(dataset.storage_key).write_bytes(b"amount,group\n999,A\n")
    assert evaluate(env,item).status_code==409


def test_bad_rows_block_calculations(env):
    item=setup(env,b"amount,group\n1,A\n2\n")
    response=evaluate(env,item)
    assert response.status_code==422
    assert "unreadable" in response.json()["detail"]


def test_sidecar_rows_cannot_change_calculations(env):
    item=setup(env)
    with env.db() as db:
        dataset=db.get(Dataset,uuid.UUID(item["id"]))
        artifact_path(dataset,"rows.jsonl").write_text('{"cells":["9999","A"]}\n')
    assert evaluate(env,item).json()["results"][0]["result"]["rows"][0]["value"]=="0.3"


def test_no_arbitrary_sql_paths_or_partial_results(env):
    item=setup(env)
    assert evaluate(env,item,sql="SELECT 1").status_code==422
    assert evaluate(env,item,path="/etc/passwd").status_code==422
    response=evaluate(env,item,calculations=[{"id":"good","type":"metric","operation":"sum","column":"c0"},{"id":"bad","type":"metric","operation":"sum","column":"c1"}])
    assert response.status_code==422
    assert "results" not in response.json()


def test_saturation_is_explicit_and_slots_release_after_errors(env, monkeypatch):
    item=setup(env)
    assert analytics.SLOTS.acquire(False)
    assert analytics.SLOTS.acquire(False)
    try:
        response=evaluate(env,item)
        assert response.status_code==429
        assert response.headers["retry-after"]=="2"
    finally:
        analytics.SLOTS.release();analytics.SLOTS.release()
    assert evaluate(env,item,calculations=[{"id":"bad","type":"metric","operation":"sum","column":"c99"}]).status_code==422
    assert evaluate(env,item).status_code==200


def test_public_sample_metric_and_chart_share_filtered_value(env):
    env.app.include_router(analytics_router,prefix="/api/v1")
    item=env.client.post("/api/v1/datasets/sample",headers={"X-Trace-Client":"web"}).json()
    response=evaluate(env,item,filters=[{"type":"category","column":"c4","values":["Sun"]}],calculations=[{"id":"m","type":"metric","operation":"sum","column":"c1"},{"id":"c","type":"chart","chart_type":"bar","operation":"sum","column":"c1","group_by":"c4"}])
    assert response.status_code==200,response.text
    metric,chart=response.json()["results"]
    assert metric["result"]["rows"][0]["value"]==chart["result"]["rows"][0]["value"]
    assert metric["receipt"]["included_rows"]==76
