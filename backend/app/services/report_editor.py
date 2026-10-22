import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import update

from app.api.v1.routes.workspace import owned_dataset, owned_report
from app.models.workspace import Report
from app.schemas.analytics import EvaluateRequest
from app.schemas.report_editor import ReportDefinition
from app.schemas.workspace import DatasetResponse
from app.services.analytics import evaluate_dataset
from app.services.csv_ingestion import ensure_profile


def version_check(report, dataset, body):
    if report.revision != body.expected_revision or dataset.sha256 != body.expected_sha256:
        raise HTTPException(409, "This report changed in another tab. Your draft is kept here. Reload the saved version before saving again.")


def definition_of(report):
    try:
        return ReportDefinition.model_validate(report.definition)
    except ValidationError:
        raise HTTPException(409, "Saved report definition is invalid. Restore a valid report backup.") from None


def context(db, report_id, owner_id):
    report = owned_report(db, report_id, owner_id)
    dataset = owned_dataset(db, report.dataset_id, owner_id)
    return report, dataset


def editor_response(report, dataset, profile):
    return {
        "id": str(report.id), "title": report.title, "revision": report.revision,
        "dataset_id": str(report.dataset_id), "definition": definition_of(report).model_dump(mode="json"),
        "dataset": DatasetResponse.model_validate(dataset).model_dump(mode="json"), "profile": profile,
    }


def validate_references(definition, profile):
    keys = {column["key"] for column in profile["columns"]}
    for block in definition.blocks:
        for name in ["column", "group_by", "sort_by"]:
            value = getattr(block, name, None)
            if value is not None and value not in keys:
                raise HTTPException(422, f"Block {block.id} references an unknown column. Reload its dataset profile.")
    for item in definition.filters:
        if item.column not in keys:
            raise HTTPException(422, "A report filter references an unknown column.")


def save_editor(db, report_id, owner_id, body):
    report, dataset = context(db, report_id, owner_id)
    version_check(report, dataset, body)
    profile = ensure_profile(dataset)
    if not profile["analysis_ready"]:
        raise HTTPException(422, "Fix and re-upload the unreadable CSV before editing its report.")
    validate_references(body.definition, profile)
    data = body.definition.model_dump(mode="json")
    if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) > 64 * 1024:
        raise HTTPException(422, "Report definition exceeds 64 KiB. Shorten notes or remove blocks.")
    # One atomic conditional UPDATE. Never accept a client-supplied owner,
    # dataset change, or revision increment. ORM title changes also bump revision.
    result = db.execute(update(Report).where(
        Report.id == report.id, Report.owner_id == owner_id, Report.revision == body.expected_revision,
    ).values(title=body.title, definition=data, revision=Report.revision + 1)
        .returning(Report.id).execution_options(synchronize_session=False)).scalar_one_or_none()
    if result is None:
        db.rollback()
        raise HTTPException(409, "This report changed while saving. Your draft is kept here; reload the saved version.")
    db.commit()
    db.refresh(report)
    return editor_response(report, dataset, profile)


def block_issues(definition, profile):
    """Preflight for useful block-local errors; actual math remains Phase 5."""
    columns = {column["key"]: column for column in profile["columns"]}
    issues = []
    for block in definition.blocks:
        if block.type == "note":
            continue
        error = None
        if block.type != "table":
            kind = columns[block.column]["type"] if block.column else None
            if block.operation in {"sum", "average"} and kind != "number":
                error = "Sum and average need a number column."
            elif block.operation in {"min", "max"} and kind not in {"number", "date"}:
                error = "Min and max need a number or date column."
            elif block.type == "chart" and block.operation != "count" and kind != "number":
                error = "Chart values must be numeric. Use count for text/date columns."
            if block.group_by:
                allowed = {"category"} if block.type == "metric" else ({"number", "date"} if block.chart_type == "line" else {"category", "date"})
                if columns[block.group_by]["type"] not in allowed:
                    error = "Metric splits need a category; bar charts need category/date; line charts need number/date."
        if error:
            issues.append({"block_id": block.id, "message": error})
    return issues


def evaluate_report(db, report_id, owner_id, body):
    report, dataset = context(db, report_id, owner_id)
    version_check(report, dataset, body)
    definition = definition_of(report)
    profile = ensure_profile(dataset)
    if not profile["analysis_ready"]:
        raise HTTPException(422, "This CSV has unreadable records. Fix and re-upload it before calculating.")
    validate_references(definition, profile)
    issues = block_issues(definition, profile)
    base = {"report_id": str(report.id), "revision": report.revision, "dataset_sha256": dataset.sha256}
    if issues:
        # Do not present a partly computed report as complete. The draft can
        # still be saved, edited and reordered while these blocks are repaired.
        return base | {"complete": False, "errors": issues, "results": []}
    calculations = [block.model_dump(exclude={"title"}) for block in definition.blocks if block.type != "note"]
    if not calculations:
        return base | {"complete": True, "errors": [], "results": []}
    request = EvaluateRequest(expected_sha256=dataset.sha256, filters=definition.filters, calculations=calculations)
    response = evaluate_dataset(dataset, request)
    for item in response["results"]:
        item["receipt"].update(report_id=str(report.id), report_revision=report.revision)
    return base | response | {"complete": True, "errors": []}
