# -*- coding: utf-8 -*-
"""快捷记下：一个入口，时刻 / 灵感 / 待办三种去处。"""
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import DailyTodo, FutureAction, Idea, User
from app.routers.time_log import NodeCreate, punch_node

router = APIRouter(prefix="/capture", tags=["快捷记下"])
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
CAPTURE_KINDS = {"moment", "idea", "todo"}
TODO_WHENS = {"today", "later"}


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def beijing_today():
    return beijing_now().date()


def normalize_kind(value: Optional[str]) -> str:
    kind = (value or "").strip().lower()
    return kind if kind in CAPTURE_KINDS else "moment"


def normalize_todo_when(value: Optional[str]) -> str:
    when = (value or "").strip().lower()
    return when if when in TODO_WHENS else "today"


class PreferenceOut(BaseModel):
    kind: str


class PreferenceUpdate(BaseModel):
    kind: str

    @field_validator("kind")
    @classmethod
    def check_kind(cls, value: str) -> str:
        kind = normalize_kind(value)
        if (value or "").strip().lower() not in CAPTURE_KINDS:
            raise ValueError("去处只能是时刻、灵感或待办")
        return kind


class CaptureIn(BaseModel):
    kind: str = "moment"
    text: str = Field(..., min_length=1, max_length=500)
    todo_when: Optional[str] = None
    logged_at: Optional[datetime] = None

    @field_validator("kind")
    @classmethod
    def check_kind(cls, value: str) -> str:
        kind = (value or "").strip().lower()
        if kind not in CAPTURE_KINDS:
            raise ValueError("去处只能是时刻、灵感或待办")
        return kind

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("请先写下内容")
        return text

    @field_validator("todo_when")
    @classmethod
    def check_when(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        when = value.strip().lower()
        if when not in TODO_WHENS:
            raise ValueError("待办请选择今天或以后")
        return when


class CaptureOut(BaseModel):
    kind: str
    id: int
    todo_when: Optional[str] = None


class IdeaOut(BaseModel):
    id: int
    text: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class IdeaListOut(BaseModel):
    items: List[IdeaOut]


class IdeaUpdate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("请先写下内容")
        return text


def visible_ideas(db: Session, user_id: int) -> List[Idea]:
    return (
        db.query(Idea)
        .filter(Idea.user_id == user_id, Idea.deleted_at.is_(None))
        .order_by(Idea.id.desc())
        .all()
    )


def get_idea_or_404(db: Session, user_id: int, item_id: int) -> Idea:
    item = (
        db.query(Idea)
        .filter(Idea.id == item_id, Idea.user_id == user_id, Idea.deleted_at.is_(None))
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="这条灵感不存在")
    return item


@router.get("/preference", response_model=PreferenceOut)
async def get_capture_preference(current_user: User = Depends(get_current_active_user)):
    return PreferenceOut(kind=normalize_kind(getattr(current_user, "capture_kind", None)))


@router.patch("/preference", response_model=PreferenceOut)
async def update_capture_preference(
    body: PreferenceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    current_user.capture_kind = body.kind
    db.commit()
    return PreferenceOut(kind=body.kind)


@router.post("/save", response_model=CaptureOut)
async def capture_note(
    body: CaptureIn,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if body.kind == "moment":
        node = await punch_node(
            NodeCreate(label=body.text, logged_at=body.logged_at),
            current_user,
            db,
        )
        return CaptureOut(kind="moment", id=node.id)

    if body.kind == "idea":
        item = Idea(user_id=current_user.id, text=body.text)
        db.add(item)
        db.commit()
        db.refresh(item)
        return CaptureOut(kind="idea", id=item.id)

    when = normalize_todo_when(body.todo_when)
    if when == "later":
        item = FutureAction(user_id=current_user.id, text=body.text)
        db.add(item)
        db.commit()
        db.refresh(item)
        return CaptureOut(kind="todo", id=item.id, todo_when="later")

    row = DailyTodo(
        user_id=current_user.id,
        text=body.text,
        todo_date=beijing_today(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return CaptureOut(kind="todo", id=row.id, todo_when="today")


@router.get("/ideas", response_model=IdeaListOut)
async def list_ideas(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return IdeaListOut(items=[IdeaOut.model_validate(item) for item in visible_ideas(db, current_user.id)])


@router.patch("/ideas/{item_id}", response_model=IdeaOut)
async def update_idea(
    item_id: int,
    body: IdeaUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = get_idea_or_404(db, current_user.id, item_id)
    item.text = body.text
    db.commit()
    db.refresh(item)
    return item


@router.delete("/ideas/{item_id}", response_model=IdeaListOut)
async def delete_idea(
    item_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    item = get_idea_or_404(db, current_user.id, item_id)
    item.deleted_at = beijing_now()
    db.commit()
    return IdeaListOut(items=[IdeaOut.model_validate(row) for row in visible_ideas(db, current_user.id)])
