import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.api.dependencies import get_current_user
from app.api.v1.routes.auth import protect_write
from app.db.session import get_db
from app.models.auth import User
from app.models.workspace import Dataset, Report
from app.schemas.workspace import DatasetResponse, ReportCreate, ReportResponse, ReportTitle
from app.services.workspace import import_sample, remove_private_file
from app.services.csv_ingestion import ensure_analyzable

def no_cache(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["Workspace"], dependencies=[Depends(protect_write), Depends(no_cache)])


def owned_dataset(db: Session, dataset_id: uuid.UUID, owner_id: uuid.UUID) -> Dataset:
    item = db.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.owner_id == owner_id))
    if item is None:
        raise HTTPException(404, "Dataset not found")
    return item


def owned_report(db: Session, report_id: uuid.UUID, owner_id: uuid.UUID) -> Report:
    item = db.scalar(select(Report).where(Report.id == report_id, Report.owner_id == owner_id))
    if item is None:
        raise HTTPException(404, "Report not found")
    return item


@router.post("/datasets/sample", response_model=DatasetResponse)
def add_sample(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return import_sample(db, user.id)


@router.get("/datasets", response_model=list[DatasetResponse])
def list_datasets(
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=100),
):
    return list(db.scalars(select(Dataset).where(Dataset.owner_id == user.id)
        .order_by(Dataset.created_at.desc(), Dataset.id).limit(limit)))


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return owned_dataset(db, dataset_id, user.id)


@router.delete("/datasets/{dataset_id}", status_code=204, response_class=Response)
def delete_dataset(dataset_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = owned_dataset(db, dataset_id, user.id)
    if db.scalar(select(Report.id).where(Report.dataset_id == dataset_id).limit(1)):
        raise HTTPException(409, "Delete reports using this dataset first.")
    storage_key = item.storage_key
    db.delete(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Delete reports using this dataset first.") from None
    remove_private_file(storage_key)
    return Response(status_code=204)


@router.post("/reports", response_model=ReportResponse, status_code=201)
def create_report(body: ReportCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dataset = owned_dataset(db, body.dataset_id, user.id)
    ensure_analyzable(dataset)
    report = Report(owner_id=user.id, dataset_id=body.dataset_id, title=body.title)
    db.add(report)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Dataset changed. Reload your workspace and try again.") from None
    db.refresh(report)
    return report


@router.get("/reports", response_model=list[ReportResponse])
def list_reports(
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=100),
):
    return list(db.scalars(select(Report).where(Report.owner_id == user.id)
        .order_by(Report.created_at.desc(), Report.id).limit(limit)))


@router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return owned_report(db, report_id, user.id)


@router.patch("/reports/{report_id}", response_model=ReportResponse)
def rename_report(body: ReportTitle, report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report = owned_report(db, report_id, user.id)
    report.title = body.title
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(409, "This report changed. Reload your workspace before renaming.") from None
    db.refresh(report)
    return report


@router.delete("/reports/{report_id}", status_code=204, response_class=Response)
def delete_report(report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned_report(db, report_id, user.id))
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(409, "This report changed. Reload before deleting.") from None
    return Response(status_code=204)
