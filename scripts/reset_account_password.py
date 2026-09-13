# -*- coding: utf-8 -*-
"""Inspect or reset a login account. Type the new password on the server; do not commit it."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import func, or_

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.accounts import find_user_by_account
from app.auth import bump_token_version, get_password_hash
from app.database import SessionLocal
from app.models import User

OWNER_EMAIL = "2721095772@qq.com"


def _lookup(db, account: str) -> User | None:
    user = find_user_by_account(db, account)
    if user:
        return user
    needle = (account or "").strip().lower()
    return (
        db.query(User)
        .filter(
            or_(
                func.lower(func.trim(User.email)) == needle,
                User.phone == needle,
            )
        )
        .first()
    )


def _print_status(user: User | None, account: str) -> None:
    if user is None:
        print(f"STATUS missing account={account}")
        return
    hash_value = user.password_hash or ""
    print(
        "STATUS",
        {
            "id": user.id,
            "email": user.email,
            "phone": user.phone or "",
            "is_active": bool(user.is_active),
            "deleted": bool(user.deleted_at),
            "hash_ok": hash_value.startswith("$2"),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or reset an account password")
    parser.add_argument("account", nargs="?", default=OWNER_EMAIL, help="email or phone")
    parser.add_argument("--status", action="store_true", help="only print account status")
    args = parser.parse_args()
    account = (args.account or "").strip()
    if not account:
        raise SystemExit("请填写邮箱或手机号")

    db = SessionLocal()
    try:
        user = _lookup(db, account)
        _print_status(user, account)
        if args.status:
            raise SystemExit(0 if user else 2)
        if user is None:
            raise SystemExit(2)
        if user.deleted_at is not None:
            raise SystemExit("该账户已删除，未改密码")

        password = getpass.getpass("新密码（至少 6 位，输入时不显示）: ")
        confirm = getpass.getpass("再输入一次: ")
        if password != confirm:
            raise SystemExit("两次密码不一致")
        if len(password) < 6:
            raise SystemExit("密码至少 6 位")

        user.password_hash = get_password_hash(password)
        user.is_active = True
        bump_token_version(user)
        db.commit()
        print("密码已更新，请立刻用新密码登录，再在「我的」里改成自己记得的。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
