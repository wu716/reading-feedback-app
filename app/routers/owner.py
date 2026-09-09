# -*- coding: utf-8 -*-
"""站长：邀请码与套餐开通。"""
import secrets
from datetime import datetime, timedelta, timezone

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts import public_email, user_to_public_dict
from app.auth import get_current_owner
from app.database import get_db
from app.models import InviteCode, User
from app.plans import PLANS, apply_plan, plan_label, sync_subscription

router = APIRouter(prefix="/owner", tags=["站长"])

INVITE_TTL_DAYS = 7
MAX_GENERATE = 5


class InviteGenerateIn(BaseModel):
    plan: str = Field(default="free")
    count: int = Field(default=1, ge=1, le=MAX_GENERATE)
    note: Optional[str] = Field(default=None, max_length=100)


class UserPlanIn(BaseModel):
    plan: str


def _ensure_plan(plan_key: str) -> str:
    key = (plan_key or "").strip().lower()
    if key not in PLANS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="套餐不存在")
    return key


def _random_code(db: Session) -> str:
    for _ in range(40):
        code = f"{secrets.randbelow(10000):04d}"
        exists = db.query(InviteCode).filter(InviteCode.code == code).first()
        if not exists:
            return code
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="邀请码已用尽，请稍后再试")


def _invite_payload(row: InviteCode) -> dict:
    used_name = None
    used_phone = None
    if row.used_by_user is not None:
        used_name = row.used_by_user.name
        used_phone = row.used_by_user.phone
    now = datetime.now(timezone.utc)
    expires_at = row.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return {
        "id": row.id,
        "code": row.code,
        "plan": row.plan,
        "plan_label": plan_label(row.plan),
        "note": row.note,
        "expires_at": row.expires_at,
        "used_at": row.used_at,
        "used_by_user_id": row.used_by_user_id,
        "used_by_name": used_name,
        "used_by_phone": used_phone,
        "created_at": row.created_at,
        "status": "used" if row.used_at else ("expired" if expires_at and expires_at <= now else "unused"),
    }


@router.post("/invite-codes")
async def generate_invite_codes(
    payload: InviteGenerateIn,
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    plan_key = _ensure_plan(payload.plan)
    note = (payload.note or "").strip() or None
    expires_at = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)
    created = []
    for _ in range(payload.count):
        row = InviteCode(
            code=_random_code(db),
            plan=plan_key,
            note=note,
            expires_at=expires_at,
        )
        db.add(row)
        db.flush()
        created.append(_invite_payload(row))
    db.commit()
    return {"items": created}


@router.get("/invite-codes")
async def list_invite_codes(
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    rows = (
        db.query(InviteCode)
        .order_by(InviteCode.created_at.desc(), InviteCode.id.desc())
        .limit(200)
        .all()
    )
    return {"items": [_invite_payload(row) for row in rows]}


@router.get("/users")
async def list_users(
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    rows = (
        db.query(User)
        .filter(User.deleted_at.is_(None))
        .order_by(User.id.desc())
        .limit(300)
        .all()
    )
    items = []
    for user in rows:
        data = user_to_public_dict(user)
        data["email"] = public_email(user.email)
        items.append(data)
    return {"items": items}


@router.patch("/users/{user_id}")
async def update_user_plan(
    user_id: int,
    payload: UserPlanIn,
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    plan_key = _ensure_plan(payload.plan)
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    apply_plan(user, plan_key, persist_subscription=False)
    sync_subscription(db, user, plan_key)
    db.commit()
    db.refresh(user)
    return user_to_public_dict(user)
