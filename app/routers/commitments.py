"""Reviewable scope changes with a durable, single-lease 30-second pause."""
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import User
from app.project_models import ProjectStage, StageCommitment, CommitmentAdjustment
from app import commitment_service as svc
from app.practice_service import lock_user, owner

router = APIRouter(prefix="/commitments")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Disposition(Strict):
    task_id: int
    action: Literal["retain", "defer", "cancel"]


class ScopeChange(Strict):
    kind: Literal["project_outcome", "task_criteria", "condition_remove", "dependency_remove"]
    id: int | None = None
    value: str = Field(default="", max_length=4000)


class AdjustmentPlan(Strict):
    target_stage_id: int | None = None
    dispositions: list[Disposition] = Field(max_length=300)
    changes: list[ScopeChange] = Field(default_factory=list, max_length=100)


class Heartbeat(Strict):
    token: str = Field(min_length=16, max_length=100)
    visible: bool


class Reason(Strict):
    reason: str = Field(min_length=1, max_length=4000)


@router.get("/projects/{project_id}")
def get_commitment(project_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    owner(db, user.id, "project", project_id)
    stage = svc.current_stage(db, project_id)
    current = svc.commitment(db, user.id, stage.id) if stage else None
    pending = db.query(CommitmentAdjustment).filter_by(user_id=user.id, project_id=project_id,
        stage_id=stage.id if stage else -1, confirmed_at=None).order_by(CommitmentAdjustment.id.desc()).first()
    return {"notice": svc.COMMITMENT_TEXT, "current_stage_id": stage.id if stage else None,
        "commitment": {"id": current.id, "snapshot": json.loads(current.snapshot_json), "at": current.created_at} if current else None,
        "pending": svc.adjustment_payload(pending) if pending else None,
        "history": [{"id": c.id, "stage_id": c.stage_id, "at": c.created_at, "snapshot": json.loads(c.snapshot_json)}
                    for c in db.query(StageCommitment).filter_by(user_id=user.id, project_id=project_id).order_by(StageCommitment.id.desc())],
        "adjustments": [svc.adjustment_payload(a) | {"reason": a.reason} for a in db.query(CommitmentAdjustment)
                        .filter_by(user_id=user.id, project_id=project_id).order_by(CommitmentAdjustment.id.desc())]}


@router.post("/stages/{stage_id}/start")
def start_commitment(stage_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    stage = db.get(ProjectStage, stage_id)
    if not stage or stage.user_id != user.id: raise HTTPException(404, "阶段不存在")
    if stage.state != "current": raise HTTPException(409, "只能确认当前阶段承诺")
    current = svc.commitment(db, user.id, stage.id)
    if current: return {"id": current.id}
    from app.start_conditions import require_ready
    require_ready(db, user.id, "project", stage.project_id)
    current = svc.commit_stage(db, user.id, stage)
    db.commit(); return {"id": current.id}


@router.post("/projects/{project_id}/preview")
def preview(project_id: int, body: AdjustmentPlan, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = svc.preview(db, user.id, project_id, body.model_dump())
    db.commit(); return svc.adjustment_payload(row)


@router.get("/adjustments/{adjustment_id}")
def get_adjustment(adjustment_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return svc.adjustment_payload(svc.owned_adjustment(db, user.id, adjustment_id))


@router.post("/adjustments/{adjustment_id}/visible")
def visible(adjustment_id: int, body: Heartbeat, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    row = svc.owned_adjustment(db, user.id, adjustment_id)
    svc.heartbeat(db, row, body.token, body.visible)
    db.commit(); return svc.adjustment_payload(row)


@router.post("/adjustments/{adjustment_id}/confirm")
def confirm(adjustment_id: int, body: Reason, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    row = svc.owned_adjustment(db, user.id, adjustment_id)
    result = svc.confirm(db, row, body.reason)
    db.commit(); return result
