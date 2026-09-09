# -*- coding: utf-8 -*-
"""每日逻辑备份：导出关键表为 CSV，保留 7 天。不含密码哈希和录音文件。"""
import csv
import io
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.accounts import public_email
from app.database import SessionLocal
from app.models import (
    Action,
    AiCallLog,
    AuditLog,
    DailyTodo,
    InviteCode,
    PracticeLog,
    ReadingEntry,
    SelfTalk,
    Subscription,
    User,
)

logger = logging.getLogger(__name__)
BEIJING = ZoneInfo("Asia/Shanghai")
BACKUP_DIR = Path("backups")
KEEP_DAYS = 7


def _csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _cell(value) -> str:
    if value is None:
        return ""
    return str(value)


def build_backup_zip(db: Session) -> bytes:
    users = db.query(User).all()
    actions = db.query(Action).filter(Action.deleted_at.is_(None)).all()
    practices = db.query(PracticeLog).filter(PracticeLog.deleted_at.is_(None)).all()
    readings = db.query(ReadingEntry).filter(ReadingEntry.deleted_at.is_(None)).all()
    talks = db.query(SelfTalk).filter(SelfTalk.deleted_at.is_(None)).all()
    todos = db.query(DailyTodo).filter(DailyTodo.deleted_at.is_(None)).all()
    ai_logs = db.query(AiCallLog).all()
    subs = db.query(Subscription).all()
    invites = db.query(InviteCode).all()
    audits = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(2000).all()

    files = {
        "users.csv": _csv_bytes(
            ["id", "name", "real_name", "phone", "email", "plan", "plan_expires_at", "is_active", "created_at", "deleted_at"],
            [
                [
                    u.id,
                    u.name,
                    u.real_name or "",
                    u.phone or "",
                    public_email(u.email) or "",
                    u.plan,
                    _cell(u.plan_expires_at),
                    u.is_active,
                    _cell(u.created_at),
                    _cell(u.deleted_at),
                ]
                for u in users
            ],
        ),
        "actions.csv": _csv_bytes(
            ["id", "user_id", "book_title", "action_text", "status", "created_at"],
            [[a.id, a.user_id, a.book_title, a.action_text, a.status, _cell(a.created_at)] for a in actions],
        ),
        "practice_logs.csv": _csv_bytes(
            ["id", "user_id", "action_id", "date", "result", "notes"],
            [[p.id, p.user_id, p.action_id, _cell(p.date), p.result, p.notes or ""] for p in practices],
        ),
        "readings.csv": _csv_bytes(
            ["id", "user_id", "book_title", "duration_minutes", "entry_date", "content", "reflection"],
            [
                [r.id, r.user_id, r.book_title or "", r.duration_minutes, _cell(r.entry_date), r.content, r.reflection or ""]
                for r in readings
            ],
        ),
        "self_talks.csv": _csv_bytes(
            ["id", "user_id", "created_at", "transcript"],
            [[t.id, t.user_id, _cell(t.created_at), t.transcript or ""] for t in talks],
        ),
        "todos.csv": _csv_bytes(
            ["id", "user_id", "todo_date", "text", "completed"],
            [[d.id, d.user_id, _cell(d.todo_date), d.text, d.completed] for d in todos],
        ),
        "ai_calls.csv": _csv_bytes(
            ["id", "user_id", "kind", "call_date"],
            [[c.id, c.user_id, c.kind, _cell(c.call_date)] for c in ai_logs],
        ),
        "subscriptions.csv": _csv_bytes(
            ["id", "user_id", "plan", "start_date", "end_date", "is_active"],
            [[s.id, s.user_id, s.plan, _cell(s.start_date), _cell(s.end_date), s.is_active] for s in subs],
        ),
        "invite_codes.csv": _csv_bytes(
            ["id", "code", "plan", "note", "used_at", "used_by_user_id"],
            [[i.id, i.code, i.plan, i.note or "", _cell(i.used_at), _cell(i.used_by_user_id)] for i in invites],
        ),
        "audit_logs.csv": _csv_bytes(
            ["id", "action", "actor_user_id", "target_user_id", "ip", "detail", "created_at"],
            [
                [x.id, x.action, _cell(x.actor_user_id), _cell(x.target_user_id), x.ip or "", x.detail or "", _cell(x.created_at)]
                for x in audits
            ],
        ),
    }

    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        zf.writestr("README.txt", "书然备份。不含密码哈希和录音文件。录音在 uploads/self_talks。\n")
    return raw.getvalue()


def latest_backup_path() -> Path | None:
    if not BACKUP_DIR.exists():
        return None
    zips = sorted(BACKUP_DIR.glob("shuran-backup-*.zip"), reverse=True)
    return zips[0] if zips else None


def run_daily_backup() -> Path | None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        payload = build_backup_zip(db)
    except Exception as exc:
        logger.error("备份失败: %s", exc)
        return None
    finally:
        db.close()

    stamp = datetime.now(BEIJING).strftime("%Y%m%d-%H%M")
    path = BACKUP_DIR / f"shuran-backup-{stamp}.zip"
    path.write_bytes(payload)
    cutoff = datetime.now(BEIJING) - timedelta(days=KEEP_DAYS)
    for old in BACKUP_DIR.glob("shuran-backup-*.zip"):
        try:
            if old.stat().st_mtime < cutoff.timestamp():
                old.unlink()
        except OSError as exc:
            logger.warning("删除过期备份失败 %s: %s", old, exc)
    logger.info("已写入备份 %s (%s bytes)", path, path.stat().st_size)
    return path
