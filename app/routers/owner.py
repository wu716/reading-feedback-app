# -*- coding: utf-8 -*-
"""站长：邀请码与套餐开通。"""
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import public_email, user_to_public_dict
from app.audit import write_audit
from app.auth import bump_token_version, get_current_owner
from app.backup import build_backup_zip, latest_backup_path, run_daily_backup
from app.database import get_db
from app.models import AuditLog, GrantEvent, InviteCode, PaymentTransaction, RefundTransaction, User
from app.plans import PLANS, _today, apply_plan, plan_label, sync_subscription
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


class PaymentIn(BaseModel):
    user_id: int = Field(gt=0)
    plan: Literal["monthly", "semester"]
    amount_cents: int = Field(gt=0)
    channel: Literal["wechat", "alipay", "bank", "other"]
    transaction_reference: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    paid_at: datetime
    note: Optional[str] = Field(default=None, max_length=300)

    @field_validator("note")
    @classmethod
    def strip_optional(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None

    @field_validator("transaction_reference")
    @classmethod
    def strip_payment_reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请填写可核对的转账单号")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def strip_key(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 8:
            raise ValueError("幂等键至少 8 个字符")
        return value

    @field_validator("paid_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("付款时间须包含时区")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("付款时间不能晚于当前时间")
        return value.astimezone(timezone.utc)


class GrantIn(BaseModel):
    user_id: int = Field(gt=0)
    plan: Literal["free", "monthly", "semester"]
    kind: Literal["gift", "correction"]
    reason: str = Field(min_length=2, max_length=300)
    expires_at: Optional[date] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=128)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("请填写具体原因")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def strip_grant_key(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 8:
            raise ValueError("幂等键至少 8 个字符")
        return value


class RefundIn(BaseModel):
    payment_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0)
    channel: Literal["wechat", "alipay", "bank", "other"]
    transaction_reference: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=128)
    refunded_at: datetime
    reason: str = Field(min_length=2, max_length=300)

    @field_validator("transaction_reference")
    @classmethod
    def strip_reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请填写可核对的退款单号")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def strip_refund_key(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 8:
            raise ValueError("幂等键至少 8 个字符")
        return value

    @field_validator("reason")
    @classmethod
    def strip_refund_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("请填写具体原因")
        return value

    @field_validator("refunded_at")
    @classmethod
    def require_refund_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("退款时间须包含时区")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("退款时间不能晚于当前时间")
        return value.astimezone(timezone.utc)


def _payment_payload(row: PaymentTransaction) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "actor_user_id": row.actor_user_id,
        "plan": row.plan,
        "amount_cents": row.amount_cents,
        "channel": row.channel,
        "transaction_reference": row.transaction_reference,
        "idempotency_key": row.idempotency_key,
        "paid_at": _utc_datetime(row.paid_at),
        "note": row.note,
        "prior_plan": row.prior_plan,
        "prior_expires_at": row.prior_expires_at,
        "new_expires_at": row.new_expires_at,
        "recorded_at": _utc_datetime(row.recorded_at),
    }


def _refund_payload(row: RefundTransaction) -> dict:
    return {
        "id": row.id,
        "payment_id": row.payment_id,
        "user_id": row.user_id,
        "actor_user_id": row.actor_user_id,
        "amount_cents": row.amount_cents,
        "channel": row.channel,
        "transaction_reference": row.transaction_reference,
        "idempotency_key": row.idempotency_key,
        "refunded_at": _utc_datetime(row.refunded_at),
        "reason": row.reason,
        "recorded_at": _utc_datetime(row.recorded_at),
    }


def _grant_payload(row: GrantEvent) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "actor_user_id": row.actor_user_id,
        "kind": row.kind,
        "plan": row.plan,
        "reason": row.reason,
        "idempotency_key": row.idempotency_key,
        "requested_expires_at": row.requested_expires_at,
        "prior_plan": row.prior_plan,
        "prior_expires_at": row.prior_expires_at,
        "new_expires_at": row.new_expires_at,
        "invite_code_id": row.invite_code_id,
        "created_at": _utc_datetime(row.created_at),
    }


def _utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite drops timezone metadata; billing timestamps are stored in UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _same_payment(row: PaymentTransaction, payload: PaymentIn) -> bool:
    paid_at = row.paid_at.replace(tzinfo=timezone.utc) if row.paid_at.tzinfo is None else row.paid_at.astimezone(timezone.utc)
    return (
        row.user_id == payload.user_id
        and row.plan == payload.plan
        and row.amount_cents == payload.amount_cents
        and row.channel == payload.channel
        and row.transaction_reference == payload.transaction_reference
        and paid_at == payload.paid_at
        and row.note == payload.note
    )


