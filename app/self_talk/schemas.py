# -*- coding: utf-8 -*-
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
from datetime import datetime


class SelfTalkCreate(BaseModel):
    """创建 Self-talk 的请求模型"""
    action_id: Optional[int] = None  # 可选，关联读书行动项


class SelfTalkResponse(BaseModel):
    """Self-talk 响应模型"""
    id: int
    user_id: int
    action_id: Optional[int]
    audio_path: str
    transcript: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class SelfTalkTranscriptUpdate(BaseModel):
    """更新转写文字"""
    transcript: str


class SelfTalkListResponse(BaseModel):
    """Self-talk 列表响应模型"""
    self_talks: list[SelfTalkResponse]
    total: int


class PlaybackLogCreate(BaseModel):
    """播放记录上报"""
    self_talk_id: int
    duration_seconds: int = Field(ge=0, le=86400)
    loops_completed: int = Field(1, ge=1, le=999)
    loop_mode: Literal["once", "count", "time"] = "once"
    loop_target: Optional[int] = Field(None, ge=1, le=99999)


class PlaybackLogResponse(BaseModel):
    id: int
    self_talk_id: int
    duration_seconds: int
    loops_completed: int
    loop_mode: str

    model_config = ConfigDict(from_attributes=True)
