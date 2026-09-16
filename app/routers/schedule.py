# -*- coding: utf-8 -*-
"""每日日程：写下行动，可选进入流程设计。"""
from collections import defaultdict
from datetime import date, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.habit_due import quarter_bounds, suggest_for_day, week_bounds
from app.models import Action, DailySchedule, DailyTask, FutureAction, User

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
    action_id: Optional[int] = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("行动内容不能为空")
        return text


class TaskUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=500)
    completed: Optional[bool] = None
    note: Optional[str] = Field(None, max_length=500)
    familiarity: Optional[str] = None
    estimated_minutes: Optional[int] = Field(None, ge=0, le=24 * 60)
    sort_order: Optional[int] = None
    parallel_group: Optional[int] = None
    parent_id: Optional[int] = None
    clear_familiarity: bool = False
    clear_estimate: bool = False
    clear_parallel: bool = False
    clear_note: bool = False

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


class ReorderBody(BaseModel):
    task_date: Optional[date] = None
    items: List[ReorderItem]


class DesignBody(BaseModel):
    task_date: Optional[date] = None


class TaskOut(BaseModel):
    id: int
    parent_id: Optional[int] = None
    action_id: Optional[int] = None
    text: str
    completed: bool
    note: Optional[str] = None
    sort_order: int
    familiarity: Optional[str] = None
    estimated_minutes: Optional[int] = None
    parallel_group: Optional[int] = None
    children: List["TaskOut"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SuggestionOut(BaseModel):
    action_id: int
    text: str
    frequency: str
    reason: str


class SuggestionsOut(BaseModel):
    date: date
    items: List[SuggestionOut]


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


def build_tree(tasks: List[DailyTask]) -> List[TaskOut]:
    by_parent = defaultdict(list)
    for task in tasks:
        by_parent[task.parent_id].append(task)

    def node(task: DailyTask) -> TaskOut:
        return TaskOut(
            id=task.id,
            parent_id=task.parent_id,
            action_id=task.action_id,
            text=task.text,
            completed=bool(task.completed),
            note=task.note,
            sort_order=task.sort_order or 0,
            familiarity=task.familiarity,
            estimated_minutes=task.estimated_minutes,
            parallel_group=task.parallel_group,
            children=[node(child) for child in by_parent.get(task.id, [])],
        )

    return [node(task) for task in by_parent.get(None, [])]


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
    schedule = (
        db.query(DailySchedule)
        .filter(DailySchedule.user_id == user.id, DailySchedule.schedule_date == day)
        .first()
    )
    return DayScheduleOut(
        date=day,
        designed_at=schedule.designed_at if schedule else None,
        tasks=build_tree(visible_tasks(db, user.id, day)),
    )


@router.get("", response_model=DayScheduleOut)
async def get_day_schedule(
    task_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return day_payload(db, current_user, parse_day(task_date))


@router.get("/suggestions", response_model=SuggestionsOut)
async def get_schedule_suggestions(
    task_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    day = parse_day(task_date)
    actions = (
        db.query(Action)
        .filter(
            Action.user_id == current_user.id,
            Action.deleted_at.is_(None),
            Action.status != "done",
        )
        .order_by(Action.id.asc())
        .all()
    )
    lookback_start, _ = quarter_bounds(day)
    week_start, _ = week_bounds(day)
    range_start = min(lookback_start, week_start, date(day.year, day.month, 1))
    scheduled = (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == current_user.id,
            DailyTask.deleted_at.is_(None),
            DailyTask.task_date >= range_start,
            DailyTask.task_date <= day,
        )
        .all()
    )
    items = suggest_for_day(actions, scheduled, day)
    return SuggestionsOut(
        date=day,
        items=[
            SuggestionOut(
                action_id=item.action_id,
                text=item.text,
                frequency=item.frequency,
                reason=item.reason,
            )
            for item in items
        ],
    )


@router.post("/tasks", response_model=DayScheduleOut)
async def create_task(
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
    action_id = body.action_id
    if action_id is not None:
        action = (
            db.query(Action)
            .filter(
                Action.id == action_id,
                Action.user_id == current_user.id,
                Action.deleted_at.is_(None),
            )
            .first()
        )
        if not action:
            raise HTTPException(status_code=404, detail="行动项不存在")
    task = DailyTask(
        user_id=current_user.id,
        parent_id=parent_id,
        task_date=day,
        text=body.text,
        action_id=action_id,
        sort_order=next_sort_order(db, current_user.id, day, parent_id),
    )
    db.add(task)
    db.commit()
    return day_payload(db, current_user, day)


@router.patch("/tasks/{task_id}", response_model=DayScheduleOut)
async def update_task(
    task_id: int,
    body: TaskUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    task = get_task_or_404(db, current_user.id, task_id)
    if body.text is not None:
        task.text = body.text
    if body.completed is not None:
        task.completed = body.completed
    if body.clear_note:
        task.note = None
    elif body.note is not None:
        task.note = body.note or None
    if body.clear_familiarity:
        task.familiarity = None
    elif body.familiarity is not None:
        task.familiarity = body.familiarity
    if body.clear_estimate:
        task.estimated_minutes = None
    elif body.estimated_minutes is not None:
        task.estimated_minutes = body.estimated_minutes
    if body.sort_order is not None:
        task.sort_order = body.sort_order
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
    db.commit()
    return day_payload(db, current_user, task.task_date)


@router.delete("/tasks/{task_id}", response_model=DayScheduleOut)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    task = get_task_or_404(db, current_user.id, task_id)
    day = task.task_date
    now = beijing_now()
    task.deleted_at = now
    for child in collect_descendants(visible_tasks(db, current_user.id, day), task.id):
        child.deleted_at = now
    db.commit()
    return day_payload(db, current_user, day)


@router.post("/reorder", response_model=DayScheduleOut)
async def reorder_tasks(
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
        if item.parent_id is not None:
            task.parent_id = item.parent_id
    db.commit()
    return day_payload(db, current_user, day)


@router.post("/design", response_model=DayScheduleOut)
async def mark_designed(
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
async def list_future_actions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return future_payload(db, current_user.id)


@router.post("/future", response_model=FutureListOut)
async def create_future_action(
    body: FutureCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = FutureAction(user_id=current_user.id, text=body.text)
    db.add(item)
    db.commit()
    return future_payload(db, current_user.id)


@router.patch("/future/{item_id}", response_model=FutureListOut)
async def update_future_action(
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
async def delete_future_action(
    item_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = get_future_or_404(db, current_user.id, item_id)
    item.deleted_at = beijing_now()
    db.commit()
    return future_payload(db, current_user.id)


@router.post("/future/{item_id}/schedule", response_model=DayScheduleOut)
async def schedule_future_action(
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
