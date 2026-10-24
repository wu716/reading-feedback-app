# -*- coding: utf-8 -*-
"""Todo and daily record reminders; preserve the existing settings and log tables."""
import logging
import smtplib
from datetime import datetime, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models import DailyTodo, SelfTalkReminderLog, SelfTalkReminderSetting, User

logger = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
REMINDER_TYPES = ("todo", "daily_record", "project_feedback", "feedback_report")


class ReminderService:
    @staticmethod
    def get_or_create_setting(db: Session, user_id: int) -> SelfTalkReminderSetting:
        setting = db.query(SelfTalkReminderSetting).filter(
            SelfTalkReminderSetting.user_id == user_id
        ).first()
        if setting is None:
            setting = SelfTalkReminderSetting(
                user_id=user_id,
                is_enabled=True,
                daily_reminder_enabled=False,
                after_action_reminder=False,
                after_new_action_reminder=False,
                inactive_days_threshold=0,
                browser_notification=True,
                email_notification=True,
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
        return setting

    @staticmethod
    def log_reminder(
        db: Session, user_id: int, reminder_type: str,
        notification_method: str = "both", detail: Optional[str] = None,
    ) -> SelfTalkReminderLog:
        if reminder_type not in REMINDER_TYPES:
            raise ValueError("Unsupported reminder type")
        row = SelfTalkReminderLog(
            user_id=user_id,
            reminder_type=reminder_type,
            notification_method=notification_method,
            detail=detail,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def send_email_notification(db: Session, user_id: int, subject: str, content: str) -> bool:
        from app.config import settings

        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.email or not settings.SMTP_HOST:
            return False
        try:
            msg = MIMEMultipart()
            msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
            msg["To"] = user.email
            msg["Subject"] = subject
            paragraphs = []
            for line in content.splitlines():
                safe = escape(line)
                paragraphs.append(f'<p><a href="{safe}">打开书然查看</a></p>' if line.startswith(("https://", "http://")) else f"<p>{safe}</p>")
            body = (
                '<html><body style="font-family:Arial,sans-serif;padding:20px">'
                f'<h2>{escape(subject)}</h2>' + "".join(paragraphs) +
                '</body></html>'
            )
            msg.attach(MIMEText(body, "html"))
            implicit_tls = settings.SMTP_USE_TLS and settings.SMTP_PORT == 465
            smtp = smtplib.SMTP_SSL if implicit_tls else smtplib.SMTP
            with smtp(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                if settings.SMTP_USE_TLS and not implicit_tls:
                    server.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
            return True
        except Exception:
            logger.exception("发送待办提醒邮件失败 user_id=%s", user_id)
            return False

    @staticmethod
    def dispatch_notifications(
        db: Session, user_id: int, setting: SelfTalkReminderSetting,
        reminder_type: str, title: str, message: str, detail: Optional[str] = None,
    ) -> None:
        if setting.browser_notification and setting.email_notification:
            method = "both"
        elif setting.browser_notification:
            method = "browser"
        elif setting.email_notification:
            method = "email"
        else:
            method = "in_app"
        log = ReminderService.log_reminder(db, user_id, reminder_type, method, detail)
        if setting.email_notification:
            sent = ReminderService.send_email_notification(db, user_id, title, message)
            if not sent:
                from app.project_models import FeedbackDelivery
                db.add(FeedbackDelivery(user_id=user_id, event_key=f"legacy-reminder:{log.id}", log_id=log.id,
                    title=title, message=message, email_status="retry", attempts=1))
                db.commit()

    @staticmethod
    def get_reminder_message(
        reminder_type: str, user_name: str = "用户", detail: Optional[str] = None,
    ) -> tuple[str, str]:
        if reminder_type == "daily_record":
            return "记录这一天", "留一点时间回看今天，补充长期目标里的活动、注意力与开销记录。"
        if reminder_type in ("project_feedback", "feedback_report"):
            import json
            payload = json.loads(detail or "{}")
            return payload.get("title", "反馈提醒"), payload.get("message", "打开书然查看")
        if reminder_type != "todo":
            raise ValueError("Unsupported reminder type")
        return "待办提醒", detail or f"{user_name}，你有一条待办到点了。"


def _todo_due_at(todo: DailyTodo) -> Optional[datetime]:
    raw = (todo.remind_time or "").strip()
    if not raw:
        return None
    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return datetime.combine(todo.todo_date, time(hour, minute), tzinfo=BEIJING_TZ)
    except (ValueError, IndexError, TypeError):
        return None


def check_todo_reminders(db: Session, user_id: Optional[int] = None) -> int:
    """Record due todos for browser and native notification polling."""
    now = datetime.now(BEIJING_TZ)
    query = db.query(DailyTodo).filter(
        DailyTodo.deleted_at.is_(None),
        DailyTodo.completed == False,
        DailyTodo.remind_time.isnot(None),
        DailyTodo.reminded_at.is_(None),
    )
    if user_id is not None:
        query = query.filter(DailyTodo.user_id == user_id)

    fired = 0
    for todo in query.all():
        due = _todo_due_at(todo)
        if due is None or now < due:
            continue
        user = db.query(User).filter(User.id == todo.user_id).first()
        if not user or not user.is_active:
            continue
        setting = ReminderService.get_or_create_setting(db, todo.user_id)
        if not setting.is_enabled:
            continue
        title, message = ReminderService.get_reminder_message("todo", user.name, todo.text)
        ReminderService.dispatch_notifications(
            db, todo.user_id, setting, "todo", title, message, detail=todo.text
        )
        todo.reminded_at = datetime.now(BEIJING_TZ)
        fired += 1
    if fired:
        db.commit()
        logger.info("已触发 %s 条待办提醒", fired)
    return fired


def record_status(db: Session, user_id: int, day=None) -> dict:
    from app.routers.long_term_details import read_range

    day = day or datetime.now(BEIJING_TZ).date()
    record = read_range(db, user_id, day, day)[0]
    return {"record_date": day, "record_complete": all(record[key] for key in (
        "day_confirmed", "attention_confirmed", "expense_confirmed",
    ))}


def check_record_reminders(db: Session, user_id: Optional[int] = None, *, now=None) -> int:
    """Claim each Beijing calendar day atomically before logging or sending mail."""
    now = now or datetime.now(BEIJING_TZ)
    now = now.astimezone(BEIJING_TZ)
    day = now.date()
    query = db.query(SelfTalkReminderSetting).join(User).filter(
        User.is_active == True,
        SelfTalkReminderSetting.is_enabled == True,
        SelfTalkReminderSetting.record_reminder_enabled == True,
        or_(SelfTalkReminderSetting.record_reminded_on.is_(None),
            SelfTalkReminderSetting.record_reminded_on < day),
    )
    if user_id is not None:
        query = query.filter(SelfTalkReminderSetting.user_id == user_id)
    fired = 0
    for setting in query.all():
        try:
            due = time.fromisoformat(setting.record_reminder_time or "21:00")
        except ValueError:
            continue
        if now.time().replace(tzinfo=None) < due or record_status(db, setting.user_id, day)["record_complete"]:
            continue
        claimed = db.query(SelfTalkReminderSetting).filter(
            SelfTalkReminderSetting.id == setting.id,
            SelfTalkReminderSetting.is_enabled == True,
            SelfTalkReminderSetting.record_reminder_enabled == True,
            or_(SelfTalkReminderSetting.record_reminded_on.is_(None),
                SelfTalkReminderSetting.record_reminded_on < day),
        ).update({"record_reminded_on": day}, synchronize_session=False)
        if not claimed:
            continue
        method = ("both" if setting.browser_notification else "email") if setting.email_notification else (
            "browser" if setting.browser_notification else "in_app")
        db.add(SelfTalkReminderLog(user_id=setting.user_id, reminder_type="daily_record",
                                   detail=day.isoformat(), triggered_at=now, notification_method=method))
        db.commit()
        fired += 1
        if setting.email_notification:
            title, message = ReminderService.get_reminder_message("daily_record")
            ReminderService.send_email_notification(db, setting.user_id, title, message)
    return fired
