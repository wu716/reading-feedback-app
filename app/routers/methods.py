"""方法卡首发版：情境、第一步、实际使用反馈与站长市场反馈。"""
from datetime import datetime, time, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_active_user, get_current_owner, resolve_user_from_access_token
from app.database import get_db
from app.models import Action, EbookNote, MethodCard, MethodUse, MethodVisit, ProductFeedback, User
from app.rate_limit import client_ip, guard_rate_limit, record_rate_hit

router = APIRouter(prefix="/methods", tags=["方法卡"])
optional_bearer = HTTPBearer(auto_error=False)
BEIJING = ZoneInfo("Asia/Shanghai")
Outcome = Literal["helpful", "not_helpful", "not_used"]
Barrier = Literal["forgot", "too_hard", "interrupted", "not_suitable", "other"]


class TextInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CardCreate(TextInput):
    client_key: UUID = Field(default_factory=uuid4)
    title: str = Field(default="", max_length=120)
    situation: str = Field(min_length=1, max_length=500)
    first_step: str = Field(min_length=1, max_length=500)
    source_title: str = Field(default="", max_length=255)
    source_excerpt: str = Field(default="", max_length=2000)
    source_note_id: Optional[int] = Field(default=None, gt=0)


class CardUpdate(TextInput):
    title: str = Field(default="", max_length=120)
    situation: str = Field(min_length=1, max_length=500)
    first_step: str = Field(min_length=1, max_length=500)
    source_title: str = Field(default="", max_length=255)
    source_excerpt: str = Field(default="", max_length=2000)
    state: Literal["active", "paused"] = "active"


class UseStart(TextInput):
    client_key: UUID = Field(default_factory=uuid4)


class UseFeedback(TextInput):
    outcome: Outcome
    barrier: Optional[Barrier] = None
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def helpful_has_no_barrier(self):
        if self.outcome == "helpful":
            self.barrier = None
        return self


class VisitInput(TextInput):
    session_key: UUID
    event_name: Literal["opened", "demo_saved", "demo_started", "demo_feedback"] = "opened"


class ProductFeedbackInput(TextInput):
    session_key: UUID
    category: Literal["problem", "suggestion", "useful"] = "problem"
    message: str = Field(min_length=3, max_length=1500)


def optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not credentials:
        return None
    user = resolve_user_from_access_token(credentials.credentials, db)
    if not user.is_active:
        raise HTTPException(status_code=401, detail="请重新登录")
    return user


def iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def window_start(days: int = 7):
    first_day = datetime.now(BEIJING).date() - timedelta(days=days - 1)
    return datetime.combine(first_day, time.min, tzinfo=BEIJING).astimezone(timezone.utc)


def owned_card(db: Session, user_id: int, card_id: int):
    card = db.query(MethodCard).filter(
        MethodCard.id == card_id, MethodCard.user_id == user_id, MethodCard.deleted_at.is_(None)
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="这张方法卡不存在")
    return card


def use_payload(row):
    return {
        "id": row.id, "card_id": row.card_id, "outcome": row.outcome,
        "barrier": row.barrier, "note": row.note or "",
        "situation": row.situation_snapshot, "first_step": row.step_snapshot,
        "started_at": iso(row.started_at), "finished_at": iso(row.finished_at),
    }


def card_payload(card, uses=()):
    pending = next((use for use in uses if use.finished_at is None), None)
    finished = [use for use in uses if use.finished_at is not None]
    return {
        "id": card.id, "title": card.title, "situation": card.situation,
        "first_step": card.first_step, "source_title": card.source_title or "",
        "source_excerpt": card.source_excerpt or "", "state": card.state,
        "created_at": iso(card.created_at),
        "tried_count": sum(use.outcome in ("helpful", "not_helpful") for use in finished),
        "helpful_count": sum(use.outcome == "helpful" for use in finished),
        "pending_use": use_payload(pending) if pending else None,
        "recent_uses": [use_payload(use) for use in finished[:5]],
    }


@router.post("/visits", status_code=201)
def record_visit(
    body: VisitInput, request: Request, db: Session = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    key = f"method-visit:{client_ip(request)}"
    guard_rate_limit(key, 180, 60, "访问过于频繁，请稍后再试")
    record_rate_hit(key)
    session_key = str(body.session_key)
    row = db.query(MethodVisit).filter(
        MethodVisit.session_key == session_key, MethodVisit.event_name == body.event_name
    ).first()
    if row:
        # Preserve the first visit; a session may later sign in.
        if user and row.user_id is None:
            row.user_id = user.id
            db.commit()
        return {"recorded": False}
    db.add(MethodVisit(session_key=session_key, event_name=body.event_name, user_id=user.id if user else None))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"recorded": False}
    return {"recorded": True}


