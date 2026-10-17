# -*- coding: utf-8 -*-
"""Todo reminder delivery; legacy table names remain until schema migration."""
import logging
import smtplib
from datetime import datetime, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import DailyTodo, SelfTalkReminderLog, SelfTalkReminderSetting, User

logger = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


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
        if reminder_type != "todo":
            raise ValueError("Only todo reminders are supported")
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
            body = (
                '<html><body style="font-family:Arial,sans-serif;padding:20px">'
                f'<h2>书然待办提醒</h2><p>{escape(content)}</p>'
                '</body></html>'
            )
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                if settings.SMTP_USE_TLS:
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
        ReminderService.log_reminder(db, user_id, reminder_type, method, detail)
        if setting.email_notification:
            ReminderService.send_email_notification(db, user_id, title, message)

    @staticmethod
    def get_reminder_message(
        reminder_type: str, user_name: str = "用户", detail: Optional[str] = None,
    ) -> tuple[str, str]:
        if reminder_type != "todo":
            raise ValueError("Only todo reminders are supported")
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
