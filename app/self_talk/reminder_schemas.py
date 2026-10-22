# -*- coding: utf-8 -*-
"""Settings and logs for todo and daily record reminders."""
from datetime import date, datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field

ReminderTime = Annotated[str, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]


class ReminderSettingBase(BaseModel):
    is_enabled: bool = True
    browser_notification: bool = True
    email_notification: bool = True
    record_reminder_enabled: bool = False
    record_reminder_time: ReminderTime = "21:00"


class ReminderSettingCreate(ReminderSettingBase):
    pass


class ReminderSettingUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    browser_notification: Optional[bool] = None
    email_notification: Optional[bool] = None
    record_reminder_enabled: Optional[bool] = None
    record_reminder_time: Optional[ReminderTime] = None


class ReminderSettingResponse(ReminderSettingBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: Optional[datetime]
    record_date: date
    record_complete: bool

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
