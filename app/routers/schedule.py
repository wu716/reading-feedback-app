# -*- coding: utf-8 -*-
"""每日日程：安排日期、任务属性与顺序。"""
from collections import defaultdict
import json
import hashlib
import hmac
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.config import settings
from app.database import get_db
from app.models import DailySchedule, DailyTask, DailyTodo, FutureAction, User
from app.schedule_todos import import_day_todos, sync_task_reminder
from app.stage_schedule_models import DailyProjectPlan, day_plan, legacy_daily_filter

router = APIRouter(prefix="/schedule", tags=["日程安排"])
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
FAMILIARITY_VALUES = {"familiar", "unfamiliar"}


def beijing_today() -> date:
    return datetime.now(BEIJING_TZ).date()


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def parse_day(value: Optional[date]) -> date:
    return value or beijing_today()


class TaskCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    task_date: Optional[date] = None
    parent_id: Optional[int] = None
    priority: int = Field(0, ge=0, le=2)
    familiarity: Optional[str] = None
    difficulty: Literal["simple", "difficult"] | None = None
    importance: Literal["unimportant", "ordinary", "important"] | None = None
    estimated_minutes: Optional[int] = Field(None, ge=0, le=24 * 60)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("行动内容不能为空")
        return text

    @field_validator("familiarity")
    @classmethod
    def check_familiarity(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        if value not in FAMILIARITY_VALUES:
            raise ValueError("熟悉程度只能是 familiar 或 unfamiliar")
        return value


class TaskUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=500)
    completed: Optional[bool] = None
    note: Optional[str] = Field(None, max_length=500)
    familiarity: Optional[str] = None
    estimated_minutes: Optional[int] = Field(None, ge=0, le=24 * 60)
    sort_order: Optional[int] = None
    parallel_group: Optional[int] = None
    priority: Optional[int] = Field(None, ge=0, le=2)
    flow_order: Optional[int] = Field(None, ge=0)
    parent_id: Optional[int] = None
    clear_familiarity: bool = False
    clear_estimate: bool = False
    clear_parallel: bool = False
    clear_note: bool = False
    remind_time: Optional[str] = None
    checklist_done: Optional[List[bool]] = None
    checklist_exception: Optional[str] = Field(None, max_length=4000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("行动内容不能为空")
        return text

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @field_validator("familiarity")
    @classmethod
    def check_familiarity(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        if value not in FAMILIARITY_VALUES:
            raise ValueError("熟悉程度只能是 familiar 或 unfamiliar")
        return value


class ReorderItem(BaseModel):
    id: int
    sort_order: int
    parallel_group: Optional[int] = None
    parent_id: Optional[int] = None
    priority: Optional[int] = Field(None, ge=0, le=2)
    flow_order: Optional[int] = Field(None, ge=0)


class ReorderBody(BaseModel):
    task_date: Optional[date] = None
    items: List[ReorderItem]


class DesignBody(BaseModel):
    task_date: Optional[date] = None


class TaskOut(BaseModel):
    id: int
    parent_id: Optional[int] = None
    action_id: Optional[int] = None
    project_task_id: Optional[int] = None
    project_id: Optional[int] = None
    project_title: Optional[str] = None
    actual_minutes: float = 0
    readiness: dict | None = None
    text: str
    completed: bool
    note: Optional[str] = None
    sort_order: int
    priority: int = 0
    flow_order: int = 0
    familiarity: Optional[str] = None
    estimated_minutes: Optional[int] = None
    parallel_group: Optional[int] = None
    children: List["TaskOut"] = Field(default_factory=list)
    remind_time: Optional[str] = None
    steps: List[str] = Field(default_factory=list)
    checklist: List[dict] = Field(default_factory=list)
    common_problems: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    practice: dict | None = None
    project_day_plan: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class DayScheduleOut(BaseModel):
    date: date
    designed_at: Optional[datetime] = None
    tasks: List[TaskOut]


class FutureCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def strip_future_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("内容不能为空")
        return text


class FutureUpdate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def strip_future_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("内容不能为空")
        return text


class FutureScheduleBody(BaseModel):
    task_date: Optional[date] = None


class FutureOut(BaseModel):
    id: int
    text: str

    model_config = ConfigDict(from_attributes=True)


class FutureListOut(BaseModel):
    items: List[FutureOut]
    undo_token: Optional[str] = None


class FutureRestoreBody(BaseModel):
    undo_token: str = Field(..., min_length=1, max_length=200)


def future_delete_signature(user_id: int, item_id: int, timestamp: str) -> str:
    message = f"future-delete:{user_id}:{item_id}:{timestamp}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def visible_tasks(db: Session, user_id: int, day: date) -> List[DailyTask]:
    return (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == user_id,
            DailyTask.task_date == day,
            DailyTask.deleted_at.is_(None),
        )
        .order_by(DailyTask.sort_order.asc(), DailyTask.id.asc())
        .all()
    )


def get_task_or_404(db: Session, user_id: int, task_id: int) -> DailyTask:
    task = (
        db.query(DailyTask)
        .filter(
            DailyTask.id == task_id,
            DailyTask.user_id == user_id,
            DailyTask.deleted_at.is_(None),
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="行动不存在")
    return task


def get_or_create_schedule(db: Session, user_id: int, day: date) -> DailySchedule:
    row = (
        db.query(DailySchedule)
        .filter(DailySchedule.user_id == user_id, DailySchedule.schedule_date == day)
        .first()
    )
    if row:
        return row
    row = DailySchedule(user_id=user_id, schedule_date=day)
    db.add(row)
    db.flush()
    return row


def next_sort_order(db: Session, user_id: int, day: date, parent_id: Optional[int]) -> int:
    siblings = [
        t for t in visible_tasks(db, user_id, day) if t.parent_id == parent_id
    ]
    if not siblings:
        return 0
    return max(t.sort_order for t in siblings) + 1


def next_flow_order(db: Session, user_id: int, day: date) -> int:
    tasks = visible_tasks(db, user_id, day)
    if not tasks:
        return 0
    return max((t.flow_order or t.sort_order or 0) for t in tasks) + 1


def collect_descendants(tasks: List[DailyTask], root_id: int) -> List[DailyTask]:
    by_parent = defaultdict(list)
    for task in tasks:
        by_parent[task.parent_id].append(task)
    found = []

    def walk(pid: int):
        for child in by_parent.get(pid, []):
            found.append(child)
            walk(child.id)

    walk(root_id)
    return found


def refresh_parent_completion(db: Session, user_id: int, task: DailyTask) -> None:
    """Keep container completion derived from its direct children."""
    parent = task.parent
    while parent is not None:
        children = [child for child in parent.children if child.deleted_at is None]
        next_value = bool(children) and all(child.completed for child in children)
        if next_value:
            from app.start_conditions import readiness
            # A container's delivery check must not block an independent child,
            # or be silently satisfied by completing its final child.
            if day_plan(db, user_id, parent.id):
                from app.stage_schedule_models import require_scope_completion_ready
                try:
                    require_scope_completion_ready(db, user_id, parent)
                except HTTPException:
                    next_value = False
            else:
                next_value = readiness(db, user_id, "daily", parent.id, purpose="delivery")["can_start"]
        if parent.completed == next_value:
            parent = parent.parent
            continue
        parent.completed = next_value
        parent = parent.parent


def build_tree(tasks: List[DailyTask], linked=None, actual=None, readiness_by_id=None, reminders=None, practice_by_id=None, plans=None) -> List[TaskOut]:
    linked, actual = linked or {}, actual or {}
    by_parent = defaultdict(list)
    for task in tasks:
        by_parent[task.parent_id].append(task)

    def node(task: DailyTask) -> TaskOut:
        plan = (plans or {}).get(task.id)
        return TaskOut(
            id=task.id,
            parent_id=task.parent_id,
            action_id=task.action_id,
            project_task_id=task.project_task_id,
            project_id=linked[task.project_task_id][0] if task.project_task_id in linked else (plan["project_id"] if plan else None),
            project_title=linked[task.project_task_id][1] if task.project_task_id in linked else (plan["project_title"] if plan else None),
            actual_minutes=plan["today_recorded_minutes"] if plan else actual.get(("project", task.project_task_id) if task.project_task_id else ("daily", task.id), 0),
            readiness=(readiness_by_id or {}).get(task.id),
            text=task.text,
            completed=bool(task.completed),
            note=task.note,
            sort_order=task.sort_order or 0,
            priority=task.priority or 0,
            flow_order=task.flow_order or task.sort_order or 0,
            familiarity=task.familiarity,
            estimated_minutes=(practice_by_id or {}).get(task.id, {}).get("estimated_minutes", task.estimated_minutes)
                if task.project_task_id and not plan else task.estimated_minutes,
            parallel_group=task.parallel_group,
            children=[node(child) for child in by_parent.get(task.id, [])],
            remind_time=(reminders or {}).get(task.legacy_todo_id),
            steps=json.loads(task.steps_json or "[]"),
            checklist=json.loads(task.checklist_json or "[]"),
            common_problems=task.common_problems,
            acceptance_criteria=task.acceptance_criteria,
            practice=(practice_by_id or {}).get(task.id),
            project_day_plan=plan,
        )

    # Completed children remain visible when their unfinished container is deleted.
    # Keep the stored parent identity intact so recovery can rebuild the same tree.
    visible_ids = {task.id for task in tasks}
    return [node(task) for task in tasks if task.parent_id is None or task.parent_id not in visible_ids]


def visible_future_actions(db: Session, user_id: int) -> List[FutureAction]:
    return (
        db.query(FutureAction)
        .filter(
            FutureAction.user_id == user_id,
            FutureAction.deleted_at.is_(None),
        )
        .order_by(FutureAction.id.desc())
        .all()
    )


def get_future_or_404(db: Session, user_id: int, item_id: int) -> FutureAction:
    item = (
        db.query(FutureAction)
        .filter(
            FutureAction.id == item_id,
            FutureAction.user_id == user_id,
            FutureAction.deleted_at.is_(None),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="这条以后想做不存在")
    return item


def future_payload(db: Session, user_id: int) -> FutureListOut:
    return FutureListOut(items=[FutureOut.model_validate(item) for item in visible_future_actions(db, user_id)])


def day_payload(db: Session, user: User, day: date) -> DayScheduleOut:
    from app import practice_service as practice
    from app.start_conditions import readiness
    from app.execution_service import settle_expired
    from app.project_models import Project, ProjectTask, WorkSession
    import_day_todos(db, user.id, day)
    settle_expired(db, user.id)
    db.commit()
    tasks = visible_tasks(db, user.id, day)
    linked = {task.id: (project.id, project.title) for task, project in db.query(ProjectTask, Project).join(
        Project, Project.id == ProjectTask.project_id).filter(ProjectTask.user_id == user.id, Project.user_id == user.id,
        ProjectTask.id.in_([t.project_task_id for t in tasks if t.project_task_id])).all()}
    actual = defaultdict(float)
    plans = {p.daily_task_id: p for p in db.query(DailyProjectPlan).filter(
        DailyProjectPlan.user_id == user.id, DailyProjectPlan.daily_task_id.in_([t.id for t in tasks])).all()}
    source_tasks = {t.id: t for t in db.query(ProjectTask).filter(ProjectTask.user_id == user.id,
        ProjectTask.id.in_([t.project_task_id for t in tasks if t.project_task_id])).all()}
    today_actual = defaultdict(float)
    daily_actual = defaultdict(float)
    start = datetime.combine(day, time.min, BEIJING_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    end = start + timedelta(days=1)
    for session, daily_project_id in db.query(WorkSession, DailyTask.project_task_id).outerjoin(DailyTask,
        (DailyTask.id == WorkSession.daily_task_id) & (DailyTask.user_id == user.id)).filter(
        WorkSession.user_id == user.id, WorkSession.kind == "work", WorkSession.ended_at.isnot(None),
        or_(WorkSession.project_task_id.in_(list(linked)), DailyTask.project_task_id.in_(list(linked)),
            WorkSession.daily_task_id.in_([t.id for t in tasks]))).all():
        project_task_id = session.project_task_id or daily_project_id
        key = ("project", project_task_id) if project_task_id else ("daily", session.daily_task_id)
        actual[key] += (session.ended_at - session.started_at).total_seconds() / 60
        today_actual[key] += max(0, (min(end, session.ended_at) - max(start, session.started_at)).total_seconds()) / 60
        if session.daily_task_id:
            daily_actual[session.daily_task_id] += max(0, (min(end, session.ended_at) - max(start, session.started_at)).total_seconds()) / 60
    actual = {key: round(value, 2) for key, value in actual.items()}
    plan_payloads = {daily.id: {
        "project_id": plans[daily.id].project_id, "project_title": plans[daily.id].project_title,
        "stage_id": plans[daily.id].stage_id, "stage_title": plans[daily.id].stage_title,
        "task_title": plans[daily.id].task_title, "source_estimated_minutes": plans[daily.id].source_estimate_minutes,
        "project_actual_minutes": actual.get(("project", daily.project_task_id), 0),
        "source_completed": source_tasks.get(daily.project_task_id) is not None and source_tasks[daily.project_task_id].state == "completed",
        "source_missing": daily.project_task_id not in source_tasks or source_tasks[daily.project_task_id].deleted_at is not None,
        "today_recorded_minutes": round(daily_actual[daily.id] if daily.parent_id is not None else today_actual.get(("project", daily.project_task_id), 0), 2),
    } for daily in tasks if daily.id in plans}
    schedule = (
        db.query(DailySchedule)
        .filter(DailySchedule.user_id == user.id, DailySchedule.schedule_date == day)
        .first()
    )
    return DayScheduleOut(
        date=day,
        designed_at=schedule.designed_at if schedule else None,
        tasks=build_tree(tasks, linked, actual, {t.id: readiness(db, user.id, "daily", t.id) for t in tasks},
            dict(db.query(DailyTodo.id, DailyTodo.remind_time).filter(DailyTodo.user_id == user.id,
                 DailyTodo.id.in_([t.legacy_todo_id for t in tasks if t.legacy_todo_id])).all()),
            {t.id: practice.day_task_payload(db, user.id, "task" if t.project_task_id and t.id not in plans else "daily",
                db.get(ProjectTask, t.project_task_id) if t.project_task_id and t.id not in plans else t, day)
                for t in tasks if not t.project_task_id or (db.get(ProjectTask, t.project_task_id) is not None
                    and db.get(ProjectTask, t.project_task_id).user_id == user.id)}, plan_payloads),
    )


@router.get("", response_model=DayScheduleOut)
def get_day_schedule(
    task_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return day_payload(db, current_user, parse_day(task_date))


@router.post("/tasks", response_model=DayScheduleOut)
def create_task(
    body: TaskCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    day = parse_day(body.task_date)
    parent_id = body.parent_id
    if parent_id is not None:
        parent = get_task_or_404(db, current_user.id, parent_id)
        if parent.task_date != day:
            raise HTTPException(status_code=400, detail="子行动必须和父行动在同一天")
    get_or_create_schedule(db, current_user.id, day)
    task = DailyTask(
        user_id=current_user.id,
        parent_id=parent_id,
        task_date=day,
        text=body.text,
        action_id=None,
        sort_order=next_sort_order(db, current_user.id, day, parent_id),
        priority=body.priority,
        familiarity=body.familiarity,
        estimated_minutes=body.estimated_minutes,
        flow_order=next_flow_order(db, current_user.id, day),
    )
    db.add(task)
    db.flush()
    if parent_id is not None:
        parent_plan = day_plan(db, current_user.id, parent_id)
        if parent_plan:
            task.project_task_id = parent.project_task_id
            db.add(DailyProjectPlan(**{c.name: getattr(parent_plan, c.name) for c in DailyProjectPlan.__table__.columns
                if c.name not in ("daily_task_id", "item_key", "created_at")}, daily_task_id=task.id, item_key=f"split-{task.id}"))
            db.flush()
    from app import practice_service as practice
    practice.note_estimate(db, current_user.id, "daily", task, body.estimated_minutes, created=True)
    if body.difficulty is not None or body.importance is not None:
        state = practice.practice(db, current_user.id, "daily", task)
        state.difficulty = body.difficulty
        state.importance = body.importance
        if body.importance is not None:
            state.initial_importance = body.importance
            state.initial_marked_at = datetime.utcnow()
        practice.event(db, current_user.id, "daily", task.id, "attributes", {
            "difficulty": body.difficulty, "importance": body.importance,
            "title": task.text, "source": "task_create",
        })
    db.commit()
    return day_payload(db, current_user, day)


@router.patch("/tasks/{task_id}", response_model=DayScheduleOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    db.query(User).filter(User.id == current_user.id).with_for_update().first()
    task = get_task_or_404(db, current_user.id, task_id)
    scoped = day_plan(db, current_user.id, task.id)
    from app import practice_service as practice
    if body.text is not None:
        task.text = body.text
        if task.project_task_id and not scoped:
            from app.project_models import ProjectTask
            project_task = db.query(ProjectTask).filter(ProjectTask.id == task.project_task_id,
                ProjectTask.user_id == current_user.id, ProjectTask.deleted_at.is_(None)).first()
            if project_task:
                project_task.title = body.text
                db.query(DailyTask).filter(DailyTask.user_id == current_user.id,
                    DailyTask.project_task_id == project_task.id, DailyTask.deleted_at.is_(None), legacy_daily_filter(current_user.id)).update({"text": body.text}, synchronize_session=False)
    if body.completed is not None:
        if scoped and body.completed and task.task_date > beijing_today():
            raise HTTPException(409, "未来日期的安排请到当天再记录完成")
        if task.project_task_id is not None and not scoped:
            raise HTTPException(status_code=409, detail="请到关联项目核对完成标准并验收；验收结果会同步到日程")
        if body.completed:
            from app.start_conditions import require_ready
            targets = [task] + collect_descendants(visible_tasks(db, current_user.id, task.task_date), task.id)
            for target in targets:
                if day_plan(db, current_user.id, target.id):
                    from app.stage_schedule_models import require_scope_completion_ready
                    require_scope_completion_ready(db, current_user.id, target)
                else:
                    require_ready(db, current_user.id, "daily", target.id, purpose="delivery")
                practice.require_checklist(db, current_user.id, "daily", target, body.checklist_exception)
        task.completed = body.completed
        if task.completed:
            for target in [task] + collect_descendants(visible_tasks(db, current_user.id, task.task_date), task.id):
                if target.completed: practice.settle_daily_completion(db, current_user.id, target)
        refresh_parent_completion(db, current_user.id, task)
    if body.clear_note:
        task.note = None
    elif body.note is not None:
        task.note = body.note or None
    if body.clear_familiarity:
        task.familiarity = None
    elif body.familiarity is not None:
        task.familiarity = body.familiarity
    if body.clear_estimate:
        kind, actual_task = practice.owner(db, current_user.id, "daily", task.id)
        practice.note_estimate(db, current_user.id, kind, actual_task, None, "日程中清除当前估计")
        actual_task.estimated_minutes = None
        task.estimated_minutes = None
    elif body.estimated_minutes is not None:
        kind, actual_task = practice.owner(db, current_user.id, "daily", task.id)
        practice.note_estimate(db, current_user.id, kind, actual_task, body.estimated_minutes, "日程中修订")
        actual_task.estimated_minutes = body.estimated_minutes
        task.estimated_minutes = body.estimated_minutes
    if body.sort_order is not None:
        task.sort_order = body.sort_order
    if body.priority is not None:
        task.priority = body.priority
    if body.flow_order is not None:
        task.flow_order = body.flow_order
    if body.clear_parallel:
        task.parallel_group = None
    elif body.parallel_group is not None:
        task.parallel_group = body.parallel_group
    if body.parent_id is not None:
        if body.parent_id == task.id:
            raise HTTPException(status_code=400, detail="不能把行动挂到自己下面")
        parent = get_task_or_404(db, current_user.id, body.parent_id)
        if parent.task_date != task.task_date:
            raise HTTPException(status_code=400, detail="子行动必须和父行动在同一天")
        descendants = {t.id for t in collect_descendants(visible_tasks(db, current_user.id, task.task_date), task.id)}
        if body.parent_id in descendants:
            raise HTTPException(status_code=400, detail="不能把行动挂到自己的子行动下")
        task.parent_id = body.parent_id
    if body.checklist_done is not None:
        if task.project_task_id:
            raise HTTPException(status_code=409, detail="请在项目任务中核对检查项")
        checks = json.loads(task.checklist_json or "[]")
        if len(checks) != len(body.checklist_done):
            raise HTTPException(status_code=409, detail="检查项已变化，请刷新后重试")
        task.checklist_json = json.dumps([dict(item, done=done) for item, done in zip(checks, body.checklist_done)], ensure_ascii=False)
    if "remind_time" in body.model_fields_set:
        from app.routers.today import normalize_remind_time
        sync_task_reminder(db, task, remind_time=normalize_remind_time(body.remind_time))
    else:
        sync_task_reminder(db, task)
    for related in visible_tasks(db, current_user.id, task.task_date):
        sync_task_reminder(db, related)
    if body.text is not None and task.project_task_id and not scoped:
        for related in db.query(DailyTask).filter(DailyTask.user_id == current_user.id,
                DailyTask.project_task_id == task.project_task_id, DailyTask.deleted_at.is_(None)).all():
            sync_task_reminder(db, related)
    db.commit()
    return day_payload(db, current_user, task.task_date)


@router.delete("/tasks/{task_id}", response_model=DayScheduleOut)
def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    db.query(User).filter(User.id == current_user.id).with_for_update().first()
    task = get_task_or_404(db, current_user.id, task_id)
    day = task.task_date
    now = beijing_now()
    task.deleted_at = now
    for child in collect_descendants(visible_tasks(db, current_user.id, day), task.id):
        child.deleted_at = now
        sync_task_reminder(db, child)
    sync_task_reminder(db, task)
    db.commit()
    return day_payload(db, current_user, day)


@router.post("/reorder", response_model=DayScheduleOut)
def reorder_tasks(
    body: ReorderBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    day = parse_day(body.task_date)
    tasks = {t.id: t for t in visible_tasks(db, current_user.id, day)}
    for item in body.items:
        task = tasks.get(item.id)
        if not task:
            raise HTTPException(status_code=404, detail="行动不存在")
        task.sort_order = item.sort_order
        task.parallel_group = item.parallel_group
        if item.priority is not None:
            task.priority = item.priority
        if item.flow_order is not None:
            task.flow_order = item.flow_order
        if item.parent_id is not None:
            task.parent_id = item.parent_id
    db.commit()
    return day_payload(db, current_user, day)


@router.post("/design", response_model=DayScheduleOut)
def mark_designed(
    body: DesignBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    day = parse_day(body.task_date)
    if not visible_tasks(db, current_user.id, day):
        raise HTTPException(status_code=400, detail="先写下今天要做的行动")
    schedule = get_or_create_schedule(db, current_user.id, day)
    schedule.designed_at = beijing_now()
    db.commit()
    return day_payload(db, current_user, day)


@router.get("/future", response_model=FutureListOut)
def list_future_actions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return future_payload(db, current_user.id)


@router.post("/future", response_model=FutureListOut)
def create_future_action(
    body: FutureCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = FutureAction(user_id=current_user.id, text=body.text)
    db.add(item)
    db.commit()
    return future_payload(db, current_user.id)


@router.patch("/future/{item_id}", response_model=FutureListOut)
def update_future_action(
    item_id: int,
    body: FutureUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = get_future_or_404(db, current_user.id, item_id)
    item.text = body.text
    db.commit()
    return future_payload(db, current_user.id)


@router.delete("/future/{item_id}", response_model=FutureListOut)
def delete_future_action(
    item_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = get_future_or_404(db, current_user.id, item_id)
    item.deleted_at = beijing_now()
    db.commit()
    db.refresh(item)
    stamp = item.deleted_at.isoformat()
    result = future_payload(db, current_user.id)
    result.undo_token = stamp + "|" + future_delete_signature(current_user.id, item_id, stamp)
    return result


@router.post("/future/{item_id}/restore", response_model=FutureListOut)
def restore_future_action(
    item_id: int,
    body: FutureRestoreBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = db.query(FutureAction).filter(FutureAction.id == item_id, FutureAction.user_id == current_user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="这条以后想做不存在")
    stamp, separator, signature = body.undo_token.rpartition("|")
    expected = future_delete_signature(current_user.id, item_id, stamp)
    if not separator or not hmac.compare_digest(signature.encode(), expected.encode()):
        raise HTTPException(status_code=400, detail="撤销凭据无效")
    if item.deleted_at is None or item.deleted_at.isoformat() != stamp:
        raise HTTPException(status_code=409, detail="记录已变化，请刷新列表")
    deleted_at = item.deleted_at
    if deleted_at.tzinfo is None:
        deleted_at = deleted_at.replace(tzinfo=BEIJING_TZ)
    if (beijing_now() - deleted_at).total_seconds() > 600:
        raise HTTPException(status_code=410, detail="撤销已超过十分钟")
    item.deleted_at = None
    db.commit()
    return future_payload(db, current_user.id)


@router.post("/future/{item_id}/schedule", response_model=DayScheduleOut)
def schedule_future_action(
    item_id: int,
    body: FutureScheduleBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = get_future_or_404(db, current_user.id, item_id)
    day = parse_day(body.task_date)
    get_or_create_schedule(db, current_user.id, day)
    db.add(
        DailyTask(
            user_id=current_user.id,
            task_date=day,
            text=item.text,
            sort_order=next_sort_order(db, current_user.id, day, None),
        )
    )
    item.deleted_at = beijing_now()
    db.commit()
    return day_payload(db, current_user, day)


from app.routers.stage_schedule import router as stage_schedule_router
router.include_router(stage_schedule_router)
