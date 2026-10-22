import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.routes.auth import protect_write
from app.db.session import get_db
from app.models.auth import User
from app.schemas.report_editor import CreateShareLink
from app.services.sharing import create_share_link, list_share_links, public_snapshot, revoke_share_link

private = APIRouter(tags=["Report sharing"], dependencies=[Depends(protect_write)])
public = APIRouter(tags=["Public reports"])

def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"

@private.post("/reports/{report_id}/share-links", status_code=201, dependencies=[Depends(no_store)])
def create(report_id: uuid.UUID, body: CreateShareLink, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return create_share_link(db, report_id, user.id, body)

@private.get("/reports/{report_id}/share-links", dependencies=[Depends(no_store)])
def list_links(report_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list_share_links(db, report_id, user.id)

@private.delete("/reports/{report_id}/share-links/{link_id}", status_code=204, response_class=Response, dependencies=[Depends(no_store)])
def revoke(report_id: uuid.UUID, link_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    revoke_share_link(db, report_id, link_id, user.id)
    return Response(status_code=204)

@public.get("/public/shares/{token}", dependencies=[Depends(no_store)])
def get_public(token: str, db: Session = Depends(get_db)):
    return public_snapshot(db, token)
