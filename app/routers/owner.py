# -*- coding: utf-8 -*-
"""站长：邀请码与套餐开通。"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts import public_email, user_to_public_dict
from app.audit import write_audit
from app.auth import bump_token_version, get_current_owner
from app.backup import build_backup_zip, latest_backup_path, run_daily_backup
from app.database import get_db
from app.models import AuditLog, InviteCode, User
from app.plans import PLANS, apply_plan, plan_label, sync_subscription
from app.rate_limit import client_ip

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
    write_audit(
        db,
        "invite_generate",
        actor_user_id=_owner.id,
        detail=f"{plan_key} x{payload.count}",
    )
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
    write_audit(
        db,
        "plan_update",
        actor_user_id=_owner.id,
        target_user_id=user.id,
        detail=plan_key,
    )
    return user_to_public_dict(user)


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_user_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    user = db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    bump_token_version(user)
    db.commit()
    write_audit(db, "revoke_sessions", actor_user_id=_owner.id, target_user_id=user.id)
    return {"message": "已作废该用户现有登录"}


@router.get("/export")
async def export_user_details(
    request: Request,
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    payload = build_backup_zip(db)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    write_audit(db, "export", actor_user_id=_owner.id, ip=client_ip(request), detail="zip")
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="shuran-users-{stamp}.zip"'},
    )


@router.get("/audit-logs")
async def list_audit_logs(
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
    return {
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "actor_user_id": row.actor_user_id,
                "target_user_id": row.target_user_id,
                "ip": row.ip,
                "detail": row.detail,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.get("/backups/latest")
async def download_latest_backup(
    request: Request,
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    path = latest_backup_path()
    if path is None or not path.exists():
        path = run_daily_backup()
    if path is None or not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="还没有备份")
    write_audit(db, "backup_download", actor_user_id=_owner.id, ip=client_ip(request))
    return Response(
        content=path.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
    )
