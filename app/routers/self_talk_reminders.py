# -*- coding: utf-8 -*-
"""
Self-talk 提醒功能 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import json
import logging

from app.database import get_db
from app.auth import get_current_user
from app.models import User, SelfTalkReminderSetting, SelfTalkReminderLog
from app.self_talk.reminder_schemas import (
    ReminderSettingCreate, ReminderSettingUpdate, ReminderSettingResponse,
    ReminderLogResponse, ReminderLogListResponse, TriggerReminderRequest
)
from app.self_talk.reminder_service import ReminderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/self_talk_reminders", tags=["self-talk-reminders"])


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
        
        # 解析 reminder_days JSON
        try:
            reminder_days = json.loads(setting.reminder_days)
        except:
            reminder_days = [0,1,2,3,4,5,6]
        
        return ReminderSettingResponse(
            id=setting.id,
            user_id=setting.user_id,
            is_enabled=setting.is_enabled,
            daily_reminder_enabled=setting.daily_reminder_enabled,
            daily_reminder_time=setting.daily_reminder_time,
            reminder_days=reminder_days,
            after_action_reminder=setting.after_action_reminder,
            after_new_action_reminder=setting.after_new_action_reminder,
            inactive_days_threshold=setting.inactive_days_threshold,
            browser_notification=setting.browser_notification,
            email_notification=setting.email_notification,
            created_at=setting.created_at,
            updated_at=setting.updated_at
        )
        
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
            # 更新现有设置
            for key, value in settings.dict().items():
                if key == "reminder_days":
                    setattr(existing_setting, key, json.dumps(value))
                else:
                    setattr(existing_setting, key, value)
            
            db.commit()
            db.refresh(existing_setting)
            setting = existing_setting
        else:
            # 创建新设置
            reminder_days_json = json.dumps(settings.reminder_days)
            setting = SelfTalkReminderSetting(
                user_id=current_user.id,
                is_enabled=settings.is_enabled,
                daily_reminder_enabled=settings.daily_reminder_enabled,
                daily_reminder_time=settings.daily_reminder_time,
                reminder_days=reminder_days_json,
                after_action_reminder=settings.after_action_reminder,
                after_new_action_reminder=settings.after_new_action_reminder,
                inactive_days_threshold=settings.inactive_days_threshold,
                browser_notification=settings.browser_notification,
                email_notification=settings.email_notification
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
        
        logger.info(f"用户 {current_user.id} 的提醒设置已保存")
        
        return ReminderSettingResponse(
            id=setting.id,
            user_id=setting.user_id,
            is_enabled=setting.is_enabled,
            daily_reminder_enabled=setting.daily_reminder_enabled,
            daily_reminder_time=setting.daily_reminder_time,
            reminder_days=settings.reminder_days,
            after_action_reminder=setting.after_action_reminder,
            after_new_action_reminder=setting.after_new_action_reminder,
            inactive_days_threshold=setting.inactive_days_threshold,
            browser_notification=setting.browser_notification,
            email_notification=setting.email_notification,
            created_at=setting.created_at,
            updated_at=setting.updated_at
        )
        
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
        update_data = settings_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            if key == "reminder_days" and value is not None:
                setattr(setting, key, json.dumps(value))
            elif value is not None:
                setattr(setting, key, value)
        
        db.commit()
        db.refresh(setting)
        
        logger.info(f"用户 {current_user.id} 的提醒设置已更新")
        
        reminder_days = json.loads(setting.reminder_days)
        
        return ReminderSettingResponse(
            id=setting.id,
            user_id=setting.user_id,
            is_enabled=setting.is_enabled,
            daily_reminder_enabled=setting.daily_reminder_enabled,
            daily_reminder_time=setting.daily_reminder_time,
            reminder_days=reminder_days,
            after_action_reminder=setting.after_action_reminder,
            after_new_action_reminder=setting.after_new_action_reminder,
            inactive_days_threshold=setting.inactive_days_threshold,
            browser_notification=setting.browser_notification,
            email_notification=setting.email_notification,
            created_at=setting.created_at,
            updated_at=setting.updated_at
        )
        
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
            SelfTalkReminderLog.user_id == current_user.id
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


@router.post("/trigger")
async def trigger_reminder(
    request: TriggerReminderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    手动触发提醒（用于测试）
    """
    try:
        setting = ReminderService.get_or_create_setting(db, current_user.id)
        
        if not setting.is_enabled:
            raise HTTPException(status_code=400, detail="提醒功能未启用")
        
        # 获取提醒消息
        title, message = ReminderService.get_reminder_message(
            request.reminder_type, 
            current_user.name
        )
        
        # 记录日志
        log = ReminderService.log_reminder(
            db, 
            current_user.id, 
            request.reminder_type,
            request.notification_method
        )
        
        # 返回通知数据
        notification_data = {
            "title": title,
            "message": message,
            "notification_method": request.notification_method,
            "log_id": log.id
        }
        
        logger.info(f"已为用户 {current_user.id} 触发 {request.reminder_type} 提醒")
        
        return {
            "success": True,
            "notification": notification_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"触发提醒失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/pending")
async def get_pending_reminders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取待处理的提醒（用于前端轮询）
    """
    try:
        from datetime import datetime, timedelta
        
        # 获取最近5分钟内的未处理提醒
        recent_time = datetime.now() - timedelta(minutes=5)
        
        pending_logs = db.query(SelfTalkReminderLog).filter(
            SelfTalkReminderLog.user_id == current_user.id,
            SelfTalkReminderLog.triggered_at >= recent_time,
            SelfTalkReminderLog.dismissed_at.is_(None),
            SelfTalkReminderLog.action_taken == False
        ).all()
        
        notifications = []
        for log in pending_logs:
            title, message = ReminderService.get_reminder_message(
                log.reminder_type,
                current_user.name
            )
            notifications.append({
                "log_id": log.id,
                "title": title,
                "message": message,
                "reminder_type": log.reminder_type,
                "triggered_at": log.triggered_at.isoformat()
            })
        
        return {
            "pending_count": len(notifications),
            "notifications": notifications
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
            SelfTalkReminderLog.user_id == current_user.id
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

