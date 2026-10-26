"""Reviewed deletion and recovery, with account-scoped immutable batch identity."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import User
from app.project_models import ProjectDeletion
from app.practice_service import lock_user
from app import project_deletion_service as svc
from app.commitment_service import heartbeat

router = APIRouter(prefix="/deletions", tags=["项目删除与恢复"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Preview(Strict):
    kind: Literal["project", "stage", "task"]
    target_id: int = Field(gt=0)
    stage_tasks: Literal["delete", "keep"] = "delete"


class Confirm(Strict):
    reason: str = Field(default="", max_length=4000)


class Visible(Strict):
    token: str = Field(min_length=16, max_length=100)
    visible: bool


class Restore(Strict):
    with_daily: bool = False
    past_date: date | None = None
    stage_as_next: bool = False
    daily_ids: list[int] | None = Field(default=None, max_length=1000)
    daily_dates: dict[int, date] = Field(default_factory=dict)


@router.get("")
def deleted_content(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(ProjectDeletion).filter(ProjectDeletion.user_id == user.id,
        ProjectDeletion.confirmed_at.isnot(None)).order_by(ProjectDeletion.id.desc())
    return {"items": [svc.payload(db, row) for row in rows if row.restored_at is None or svc.pending_daily(db, row)]}


@router.post("/preview")
def preview(body: Preview, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = svc.preview(db, user.id, body.kind, body.target_id, stage_tasks=body.stage_tasks)
    db.commit()
    return svc.payload(db, row)


@router.post("/{batch_id}/visible")
def visible(batch_id: int, body: Visible, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    row = svc.batch(db, user.id, batch_id)
    heartbeat(db, row, body.token, body.visible)
    db.commit()
    return svc.payload(db, row)


@router.post("/{batch_id}/confirm")
def confirm(batch_id: int, body: Confirm, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    result = svc.confirm(db, svc.batch(db, user.id, batch_id), body.reason)
    db.commit()
    return result


@router.post("/{batch_id}/restore")
def restore(batch_id: int, body: Restore, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    result = svc.restore(db, svc.batch(db, user.id, batch_id), **body.model_dump())
    db.commit()
    return result