def _same_refund(row: RefundTransaction, payload: RefundIn) -> bool:
    refunded_at = row.refunded_at.replace(tzinfo=timezone.utc) if row.refunded_at.tzinfo is None else row.refunded_at.astimezone(timezone.utc)
    return (
        row.payment_id == payload.payment_id
        and row.amount_cents == payload.amount_cents
        and row.channel == payload.channel
        and row.transaction_reference == payload.transaction_reference
        and refunded_at == payload.refunded_at
        and row.reason == payload.reason
    )


def _same_grant(row: GrantEvent, payload: GrantIn) -> bool:
    return (
        row.user_id == payload.user_id
        and row.kind == payload.kind
        and row.plan == payload.plan
        and row.reason == payload.reason
        and row.requested_expires_at == payload.expires_at
    )


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
    if plan_key != "free":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新邀请码仅用于体验注册；付费请在用户注册后登记收款并开通")
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


@router.post("/payments", status_code=status.HTTP_201_CREATED)
async def record_payment(
    payload: PaymentIn,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    """Record money already received and extend entitlement in one transaction."""
    user = db.query(User).filter(User.id == payload.user_id, User.deleted_at.is_(None)).with_for_update().first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    catalog_cents = {"monthly": 990, "semester": 3900}[payload.plan]
    if payload.amount_cents != catalog_cents and not payload.note:
        raise HTTPException(status_code=400, detail="实收金额与套餐定价不同，请在内部备注说明原因")
    previous = db.query(PaymentTransaction).filter(PaymentTransaction.idempotency_key == payload.idempotency_key).first()
    if previous is not None:
        if _same_payment(previous, payload):
            return _payment_payload(previous)
        raise HTTPException(status_code=409, detail="幂等键已用于另一笔收款")
    if payload.transaction_reference:
        duplicate = db.query(PaymentTransaction).filter(
            PaymentTransaction.channel == payload.channel,
            PaymentTransaction.transaction_reference == payload.transaction_reference,
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="该渠道交易参考号已登记")

    prior_plan = user.plan or "free"
    prior_expires_at = user.plan_expires_at
    apply_plan(user, payload.plan, persist_subscription=False, renew=True)
    sync_subscription(db, user, payload.plan)
    row = PaymentTransaction(
        user_id=user.id,
        actor_user_id=owner.id,
        plan=payload.plan,
        amount_cents=payload.amount_cents,
        channel=payload.channel,
        transaction_reference=payload.transaction_reference,
        idempotency_key=payload.idempotency_key,
        paid_at=payload.paid_at,
        note=payload.note,
        prior_plan=prior_plan,
        prior_expires_at=prior_expires_at,
        new_expires_at=user.plan_expires_at,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        previous = db.query(PaymentTransaction).filter(PaymentTransaction.idempotency_key == payload.idempotency_key).first()
        if previous is not None and _same_payment(previous, payload):
            return _payment_payload(previous)
        raise HTTPException(status_code=409, detail="收款记录重复，请核对交易参考号") from exc
    db.refresh(row)
    return _payment_payload(row)


@router.get("/payments")
async def list_payments(
    user_id: Optional[int] = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    query = db.query(PaymentTransaction)
    if user_id is not None:
        query = query.filter(PaymentTransaction.user_id == user_id)
    return {
        "items": [_payment_payload(row) for row in query.order_by(PaymentTransaction.id.desc()).offset(offset).limit(limit).all()],
        "total": query.count(),
    }


@router.post("/refunds", status_code=status.HTTP_201_CREATED)
async def record_refund(
    payload: RefundIn,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    """Record an actual exceptional refund; entitlement correction is separate."""
    payment = db.query(PaymentTransaction).filter(PaymentTransaction.id == payload.payment_id).with_for_update().first()
    if payment is None:
        raise HTTPException(status_code=404, detail="原收款记录不存在")
    paid_at = payment.paid_at.replace(tzinfo=timezone.utc) if payment.paid_at.tzinfo is None else payment.paid_at.astimezone(timezone.utc)
    if payload.refunded_at < paid_at:
        raise HTTPException(status_code=400, detail="退款时间不能早于付款时间")
    previous = db.query(RefundTransaction).filter(RefundTransaction.idempotency_key == payload.idempotency_key).first()
    if previous is not None:
        if _same_refund(previous, payload):
            return _refund_payload(previous)
        raise HTTPException(status_code=409, detail="幂等键已用于另一笔退款")
    if payload.transaction_reference:
        duplicate = db.query(RefundTransaction).filter(
            RefundTransaction.channel == payload.channel,
            RefundTransaction.transaction_reference == payload.transaction_reference,
        ).first()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="该渠道退款交易参考号已登记")
    refunded_cents = db.query(func.coalesce(func.sum(RefundTransaction.amount_cents), 0)).filter(
        RefundTransaction.payment_id == payment.id
    ).scalar()
    if refunded_cents + payload.amount_cents > payment.amount_cents:
        raise HTTPException(status_code=409, detail="累计退款不能超过原收款金额")
    row = RefundTransaction(
        payment_id=payment.id,
        user_id=payment.user_id,
        actor_user_id=owner.id,
        amount_cents=payload.amount_cents,
        channel=payload.channel,
        transaction_reference=payload.transaction_reference,
        idempotency_key=payload.idempotency_key,
        refunded_at=payload.refunded_at,
        reason=payload.reason,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        previous = db.query(RefundTransaction).filter(RefundTransaction.idempotency_key == payload.idempotency_key).first()
        if previous is not None and _same_refund(previous, payload):
            return _refund_payload(previous)
        raise HTTPException(status_code=409, detail="退款记录重复，请核对交易参考号") from exc
    db.refresh(row)
    return _refund_payload(row)


@router.get("/refunds")
async def list_refunds(
    user_id: Optional[int] = Query(default=None, gt=0),
    payment_id: Optional[int] = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    query = db.query(RefundTransaction)
    if user_id is not None:
        query = query.filter(RefundTransaction.user_id == user_id)
    if payment_id is not None:
        query = query.filter(RefundTransaction.payment_id == payment_id)
    return {
        "items": [_refund_payload(row) for row in query.order_by(RefundTransaction.id.desc()).offset(offset).limit(limit).all()],
        "total": query.count(),
    }


@router.post("/grants", status_code=status.HTTP_201_CREATED)
async def record_grant(
    payload: GrantIn,
    db: Session = Depends(get_db),
    owner: User = Depends(get_current_owner),
):
    """Gift or correct entitlement with a mandatory reason and durable event."""
    if payload.kind == "gift" and (payload.plan == "free" or payload.expires_at is not None):
        raise HTTPException(status_code=400, detail="赠送请选择付费套餐，且不指定到期日")
    if payload.plan == "free" and payload.expires_at is not None:
        raise HTTPException(status_code=400, detail="体验套餐不能指定到期日")
    if payload.expires_at is not None and payload.expires_at < _today():
        raise HTTPException(status_code=400, detail="更正到期日不能早于今天")

    user = db.query(User).filter(User.id == payload.user_id, User.deleted_at.is_(None)).with_for_update().first()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.idempotency_key:
        previous = db.query(GrantEvent).filter(GrantEvent.idempotency_key == payload.idempotency_key).first()
        if previous is not None:
            if _same_grant(previous, payload):
                return _grant_payload(previous)
            raise HTTPException(status_code=409, detail="幂等键已用于另一项权益调整")
    prior_plan = user.plan or "free"
    prior_expires_at = user.plan_expires_at
    apply_plan(user, payload.plan, persist_subscription=False, renew=payload.kind == "gift")
    if payload.kind == "correction" and payload.expires_at is not None:
        user.plan_expires_at = payload.expires_at
    sync_subscription(db, user, payload.plan)
    row = GrantEvent(
        user_id=user.id,
        actor_user_id=owner.id,
        kind=payload.kind,
        plan=payload.plan,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
        requested_expires_at=payload.expires_at,
        prior_plan=prior_plan,
        prior_expires_at=prior_expires_at,
        new_expires_at=user.plan_expires_at,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if payload.idempotency_key:
            previous = db.query(GrantEvent).filter(GrantEvent.idempotency_key == payload.idempotency_key).first()
            if previous is not None and _same_grant(previous, payload):
                return _grant_payload(previous)
        raise HTTPException(status_code=409, detail="权益调整重复，请核对后重试") from exc
    db.refresh(row)
    return _grant_payload(row)


@router.get("/grants")
async def list_grants(
    user_id: Optional[int] = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    query = db.query(GrantEvent)
    if user_id is not None:
        query = query.filter(GrantEvent.user_id == user_id)
    return {
        "items": [_grant_payload(row) for row in query.order_by(GrantEvent.id.desc()).offset(offset).limit(limit).all()],
        "total": query.count(),
    }


@router.patch("/users/{user_id}")
async def update_user_plan(
    user_id: int,
    payload: UserPlanIn,
    db: Session = Depends(get_db),
    _owner: User = Depends(get_current_owner),
):
    raise HTTPException(status_code=409, detail="请使用收款登记或赠送/更正接口，并保留可核对的记录")


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
