# -*- coding: utf-8 -*-
"""Focused habit programs that connect actions, schedule, practice, and Capture."""
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.habit_service import (
    beijing_today,
    get_active_program,
    summarize_events,
    sync_schedule_event,
)
from app.models import (
    Action,
    DailySchedule,
    DailyTask,
    DailyTodo,
    FutureAction,
    HabitEvent,
    HabitProgram,
    Idea,
    TimeLogNode,
    User,
)


router = APIRouter(prefix="/habits", tags=["习惯计划"])


class HabitProgramCreate(BaseModel):
    action_id: Optional[int] = None
    mode: Literal["build", "break"] = "build"
    title: str = Field(..., min_length=1, max_length=120)
    anchor_text: str = Field(..., min_length=1, max_length=500)
    minimum_action: Optional[str] = Field(None, max_length=500)
    replacement_action: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = Field(None, max_length=500)
    target_days_per_week: int = Field(5, ge=1, le=7)

    @field_validator(
        "title",
        "anchor_text",
        "minimum_action",
        "replacement_action",
        "reason",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class HabitProgramUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    anchor_text: Optional[str] = Field(None, min_length=1, max_length=500)
    minimum_action: Optional[str] = Field(None, max_length=500)
    replacement_action: Optional[str] = Field(None, max_length=500)
    reason: Optional[str] = Field(None, max_length=500)
    target_days_per_week: Optional[int] = Field(None, ge=1, le=7)
    status: Optional[Literal["active", "paused", "completed"]] = None

    @field_validator(
        "title",
        "anchor_text",
        "minimum_action",
        "replacement_action",
        "reason",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class HabitCheckIn(BaseModel):
    event_date: Optional[date] = None
    outcome: Literal["completed", "partial", "missed"]
    effort: Optional[int] = Field(None, ge=1, le=5)
    urge: Optional[int] = Field(None, ge=1, le=5)
    barrier: Optional[str] = Field(None, max_length=120)
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("barrier", "note")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class HabitScheduleIn(BaseModel):
    task_date: Optional[date] = None


def get_program_or_404(db: Session, user_id: int, program_id: int) -> HabitProgram:
    program = (
        db.query(HabitProgram)
        .filter(
            HabitProgram.id == program_id,
            HabitProgram.user_id == user_id,
            HabitProgram.deleted_at.is_(None),
        )
        .first()
    )
    if not program:
        raise HTTPException(status_code=404, detail="习惯计划不存在")
    return program


def validate_path(mode: str, minimum_action: Optional[str], replacement_action: Optional[str]) -> None:
    if mode == "build" and not (minimum_action or "").strip():
        raise HTTPException(status_code=422, detail="请写下最小行动")
    if mode == "break" and not (replacement_action or "").strip():
        raise HTTPException(status_code=422, detail="请写下触发后的替代动作")


def program_dict(program: HabitProgram) -> dict:
    return {
        "id": program.id,
        "action_id": program.action_id,
        "mode": program.mode,
        "title": program.title,
        "anchor_text": program.anchor_text,
        "minimum_action": program.minimum_action,
        "replacement_action": program.replacement_action,
        "reason": program.reason,
        "target_days_per_week": program.target_days_per_week,
        "status": program.status,
        "start_date": program.start_date,
        "end_date": program.end_date,
        "created_at": program.created_at,
        "updated_at": program.updated_at,
    }


def source_text(db: Session, user_id: int, event: HabitEvent) -> Optional[str]:
    model_and_field = {
        "moment": (TimeLogNode, TimeLogNode.label),
        "idea": (Idea, Idea.text),
        "todo_today": (DailyTodo, DailyTodo.text),
        "todo_later": (FutureAction, FutureAction.text),
    }.get(event.source_kind)
    if not model_and_field or not event.source_id:
        return None
    model, field = model_and_field
    row = (
        db.query(field)
        .filter(model.id == event.source_id, model.user_id == user_id, model.deleted_at.is_(None))
        .first()
    )
    return row[0] if row and row[0] else None


def active_payload(db: Session, user_id: int) -> dict:
    program = get_active_program(db, user_id)
    if not program:
        return {"program": None, "summary": None}
    start = beijing_today() - timedelta(days=6)
    events = (
        db.query(HabitEvent)
        .filter(
            HabitEvent.habit_program_id == program.id,
            HabitEvent.event_date >= start,
            HabitEvent.deleted_at.is_(None),
        )
        .order_by(HabitEvent.created_at.desc(), HabitEvent.id.desc())
        .all()
    )
    visible_events = []
    signal_rows = []
    for event in events:
        if event.event_type != "signal":
            visible_events.append(event)
            continue
        text = source_text(db, user_id, event)
        if not text:
            continue
        visible_events.append(event)
        signal_rows.append((event, text))

    summary = summarize_events(visible_events, program.target_days_per_week)
    recent_signals = []
    for event, text in signal_rows:
        recent_signals.append(
            {
                "id": event.id,
                "date": event.event_date,
                "source_kind": event.source_kind,
                "text": text,
            }
        )
        if len(recent_signals) == 3:
            break
    summary["recent_signals"] = recent_signals
    return {"program": program_dict(program), "summary": summary}


@router.get("/active")
async def get_active_habit(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return active_payload(db, current_user.id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_habit_program(
    body: HabitProgramCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    validate_path(body.mode, body.minimum_action, body.replacement_action)
    action = None
    if body.action_id:
        action = (
            db.query(Action)
            .filter(
                Action.id == body.action_id,
                Action.user_id == current_user.id,
                Action.deleted_at.is_(None),
            )
            .first()
        )
        if not action:
            raise HTTPException(status_code=404, detail="行动项不存在")
        if action.status == "done":
            raise HTTPException(status_code=409, detail="已完成的行动不能设为主要习惯")
    if not action:
        action = Action(
            user_id=current_user.id,
            book_title="习惯计划",
            source_excerpt=(body.reason or body.anchor_text)[:500],
            action_text=body.title,
            tags='["习惯计划"]',
            frequency="daily",
            status="in_progress",
            action_type="habit",
            duration_type="long_term",
            target_duration_days=30,
            target_frequency="daily",
            start_date=beijing_today(),
        )
        db.add(action)
        db.flush()
    elif action.status == "todo":
        action.status = "in_progress"

    for old in (
        db.query(HabitProgram)
        .filter(
            HabitProgram.user_id == current_user.id,
            HabitProgram.status == "active",
            HabitProgram.deleted_at.is_(None),
        )
        .all()
    ):
        old.status = "paused"

    program = HabitProgram(
        user_id=current_user.id,
        action_id=action.id,
        mode=body.mode,
        title=body.title,
        anchor_text=body.anchor_text,
        minimum_action=body.minimum_action or None,
        replacement_action=body.replacement_action or None,
        reason=body.reason or None,
        target_days_per_week=body.target_days_per_week,
        status="active",
        start_date=beijing_today(),
    )
    db.add(program)
    db.commit()
    return active_payload(db, current_user.id)


@router.patch("/{program_id}")
async def update_habit_program(
    program_id: int,
    body: HabitProgramUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    program = get_program_or_404(db, current_user.id, program_id)
    values = body.model_dump(exclude_unset=True)
    mode = program.mode
    minimum = values.get("minimum_action", program.minimum_action)
    replacement = values.get("replacement_action", program.replacement_action)
    validate_path(mode, minimum, replacement)
    if values.get("status") == "active":
        for old in (
            db.query(HabitProgram)
            .filter(
                HabitProgram.user_id == current_user.id,
                HabitProgram.id != program.id,
                HabitProgram.status == "active",
                HabitProgram.deleted_at.is_(None),
            )
            .all()
        ):
            old.status = "paused"
    nullable_text = {"minimum_action", "replacement_action", "reason"}
    for key, value in values.items():
        setattr(program, key, (value or None) if key in nullable_text else value)
    if program.action and program.action.book_title == "习惯计划":
        program.action.action_text = program.title
        program.action.source_excerpt = (program.reason or program.anchor_text)[:500]
    if program.status == "completed" and not program.end_date:
        program.end_date = beijing_today()
    db.commit()
    return active_payload(db, current_user.id)


@router.post("/{program_id}/check-ins")
async def save_habit_check_in(
    program_id: int,
    body: HabitCheckIn,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    program = get_program_or_404(db, current_user.id, program_id)
    if program.status != "active":
        raise HTTPException(status_code=409, detail="这个习惯计划当前未启用")
    event_day = body.event_date or beijing_today()
    if event_day > beijing_today():
        raise HTTPException(status_code=422, detail="不能记录未来的反馈")
    event = (
        db.query(HabitEvent)
        .filter(
            HabitEvent.habit_program_id == program.id,
            HabitEvent.event_date == event_day,
            HabitEvent.event_type == "check_in",
            HabitEvent.source_kind == "manual",
        )
        .first()
    )
    if not event:
        event = HabitEvent(
            user_id=current_user.id,
            habit_program_id=program.id,
            event_date=event_day,
            event_type="check_in",
            source_kind="manual",
        )
        db.add(event)
    event.deleted_at = None
    event.outcome = body.outcome
    event.effort = body.effort if program.mode == "build" else None
    event.urge = body.urge if program.mode == "break" else None
    event.barrier = body.barrier or None
    event.note = body.note or None
    db.commit()
    return active_payload(db, current_user.id)


@router.post("/{program_id}/schedule")
async def schedule_habit_action(
    program_id: int,
    body: HabitScheduleIn,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    program = get_program_or_404(db, current_user.id, program_id)
    if program.status != "active":
        raise HTTPException(status_code=409, detail="这个习惯计划当前未启用")
    task_day = body.task_date or beijing_today()
    existing = (
        db.query(DailyTask)
        .filter(
            DailyTask.user_id == current_user.id,
            DailyTask.task_date == task_day,
            DailyTask.action_id == program.action_id,
            DailyTask.deleted_at.is_(None),
        )
        .first()
    )
    if existing:
        if existing.completed:
            sync_schedule_event(db, current_user.id, existing, True)
            db.commit()
        return {"created": False, "task_id": existing.id, "task_date": task_day}
    text = (
        program.minimum_action
        if program.mode == "build"
        else program.replacement_action
    ) or program.title
    max_order = (
        db.query(func.max(DailyTask.sort_order))
        .filter(
            DailyTask.user_id == current_user.id,
            DailyTask.task_date == task_day,
            DailyTask.parent_id.is_(None),
            DailyTask.deleted_at.is_(None),
        )
        .scalar()
        or 0
    )
    schedule = (
        db.query(DailySchedule)
        .filter(
            DailySchedule.user_id == current_user.id,
            DailySchedule.schedule_date == task_day,
        )
        .first()
    )
    if not schedule:
        db.add(DailySchedule(user_id=current_user.id, schedule_date=task_day))
    task = DailyTask(
        user_id=current_user.id,
        task_date=task_day,
        text=text,
        action_id=program.action_id,
        sort_order=max_order + 1,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"created": True, "task_id": task.id, "task_date": task_day}
