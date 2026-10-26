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
from app.project_models import StageCommitment, StageCommitmentDraft, CommitmentAdjustment
from app import commitment_service as svc
from app.practice_service import lock_user, owner

router = APIRouter(prefix="/commitments")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Disposition(Strict):
    task_id: int
    action: Literal["retain", "defer", "cancel"]


class ScopeChange(Strict):
    kind: Literal["project_outcome", "task_criteria", "condition_remove", "dependency_remove", "commitment_statement"]
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


class DraftInput(Strict):
    statement: str = Field(max_length=2000)
    revision: int = Field(ge=0)


class CommitmentInput(Strict):
    statement: str | None = Field(default=None, max_length=2000)
    draft_revision: int | None = Field(default=None, ge=0)
    base_commitment_id: int | None = None


@router.get("/projects/{project_id}")
def get_commitment(project_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    owner(db, user.id, "project", project_id)
    stage = svc.current_stage(db, project_id)
    current = svc.commitment(db, user.id, stage.id) if stage else None
    saved = svc.draft(db, user.id, stage.id) if stage else None
    versions = db.query(StageCommitment).filter_by(user_id=user.id, project_id=project_id).order_by(StageCommitment.id).all()
    numbers = {c.id: i + 1 for i, c in enumerate(versions)}
    pending = db.query(CommitmentAdjustment).filter_by(user_id=user.id, project_id=project_id,
        stage_id=stage.id if stage else -1, confirmed_at=None).filter(CommitmentAdjustment.fingerprint != "").order_by(CommitmentAdjustment.id.desc()).first()
    return {"notice": svc.COMMITMENT_TEXT, "current_stage_id": stage.id if stage else None,
        "commitment": {"id": current.id, "version": numbers[current.id], "snapshot": json.loads(current.snapshot_json), "at": current.created_at} if current else None,
        "draft": {"statement": saved.statement, "revision": saved.revision, "updated_at": saved.updated_at} if saved else None,
        "scope": svc.stage_snapshot(db, user.id, stage) if stage else None,
        "pending": svc.adjustment_payload(pending) if pending else None,
        "history": [{"id": c.id, "version": numbers[c.id], "stage_id": c.stage_id,
                     "original_stage_id": c.stage_original_id or c.stage_id,
                     "stage_title": c.stage_title_snapshot, "stage_deleted": c.stage_id is None,
                     "at": c.created_at, "snapshot": json.loads(c.snapshot_json)}
                    for c in reversed(versions)],
        "adjustments": [svc.adjustment_payload(a) | {"reason": a.reason} for a in db.query(CommitmentAdjustment)
                        .filter_by(user_id=user.id, project_id=project_id).order_by(CommitmentAdjustment.id.desc())]}


@router.post("/stages/{stage_id}/start")
def start_commitment(stage_id: int, body: CommitmentInput | None = None, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    stage = svc.owned_current_stage(db, user.id, stage_id)
    current = svc.commitment(db, user.id, stage.id)
    statement = body.statement.strip() if body and body.statement is not None else None
    if statement is not None:
        if not statement: raise HTTPException(400, "请先写下本轮承诺")
        old_statement = json.loads(current.snapshot_json).get("statement", "") if current else ""
        if old_statement:
            if statement == old_statement: return {"id": current.id}
            raise HTTPException(409, "承诺文字已确认，请通过“调整当前承诺”说明后果并保留版本")
        if "base_commitment_id" in body.model_fields_set and body.base_commitment_id != (current.id if current else None):
            raise HTTPException(409, "当前任务范围已变化，请重新读取并核对后确认")
        saved = svc.draft(db, user.id, stage.id)
        if body.draft_revision is not None and body.draft_revision != (saved.revision if saved else 0):
            raise HTTPException(409, "草稿已在另一页面更新，请先读取服务器草稿")
    elif current:
        return {"id": current.id}
    from app.start_conditions import require_ready
    require_ready(db, user.id, "project", stage.project_id)
    current = svc.commit_stage(db, user.id, stage, statement=statement)
    db.commit(); return {"id": current.id}


@router.put("/stages/{stage_id}/draft")
def save_draft(stage_id: int, body: DraftInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    lock_user(db, user.id)
    stage = svc.owned_current_stage(db, user.id, stage_id)
    current = svc.commitment(db, user.id, stage.id)
    if current and json.loads(current.snapshot_json).get("statement"):
        raise HTTPException(409, "本轮承诺已经确认，请使用“调整当前承诺”")
    saved = svc.draft(db, user.id, stage.id)
    if body.revision != (saved.revision if saved else 0):
        raise HTTPException(409, "草稿已在另一页面更新，请先读取服务器草稿")
    if saved is None:
        saved = StageCommitmentDraft(user_id=user.id, project_id=stage.project_id, stage_id=stage.id)
        db.add(saved)
    saved.statement, saved.revision, saved.updated_at = body.statement, body.revision + 1, datetime.utcnow()
    db.commit()
    return {"statement": saved.statement, "revision": saved.revision, "updated_at": saved.updated_at}


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
