import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.routes.auth import protect_write
from app.db.session import get_db
from app.models.auth import User
from app.schemas.report_editor import ReportVersion, SaveReport
from app.services.csv_ingestion import ensure_profile
from app.services.report_editor import context, editor_response, evaluate_report, save_editor


def no_cache(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["Report editor"], dependencies=[Depends(protect_write), Depends(no_cache)])


@router.get("/reports/{report_id}/editor")
def load(report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    report, dataset = context(db, report_id, user.id)
    return editor_response(report, dataset, ensure_profile(dataset))


@router.patch("/reports/{report_id}/editor")
def save(report_id: uuid.UUID, body: SaveReport, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return save_editor(db, report_id, user.id, body)


@router.post("/reports/{report_id}/evaluate")
def evaluate(report_id: uuid.UUID, body: ReportVersion, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return evaluate_report(db, report_id, user.id, body)
