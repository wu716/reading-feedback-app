"""Choose a stage, edit a daily draft, then save linked scopes in one transaction."""
from datetime import date, datetime
import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import DailyTask, User
from app.project_models import Project, ProjectStage, ProjectTask
from app.stage_schedule_models import DailyProjectPlan

router = APIRouter(prefix="/project-stages", tags=["从项目阶段安排日程"])


class DayScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_key: str = Field(min_length=1, max_length=80)
    project_task_id: int | None = None
    text: str = Field(min_length=1, max_length=500)
    estimated_minutes: int | None = Field(default=None, ge=0, le=1440)
    familiarity: Literal["familiar", "unfamiliar"] | None = None
    difficulty: Literal["simple", "difficult"] | None = None
    importance: Literal["unimportant", "ordinary", "important"] | None = None

    @field_validator("text")
    @classmethod
    def clean_text(cls, value):
        if not value.strip():
            raise ValueError("请填写今天做到什么")
        return value.strip()


class StageScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_date: date
    request_key: str = Field(min_length=1, max_length=80)
    items: list[DayScope] = Field(min_length=1, max_length=200)


def owned_stage(db, user_id, stage_id):
    stage = db.query(ProjectStage).filter_by(id=stage_id, user_id=user_id).first()
    project = db.get(Project, stage.project_id) if stage else None
    if not project or project.user_id != user_id or project.deleted_at is not None or getattr(stage, "deleted_at", None) is not None:
        raise HTTPException(404, "项目阶段不存在")
    return project, stage


@router.get("")
def list_projects(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.user_id == user.id, Project.deleted_at.is_(None)).order_by(Project.id.desc()).all()
    stages = db.query(ProjectStage).filter_by(user_id=user.id).order_by(ProjectStage.position, ProjectStage.id).all()
    return {"projects": [{"id": p.id, "title": p.title, "execution_state": p.execution_state,
        "stages": [{"id": s.id, "title": s.title, "state": s.state} for s in stages
                   if s.project_id == p.id and s.state != "closed" and getattr(s, "deleted_at", None) is None]} for p in projects
        if p.execution_state not in ("delivered", "accepted") and any(s.project_id == p.id and s.state != "closed" and getattr(s, "deleted_at", None) is None for s in stages)]}


