"""Personal projects, actual work intervals, reflection, and reusable processes."""

from datetime import date, datetime, timedelta, timezone
import json
import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.execution_service import budget_seconds, execution_plan, settle_expired
from app.models import DailyTask, TimeLogNode, User
from app.schedule_todos import sync_task_reminder
from app.project_models import (
    Goal, ProcessTemplate, Project, ProjectStage, ProjectTask, TaskChecklistItem,
    TaskDependency, TimeActivityAssessment, WorkSession,
)
from app.start_conditions import readiness, record_event, require_ready, validate_dependency_graph
from app.routers.start_conditions import router as conditions_router
from app.routers.practice import router as practice_router
from app.routers.commitments import router as commitments_router
from app import practice_service
from app.commitment_service import guard_scope, record_scope_addition

router = APIRouter(prefix="/projects", tags=["个人项目"])
router.include_router(conditions_router)
router.include_router(practice_router)
router.include_router(commitments_router)


def fail(message: str, code: int = 400):
    raise HTTPException(status_code=code, detail=message)


def required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        fail("内容不能为空")
    return cleaned


def require_open_project(project):
    if project.execution_state in ("delivered", "accepted"):
        fail("项目已交付。添加工作前请先说明原因并重新开始项目", 409)


def owned(db: Session, model, row_id: int, user_id: int):
    row = db.query(model).filter(model.id == row_id, model.user_id == user_id).first()
    if row is None or getattr(row, "deleted_at", None) is not None:
        fail("记录不存在", 404)
    return row


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        fail("时间必须包含时区")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def stamp(value):
    return value.isoformat() + "Z" if isinstance(value, datetime) else value


class GoalInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    horizon_end: date | None = None


class ProjectInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    outcome: str | None = Field(default=None, max_length=4000)
    goal_id: int | None = None


class StageInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    stage_id: int | None = None
    familiarity: Literal["familiar", "unfamiliar"] | None = None
    execution_role: Literal["formal", "preparation"] = "formal"
    estimated_minutes: int | None = Field(default=None, ge=0, le=100000)
    goal_reason: str | None = Field(default=None, max_length=4000)
    acceptance_criteria: str | None = Field(default=None, max_length=4000)
    rehearsal_note: str | None = Field(default=None, max_length=4000)
    blocker_note: str | None = Field(default=None, max_length=4000)
    steps: list[str] = Field(default_factory=list, max_length=50)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    stage_id: int | None = None
    familiarity: Literal["familiar", "unfamiliar"] | None = None
    estimated_minutes: int | None = Field(default=None, ge=0, le=100000)
    goal_reason: str | None = Field(default=None, max_length=4000)
    acceptance_criteria: str | None = Field(default=None, max_length=4000)
    rehearsal_note: str | None = Field(default=None, max_length=4000)
    blocker_note: str | None = Field(default=None, max_length=4000)
    variance_reason: str | None = Field(default=None, max_length=4000)
    steps: list[str] | None = Field(default=None, max_length=50)


class DependencyInput(BaseModel):
    prerequisite_id: int


class CompletionInput(BaseModel):
    result: Literal["completed", "partial", "rework"]
    outcome_note: str | None = Field(default=None, max_length=4000)
    variance_reason: str | None = Field(default=None, max_length=4000)
    checklist_exception: str | None = Field(default=None, max_length=4000)


