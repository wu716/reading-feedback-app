# -*- coding: utf-8 -*-
"""今日待办与概览 API"""
import logging
import re
from datetime import date, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import (
    DailyTodo,
    User,
)
from app.schedule_todos import attach_todo, task_for_todo

router = APIRouter(prefix="/today", tags=["今日概览"])
logger = logging.getLogger(__name__)

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
REMIND_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def beijing_today() -> date:
    return datetime.now(BEIJING_TZ).date()


def normalize_remind_time(value: Optional[str]) -> Optional[str]:
    """Accept HH:MM, H:MM, HH:MM:SS, and common Android WebView variants."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    value = value.replace("时", ":").replace("分", "").replace("．", ":").strip()
    lower = value.lower().replace(" ", "")
    ampm = None
    if lower.endswith("am") or lower.endswith("pm"):
        ampm = lower[-2:]
        value = re.sub(r"(?i)\s*[ap]m$", "", value).strip()
    match = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2}(?:[.:]\d+)?)?$", value)
    if not match:
        if not REMIND_TIME_RE.fullmatch(value):
            raise HTTPException(status_code=400, detail="提醒时间格式应为 HH:MM")
        return value
    hour = int(match.group(1))
    minute = int(match.group(2))
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise HTTPException(status_code=400, detail="提醒时间格式应为 HH:MM")
    return f"{hour:02d}:{minute:02d}"


# ---------- Schemas ----------


class DailyTodoCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    todo_date: Optional[date] = None
    remind_time: Optional[str] = None

    @field_validator("text")
    @classmethod
    def strip_todo_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("待办内容不能为空")
        return text

    @field_validator("remind_time", mode="before")
    @classmethod
    def coerce_remind_time(cls, value):
        if value is None or value == "":
            return None
        return str(value).strip() or None


class DailyTodoUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=500)
    completed: Optional[bool] = None
    remind_time: Optional[str] = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value):
        if value is not None and not value.strip():
            raise ValueError("待办内容不能为空")
        return value.strip() if value is not None else None


class DailyTodoResponse(BaseModel):
    id: int
    text: str
    completed: bool
    todo_date: date
    remind_time: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TodayOverviewResponse(BaseModel):
    date: date
    todos: List[DailyTodoResponse]


# ---------- Daily Todos ----------


@router.get("/todos", response_model=List[DailyTodoResponse])
async def list_daily_todos(
    todo_date: Optional[date] = Query(None, description="日期，默认今天（北京时间）"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = todo_date or beijing_today()
    rows = (
        db.query(DailyTodo)
        .filter(
            DailyTodo.user_id == current_user.id,
            DailyTodo.todo_date == target,
            DailyTodo.deleted_at.is_(None),
        )
        .order_by(DailyTodo.id.asc())
        .all()
    )
    return rows


@router.get("/todos/scheduled", response_model=List[DailyTodoResponse])
async def list_scheduled_todos(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """未完成且设了提醒时间的今日及未来待办，供原生闹钟同步。"""
    today = beijing_today()
    return (
        db.query(DailyTodo)
        .filter(
            DailyTodo.user_id == current_user.id,
            DailyTodo.deleted_at.is_(None),
            DailyTodo.completed == False,
            DailyTodo.remind_time.isnot(None),
            DailyTodo.todo_date >= today,
        )
        .order_by(DailyTodo.todo_date.asc(), DailyTodo.id.asc())
        .all()
    )


class TodoMonthDayCount(BaseModel):
    date: date
    total: int
    completed: int


class TodoMonthSummaryResponse(BaseModel):
    year: int
    month: int
    days: List[TodoMonthDayCount]


@router.get("/todos/month", response_model=TodoMonthSummaryResponse)
async def list_month_todo_summary(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """按月返回有待办的日期，供首页日历圆点标记。"""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    rows = (
        db.query(
            DailyTodo.todo_date,
            func.count(DailyTodo.id).label("total"),
            func.sum(func.cast(DailyTodo.completed, Integer)).label("completed"),
        )
        .filter(
            DailyTodo.user_id == current_user.id,
            DailyTodo.todo_date >= start,
            DailyTodo.todo_date < end,
            DailyTodo.deleted_at.is_(None),
        )
        .group_by(DailyTodo.todo_date)
        .all()
    )
    return TodoMonthSummaryResponse(
        year=year,
        month=month,
        days=[
            TodoMonthDayCount(
                date=row.todo_date,
                total=int(row.total or 0),
                completed=int(row.completed or 0),
            )
            for row in rows
        ],
    )


@router.post("/todos", response_model=DailyTodoResponse, status_code=status.HTTP_201_CREATED)
async def create_daily_todo(
    body: DailyTodoCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="待办内容不能为空")
    row = DailyTodo(
        user_id=current_user.id,
        text=text,
        todo_date=body.todo_date or beijing_today(),
        remind_time=normalize_remind_time(body.remind_time),
    )
    try:
        db.query(User).filter(User.id == current_user.id).with_for_update().first()
        db.add(row)
        db.flush()
        attach_todo(db, row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        logger.exception("创建待办失败 user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="保存待办失败，请稍后重试")
    return row


@router.patch("/todos/{todo_id}", response_model=DailyTodoResponse)
async def update_daily_todo(
    todo_id: int,
    body: DailyTodoUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(DailyTodo)
        .filter(
            DailyTodo.id == todo_id,
            DailyTodo.user_id == current_user.id,
            DailyTodo.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="待办不存在")

    task = attach_todo(db, row)
    # Delegate shared mutations to the schedule rules (including project acceptance).
    from app.routers.schedule import TaskUpdate, update_task
    changes = body.model_dump(exclude_unset=True)
    await update_task(task.id, TaskUpdate(**changes), current_user, db)
    db.refresh(row)
    return row


@router.delete("/todos/{todo_id}")
async def delete_daily_todo(
    todo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    db.query(User).filter(User.id == current_user.id).with_for_update().first()
    row = (
        db.query(DailyTodo)
        .filter(
            DailyTodo.id == todo_id,
            DailyTodo.user_id == current_user.id,
            DailyTodo.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="待办不存在")
    task = task_for_todo(db, row)
    if task is not None and task.deleted_at is None:
        from app.routers.schedule import delete_task
        await delete_task(task.id, current_user, db)
        return {"message": "已删除"}
    row.deleted_at = datetime.utcnow()
    db.commit()
    return {"message": "已删除"}


# ---------- Overview ----------


@router.get("/overview", response_model=TodayOverviewResponse)
async def get_today_overview(
    overview_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = overview_date or beijing_today()

    todos = (
        db.query(DailyTodo)
        .filter(
            DailyTodo.user_id == current_user.id,
            DailyTodo.todo_date == target,
            DailyTodo.deleted_at.is_(None),
        )
        .order_by(DailyTodo.id.asc())
        .all()
    )

    return TodayOverviewResponse(
        date=target,
        todos=todos,
    )
