# -*- coding: utf-8 -*-
"""手机号 / 登录账号辅助。"""
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models import User
from app.plans import effective_plan_key, is_owner_user, plan_label

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
REAL_NAME_RE = re.compile(r"^[\u4e00-\u9fa5a-zA-Z·•\s]{2,20}$")
PLACEHOLDER_EMAIL_SUFFIX = "@phone.invalid"


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", (raw or "").strip())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits


def validate_phone(raw: str) -> str:
    phone = normalize_phone(raw)
    if not PHONE_RE.match(phone):
        raise ValueError("请填写有效的大陆手机号")
    return phone


def validate_real_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if not REAL_NAME_RE.match(name):
        raise ValueError("真实姓名请用 2–20 个中文或英文字符")
    return name


def placeholder_email(phone: str) -> str:
    return f"{phone}{PLACEHOLDER_EMAIL_SUFFIX}"


def is_placeholder_email(email: Optional[str]) -> bool:
    value = (email or "").strip().lower()
    return value.endswith(PLACEHOLDER_EMAIL_SUFFIX)


def public_email(email: Optional[str]) -> Optional[str]:
    if not email or is_placeholder_email(email):
        return None
    return email


def find_user_by_account(db: Session, account: str) -> Optional[User]:
    value = (account or "").strip()
    if not value:
        return None
    query = db.query(User).filter(User.deleted_at.is_(None))
    phone = normalize_phone(value)
    if PHONE_RE.match(phone):
        user = query.filter(User.phone == phone).first()
        if user:
            return user
    return query.filter(User.email == value).first()


def find_active_phone(db: Session, phone: str, exclude_user_id: Optional[int] = None) -> Optional[User]:
    query = db.query(User).filter(User.phone == phone, User.deleted_at.is_(None))
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.first()


def user_to_public_dict(user: User) -> dict:
    key = effective_plan_key(user)
    return {
        "id": user.id,
        "email": public_email(user.email),
        "phone": user.phone,
        "name": user.name,
        "real_name": user.real_name,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "plan": key,
        "plan_label": plan_label(key),
        "plan_expires_at": user.plan_expires_at,
        "phone_verified": bool(getattr(user, "phone_verified", False)),
        "is_owner": is_owner_user(user),
        "phone_bound": bool(user.phone),
    }
