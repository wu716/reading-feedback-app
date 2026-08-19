# -*- coding: utf-8 -*-
"""今日待办、阅读记录、今日概览 API"""
from datetime import date, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import (
    Action,
    DailyTodo,
    PracticeLog,
    ReadingEntry,
    SelfTalk,
    SelfTalkPlaybackLog,
    User,
)

router = APIRouter(prefix="/today", tags=["今日概览"])

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_today() -> date:
    return datetime.now(BEIJING_TZ).date()


# ---------- Schemas ----------


class DailyTodoCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    todo_date: Optional[date] = None


class DailyTodoUpdate(BaseModel):
    text: Optional[str] = Field(None, min_length=1, max_length=500)
    completed: Optional[bool] = None


class DailyTodoResponse(BaseModel):
    id: int
    text: str
    completed: bool
    todo_date: date

    model_config = ConfigDict(from_attributes=True)


class ReadingEntryCreate(BaseModel):
    book_title: Optional[str] = Field(None, max_length=255)
    content: str = Field(..., min_length=1, max_length=20000)
    reflection: Optional[str] = Field(None, max_length=20000)
    duration_minutes: int = Field(0, ge=0, le=24 * 60)
    entry_date: Optional[date] = None


class ReadingEntryUpdate(BaseModel):
    book_title: Optional[str] = Field(None, max_length=255)
    content: Optional[str] = Field(None, min_length=1, max_length=20000)
    reflection: Optional[str] = Field(None, max_length=20000)
    duration_minutes: Optional[int] = Field(None, ge=0, le=24 * 60)


class ReadingEntryResponse(BaseModel):
    id: int
    book_title: Optional[str]
    content: str
    reflection: Optional[str]
    duration_minutes: int
    entry_date: date
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TodayActionItem(BaseModel):
    id: int
    book_title: str
    action_text: str
    source_excerpt: str
    status: str
    practiced_today: bool = False


class TodayPracticeItem(BaseModel):
    id: int
    action_id: int
    action_text: str
    book_title: str
    result: str
    notes: Optional[str]
    date: date
    created_at: datetime


class TodaySelfTalkPlaybackItem(BaseModel):
    id: int
    self_talk_id: int
    duration_seconds: int
    loops_completed: int
    loop_mode: str
    transcript_preview: Optional[str] = None
    created_at: datetime


class TodayOverviewResponse(BaseModel):
    date: date
    reading_total_minutes: int
    reading_goal_minutes: int
    reading_entries: List[ReadingEntryResponse]
    actions_completed: int
    actions_total: int
    action_items: List[TodayActionItem]
    practice_count: int
    practice_items: List[TodayPracticeItem]
    self_talk_play_count: int = 0
    self_talk_play_seconds: int = 0
    self_talk_play_items: List[TodaySelfTalkPlaybackItem] = []
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


