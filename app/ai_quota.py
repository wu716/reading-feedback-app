# -*- coding: utf-8 -*-
"""AI 调用额度：抽取与建议分池限制，按套餐读取。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AiCallLog, User
from app.plans import is_owner_user, quota_limits_for_user, resolve_user_plan

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
EXTRACT_KINDS = ("upload-notes",)
ADVICE_KINDS = ("ai-advice", "ai-advice-stream")


def _is_unlimited_user(user: User) -> bool:
    return is_owner_user(user)


def _today():
    return datetime.now(BEIJING_TZ).date()


def _count_used(db: Session, user_id: int, kinds: tuple[str, ...]) -> int:
    today = _today()
    return (
        db.query(func.count(AiCallLog.id))
        .filter(
            AiCallLog.user_id == user_id,
            AiCallLog.call_date == today,
            AiCallLog.kind.in_(kinds),
        )
        .scalar()
        or 0
    )


def _limit_and_kinds(user: User, kind: str) -> tuple[int, tuple[str, ...], str]:
    extract_limit, advice_limit = quota_limits_for_user(user)
    if kind in EXTRACT_KINDS:
        return extract_limit, EXTRACT_KINDS, "抽取行动项"
    return advice_limit, ADVICE_KINDS, "AI 建议"


def enforce_ai_quota(db: Session, user: User, kind: str = "generic") -> None:
    resolve_user_plan(db, user)
    if _is_unlimited_user(user):
        return

    limit, kinds, label = _limit_and_kinds(user, kind)
    if limit <= 0:
        return

    used = _count_used(db, user.id, kinds)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"今日{label}次数已用完（{limit} 次/天），请明天再试或联系管理员",
        )
    db.add(AiCallLog(user_id=user.id, kind=kind, call_date=_today()))
    db.commit()


def get_quota_status(db: Session, user: User) -> dict:
    resolve_user_plan(db, user)
    extract_used = _count_used(db, user.id, EXTRACT_KINDS)
    advice_used = _count_used(db, user.id, ADVICE_KINDS)
    if _is_unlimited_user(user):
        return {
            "extract_limit": 0,
            "extract_used": extract_used,
            "extract_remaining": None,
            "advice_limit": 0,
            "advice_used": advice_used,
            "advice_remaining": None,
        }

    extract_limit, advice_limit = quota_limits_for_user(user)
    return {
        "extract_limit": extract_limit,
        "extract_used": extract_used,
        "extract_remaining": max(0, extract_limit - extract_used) if extract_limit > 0 else None,
        "advice_limit": advice_limit,
        "advice_used": advice_used,
        "advice_remaining": max(0, advice_limit - advice_used) if advice_limit > 0 else None,
    }
