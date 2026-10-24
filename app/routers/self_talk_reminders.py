# -*- coding: utf-8 -*-
"""待办与每日记录提醒；保留既有通知偏好和历史日志。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
import logging

from app.database import get_db
from app.auth import get_current_user
from app.models import User, SelfTalkReminderSetting, SelfTalkReminderLog
from app.self_talk.reminder_schemas import (
    ReminderSettingCreate, ReminderSettingUpdate, ReminderSettingResponse,
    ReminderLogResponse, ReminderLogListResponse
)
from app.self_talk.reminder_service import (
    ReminderService,
    check_todo_reminders,
    check_record_reminders, record_status, REMINDER_TYPES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reminders", tags=["todo-reminders"])
SETTING_FIELDS = {"is_enabled", "browser_notification", "email_notification",
                  "record_reminder_enabled", "record_reminder_time"}


def _setting_response(setting: SelfTalkReminderSetting, db: Session) -> ReminderSettingResponse:
    return ReminderSettingResponse(
        id=setting.id,
        user_id=setting.user_id,
        is_enabled=setting.is_enabled,
        browser_notification=setting.browser_notification,
        email_notification=setting.email_notification,
        record_reminder_enabled=bool(setting.record_reminder_enabled),
        record_reminder_time=setting.record_reminder_time or "21:00",
        **record_status(db, setting.user_id),
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


@router.get("/settings", response_model=ReminderSettingResponse)
async def get_reminder_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的提醒设置
    如果不存在则创建默认设置
    """
    try:
        setting = ReminderService.get_or_create_setting(db, current_user.id)
        return _setting_response(setting, db)
        
    except Exception as e:
        logger.error(f"获取提醒设置失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/settings", response_model=ReminderSettingResponse)
async def create_reminder_settings(
    settings: ReminderSettingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建或更新提醒设置
    """
    try:
        # 检查是否已存在
        existing_setting = db.query(SelfTalkReminderSetting).filter(
            SelfTalkReminderSetting.user_id == current_user.id
        ).first()
        
        if existing_setting:
            payload = settings.model_dump(exclude_unset=True) if hasattr(settings, "model_dump") else settings.dict(exclude_unset=True)
            for key, value in payload.items():
                if key in SETTING_FIELDS:
                    setattr(existing_setting, key, value)
            
            db.commit()
            db.refresh(existing_setting)
            setting = existing_setting
        else:
            # 创建新设置
            setting = SelfTalkReminderSetting(
                user_id=current_user.id,
                is_enabled=settings.is_enabled,
                daily_reminder_enabled=False,
                after_action_reminder=False,
                after_new_action_reminder=False,
                inactive_days_threshold=0,
                browser_notification=settings.browser_notification,
                email_notification=settings.email_notification,
                record_reminder_enabled=settings.record_reminder_enabled,
                record_reminder_time=settings.record_reminder_time,
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
        
        logger.info(f"用户 {current_user.id} 的提醒设置已保存")
        
        return _setting_response(setting, db)
        
    except Exception as e:
        logger.error(f"保存提醒设置失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.patch("/settings", response_model=ReminderSettingResponse)
async def update_reminder_settings(
    settings_update: ReminderSettingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    部分更新提醒设置
    """
    try:
        setting = ReminderService.get_or_create_setting(db, current_user.id)
        
        # 更新非空字段
        update_data = settings_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key in SETTING_FIELDS and value is not None:
                setattr(setting, key, value)
        
        db.commit()
        db.refresh(setting)
        
        logger.info(f"用户 {current_user.id} 的提醒设置已更新")
        
        return _setting_response(setting, db)
        
    except Exception as e:
        logger.error(f"更新提醒设置失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/logs", response_model=ReminderLogListResponse)
async def get_reminder_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20
):
    """
    获取用户的提醒日志
    """
    try:
        query = db.query(SelfTalkReminderLog).filter(
            SelfTalkReminderLog.user_id == current_user.id,
            SelfTalkReminderLog.reminder_type.in_(REMINDER_TYPES),
        ).order_by(SelfTalkReminderLog.triggered_at.desc())
        
        total = query.count()
        logs = query.offset(skip).limit(limit).all()
        
        log_responses = [
            ReminderLogResponse(
                id=log.id,
                user_id=log.user_id,
                reminder_type=log.reminder_type,
                triggered_at=log.triggered_at,
                dismissed_at=log.dismissed_at,
                action_taken=log.action_taken,
                notification_method=log.notification_method
            )
            for log in logs
        ]
        
        return ReminderLogListResponse(logs=log_responses, total=total)
        
    except Exception as e:
        logger.error(f"获取提醒日志失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/pending")
