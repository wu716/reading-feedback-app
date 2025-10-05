# -*- coding: utf-8 -*-
from pydantic import BaseModel
from typing import Optional
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
    
    class Config:
        from_attributes = True


class SelfTalkListResponse(BaseModel):
    """Self-talk 列表响应模型"""
    self_talks: list[SelfTalkResponse]
    total: int