@router.get("/{stage_id}")
def preview_stage(stage_id: int, task_date: date = Query(...), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.routers.projects import task_payload
    project, stage = owned_stage(db, user.id, stage_id)
    tasks = db.query(ProjectTask).filter_by(user_id=user.id, project_id=project.id, stage_id=stage.id).filter(
        ProjectTask.deleted_at.is_(None)).order_by(ProjectTask.id).all()
    planned = {r.project_task_id: r.id for r in db.query(DailyTask).filter_by(user_id=user.id, task_date=task_date).filter(
        DailyTask.deleted_at.is_(None), DailyTask.project_task_id.in_([t.id for t in tasks])).all()}
    items = []
    for task in tasks:
        if task.state in ("completed", "cancelled"):
            continue
        payload = task_payload(db, task)
        prior = db.query(DailyTask).filter(DailyTask.user_id == user.id, DailyTask.project_task_id == task.id,
            DailyTask.task_date < task_date, DailyTask.deleted_at.is_(None)).order_by(DailyTask.task_date.desc(), DailyTask.id.desc()).first()
        payload["scheduled_daily_id"] = planned.get(task.id)
        payload["previous_progress"] = {"date": prior.task_date, "text": prior.text, "note": prior.note,
                                        "completed": bool(prior.completed)} if prior else None
        items.append(payload)
    return {"project": {"id": project.id, "title": project.title, "outcome": project.outcome},
        "stage": {"id": stage.id, "title": stage.title, "state": stage.state}, "tasks": items,
        "completed_count": sum(t.state == "completed" for t in tasks), "has_tasks": bool(tasks)}


@router.post("/{stage_id}")
def save_stage(stage_id: int, body: StageScheduleInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app import practice_service as practice
    from app.commitment_service import record_scope_addition
    from app.routers.projects import require_open_project
    from app.routers.schedule import get_or_create_schedule, next_flow_order, next_sort_order, day_payload
    practice.lock_user(db, user.id)
    project, stage = owned_stage(db, user.id, stage_id)
    request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    # A retry must return the same saved result without creating another empty-stage task.
    prior = db.query(DailyProjectPlan).filter_by(user_id=user.id, request_key=body.request_key).all()
    if prior:
        if any(p.stage_id != stage.id or p.task_date != body.task_date for p in prior):
            raise HTTPException(409, "本次保存标识已用于其他阶段或日期，请重新调入")
        if any(p.request_hash != request_hash for p in prior):
            raise HTTPException(409, "这份草稿已经保存，请重新打开阶段核对已保存内容后再修改")
        return day_payload(db, user, body.task_date)
    require_open_project(project)
    if stage.state == "closed":
        raise HTTPException(409, "阶段已结束，请重新选择阶段")
    ids = [i.project_task_id for i in body.items if i.project_task_id is not None]
    if len(set(ids)) != len(ids) or len({i.item_key for i in body.items}) != len(body.items):
        raise HTTPException(422, "同一次安排中不能重复添加任务")
    sources = {}
    # Validate the whole draft before making any writes.
    for source_id in ids:
        task = db.get(ProjectTask, source_id)
        if not task or task.user_id != user.id or task.project_id != project.id or task.stage_id != stage.id or task.deleted_at is not None:
            raise HTTPException(409, "阶段任务已变更或移除，请重新调入后保留需要的安排")
        if task.state in ("completed", "cancelled"):
            raise HTTPException(409, "项目任务已完成或取消，请重新调入")
        sources[source_id] = task
    get_or_create_schedule(db, user.id, body.task_date)
    sort_order, flow_order = next_sort_order(db, user.id, body.task_date, None), next_flow_order(db, user.id, body.task_date)
    for item in body.items:
        source = sources.get(item.project_task_id)
        if source and db.query(DailyTask.id).filter_by(user_id=user.id, task_date=body.task_date, project_task_id=source.id).filter(DailyTask.deleted_at.is_(None)).first():
            continue
        if source is None:
            source = ProjectTask(user_id=user.id, project_id=project.id, stage_id=stage.id,
                title=item.text, estimated_minutes=item.estimated_minutes,
                original_estimate_minutes=item.estimated_minutes, familiarity=item.familiarity)
            db.add(source); db.flush()
            practice.note_estimate(db, user.id, "task", source, item.estimated_minutes, created=True)
            record_scope_addition(db, user.id, source)
        daily = DailyTask(user_id=user.id, project_task_id=source.id, task_date=body.task_date,
            text=item.text, estimated_minutes=item.estimated_minutes, familiarity=item.familiarity,
            sort_order=sort_order, flow_order=flow_order, completed=False)
        db.add(daily); db.flush()
        db.add(DailyProjectPlan(daily_task_id=daily.id, user_id=user.id, task_date=body.task_date,
            project_id=project.id, stage_id=stage.id, project_title=project.title, stage_title=stage.title,
            task_title=source.title, source_estimate_minutes=source.estimated_minutes,
            request_key=body.request_key, item_key=item.item_key, request_hash=request_hash))
        db.flush()
        practice.note_estimate(db, user.id, "daily", daily, item.estimated_minutes, created=True)
        state = practice.practice(db, user.id, "daily", daily)
        state.difficulty, state.importance, state.initial_importance = item.difficulty, item.importance, item.importance
        if item.importance is not None:
            state.initial_marked_at = datetime.utcnow()
        sort_order += 1; flow_order += 1
    db.commit()
    return day_payload(db, user, body.task_date)
