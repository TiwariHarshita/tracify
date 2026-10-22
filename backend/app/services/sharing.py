"""Frozen public-report snapshots. Public reads never resolve a Dataset or Report."""
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.workspace import owned_report
from app.models.workspace import ReportShareLink, ReportSnapshot
from app.services.auth.security import hash_token
from app.services.csv_ingestion import ensure_profile
from app.services.report_editor import evaluate_report, definition_of


def utc_now():
    return datetime.now(timezone.utc)


def create_share_link(db: Session, report_id, owner_id, body):
    report = owned_report(db, report_id, owner_id)
    if body.expires_at is not None and body.expires_at <= utc_now():
        raise HTTPException(422, "Share-link expiry must be in the future.")
    # This is the same server-side evaluator used by the editor. Never accept
    # browser supplied results, receipts, or a client-created snapshot.
    output = evaluate_report(db, report_id, owner_id, body)
    if not output["complete"]:
        raise HTTPException(422, "Fix every report block before sharing. No incomplete snapshot was created.")
    # Re-read after evaluation: an edit in another tab must not be labelled as
    # the revision that was just frozen.
    db.refresh(report)
    if report.revision != body.expected_revision:
        raise HTTPException(409, "This report changed while it was being frozen. Reload and share again.")
    profile = ensure_profile(owned_report_dataset(db, report, owner_id))
    payload = {
        "title": report.title,
        "definition": definition_of(report).model_dump(mode="json"),
        "profile": {"columns": profile["columns"]},
        "results": output["results"],
        "report_revision": report.revision,
        "dataset_sha256": output["dataset_sha256"],
        "published_at": utc_now().isoformat(),
    }
    # The URL token is returned once only. DB compromise does not expose links.
    token = secrets.token_urlsafe(32)
    snapshot = ReportSnapshot(report_id=report.id, owner_id=owner_id,
        report_revision=report.revision, dataset_sha256=output["dataset_sha256"], payload=payload)
    db.add(snapshot)
    db.flush()  # allocate snapshot.id before the link references it
    link = ReportShareLink(report_id=report.id, owner_id=owner_id, snapshot_id=snapshot.id,
        token_hash=hash_token(token), expires_at=body.expires_at)
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": str(link.id), "url_token": token, "expires_at": link.expires_at, "created_at": link.created_at}


def owned_report_dataset(db, report, owner_id):
    # Import lazily to avoid the workspace/report-editor import cycle.
    from app.api.v1.routes.workspace import owned_dataset
    return owned_dataset(db, report.dataset_id, owner_id)


def list_share_links(db: Session, report_id, owner_id):
    owned_report(db, report_id, owner_id)
    links = list(db.scalars(select(ReportShareLink).where(
        ReportShareLink.report_id == report_id, ReportShareLink.owner_id == owner_id
    ).order_by(ReportShareLink.created_at.desc())))
    # Do not expose stored hashes or internal snapshot identifiers, even to the
    # owner; the raw URL exists only in the create response.
    return [{"id": str(link.id), "expires_at": link.expires_at,
             "revoked_at": link.revoked_at, "created_at": link.created_at} for link in links]


def revoke_share_link(db: Session, report_id, link_id, owner_id):
    link = db.scalar(select(ReportShareLink).where(
        ReportShareLink.id == link_id, ReportShareLink.report_id == report_id,
        ReportShareLink.owner_id == owner_id
    ))
    if link is None:
        raise HTTPException(404, "Share link not found")
    if link.revoked_at is None:
        link.revoked_at = utc_now()
        db.commit()


def public_snapshot(db: Session, token: str):
    # A generic 404 prevents token probing from distinguishing link states.
    if len(token) > 256:
        raise HTTPException(404, "Shared report not found")
    link = db.scalar(select(ReportShareLink).where(ReportShareLink.token_hash == hash_token(token)))
    if link is None or link.revoked_at is not None or (link.expires_at and link.expires_at <= utc_now()):
        raise HTTPException(404, "Shared report not found")
    snapshot = db.get(ReportSnapshot, link.snapshot_id)
    if snapshot is None:
        raise HTTPException(404, "Shared report not found")
    return snapshot.payload