@router.post("/todos", response_model=DailyTodoResponse, status_code=status.HTTP_201_CREATED)
async def create_daily_todo(
    body: DailyTodoCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = DailyTodo(
        user_id=current_user.id,
        text=body.text.strip(),
        todo_date=body.todo_date or beijing_today(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
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

    if body.text is not None:
        row.text = body.text.strip()
    if body.completed is not None:
        row.completed = body.completed
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


@router.delete("/todos/{todo_id}")
async def delete_daily_todo(
    todo_id: int,
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
    row.deleted_at = datetime.utcnow()
    db.commit()
    return {"message": "已删除"}


# ---------- Reading Entries ----------


@router.get("/reading-entries", response_model=List[ReadingEntryResponse])
async def list_reading_entries(
    entry_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target = entry_date or beijing_today()
    rows = (
        db.query(ReadingEntry)
        .filter(
            ReadingEntry.user_id == current_user.id,
            ReadingEntry.entry_date == target,
            ReadingEntry.deleted_at.is_(None),
        )
        .order_by(ReadingEntry.id.desc())
        .all()
    )
    return rows


@router.post("/reading-entries", response_model=ReadingEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_reading_entry(
    body: ReadingEntryCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = ReadingEntry(
        user_id=current_user.id,
        book_title=body.book_title,
        content=body.content.strip(),
        reflection=body.reflection.strip() if body.reflection else None,
        duration_minutes=body.duration_minutes,
        entry_date=body.entry_date or beijing_today(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/reading-entries/{entry_id}", response_model=ReadingEntryResponse)
async def update_reading_entry(
    entry_id: int,
    body: ReadingEntryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ReadingEntry)
        .filter(
            ReadingEntry.id == entry_id,
            ReadingEntry.user_id == current_user.id,
            ReadingEntry.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="阅读记录不存在")

    if body.book_title is not None:
        row.book_title = body.book_title
    if body.content is not None:
        row.content = body.content.strip()
    if body.reflection is not None:
        row.reflection = body.reflection.strip() or None
    if body.duration_minutes is not None:
        row.duration_minutes = body.duration_minutes
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


@router.delete("/reading-entries/{entry_id}")
async def delete_reading_entry(
    entry_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ReadingEntry)
        .filter(
            ReadingEntry.id == entry_id,
            ReadingEntry.user_id == current_user.id,
            ReadingEntry.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="阅读记录不存在")
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

    reading_entries = (
        db.query(ReadingEntry)
        .filter(
            ReadingEntry.user_id == current_user.id,
            ReadingEntry.entry_date == target,
            ReadingEntry.deleted_at.is_(None),
        )
        .order_by(ReadingEntry.id.desc())
        .all()
    )
    reading_total = sum(e.duration_minutes or 0 for e in reading_entries)

    actions = (
        db.query(Action)
        .filter(
            Action.user_id == current_user.id,
            Action.deleted_at.is_(None),
        )
        .all()
    )
    actions_total = len(actions)

    practice_rows = (
        db.query(PracticeLog, Action)
        .join(Action, PracticeLog.action_id == Action.id)
        .filter(
            PracticeLog.user_id == current_user.id,
            PracticeLog.date == target,
            PracticeLog.deleted_at.is_(None),
            Action.deleted_at.is_(None),
        )
        .order_by(PracticeLog.created_at.desc())
        .all()
    )
    practiced_action_ids = {log.action_id for log, _ in practice_rows}
    actions_completed = len(practiced_action_ids)

    action_items = [
        TodayActionItem(
            id=a.id,
            book_title=a.book_title,
            action_text=a.action_text,
            source_excerpt=a.source_excerpt,
            status=a.status,
            practiced_today=a.id in practiced_action_ids,
        )
        for a in actions
    ]

    practice_items = [
        TodayPracticeItem(
            id=log.id,
            action_id=log.action_id,
            action_text=action.action_text,
            book_title=action.book_title,
            result=log.result,
            notes=log.notes,
            date=log.date,
            created_at=log.created_at,
        )
        for log, action in practice_rows
    ]

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

    st_play_rows = (
        db.query(SelfTalkPlaybackLog, SelfTalk)
        .join(SelfTalk, SelfTalkPlaybackLog.self_talk_id == SelfTalk.id)
        .filter(
            SelfTalkPlaybackLog.user_id == current_user.id,
            SelfTalkPlaybackLog.play_date == target,
        )
        .order_by(SelfTalkPlaybackLog.created_at.desc())
        .all()
    )
    self_talk_play_count = len(st_play_rows)
    self_talk_play_seconds = sum(r[0].duration_seconds or 0 for r in st_play_rows)
    self_talk_play_items = [
        TodaySelfTalkPlaybackItem(
            id=log.id,
            self_talk_id=log.self_talk_id,
            duration_seconds=log.duration_seconds,
            loops_completed=log.loops_completed,
            loop_mode=log.loop_mode,
            transcript_preview=(talk.transcript or "")[:80] if talk.transcript else None,
            created_at=log.created_at,
        )
        for log, talk in st_play_rows
    ]

    return TodayOverviewResponse(
        date=target,
        reading_total_minutes=reading_total,
        reading_goal_minutes=120,
        reading_entries=reading_entries,
        actions_completed=actions_completed,
        actions_total=actions_total,
        action_items=action_items,
        practice_count=len(practice_items),
        practice_items=practice_items,
        self_talk_play_count=self_talk_play_count,
        self_talk_play_seconds=self_talk_play_seconds,
        self_talk_play_items=self_talk_play_items,
        todos=todos,
    )