@router.post("/product-feedback", status_code=201)
def send_product_feedback(
    body: ProductFeedbackInput, request: Request, db: Session = Depends(get_db),
    user: Optional[User] = Depends(optional_user),
):
    key = f"method-feedback:{client_ip(request)}"
    guard_rate_limit(key, 8, 3600, "反馈提交较多，请稍后再试")
    record_rate_hit(key)
    row = ProductFeedback(
        session_key=str(body.session_key), user_id=user.id if user else None,
        category=body.category, message=body.message,
    )
    db.add(row)
    db.commit()
    return {"message": "收到，谢谢你告诉我们实际遇到的问题。"}


@router.get("/market")
def market_feedback(owner: User = Depends(get_current_owner), db: Session = Depends(get_db)):
    since = window_start()
    cards = db.query(MethodCard).filter(MethodCard.deleted_at.is_(None))
    uses = db.query(MethodUse).join(MethodCard).filter(MethodCard.deleted_at.is_(None))
    visit_counts = dict(db.query(MethodVisit.event_name, func.count(MethodVisit.id)).filter(
        MethodVisit.created_at >= since
    ).group_by(MethodVisit.event_name).all())
    # A click on "start" is not evidence that the method was actually tried.
    started_users = uses.filter(MethodUse.started_at >= since).with_entities(MethodUse.user_id).distinct().count()
    tried = uses.filter(MethodUse.finished_at >= since, MethodUse.outcome.in_(["helpful", "not_helpful"]))
    trial_days = {}
    for user_id, started_at in tried.filter(MethodUse.started_at >= since).with_entities(MethodUse.user_id, MethodUse.started_at).all():
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        trial_days.setdefault(user_id, set()).add(started_at.astimezone(BEIJING).date())
    messages = db.query(ProductFeedback).filter(ProductFeedback.created_at >= since).order_by(
        ProductFeedback.created_at.desc(), ProductFeedback.id.desc()
    ).limit(50).all()
    return {
        "period_days": 7, "since": iso(since),
        "visit_sessions": visit_counts.get("opened", 0),
        "demo_sessions": {name: visit_counts.get(name, 0) for name in ("demo_saved", "demo_started", "demo_feedback")},
        "created_users": cards.filter(MethodCard.created_at >= since).with_entities(MethodCard.user_id).distinct().count(),
        "started_users": started_users,
        "tried_users": tried.with_entities(MethodUse.user_id).distinct().count(),
        "returning_users": sum(len(days) >= 2 for days in trial_days.values()),
        "helpful_feedback": tried.filter(MethodUse.outcome == "helpful").count(),
        "not_helpful_feedback": tried.filter(MethodUse.outcome == "not_helpful").count(),
        "not_used_feedback": uses.filter(MethodUse.finished_at >= since, MethodUse.outcome == "not_used").count(),
        "feedback": [{"id": row.id, "category": row.category, "message": row.message,
                      "from_member": row.user_id is not None, "created_at": iso(row.created_at)} for row in messages],
    }


