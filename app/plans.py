# -*- coding: utf-8 -*-
"""产品套餐：体验 / 月卡 / 学期卡。"""
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Subscription, User

OWNER_EMAILS = frozenset({"2721095772@qq.com"})

PLAN_FREE = "free"
PLAN_MONTHLY = "monthly"
PLAN_SEMESTER = "semester"

PLANS = {
    PLAN_FREE: {
        "key": PLAN_FREE,
        "label": "体验",
        "price": 0,
        "price_text": "免费",
        "days": None,
        "duration_text": "长期有效",
        "summary": "完整记录与计时、日报周报、本人数据导出。",
    },
    PLAN_MONTHLY: {
        "key": PLAN_MONTHLY,
        "label": "月卡",
        "price": 9.9,
        "price_text": "¥9.9 / 30 天",
        "days": 30,
        "duration_text": "30 天",
        "summary": "深度复盘：月季年报、跨期对比、主题分析、复盘目标与消费预算。",
    },
    PLAN_SEMESTER: {
        "key": PLAN_SEMESTER,
        "label": "学期卡",
        "price": 39,
        "price_text": "¥39 / 120 天",
        "days": 120,
        "duration_text": "120 天",
        "summary": "与月卡权益相同，连续使用 120 天。",
    },
}

PAID_PLANS = (PLAN_MONTHLY, PLAN_SEMESTER)


def plan_catalog() -> list[dict]:
    return [dict(spec) for spec in PLANS.values()]


def is_owner_user(user: Optional[User]) -> bool:
    if user is None:
        return False
    email = (getattr(user, "email", None) or "").strip().lower()
    return email in OWNER_EMAILS


def get_plan_spec(plan_key: str) -> dict:
    return PLANS.get(plan_key) or PLANS[PLAN_FREE]


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def effective_plan_key(user: User) -> str:
    if is_owner_user(user):
        return PLAN_SEMESTER
    key = (getattr(user, "plan", None) or PLAN_FREE).strip().lower()
    if key not in PLANS:
        return PLAN_FREE
    expires = getattr(user, "plan_expires_at", None)
    if key in PAID_PLANS and (expires is None or expires < _today()):
        return PLAN_FREE
    return key


def resolve_user_plan(db: Session, user: User) -> str:
    """缺少有效到期日的付费套餐落回体验并写回数据库。"""
    if is_owner_user(user):
        return PLAN_SEMESTER
    key = (getattr(user, "plan", None) or PLAN_FREE).strip().lower()
    if key not in PLANS:
        key = PLAN_FREE
    expires = getattr(user, "plan_expires_at", None)
    if key in PAID_PLANS and (expires is None or expires < _today()):
        apply_plan(user, PLAN_FREE, persist_subscription=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return PLAN_FREE
    return key


def apply_plan(user: User, plan_key: str, persist_subscription: bool = True, *, renew: bool = False) -> None:
    """Apply a plan. Paid renewals preserve the remaining time of any active paid plan."""
    spec = get_plan_spec(plan_key)
    today = _today()
    previous_plan = (getattr(user, "plan", None) or PLAN_FREE).strip().lower()
    previous_expiry = getattr(user, "plan_expires_at", None)
    days = spec.get("days")
    if days:
        starts_after = today
        if renew and previous_plan in PAID_PLANS and previous_expiry and previous_expiry >= today:
            starts_after = previous_expiry
        user.plan_expires_at = starts_after + timedelta(days=days)
    else:
        user.plan_expires_at = None
    user.plan = spec["key"]
    if persist_subscription and getattr(user, "subscription", None):
        user.subscription.plan = spec["key"]
        user.subscription.start_date = today
        user.subscription.end_date = user.plan_expires_at
        user.subscription.is_active = True


def sync_subscription(db: Session, user: User, plan_key: str) -> Subscription:
    spec = get_plan_spec(plan_key)
    sub = user.subscription
    if sub is None:
        sub = Subscription(
            user_id=user.id,
            plan=spec["key"],
            start_date=_today(),
            end_date=user.plan_expires_at,
            is_active=True,
        )
        db.add(sub)
        return sub
    sub.plan = spec["key"]
    sub.start_date = _today()
    sub.end_date = user.plan_expires_at
    sub.is_active = True
    return sub


def plan_label(plan_key: str) -> str:
    return get_plan_spec(plan_key)["label"]
