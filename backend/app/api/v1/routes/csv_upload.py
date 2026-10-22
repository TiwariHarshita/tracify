import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.routes.auth import protect_write
from app.api.v1.routes.workspace import owned_dataset
from app.db.session import get_db
from app.models.auth import User
from app.schemas.workspace import DatasetResponse
from app.services.csv_ingestion import ensure_profile, read_page, upload_dataset, verified_source
from app.services.csv_parser import MAX_BYTES


def no_cache(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/datasets", tags=["CSV"], dependencies=[Depends(protect_write), Depends(no_cache)])


@router.post("/upload", response_model=DatasetResponse)
def upload(
    file: UploadFile = File(...), delimiter: str = Form(","),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        if not (file.filename or "").lower().endswith(".csv"):
            raise HTTPException(400, "Choose a .csv file containing UTF-8 text.")
        data = file.file.read(MAX_BYTES + 1)
        return upload_dataset(db, user.id, data, file.filename, delimiter)
    finally:
        file.file.close()


@router.get("/{dataset_id}/profile")
def profile(dataset_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ensure_profile(owned_dataset(db, dataset_id, user.id))


@router.get("/{dataset_id}/preview")
def preview(
    dataset_id: uuid.UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return read_page(owned_dataset(db, dataset_id, user.id), "rows.jsonl", offset, limit)


@router.get("/{dataset_id}/errors")
def errors(
    dataset_id: uuid.UUID, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return read_page(owned_dataset(db, dataset_id, user.id), "errors.jsonl", offset, limit)


@router.get("/{dataset_id}/raw")
def original_csv(dataset_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dataset = owned_dataset(db, dataset_id, user.id)
    return Response(
        content=verified_source(dataset), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="trace-original.csv"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