@router.get("/sources")
def existing_sources(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    actions = db.query(Action).filter(Action.user_id == user.id, Action.deleted_at.is_(None)).order_by(
        Action.created_at.desc(), Action.id.desc()
    ).limit(50).all()
    return {"items": [{"id": row.id, "title": row.action_text[:120], "first_step": row.action_text[:500],
                       "source_title": row.book_title, "source_excerpt": (row.source_excerpt or "")[:2000]} for row in actions]}


@router.get("")
def list_cards(
    search: str = "", state: Literal["active", "paused", "all"] = "active",
    user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
):
    query = db.query(MethodCard).filter(MethodCard.user_id == user.id, MethodCard.deleted_at.is_(None))
    if state != "all":
        query = query.filter(MethodCard.state == state)
    term = search.strip()[:100]
    if term:
        query = query.filter(or_(MethodCard.title.icontains(term, autoescape=True), MethodCard.situation.icontains(term, autoescape=True),
                                 MethodCard.first_step.icontains(term, autoescape=True), MethodCard.source_title.icontains(term, autoescape=True)))
    total = query.count()
    cards = query.order_by(MethodCard.created_at.desc(), MethodCard.id.desc()).limit(100).all()
    ids = [card.id for card in cards]
    by_card = {}
    if ids:
        for use in db.query(MethodUse).filter(MethodUse.user_id == user.id, MethodUse.card_id.in_(ids)).order_by(
            MethodUse.started_at.desc(), MethodUse.id.desc()
        ).all():
            by_card.setdefault(use.card_id, []).append(use)
    return {"items": [card_payload(card, by_card.get(card.id, [])) for card in cards], "limit": 100, "total": total}


@router.post("", status_code=201)
def create_card(body: CardCreate, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    key = str(body.client_key)
    existing = db.query(MethodCard).filter(MethodCard.user_id == user.id, MethodCard.client_key == key).first()
    if existing:
        if existing.deleted_at is not None:
            raise HTTPException(status_code=409, detail="这张方法卡已移除，请重新新建")
        return card_payload(existing)
    if body.source_note_id is not None:
        note = db.query(EbookNote).filter(EbookNote.id == body.source_note_id, EbookNote.user_id == user.id).first()
        if not note:
            raise HTTPException(status_code=404, detail="来源笔记不存在")
    card = MethodCard(
        user_id=user.id, client_key=key, title=body.title or body.first_step[:60],
        situation=body.situation, first_step=body.first_step,
        source_title=body.source_title or None, source_excerpt=body.source_excerpt or None,
        source_note_id=body.source_note_id,
    )
    db.add(card)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        card = db.query(MethodCard).filter(MethodCard.user_id == user.id, MethodCard.client_key == key).first()
        if not card or card.deleted_at is not None:
            raise HTTPException(status_code=409, detail="保存冲突，请重新新建")
    db.refresh(card)
    return card_payload(card)


@router.put("/{card_id}")
def update_card(card_id: int, body: CardUpdate, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    card = owned_card(db, user.id, card_id)
    card.title = body.title or body.first_step[:60]
    card.situation = body.situation
    card.first_step = body.first_step
    card.source_title = body.source_title or None
    card.source_excerpt = body.source_excerpt or None
    card.state = body.state
    db.commit()
    db.refresh(card)
    return card_payload(card)


@router.delete("/{card_id}", status_code=204)
def delete_card(card_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    card = owned_card(db, user.id, card_id)
    card.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{card_id}/uses", status_code=201)
def start_use(card_id: int, body: UseStart, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    card = owned_card(db, user.id, card_id)
    if card.state != "active":
        raise HTTPException(status_code=409, detail="请先恢复这张方法卡，再开始尝试")
    key = str(body.client_key)
    existing = db.query(MethodUse).filter(MethodUse.user_id == user.id, MethodUse.client_key == key).first()
    if existing:
        if existing.card_id != card.id:
            raise HTTPException(status_code=409, detail="尝试记录冲突，请重新打开方法卡")
        return use_payload(existing)
    pending = db.query(MethodUse).filter(MethodUse.user_id == user.id, MethodUse.card_id == card.id,
                                        MethodUse.finished_at.is_(None)).order_by(MethodUse.id.desc()).first()
    if pending:
        return use_payload(pending)
    row = MethodUse(user_id=user.id, card_id=card.id, client_key=key,
                    situation_snapshot=card.situation, step_snapshot=card.first_step)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(MethodUse).filter(MethodUse.user_id == user.id, MethodUse.client_key == key).first()
        if row is None:
            row = db.query(MethodUse).filter(MethodUse.user_id == user.id, MethodUse.card_id == card.id,
                                             MethodUse.finished_at.is_(None)).first()
        if not row or row.card_id != card.id:
            raise HTTPException(status_code=409, detail="尝试记录冲突，请稍后再试")
    db.refresh(row)
    return use_payload(row)


@router.put("/uses/{use_id}")
def finish_use(use_id: int, body: UseFeedback, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = db.query(MethodUse).join(MethodCard).filter(
        MethodUse.id == use_id, MethodUse.user_id == user.id,
        MethodCard.user_id == user.id, MethodCard.deleted_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="这次尝试不存在")
    row.outcome, row.barrier, row.note = body.outcome, body.barrier, body.note or None
    if row.finished_at is None:
        row.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return use_payload(row)