class ChecklistInput(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class StageChangeInput(BaseModel):
    decision: Literal["continue", "adjust", "close"]
    reason: str | None = Field(default=None, max_length=4000)


class ScheduleInput(BaseModel):
    task_date: date


class GoalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    horizon_end: date | None = None


def task_payload(db: Session, row: ProjectTask) -> dict:
    prerequisites = db.query(TaskDependency).filter(TaskDependency.task_id == row.id).all()
    blockers = [
        dep.prerequisite_id for dep in prerequisites
        if (prior := db.query(ProjectTask).filter(ProjectTask.id == dep.prerequisite_id).first())
        and (prior.state != "completed" or prior.deleted_at is not None)
    ]
    checks = db.query(TaskChecklistItem).filter(TaskChecklistItem.task_id == row.id).order_by(TaskChecklistItem.position, TaskChecklistItem.id).all()
    linked_daily = db.query(DailyTask.id).filter(DailyTask.user_id == row.user_id, DailyTask.project_task_id == row.id)
    sessions = db.query(WorkSession).filter(
        WorkSession.user_id == row.user_id,
        or_(WorkSession.project_task_id == row.id,
            and_(WorkSession.project_task_id.is_(None), WorkSession.daily_task_id.in_(linked_daily))),
        WorkSession.kind == "work", WorkSession.ended_at.isnot(None)
    ).all()
    actual = round(sum((s.ended_at - s.started_at).total_seconds() for s in sessions) / 60, 2)
    ready = readiness(db, row.user_id, "task", row.id)
    return {
        "id": row.id, "project_id": row.project_id, "stage_id": row.stage_id,
        "title": row.title, "state": row.state, "familiarity": row.familiarity,
        "execution_role": row.execution_role, "readiness": ready,
        "practice": practice_service.task_payload(db, row.user_id, "task", row),
        "original_estimate_minutes": row.original_estimate_minutes,
        "estimated_minutes": row.estimated_minutes, "actual_minutes": actual,
        "scheduled_dates": [str(d[0]) for d in db.query(DailyTask.task_date).filter(DailyTask.user_id == row.user_id,
            DailyTask.project_task_id == row.id, DailyTask.deleted_at.is_(None)).distinct().order_by(DailyTask.task_date).all()],
        "difference_minutes": round(actual - row.original_estimate_minutes, 2) if row.original_estimate_minutes is not None else None,
        "goal_reason": row.goal_reason, "acceptance_criteria": row.acceptance_criteria,
        "rehearsal_note": row.rehearsal_note, "blocker_note": row.blocker_note,
        "steps": json.loads(row.steps_json or "[]"),
        "outcome_note": row.outcome_note, "variance_reason": row.variance_reason,
        "prerequisite_ids": [dep.prerequisite_id for dep in prerequisites],
        "dependencies": [{"id": dep.id, "prerequisite_id": dep.prerequisite_id} for dep in prerequisites],
        "blocked_by": blockers, "can_start": ready["can_start"],
        "checklist": [{"id": c.id, "text": c.text, "done": c.done, "group": c.purpose,
                       "not_applicable": c.not_applicable_reason} for c in checks],
    }


@router.get("/overview")
def overview(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    settle_expired(db, user.id)
    db.commit()
    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.deleted_at.is_(None)).order_by(Goal.id.desc()).all()
    projects = db.query(Project).filter(Project.user_id == user.id, Project.deleted_at.is_(None)).order_by(Project.id.desc()).all()
    result = []
    for p in projects:
        stages = db.query(ProjectStage).filter(ProjectStage.project_id == p.id).order_by(ProjectStage.position, ProjectStage.id).all()
        tasks = db.query(ProjectTask).filter(ProjectTask.project_id == p.id, ProjectTask.deleted_at.is_(None)).order_by(ProjectTask.id).all()
        result.append({
            "id": p.id, "title": p.title, "outcome": p.outcome, "goal_id": p.goal_id, "status": p.status,
            "execution_state": p.execution_state, "started_at": stamp(p.started_at),
            "readiness": readiness(db, user.id, "project", p.id),
            "stages": [{"id": s.id, "title": s.title, "state": s.state, "position": s.position, "closed_reason": s.closed_reason} for s in stages],
            "tasks": [task_payload(db, t) for t in tasks],
        })
    return {"goals": [{"id": g.id, "title": g.title, "horizon_end": g.horizon_end, "status": g.status} for g in goals], "projects": result}


@router.post("/goals")
def create_goal(body: GoalInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = Goal(user_id=user.id, title=required_text(body.title), horizon_end=body.horizon_end)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "title": row.title, "horizon_end": row.horizon_end}


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: int, body: GoalUpdate, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    practice_service.lock_user(db, user.id)
    row = owned(db, Goal, goal_id, user.id)
    before = {"title": row.title, "horizon_end": row.horizon_end}
    if "title" in body.model_fields_set:
        if body.title is None: fail("目标名称不能为空")
        row.title = required_text(body.title)
    if "horizon_end" in body.model_fields_set: row.horizon_end = body.horizon_end
    practice_service.event(db, user.id, "goal", row.id, "goal_revision", {"before": before,
        "after": {"title": row.title, "horizon_end": row.horizon_end}, "source": "目标编辑入口，未填写修订原因"})
    db.commit()
    return {"id": row.id, "title": row.title, "horizon_end": row.horizon_end}


@router.post("")
def create_project(body: ProjectInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if body.goal_id is not None:
        owned(db, Goal, body.goal_id, user.id)
    row = Project(user_id=user.id, title=required_text(body.title), outcome=body.outcome, goal_id=body.goal_id,
                  execution_state="preparation")
    db.add(row); db.flush()
    db.add_all([
        ProjectStage(user_id=user.id, project_id=row.id, title="当前阶段", position=0, state="current"),
        ProjectStage(user_id=user.id, project_id=row.id, title="下一阶段", position=1, state="next"),
    ])
    db.commit(); db.refresh(row)
    return {"id": row.id, "title": row.title}


@router.post("/{project_id}/stages")
def add_stage(project_id: int, body: StageInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    owned(db, Project, project_id, user.id)
    stages = db.query(ProjectStage).filter(ProjectStage.project_id == project_id).all()
    row = ProjectStage(user_id=user.id, project_id=project_id, title=required_text(body.title), position=max((s.position for s in stages), default=-1) + 1)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "title": row.title, "state": row.state}


@router.post("/stages/{stage_id}/activate")
def activate_stage(stage_id: int, body: StageChangeInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    practice_service.lock_user(db, user.id)
    target = owned(db, ProjectStage, stage_id, user.id)
    project = owned(db, Project, target.project_id, user.id)
    current = db.query(ProjectStage).filter(ProjectStage.project_id == project.id, ProjectStage.state == "current").first()
    if body.decision == "continue":
        return {"id": current.id if current else target.id, "state": "current" if current else target.state}
    # Internal sequential prerequisites are checked when each task starts; they
    # must not prevent entering a stage containing the whole sequence.
    require_ready(db, user.id, "project", project.id)
    from app.commitment_service import commitment, commit_stage, require_stage_ready
    if target.state != "next": fail("只能交接到下一阶段", 409)
    require_stage_ready(db, user.id, target)
    if current and current.id != target.id:
        incomplete = db.query(ProjectTask).filter(ProjectTask.stage_id == current.id, ProjectTask.state.notin_(["completed", "cancelled"]), ProjectTask.deleted_at.is_(None)).count()
        if incomplete and commitment(db, user.id, current.id):
            fail("当前承诺尚未完成，请在“调整当前承诺”中逐项交接并完成30秒暂停", 409)
        if incomplete and not (body.reason or "").strip(): fail("交接未完成的草稿时请说明去向和原因", 409)
        if incomplete:
            fail("请先逐项处理未完成任务，再交接阶段", 409)
        current.state, current.closed_reason, current.closed_at = "closed", body.reason, datetime.utcnow()
    target.state = "current"
    commit_stage(db, user.id, target)
    db.flush()
    if not db.query(ProjectStage).filter_by(project_id=project.id, state="next").first():
        db.add(ProjectStage(user_id=user.id, project_id=project.id, title="下一阶段", state="next", position=target.position + 1))
    db.commit()
    return {"id": target.id, "state": target.state}


@router.post("/{project_id}/tasks")
def create_task(project_id: int, body: TaskInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    require_open_project(owned(db, Project, project_id, user.id))
    if body.stage_id is not None:
        stage = owned(db, ProjectStage, body.stage_id, user.id)
        if stage.project_id != project_id or stage.state == "closed": fail("阶段不属于此项目或已结束")
    fields = body.model_dump(exclude={"steps"})
    row = ProjectTask(user_id=user.id, project_id=project_id, **fields)
    row.title = required_text(row.title)
    row.original_estimate_minutes = body.estimated_minutes
    row.steps_json = json.dumps(clean_items(body.steps), ensure_ascii=False)
    db.add(row); db.flush()
    practice_service.note_estimate(db, user.id, "task", row, body.estimated_minutes, created=True)
    record_scope_addition(db, user.id, row)
    db.commit(); db.refresh(row)
    return task_payload(db, row)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdate, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    practice_service.lock_user(db, user.id)
    row = owned(db, ProjectTask, task_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    steps = changes.pop("steps", None)
    if "stage_id" in changes and changes["stage_id"] != row.stage_id:
        guard_scope(db, user.id, row)
    if "acceptance_criteria" in changes and changes["acceptance_criteria"] != row.acceptance_criteria:
        guard_scope(db, user.id, row, include_completed=True)
    if "estimated_minutes" in changes:
        practice_service.note_estimate(db, user.id, "task", row, changes["estimated_minutes"], "任务内容中修订")
    if "stage_id" in changes and changes["stage_id"] is not None:
        stage = owned(db, ProjectStage, changes["stage_id"], user.id)
        if stage.project_id != row.project_id or stage.state == "closed": fail("阶段不属于此项目或已结束")
    if "title" in changes:
        if changes["title"] is None: fail("任务名称不能为空")
        changes["title"] = required_text(changes["title"])
    for key, value in changes.items(): setattr(row, key, value)
    if steps is not None: row.steps_json = json.dumps(clean_items(steps), ensure_ascii=False)
    if "title" in changes:
        db.query(DailyTask).filter(DailyTask.user_id == user.id, DailyTask.project_task_id == row.id,
                                   DailyTask.deleted_at.is_(None)).update({"text": row.title})
        for daily in db.query(DailyTask).filter(DailyTask.user_id == user.id, DailyTask.project_task_id == row.id).all():
            sync_task_reminder(db, daily)
    db.commit()
    return task_payload(db, row)


@router.post("/tasks/{task_id}/dependencies")
def add_dependency(task_id: int, body: DependencyInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    task = owned(db, ProjectTask, task_id, user.id)
    prior = owned(db, ProjectTask, body.prerequisite_id, user.id)
    if task.id == prior.id or task.project_id != prior.project_id: fail("前置任务必须是同项目的另一任务")
    from app.start_conditions import active_conditions
    if any(c.target_kind == "task" and c.target_id == prior.id for c in active_conditions(db, user.id, "task", task.id)):
        fail("已存在该前置关系")
    edges = db.query(TaskDependency).filter(TaskDependency.project_id == task.project_id).all()
    if any(e.task_id == task.id and e.prerequisite_id == prior.id for e in edges):
        return task_payload(db, task)
    graph = {}
    for edge in edges: graph.setdefault(edge.task_id, set()).add(edge.prerequisite_id)
    pending = [prior.id]
    seen = set()
    while pending:
        node = pending.pop()
        if node == task.id: fail("任务依赖不能形成环")
        if node not in seen:
            seen.add(node); pending.extend(graph.get(node, ()))
    db.add(TaskDependency(user_id=user.id, project_id=task.project_id, task_id=task.id, prerequisite_id=prior.id))
    db.flush()
    validate_dependency_graph(db, user.id)
    record_event(db, user.id, "task", task.id, "dependency_added", after={"prerequisite_id": prior.id})
    db.commit()
    return task_payload(db, task)


@router.delete("/tasks/{task_id}/dependencies/{prerequisite_id}")
def remove_dependency(task_id: int, prerequisite_id: int, reason: str | None = None,
                      user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    task = owned(db, ProjectTask, task_id, user.id)
    guard_scope(db, user.id, task)
    row = db.query(TaskDependency).filter(TaskDependency.user_id == user.id, TaskDependency.task_id == task.id, TaskDependency.prerequisite_id == prerequisite_id).first()
    if row is None: fail("依赖不存在", 404)
    if not (reason or "").strip(): fail("移除前置条件会改变可执行状态，请更新页面并说明原因", 409)
    if len(reason) > 4000: fail("说明不能超过4000字")
    record_event(db, user.id, "task", task.id, "dependency_removed", before={"prerequisite_id": prerequisite_id}, reason=reason.strip())
    db.delete(row); db.commit()
    return task_payload(db, task)


@router.post("/tasks/{task_id}/checklist")
def add_checklist(task_id: int, body: ChecklistInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    task = owned(db, ProjectTask, task_id, user.id)
    count = db.query(TaskChecklistItem).filter(TaskChecklistItem.task_id == task.id).count()
    row = TaskChecklistItem(user_id=user.id, task_id=task.id, text=required_text(body.text), position=count)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "text": row.text, "done": row.done}


@router.patch("/checklist/{item_id}")
def toggle_checklist(item_id: int, done: bool, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = owned(db, TaskChecklistItem, item_id, user.id)
    row.done = done; db.commit()
    return {"id": row.id, "done": row.done}


@router.post("/tasks/{task_id}/finish")
def finish_task(task_id: int, body: CompletionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    result = apply_task_completion(task_id, body, user, db)
    db.commit()
    return result


def apply_task_completion(task_id, body, user, db):
    settle_expired(db, user.id)
    row = owned(db, ProjectTask, task_id, user.id)
    if body.result == "completed":
        require_ready(db, user.id, "task", row.id, purpose="delivery")
        practice_service.require_checklist(db, user.id, "task", row, body.checklist_exception)
    else:
        project = owned(db, Project, row.project_id, user.id)
        if project.execution_state in ("delivered", "accepted"):
            if not (body.outcome_note or "").strip(): fail("重新打开已交付任务时，请说明原因", 409)
            record_event(db, user.id, "project", project.id, "project_state_changed",
                         {"state": project.execution_state}, {"state": "started"}, body.outcome_note)
            project.execution_state = "started"
    row.state = body.result
    row.completed_at = datetime.utcnow() if body.result == "completed" else None
    row.outcome_note = body.outcome_note
    row.variance_reason = body.variance_reason
    linked = db.query(DailyTask).filter(DailyTask.user_id == user.id, DailyTask.project_task_id == row.id, DailyTask.deleted_at.is_(None)).all()
    from app.routers.schedule import refresh_parent_completion
    for daily in linked:
        daily.completed = body.result == "completed"
        refresh_parent_completion(db, user.id, daily)
        sync_task_reminder(db, daily)
    for day in {daily.task_date for daily in linked}:
        for daily in db.query(DailyTask).filter(DailyTask.user_id == user.id,
                DailyTask.task_date == day, DailyTask.legacy_todo_id.isnot(None), DailyTask.deleted_at.is_(None)).all():
            sync_task_reminder(db, daily)
    if body.result == "completed":
        for active in practice_service.task_sessions(db, user.id, "task", row.id):
            if active.ended_at is None:
                active.ended_at = max(datetime.utcnow(), active.started_at + timedelta(microseconds=1))
        plan = execution_plan(db, user.id)
        paused = db.get(WorkSession, plan.paused_session_id) if plan.paused_session_id else None
        if paused and paused.project_task_id == row.id:
            plan.paused_session_id = None
            plan.remaining_seconds = None
    unchecked = db.query(TaskChecklistItem).filter(TaskChecklistItem.task_id == row.id, TaskChecklistItem.done.is_(False)).count()
    db.flush()
    return {"task": task_payload(db, row), "unchecked_count": unchecked}


@router.post("/tasks/{task_id}/schedule")
def schedule_task(task_id: int, body: ScheduleInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    task = owned(db, ProjectTask, task_id, user.id)
    existing = db.query(DailyTask).filter(DailyTask.user_id == user.id, DailyTask.project_task_id == task.id,
                                        DailyTask.task_date == body.task_date, DailyTask.deleted_at.is_(None)).first()
    if existing:
        return {"id": existing.id, "project_task_id": task.id, "task_date": existing.task_date}
    from app.routers.schedule import get_or_create_schedule, next_flow_order, next_sort_order
    get_or_create_schedule(db, user.id, body.task_date)
    row = DailyTask(user_id=user.id, project_task_id=task.id, task_date=body.task_date, text=task.title,
                    completed=task.state == "completed", sort_order=next_sort_order(db, user.id, body.task_date, None),
                    flow_order=next_flow_order(db, user.id, body.task_date),
                    estimated_minutes=task.estimated_minutes, familiarity=task.familiarity)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "project_task_id": task.id, "task_date": row.task_date}


class StartSessionInput(BaseModel):
    acknowledge_reminders: bool = False
    project_task_id: int | None = None
    daily_task_id: int | None = None
    kind: Literal["work", "break"] = "work"
    planned_minutes: int = Field(default=20, ge=1, le=180)
    planned_seconds: int | None = Field(default=None, ge=1, le=10800)
    label: str | None = Field(default=None, max_length=500)


class ManualSessionInput(BaseModel):
    project_task_id: int | None = None
    daily_task_id: int | None = None
    time_log_node_id: int | None = None
    source: Literal["manual", "moment"] = "manual"
    kind: Literal["work", "break"] = "work"
    started_at: datetime
    ended_at: datetime
    label: str | None = Field(default=None, max_length=500)
    correction_note: str | None = Field(default=None, max_length=2000)


class StopSessionInput(BaseModel):
    ended_at: datetime | None = None
    pause: bool = False


class SessionCorrectionInput(BaseModel):
    started_at: datetime
    ended_at: datetime
    correction_note: str = Field(min_length=1, max_length=2000)


class AssessmentInput(BaseModel):
    goal_id: int | None = None
    importance: Literal["unimportant", "ordinary", "important"] | None = None
    interesting: bool | None = None
    note: str | None = Field(default=None, max_length=2000)


class SwitchSessionInput(StartSessionInput):
    from_session_id: int


class ExecutionInput(BaseModel):
    queue: list[str] = Field(max_length=100)
    work_minutes: int = Field(default=20, ge=1, le=180)
    break_minutes: int = Field(default=5, ge=1, le=180)


def plan_payload(db, user_id):
    plan = execution_plan(db, user_id)
    paused = db.get(WorkSession, plan.paused_session_id) if plan.paused_session_id else None
    daily_ids = [int(key.split(":")[1]) for key in json.loads(plan.queue_json) if key.startswith("daily:")]
    daily_tasks = db.query(DailyTask).filter(DailyTask.user_id == user_id, DailyTask.id.in_(daily_ids), DailyTask.deleted_at.is_(None)).all() if daily_ids else []
    return {"queue": json.loads(plan.queue_json), "server_now": stamp(datetime.utcnow()), "daily_tasks": [{"id": t.id, "text": t.text,
            "completed": t.completed, "project_task_id": t.project_task_id, "task_date": str(t.task_date),
            "readiness": readiness(db, user_id, "daily", t.id)} for t in daily_tasks], "work_minutes": plan.work_minutes,
            "break_minutes": plan.break_minutes, "remaining_seconds": plan.remaining_seconds,
            "paused": session_payload(paused) if paused else None}


@router.get("/execution")
def get_execution(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    settle_expired(db, user.id)
    result = plan_payload(db, user.id)
    db.commit()
    return result


@router.put("/execution")
def save_execution(body: ExecutionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    settle_expired(db, user.id)
    seen, queue = set(), []
    for key in body.queue:
        kind, _, raw_id = key.partition(":")
        if kind not in ("project", "daily") or not raw_id.isdecimal(): fail("任务队列格式错误")
        row = owned(db, ProjectTask if kind == "project" else DailyTask, int(raw_id), user.id)
        identity = ("project", row.project_task_id) if kind == "daily" and row.project_task_id else (kind, row.id)
        if identity not in seen:
            seen.add(identity)
            queue.append(key)
    plan = execution_plan(db, user.id)
    plan.queue_json = json.dumps(queue)
    plan.work_minutes, plan.break_minutes = body.work_minutes, body.break_minutes
    result = plan_payload(db, user.id)
    db.commit()
    return result


@router.post("/execution/resume")
def resume_execution(acknowledge_reminders: bool = False, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    settle_expired(db, user.id)
    plan = execution_plan(db, user.id)
    if not plan.paused_session_id or not plan.remaining_seconds: fail("没有可恢复的时间片", 409)
    old = owned(db, WorkSession, plan.paused_session_id, user.id)
    body = StartSessionInput(project_task_id=old.project_task_id, daily_task_id=old.daily_task_id,
                             acknowledge_reminders=acknowledge_reminders,
                             kind=old.kind, label=old.label, planned_minutes=old.planned_minutes or 20,
                             planned_seconds=plan.remaining_seconds)
    return start_session(body, user, db)


@router.post("/execution/discard-pause")
def discard_pause(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    settle_expired(db, user.id)
    plan = execution_plan(db, user.id)
    plan.paused_session_id = None
    plan.remaining_seconds = None
    db.commit()
    return {"ok": True}


class DailyProjectInput(BaseModel):
    project_id: int


@router.post("/daily/{daily_id}/project")
def promote_daily(daily_id: int, body: DailyProjectInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    daily = owned(db, DailyTask, daily_id, user.id)
    project = owned(db, Project, body.project_id, user.id)
    if daily.project_task_id:
        return task_payload(db, owned(db, ProjectTask, daily.project_task_id, user.id))
    require_open_project(project)
    if db.query(DailyTask).filter(DailyTask.parent_id == daily.id, DailyTask.deleted_at.is_(None)).first():
        fail("请将可以直接执行的子任务纳入项目")
    stage = db.query(ProjectStage).filter(ProjectStage.project_id == project.id, ProjectStage.state == "current").first()
    task = ProjectTask(user_id=user.id, project_id=project.id, stage_id=stage.id if stage else None,
                       title=daily.text, estimated_minutes=daily.estimated_minutes,
                       original_estimate_minutes=daily.estimated_minutes, familiarity=daily.familiarity,
                       state="completed" if daily.completed else "pending", steps_json=daily.steps_json or "[]",
                       blocker_note=daily.common_problems, acceptance_criteria=daily.acceptance_criteria)
    db.add(task); db.flush()
    for position, item in enumerate(json.loads(daily.checklist_json or "[]")):
        db.add(TaskChecklistItem(user_id=user.id, task_id=task.id, text=item["text"], position=position, done=item["done"],
                                purpose=item.get("group", "delivery"), not_applicable_reason=item.get("not_applicable")))
    daily.project_task_id = task.id
    old_practice = db.query(practice_service.TaskPractice).filter_by(user_id=user.id, owner_kind="daily", owner_id=daily.id).first()
    if old_practice:
        old_practice.owner_kind, old_practice.owner_id = "task", task.id
        task.original_estimate_minutes = old_practice.original_estimate
    for e in practice_service.events(db, user.id, "daily", daily.id):
        e.owner_kind, e.owner_id = "task", task.id
    record_scope_addition(db, user.id, task)
    db.flush()
    validate_dependency_graph(db, user.id)
    # Existing daily intervals belong to the same task; preserve their original dates and durations.
    db.query(WorkSession).filter(WorkSession.user_id == user.id, WorkSession.daily_task_id == daily.id,
                                WorkSession.project_task_id.is_(None)).update({"project_task_id": task.id})
    db.commit()
    return task_payload(db, task)


class TemplateInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    steps: list[str] = Field(default_factory=list, max_length=50)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    common_problems: str | None = Field(default=None, max_length=4000)
    acceptance_criteria: str | None = Field(default=None, max_length=4000)


class InstantiateInput(BaseModel):
    project_id: int
    stage_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)


class ScheduleTemplateInput(BaseModel):
    task_date: date


@router.post("/templates/{template_id}/schedule")
def schedule_template(template_id: int, body: ScheduleTemplateInput,
                      user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.routers.schedule import next_sort_order, next_flow_order, get_or_create_schedule
    db.query(User).filter(User.id == user.id).with_for_update().first()
    template = owned(db, ProcessTemplate, template_id, user.id)
    get_or_create_schedule(db, user.id, body.task_date)
    task = DailyTask(user_id=user.id, task_date=body.task_date, text=template.title,
        sort_order=next_sort_order(db, user.id, body.task_date, None),
        flow_order=next_flow_order(db, user.id, body.task_date), steps_json=template.steps_json,
        checklist_json=json.dumps([{"text":text,"done":False} for text in json.loads(template.checklist_json or "[]")], ensure_ascii=False),
        common_problems=template.common_problems, acceptance_criteria=template.acceptance_criteria)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "task_date": task.task_date}


def validate_session_links(db: Session, user_id: int, task_id: int | None, daily_id: int | None, node_id: int | None = None):
    if task_id is not None: owned(db, ProjectTask, task_id, user_id)
    if daily_id is not None:
        daily = owned(db, DailyTask, daily_id, user_id)
        if task_id is not None and daily.project_task_id != task_id:
            fail("日程任务与项目任务不匹配")
    if node_id is not None: owned(db, TimeLogNode, node_id, user_id)


def assert_no_overlap(db: Session, user_id: int, start: datetime, end: datetime, exclude_id: int | None = None):
    if end <= start: fail("结束时间必须晚于开始时间")
    if (end - start).total_seconds() > 24 * 3600: fail("单个片段不能超过24小时；请拆分补记")
    query = db.query(WorkSession).filter(
        WorkSession.user_id == user_id, WorkSession.started_at < end,
        or_(WorkSession.ended_at.is_(None), WorkSession.ended_at > start),
    )
    if exclude_id is not None: query = query.filter(WorkSession.id != exclude_id)
    if query.first(): fail("与已有片段重叠，请先更正时间", 409)


def session_payload(row: WorkSession, assessment: TimeActivityAssessment | None = None) -> dict:
    return {
        "id": row.id, "project_task_id": row.project_task_id, "daily_task_id": row.daily_task_id,
        "time_log_node_id": row.time_log_node_id, "label": row.label,
        "kind": row.kind, "source": row.source, "started_at": stamp(row.started_at),
        "ended_at": stamp(row.ended_at), "planned_minutes": row.planned_minutes,
        "planned_seconds": budget_seconds(row),
        "deadline_at": stamp(row.started_at + timedelta(seconds=budget_seconds(row))) if row.source == "timer" else None,
        "duration_minutes": round((row.ended_at - row.started_at).total_seconds() / 60, 2) if row.ended_at else None,
        "correction_note": row.correction_note,
        "practice_snapshot": json.loads(row.practice_snapshot_json or "{}"),
        "assessment": None if assessment is None else {
            "goal_id": assessment.goal_id, "goal_title_snapshot": assessment.goal_title_snapshot,
            "importance": assessment.importance, "interesting": assessment.interesting,
            "note": assessment.note,
        },
    }


@router.get("/sessions")
def list_sessions(start_date: date | None = None, end_date: date | None = None,
                  user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    settle_expired(db, user.id)
    db.commit()
    query = db.query(WorkSession).filter(WorkSession.user_id == user.id)
    if start_date: query = query.filter(WorkSession.started_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date: query = query.filter(WorkSession.started_at < datetime.combine(date.fromordinal(end_date.toordinal() + 1), datetime.min.time()))
    sessions = query.order_by(WorkSession.started_at.desc()).limit(200).all()
    assessments = db.query(TimeActivityAssessment).filter(TimeActivityAssessment.user_id == user.id,
                                                           TimeActivityAssessment.work_session_id.in_([s.id for s in sessions])).all() if sessions else []
    by_session = {a.work_session_id: a for a in assessments}
    return {"items": [session_payload(s, by_session.get(s.id)) for s in sessions]}


@router.post("/sessions/start")
def start_session(body: StartSessionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    settle_expired(db, user.id)
    if body.daily_task_id is not None:
        daily = owned(db, DailyTask, body.daily_task_id, user.id)
        if daily.completed and body.kind == "work": fail("日程任务已完成", 409)
        if body.project_task_id is None: body.project_task_id = daily.project_task_id
    validate_session_links(db, user.id, body.project_task_id, body.daily_task_id)
    if body.kind == "work" and body.project_task_id is None and body.daily_task_id is None:
        fail("工作片需要关联任务")
    if body.kind == "work":
        ready = require_ready(db, user.id, "task" if body.project_task_id else "daily", body.project_task_id or body.daily_task_id)
        if ready["reminders"] and not body.acknowledge_reminders:
            fail("请先阅读开始条件中的提醒事项并确认；旧客户端请刷新或更新", 409)
    if db.query(WorkSession).filter(WorkSession.user_id == user.id, WorkSession.ended_at.is_(None)).first():
        fail("已有进行中的片段，请先暂停、结束或切换", 409)
    now = datetime.utcnow()
    assert_no_overlap(db, user.id, now, now + timedelta(microseconds=1))
    row = WorkSession(user_id=user.id, project_task_id=body.project_task_id, daily_task_id=body.daily_task_id,
                      kind=body.kind, source="timer", started_at=now, planned_minutes=body.planned_minutes,
                      planned_seconds=body.planned_seconds, label=body.label)
    plan = execution_plan(db, user.id)
    plan.paused_session_id = None
    plan.remaining_seconds = None
    practice_service.snapshot_session(db, row)
    db.add(row); db.commit(); db.refresh(row)
    return session_payload(row)


@router.post("/sessions/switch")
def switch_session(body: SwitchSessionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    old = owned(db, WorkSession, body.from_session_id, user.id)
    settle_expired(db, user.id)
    if body.daily_task_id is not None:
        daily = owned(db, DailyTask, body.daily_task_id, user.id)
        if daily.completed and body.kind == "work": fail("日程任务已完成", 409)
        if body.project_task_id is None: body.project_task_id = daily.project_task_id
    if old.ended_at is not None: fail("原片段已经结束", 409)
    validate_session_links(db, user.id, body.project_task_id, body.daily_task_id)
    if body.kind == "work" and body.project_task_id is None and body.daily_task_id is None:
        fail("工作片需要关联任务")
    if body.kind == "work":
        ready = require_ready(db, user.id, "task" if body.project_task_id else "daily", body.project_task_id or body.daily_task_id)
        if ready["reminders"] and not body.acknowledge_reminders:
            fail("请先阅读开始条件中的提醒事项并确认；旧客户端请刷新或更新", 409)
    moment = datetime.utcnow()
    if moment <= old.started_at: moment = old.started_at + timedelta(microseconds=1)
    assert_no_overlap(db, user.id, old.started_at, moment, old.id)
    old.ended_at = moment
    new = WorkSession(user_id=user.id, project_task_id=body.project_task_id, daily_task_id=body.daily_task_id,
                      kind=body.kind, source="timer", started_at=moment,
                      planned_minutes=body.planned_minutes, planned_seconds=body.planned_seconds, label=body.label)
    practice_service.snapshot_session(db, new)
    db.add(new); db.commit(); db.refresh(new)
    return {"ended": session_payload(old), "started": session_payload(new)}


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: int, body: StopSessionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    row = owned(db, WorkSession, session_id, user.id)
    if row.ended_at is not None: return session_payload(row)
    end = utc_naive(body.ended_at) if body.ended_at else datetime.utcnow()
    now = datetime.utcnow()
    if end > now: fail("结束时间不能晚于当前时间")
    if row.source == "timer": end = min(end, row.started_at + timedelta(seconds=budget_seconds(row)))
    if end <= row.started_at: fail("结束时间必须晚于开始时间")
    assert_no_overlap(db, user.id, row.started_at, end, row.id)
    row.ended_at = end
    plan = execution_plan(db, user.id)
    remaining = max(0, budget_seconds(row) - math.ceil((end - row.started_at).total_seconds()))
    plan.paused_session_id = row.id if body.pause and remaining else None
    plan.remaining_seconds = remaining if body.pause and remaining else None
    db.commit()
    return session_payload(row)


@router.post("/sessions/manual")
def manual_session(body: ManualSessionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    settle_expired(db, user.id)
    if body.daily_task_id is not None and body.project_task_id is None:
        body.project_task_id = owned(db, DailyTask, body.daily_task_id, user.id).project_task_id
    validate_session_links(db, user.id, body.project_task_id, body.daily_task_id, body.time_log_node_id)
    if body.source == "moment" and body.time_log_node_id is None: fail("确认时刻区间时必须选择时刻记录")
    if body.kind == "work" and body.project_task_id is None and body.daily_task_id is None: fail("工作片需要关联任务")
    if body.kind == "work":
        ready = readiness(db, user.id, "task" if body.project_task_id else "daily", body.project_task_id or body.daily_task_id)
        if ready["blockers"] and not (body.correction_note or "").strip():
            fail("当前条件未满足。实际发生的工作可以补记，请说明当时情况", 409)
    start, end = utc_naive(body.started_at), utc_naive(body.ended_at)
    assert_no_overlap(db, user.id, start, end)
    row = WorkSession(user_id=user.id, project_task_id=body.project_task_id, daily_task_id=body.daily_task_id,
                      time_log_node_id=body.time_log_node_id, kind=body.kind, source=body.source,
                      started_at=start, ended_at=end, label=body.label, correction_note=body.correction_note)
    practice_service.snapshot_session(db, row)
    db.add(row); db.commit(); db.refresh(row)
    return session_payload(row)


@router.patch("/sessions/{session_id}")
def correct_session(session_id: int, body: SessionCorrectionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    row = owned(db, WorkSession, session_id, user.id)
    if row.ended_at is None: fail("请先结束片段再更正")
    start, end = utc_naive(body.started_at), utc_naive(body.ended_at)
    assert_no_overlap(db, user.id, start, end, row.id)
    row.started_at, row.ended_at, row.correction_note = start, end, body.correction_note
    db.commit()
    return session_payload(row)


@router.put("/sessions/{session_id}/assessment")
def assess_session(session_id: int, body: AssessmentInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    practice_service.lock_user(db, user.id)
    session = owned(db, WorkSession, session_id, user.id)
    if session.ended_at is None: fail("片段结束后才能回看")
    goal = owned(db, Goal, body.goal_id, user.id) if body.goal_id is not None else None
    row = db.query(TimeActivityAssessment).filter(TimeActivityAssessment.user_id == user.id,
                                                   TimeActivityAssessment.work_session_id == session.id).first()
    if row is None:
        row = TimeActivityAssessment(user_id=user.id, work_session_id=session.id)
        db.add(row)
    row.goal_id = goal.id if goal else None
    row.goal_title_snapshot = goal.title if goal else None
    row.importance = body.importance
    row.interesting = body.interesting
    row.note = body.note
    row.assessed_at = datetime.utcnow()
    practice_service.event(db, user.id, "session", session.id, "actual_assessment", {
        "goal": row.goal_title_snapshot, "importance": row.importance, "interesting": row.interesting, "note": row.note})
    db.commit()
    return session_payload(session, row)


def template_payload(row: ProcessTemplate):
    return {"id": row.id, "title": row.title, "steps": json.loads(row.steps_json or "[]"),
            "checklist": json.loads(row.checklist_json or "[]"),
            "common_problems": row.common_problems, "acceptance_criteria": row.acceptance_criteria}


def clean_items(values: list[str]) -> list[str]:
    items = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if any(len(value) > 500 for value in items): fail("步骤或检查项不能超过500字")
    return items


@router.get("/templates")
def list_templates(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(ProcessTemplate).filter(ProcessTemplate.user_id == user.id,
                                            ProcessTemplate.deleted_at.is_(None)).order_by(ProcessTemplate.id.desc()).all()
    return {"items": [template_payload(row) for row in rows]}


@router.post("/templates")
def create_template(body: TemplateInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = ProcessTemplate(user_id=user.id, title=required_text(body.title),
                          steps_json=json.dumps(clean_items(body.steps), ensure_ascii=False),
                          checklist_json=json.dumps(clean_items(body.checklist), ensure_ascii=False),
                          common_problems=body.common_problems, acceptance_criteria=body.acceptance_criteria)
    db.add(row); db.commit(); db.refresh(row)
    return template_payload(row)


@router.put("/templates/{template_id}")
def update_template(template_id: int, body: TemplateInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = owned(db, ProcessTemplate, template_id, user.id)
    row.title = required_text(body.title)
    row.steps_json = json.dumps(clean_items(body.steps), ensure_ascii=False)
    row.checklist_json = json.dumps(clean_items(body.checklist), ensure_ascii=False)
    row.common_problems = body.common_problems
    row.acceptance_criteria = body.acceptance_criteria
    db.commit()
    return template_payload(row)


@router.post("/tasks/{task_id}/save-template")
def save_task_template(task_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    task = owned(db, ProjectTask, task_id, user.id)
    checks = db.query(TaskChecklistItem).filter(TaskChecklistItem.task_id == task.id).order_by(TaskChecklistItem.position).all()
    row = ProcessTemplate(user_id=user.id, title=task.title, steps_json=task.steps_json or "[]",
                          checklist_json=json.dumps([item.text for item in checks], ensure_ascii=False),
                          common_problems=task.blocker_note, acceptance_criteria=task.acceptance_criteria)
    db.add(row); db.commit(); db.refresh(row)
    return template_payload(row)


@router.post("/templates/{template_id}/instantiate")
def instantiate_template(template_id: int, body: InstantiateInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    template = owned(db, ProcessTemplate, template_id, user.id)
    require_open_project(owned(db, Project, body.project_id, user.id))
    if body.stage_id is not None:
        stage = owned(db, ProjectStage, body.stage_id, user.id)
        if stage.project_id != body.project_id or stage.state == "closed": fail("阶段不属于此项目或已结束")
    task = ProjectTask(user_id=user.id, project_id=body.project_id, stage_id=body.stage_id,
                       title=required_text(body.title or template.title), steps_json=template.steps_json,
                       blocker_note=template.common_problems, acceptance_criteria=template.acceptance_criteria)
    db.add(task); db.flush()
    for index, item in enumerate(json.loads(template.checklist_json or "[]")):
        db.add(TaskChecklistItem(user_id=user.id, task_id=task.id, text=item, position=index))
    record_scope_addition(db, user.id, task)
    db.commit(); db.refresh(task)
    return task_payload(db, task)
