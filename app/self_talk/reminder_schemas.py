# -*- coding: utf-8 -*-
"""
Self-talk 提醒功能的 Pydantic 模型
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime


class ReminderSettingBase(BaseModel):
    """提醒设置基础模型"""
    is_enabled: bool = True
    
    # 时间型提醒
    daily_reminder_enabled: bool = False
    daily_reminder_time: Optional[str] = Field(None, pattern=r'^\d{2}:\d{2}(:\d{2})?$')
    reminder_days: List[int] = Field(default=[0,1,2,3,4,5,6], description="周日=0, 周一=1, ..., 周六=6")
    
    # 行为触发型提醒
    after_action_reminder: bool = True
    after_new_action_reminder: bool = True
    inactive_days_threshold: int = Field(3, ge=1, le=30, description="1-30天")
    
    # 通知方式
    browser_notification: bool = True
    email_notification: bool = True


class ReminderSettingCreate(ReminderSettingBase):
    """创建提醒设置"""
    pass


class ReminderSettingUpdate(BaseModel):
    """更新提醒设置（所有字段可选）"""
    is_enabled: Optional[bool] = None
    daily_reminder_enabled: Optional[bool] = None
    daily_reminder_time: Optional[str] = None
    reminder_days: Optional[List[int]] = None
    after_action_reminder: Optional[bool] = None
    after_new_action_reminder: Optional[bool] = None
    inactive_days_threshold: Optional[int] = None
    browser_notification: Optional[bool] = None
    email_notification: Optional[bool] = None


class ReminderSettingResponse(ReminderSettingBase):
    """提醒设置响应模型"""
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)


class ReminderLogResponse(BaseModel):
    """提醒日志响应模型"""
    id: int
    user_id: int
    reminder_type: str
    triggered_at: datetime
    dismissed_at: Optional[datetime]
    action_taken: bool
    notification_method: Optional[str]
    
    model_config = ConfigDict(from_attributes=True)


class ReminderLogListResponse(BaseModel):
    """提醒日志列表响应"""
    logs: List[ReminderLogResponse]
    total: int


class TriggerReminderRequest(BaseModel):
    """手动触发提醒请求"""
    reminder_type: str = Field(..., pattern="^(daily|after_action|inactive|after_new_action)$")
    notification_method: Optional[str] = Field("both", pattern="^(browser|email|both)$")

