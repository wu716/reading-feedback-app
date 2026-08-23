# -*- coding: utf-8 -*-
"""生产环境定时任务：每日提醒、非活跃提醒、行动践行提醒"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.self_talk.reminder_service import (
    check_daily_reminders,
    check_inactive_reminders,
    check_action_practice_reminders,
    check_todo_reminders,
    check_reading_reminders,
)

logger = logging.getLogger(__name__)


def _run_with_db(fn):
    db = SessionLocal()
    try:
        fn(db)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    scheduler.add_job(
        lambda: _run_with_db(check_daily_reminders),
        IntervalTrigger(minutes=5),
        id="daily_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_with_db(check_inactive_reminders),
        IntervalTrigger(hours=1),
        id="inactive_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_with_db(check_action_practice_reminders),
        IntervalTrigger(minutes=30),
        id="action_practice_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_with_db(check_todo_reminders),
        IntervalTrigger(minutes=1),
        id="todo_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_with_db(check_reading_reminders),
        IntervalTrigger(minutes=1),
        id="reading_reminders",
        replace_existing=True,
    )

    return scheduler


def start_scheduler(app) -> BackgroundScheduler | None:
    if not settings.is_production:
        logger.info("开发环境：跳过定时任务调度器")
        return None

    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("定时任务调度器已启动（每日/非活跃/行动践行/待办提醒）")
    return scheduler
