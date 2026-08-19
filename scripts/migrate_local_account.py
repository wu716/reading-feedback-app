#!/usr/bin/env python3
"""
将本地 SQLite 账户数据导出，供生产 PostgreSQL 导入。

用法（在项目根目录）：
  python scripts/migrate_local_account.py export
  python scripts/migrate_local_account.py import --database-url postgresql://...

export 会在 scripts/ 下生成 account_backup.json（含密码哈希，请勿提交 git）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_FILE = Path(__file__).resolve().parent / "account_backup.json"
SQLITE_URL = f"sqlite:///{ROOT / 'app.db'}"


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(type(obj))


def export_account(email: str | None = None) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = ROOT / "app.db"
    if not db_path.exists():
        print(f"未找到本地数据库: {db_path}")
        print("请确认你在本机运行过应用且 app.db 存在。")
        sys.exit(1)

    sys.path.insert(0, str(ROOT))
    from app.models import (
        Action,
        DailyTodo,
        PracticeLog,
        ReadingEntry,
        SelfTalk,
        SelfTalkReminderSetting,
        Subscription,
        User,
    )

    engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    db = Session()

    q = db.query(User).filter(User.deleted_at.is_(None))
    if email:
        q = q.filter(User.email == email)
    users = q.all()
    if not users:
        print("未找到用户。可用 --email 指定邮箱。")
        sys.exit(1)

    payload = {"users": []}
    for user in users:
        uid = user.id
        payload["users"].append(
            {
                "user": {
                    "email": user.email,
                    "name": user.name,
                    "password_hash": user.password_hash,
                    "plan": user.plan,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                },
                "subscription": _first_or_none(
                    db.query(Subscription).filter(Subscription.user_id == uid).all()
                ),
                "actions": [_row_dict(a) for a in db.query(Action).filter(Action.user_id == uid, Action.deleted_at.is_(None)).all()],
                "practice_logs": [_row_dict(p) for p in db.query(PracticeLog).filter(PracticeLog.user_id == uid, PracticeLog.deleted_at.is_(None)).all()],
                "self_talks": [_row_dict(s) for s in db.query(SelfTalk).filter(SelfTalk.user_id == uid, SelfTalk.deleted_at.is_(None)).all()],
                "reminder_settings": [_row_dict(r) for r in db.query(SelfTalkReminderSetting).filter(SelfTalkReminderSetting.user_id == uid).all()],
                "daily_todos": [_row_dict(t) for t in db.query(DailyTodo).filter(DailyTodo.user_id == uid).all()],
                "reading_entries": [_row_dict(r) for r in db.query(ReadingEntry).filter(ReadingEntry.user_id == uid).all()],
            }
        )

    BACKUP_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(f"已导出 {len(users)} 个账户到 {BACKUP_FILE}")
    print("⚠️  此文件含密码哈希，请勿上传到 GitHub。")


def _first_or_none(rows):
    if not rows:
        return None
    return _row_dict(rows[0])


def _row_dict(obj) -> dict:
    d = {}
    for col in obj.__table__.columns:
        d[col.name] = getattr(obj, col.name)
    return d


def import_account(database_url: str, email: str | None = None) -> None:
    if not BACKUP_FILE.exists():
        print(f"未找到备份文件: {BACKUP_FILE}，请先 export。")
        sys.exit(1)

    sys.path.insert(0, str(ROOT))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.models import (
        Action,
        DailyTodo,
        PracticeLog,
        ReadingEntry,
        SelfTalk,
        SelfTalkReminderSetting,
        Subscription,
        User,
    )

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    payload = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
    imported = 0

    for block in payload["users"]:
        u = block["user"]
        if email and u["email"] != email:
            continue
        if db.query(User).filter(User.email == u["email"]).first():
            print(f"跳过（已存在）: {u['email']}")
            continue

        user = User(
            email=u["email"],
            name=u["name"],
            password_hash=u["password_hash"],
            plan=u.get("plan", "free"),
            is_active=u.get("is_active", True),
        )
        db.add(user)
        db.flush()

        sub = block.get("subscription")
        if sub:
            db.add(
                Subscription(
                    user_id=user.id,
                    plan=sub.get("plan", "free"),
                    start_date=date.fromisoformat(str(sub["start_date"])[:10]) if sub.get("start_date") else date.today(),
                    end_date=date.fromisoformat(str(sub["end_date"])[:10]) if sub.get("end_date") else None,
                    is_active=sub.get("is_active", True),
                )
            )

        for table, model, rows in [
            ("actions", Action, block.get("actions", [])),
            ("practice_logs", PracticeLog, block.get("practice_logs", [])),
            ("self_talks", SelfTalk, block.get("self_talks", [])),
            ("reminder_settings", SelfTalkReminderSetting, block.get("reminder_settings", [])),
            ("daily_todos", DailyTodo, block.get("daily_todos", [])),
            ("reading_entries", ReadingEntry, block.get("reading_entries", [])),
        ]:
            for row in rows:
                row = dict(row)
                row.pop("id", None)
                row["user_id"] = user.id
                if table == "practice_logs" and row.get("action_id"):
                    pass  # action_id 需在 actions 导入后映射，简化版暂跳过旧 action 关联
                if table == "actions":
                    db.add(model(**{k: v for k, v in row.items() if k in model.__table__.columns}))
                elif table in ("reminder_settings", "daily_todos", "reading_entries"):
                    db.add(model(**{k: v for k, v in row.items() if k in model.__table__.columns}))

        db.commit()
        imported += 1
        print(f"已导入: {u['email']}")

    print(f"完成，共导入 {imported} 个账户。")


def main():
    parser = argparse.ArgumentParser(description="本地账户迁移工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="从本地 SQLite 导出")
    p_export.add_argument("--email", help="仅导出指定邮箱")

    p_import = sub.add_parser("import", help="导入到 PostgreSQL")
    p_import.add_argument("--database-url", required=True)
    p_import.add_argument("--email", help="仅导入指定邮箱")

    args = parser.parse_args()
    if args.cmd == "export":
        export_account(args.email)
    else:
        import_account(args.database_url, args.email)


if __name__ == "__main__":
    main()
