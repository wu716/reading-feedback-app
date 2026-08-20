# -*- coding: utf-8 -*-
"""AI 调用额度：限制单用户每日消耗 DeepSeek 次数。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiCallLog, User

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def enforce_ai_quota(db: Session, user: User, kind: str = "generic") -> None:
    limit = settings.ai_daily_limit
    if limit <= 0:
        return

    today = datetime.now(BEIJING_TZ).date()
    used = (
        db.query(func.count(AiCallLog.id))
        .filter(AiCallLog.user_id == user.id, AiCallLog.call_date == today)
        .scalar()
        or 0
    )
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"今日 AI 次数已用完（{limit} 次/天），请明天再试或联系管理员",
        )
    db.add(AiCallLog(user_id=user.id, kind=kind, call_date=today))
    db.commit()
