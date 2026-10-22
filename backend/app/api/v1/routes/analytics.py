import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.routes.auth import protect_write
from app.api.v1.routes.workspace import owned_dataset
from app.db.session import get_db
from app.models.auth import User
from app.schemas.analytics import EvaluateRequest
from app.services.analytics import evaluate_dataset


def no_cache(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["Analytics"], dependencies=[Depends(protect_write), Depends(no_cache)])


@router.post("/datasets/{dataset_id}/evaluate")
def evaluate(
    dataset_id: uuid.UUID, body: EvaluateRequest,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return evaluate_dataset(owned_dataset(db, dataset_id, user.id), body)
