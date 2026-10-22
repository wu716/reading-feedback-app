"""Visible readiness, condition editing and explicit project lifecycle actions."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.auth import get_current_active_user
from app.database import get_db
from app.models import DailyTask, User
from app.project_models import ExecutionConditionEvent, Project, ProjectTask, StartCondition
from app.start_conditions import (
    active_conditions, condition_snapshot, evaluate_condition, readiness, record_event,
    require_ready, resolve_owner, validate_dependency_graph,
)

router = APIRouter()


class ConditionInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    kind: Literal["task", "project", "resource", "external", "time", "constraint"]
    strength: Literal["required", "reminder"] = "required"
    check_at: Literal["start", "throughout", "delivery"] = "start"
    target_id: int | None = Field(default=None, gt=0)
    required_state: Literal["completed", "delivered", "accepted"] | None = None
    not_before: datetime | None = None
    confirmation: Literal["unknown", "unmet", "met", "not_applicable"] = "unknown"
    evidence: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=4000)


class ReasonInput(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class ProjectStateInput(BaseModel):
    state: Literal["preparation", "started", "delivered", "accepted"]
    reason: str = Field(min_length=1, max_length=4000)
    acknowledge_reminders: bool = False


def nonblank(value):
    if not (value or "").strip():
        raise HTTPException(400, "请填写具体说明")
    return value.strip()


def condition_values(db, user_id, owner_kind, owner_id, body):
    fields = body.model_dump(exclude={"reason"})
    fields["title"] = nonblank(body.title)
    fields["target_kind"] = body.kind if body.kind in ("task", "project") else None
    if fields["target_kind"]:
        if not body.target_id:
            raise HTTPException(400, "请选择前置对象")
        resolve_owner(db, user_id, fields["target_kind"], body.target_id)
        if (owner_kind, owner_id) == (fields["target_kind"], body.target_id):
            raise HTTPException(400, "不能依赖自身")
        valid_states = ("completed",) if body.kind == "task" else ("delivered", "accepted")
        fields["required_state"] = body.required_state or valid_states[-1]
        if fields["required_state"] not in valid_states:
            raise HTTPException(400, "前置对象所需状态不适用")
        if body.confirmation != "unknown" or body.not_before is not None:
            raise HTTPException(400, "任务和项目依赖由系统判断，不能手动确认")
    else:
        if body.target_id or body.required_state:
            raise HTTPException(400, "此条件类型不引用前置对象")
        if body.not_before is not None:
            if body.kind != "time" or body.not_before.tzinfo is None:
                raise HTTPException(400, "允许开始时间必须包含时区且属于时间条件")
            fields["not_before"] = body.not_before.astimezone(timezone.utc).replace(tzinfo=None)
            if body.confirmation != "unknown":
                raise HTTPException(400, "日期条件由系统判断，不能手动确认")
        if body.confirmation in ("met", "not_applicable"):
            nonblank(body.evidence)
    return fields


@router.get("/readiness/{owner_kind}/{owner_id}")
def get_readiness(owner_kind: str, owner_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return readiness(db, user.id, owner_kind, owner_id)


@router.get("/conditions/{owner_kind}/{owner_id}/history")
def condition_history(owner_kind: str, owner_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    kind, row = resolve_owner(db, user.id, owner_kind, owner_id)
    owner_filter = and_(ExecutionConditionEvent.owner_kind == kind, ExecutionConditionEvent.owner_id == row.id)
    if kind == "task":
        daily_ids = db.query(DailyTask.id).filter(DailyTask.user_id == user.id, DailyTask.project_task_id == row.id)
        owner_filter = or_(owner_filter, and_(ExecutionConditionEvent.owner_kind == "daily", ExecutionConditionEvent.owner_id.in_(daily_ids)))
    events = db.query(ExecutionConditionEvent).filter(
        ExecutionConditionEvent.user_id == user.id, owner_filter,
    ).order_by(ExecutionConditionEvent.id.desc()).all()
    return {"items": [{c.name: getattr(event, c.name) for c in ExecutionConditionEvent.__table__.columns} for event in events]}


@router.post("/conditions/{owner_kind}/{owner_id:int}")
def create_condition(owner_kind: str, owner_id: int, body: ConditionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    kind, owner = resolve_owner(db, user.id, owner_kind, owner_id)
    fields = condition_values(db, user.id, kind, owner.id, body)
    for c in active_conditions(db, user.id, kind, owner.id):
        if fields["target_id"] and c.target_kind == fields["target_kind"] and c.target_id == fields["target_id"]:
            raise HTTPException(400, "已存在该前置关系")
    if kind == "task" and fields["target_kind"] == "task":
        from app.project_models import TaskDependency
        if db.query(TaskDependency).filter(TaskDependency.user_id == user.id, TaskDependency.task_id == owner.id,
                                           TaskDependency.prerequisite_id == fields["target_id"]).first():
            raise HTTPException(400, "已存在该前置关系")
    row = StartCondition(user_id=user.id, owner_kind=kind, owner_id=owner.id, **fields)
    db.add(row); db.flush()
    validate_dependency_graph(db, user.id)
    record_event(db, user.id, kind, owner.id, "condition_created", after=condition_snapshot(row), condition_id=row.id, reason=body.reason)
    db.commit()
    return evaluate_condition(db, row)


@router.put("/conditions/{condition_id}")
def update_condition(condition_id: int, body: ConditionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    row = db.get(StartCondition, condition_id)
    if row is None or row.user_id != user.id or row.removed_at is not None:
        raise HTTPException(404, "条件不存在")
    resolve_owner(db, user.id, row.owner_kind, row.owner_id)
    reason = nonblank(body.reason)
    before = condition_snapshot(row)
    fields = condition_values(db, user.id, row.owner_kind, row.owner_id, body)
    if fields["target_id"] and any(c.id != row.id and (c.target_kind, c.target_id) == (fields["target_kind"], fields["target_id"])
                                    for c in active_conditions(db, user.id, row.owner_kind, row.owner_id)):
        raise HTTPException(400, "已存在该前置关系")
    # Changing a referenced object would erase the meaning of its history.
    if (row.kind, row.target_id) != (fields["kind"], fields["target_id"]):
        raise HTTPException(400, "更换条件类型或前置对象时，请说明原因移除后重新添加")
    for key, value in fields.items():
        setattr(row, key, value)
    db.flush(); validate_dependency_graph(db, user.id)
    record_event(db, user.id, row.owner_kind, row.owner_id, "condition_updated", before,
                 condition_snapshot(row), reason, row.id)
    db.commit()
    return evaluate_condition(db, row)


@router.post("/conditions/{condition_id}/remove")
def remove_condition(condition_id: int, body: ReasonInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    row = db.get(StartCondition, condition_id)
    if row is None or row.user_id != user.id or row.removed_at is not None:
        raise HTTPException(404, "条件不存在")
    resolve_owner(db, user.id, row.owner_kind, row.owner_id)
    reason, before = nonblank(body.reason), condition_snapshot(row)
    row.removed_at = datetime.utcnow()
    record_event(db, user.id, row.owner_kind, row.owner_id, "condition_removed", before, condition_snapshot(row), reason, row.id)
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/execution-state")
def change_project_state(project_id: int, body: ProjectStateInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    _, project = resolve_owner(db, user.id, "project", project_id)
    reason, previous = nonblank(body.reason), project.execution_state
    decision = None
    if previous == body.state:
        return {"state": previous}
    if body.state == "preparation" and previous == "started":
        raise HTTPException(409, "执行中的项目保持执行状态；需要补齐条件时，可以在当前项目添加筹备任务")
    if body.state == "started":
        result = require_ready(db, user.id, "project", project.id)
        decision = result
        if result["reminders"] and not body.acknowledge_reminders:
            raise HTTPException(409, "请先阅读开始条件中的提醒事项并确认")
        project.started_at = project.started_at or datetime.utcnow()
    elif body.state in ("delivered", "accepted"):
        if previous not in (("started",) if body.state == "delivered" else ("delivered",)):
            raise HTTPException(409, "请先正式开始，再交付，最后验收")
        decision = require_ready(db, user.id, "project", project.id, purpose="delivery")
        incomplete = db.query(ProjectTask).filter(ProjectTask.project_id == project.id, ProjectTask.user_id == user.id,
            ProjectTask.deleted_at.is_(None), ProjectTask.state != "completed").count()
        if incomplete:
            raise HTTPException(409, "仍有未完成任务，不能把未完成范围记为已交付或已验收")
    project.execution_state = body.state
    record_event(db, user.id, "project", project.id, "project_state_changed",
                 {"state": previous}, {"state": body.state, "readiness": decision}, reason)
    db.commit()
    return {"state": project.execution_state, "started_at": project.started_at}
