# -*- coding: utf-8 -*-
"""生产环境定时任务：待办、每日记录提醒与每日备份。"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.self_talk.reminder_service import check_record_reminders, check_todo_reminders

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
        lambda: _run_with_db(check_record_reminders),
        IntervalTrigger(minutes=1),
        id="daily_record_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_with_db(check_todo_reminders),
        IntervalTrigger(minutes=1),
        id="todo_reminders",
        replace_existing=True,
    )
    from app.backup import run_daily_backup

    scheduler.add_job(
        run_daily_backup,
        CronTrigger(hour=3, minute=15),
        id="daily_backup",
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
    logger.info("定时任务调度器已启动（待办、每日记录提醒与每日备份）")
    return scheduler
