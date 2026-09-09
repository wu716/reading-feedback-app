# -*- coding: utf-8 -*-
"""产品套餐：体验 / 月卡 / 学期卡。"""
from datetime import date, timedelta
from typing import Optional

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
        "extract_limit": 1,
        "advice_limit": 2,
        "days": None,
        "duration_text": "长期有效",
        "summary": "邀请注册后的基础额度，适合试用。",
    },
    PLAN_MONTHLY: {
        "key": PLAN_MONTHLY,
        "label": "月卡",
        "price": 9.9,
        "price_text": "¥9.9 / 30 天",
        "extract_limit": 3,
        "advice_limit": 5,
        "days": 30,
        "duration_text": "30 天",
        "summary": "日常读写够用。",
    },
    PLAN_SEMESTER: {
        "key": PLAN_SEMESTER,
        "label": "学期卡",
        "price": 39,
        "price_text": "¥39 / 120 天",
        "extract_limit": 5,
        "advice_limit": 8,
        "days": 120,
        "duration_text": "120 天",
        "summary": "学期内主力推荐。",
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
    return date.today()


def effective_plan_key(user: User) -> str:
    if is_owner_user(user):
        return PLAN_SEMESTER
    key = (getattr(user, "plan", None) or PLAN_FREE).strip().lower()
    if key not in PLANS:
        return PLAN_FREE
    expires = getattr(user, "plan_expires_at", None)
    if key in PAID_PLANS and expires and expires < _today():
        return PLAN_FREE
    return key


def resolve_user_plan(db: Session, user: User) -> str:
    """过期套餐落回体验并写回数据库。"""
    if is_owner_user(user):
        return PLAN_SEMESTER
    key = (getattr(user, "plan", None) or PLAN_FREE).strip().lower()
    if key not in PLANS:
        key = PLAN_FREE
    expires = getattr(user, "plan_expires_at", None)
    if key in PAID_PLANS and expires and expires < _today():
        apply_plan(user, PLAN_FREE, persist_subscription=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        return PLAN_FREE
    return key


def apply_plan(user: User, plan_key: str, persist_subscription: bool = True) -> None:
    spec = get_plan_spec(plan_key)
    user.plan = spec["key"]
    days = spec.get("days")
    if days:
        user.plan_expires_at = _today() + timedelta(days=days)
    else:
        user.plan_expires_at = None
    if persist_subscription and getattr(user, "subscription", None):
        user.subscription.plan = spec["key"]
        user.subscription.start_date = _today()
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


def quota_limits_for_user(user: User) -> tuple[int, int]:
    if is_owner_user(user):
        return 0, 0
    spec = get_plan_spec(effective_plan_key(user))
    return spec["extract_limit"], spec["advice_limit"]


def plan_label(plan_key: str) -> str:
    return get_plan_spec(plan_key)["label"]