async def get_pending_reminders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取未处理的应用内提醒（前端轮询 / 铃铛列表）。
    保留到用户手动关闭，避免页面未打开时错过。
    """
    try:
        from datetime import datetime, timedelta

        check_todo_reminders(db, user_id=current_user.id)
        check_record_reminders(db, user_id=current_user.id)
        from app.feedback_service import check_feedback_reminders, latest
        from app.project_models import FeedbackOccurrence, FeedbackDelivery
        import json
        check_feedback_reminders(db, user_id=current_user.id)
        setting = ReminderService.get_or_create_setting(db, current_user.id)
        status = record_status(db, current_user.id)
        
        recent_time = datetime.now() - timedelta(days=7)
        
        pending_logs = (
            db.query(SelfTalkReminderLog)
            .filter(
                SelfTalkReminderLog.user_id == current_user.id,
                or_(SelfTalkReminderLog.triggered_at >= recent_time,
                    SelfTalkReminderLog.reminder_type.in_(("project_feedback", "feedback_report"))),
                SelfTalkReminderLog.dismissed_at.is_(None),
                SelfTalkReminderLog.action_taken == False,
                SelfTalkReminderLog.reminder_type.in_(REMINDER_TYPES)
            )
            .order_by(SelfTalkReminderLog.triggered_at.desc())
            .limit(50)
            .all()
        )
        
        notifications = []
        for log in pending_logs:
            is_record = log.reminder_type == "daily_record"
            feedback = json.loads(log.detail or "{}") if log.reminder_type in ("project_feedback", "feedback_report") else None
            if feedback:
                if not setting.is_enabled:
                    continue
                if feedback.get("occurrence_id"):
                    occurrence = db.query(FeedbackOccurrence).filter_by(id=feedback["occurrence_id"], user_id=current_user.id).first()
                    submission = latest(db, occurrence.id) if occurrence else None
                    if not occurrence or occurrence.skipped_reason or submission and submission.status != "needs_changes":
                        continue
            if is_record and (not setting.is_enabled or not setting.record_reminder_enabled
                              or status["record_complete"] or log.detail != status["record_date"].isoformat()):
                continue
            title, message = ReminderService.get_reminder_message(
                log.reminder_type,
                current_user.name,
                log.detail,
            )
            notifications.append({
                "log_id": log.id,
                "title": title,
                "message": message,
                "reminder_type": log.reminder_type,
                "triggered_at": log.triggered_at.isoformat(),
                "action_url": feedback.get("action_url") if feedback else "/static/index.html?record=today#long-term" if is_record else "/static/index.html#overview",
                "action_label": "查看报告" if log.reminder_type == "feedback_report" else "提交反馈" if feedback else "记录今天" if is_record else "查看今日",
                "system_notification": bool(setting.browser_notification and log.notification_method != "in_app"),
                "record_date": log.detail if is_record else None,
            })
        
        return {
            "pending_count": len(notifications),
            "notifications": notifications,
            **status,
            "record_reminder_enabled": bool(setting.is_enabled and setting.record_reminder_enabled),
            "record_reminder_time": setting.record_reminder_time or "21:00",
            "system_notification": setting.browser_notification,
        }
        
    except Exception as e:
        logger.error(f"获取待处理提醒失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/dismiss/{log_id}")
async def dismiss_reminder(
    log_id: int,
    action_taken: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    标记提醒为已处理/已忽略
    """
    try:
        log = db.query(SelfTalkReminderLog).filter(
            SelfTalkReminderLog.id == log_id,
            SelfTalkReminderLog.user_id == current_user.id,
            SelfTalkReminderLog.reminder_type.in_(REMINDER_TYPES),
        ).first()
        
        if not log:
            raise HTTPException(status_code=404, detail="提醒日志不存在")
        
        from datetime import datetime
        log.dismissed_at = datetime.now()
        log.action_taken = action_taken
        
        db.commit()
        
        return {"success": True, "message": "提醒已处理"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理提醒失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")

