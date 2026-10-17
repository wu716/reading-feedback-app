# -*- coding: utf-8 -*-
"""Schemas for the retained todo reminder settings and logs."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ReminderSettingBase(BaseModel):
    is_enabled: bool = True
    browser_notification: bool = True
    email_notification: bool = True


class ReminderSettingCreate(ReminderSettingBase):
    pass


class ReminderSettingUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    browser_notification: Optional[bool] = None
    email_notification: Optional[bool] = None


class ReminderSettingResponse(ReminderSettingBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ReminderLogResponse(BaseModel):
    id: int
    user_id: int
    reminder_type: str
    triggered_at: datetime
    dismissed_at: Optional[datetime]
    action_taken: bool
    notification_method: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ReminderLogListResponse(BaseModel):
    logs: List[ReminderLogResponse]
    total: int
