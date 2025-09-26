from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional
from datetime import datetime, date
from enum import Enum


# 枚举类型
class ActionStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class PracticeResult(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"
    SKIPPED = "skipped"


class Frequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# 用户相关模型
class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('密码至少6位')
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    plan: str
    
    class Config:
        from_attributes = True


# 行动项相关模型
class ActionItem(BaseModel):
    """AI 抽取的行动项模型"""
    book: str
    excerpt: str
    action: str
    tags: List[str] = []
    frequency: Frequency = Frequency.DAILY


class ActionCreate(BaseModel):
    book_title: str = Field(..., min_length=1, max_length=255)
    source_excerpt: str = Field(..., min_length=10)
    action_text: str = Field(..., min_length=5)
    tags: List[str] = []
    frequency: Frequency = Frequency.DAILY


class ActionUpdate(BaseModel):
    action_text: Optional[str] = Field(None, min_length=5)
    tags: Optional[List[str]] = None
    frequency: Optional[Frequency] = None
    status: Optional[ActionStatus] = None


class ActionResponse(BaseModel):
    id: int
    book_title: str
    source_excerpt: str
    action_text: str
    tags: List[str]
    frequency: str
    status: str
    created_at: datetime
    
    @validator('tags', pre=True)
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                import json
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        return v
    
    class Config:
        from_attributes = True


# 实践反馈相关模型
class PracticeLogCreate(BaseModel):
    action_id: int
    date: date
    result: PracticeResult
    notes: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    
    @validator('date')
    def validate_date(cls, v):
        if v > date.today():
            raise ValueError('日期不能是未来日期')
        return v


class PracticeLogUpdate(BaseModel):
    result: Optional[PracticeResult] = None
    notes: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)


class PracticeLogResponse(BaseModel):
    id: int
    action_id: int
    date: date
    result: str
    notes: Optional[str]
    rating: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True


# 笔记上传模型
class NotesUpload(BaseModel):
    content: str = Field(..., min_length=50, max_length=10000)
    book_title: Optional[str] = Field(None, max_length=255)


class NotesUploadResponse(BaseModel):
    message: str
    actions: List[ActionResponse]
    total_actions: int


# 认证相关模型
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


# 仪表盘相关模型
class DashboardStats(BaseModel):
    total_actions: int
    completed_actions: int
    completion_rate: float
    total_practice_logs: int
    success_rate: float
    recent_actions: List[ActionResponse]
    practice_trends: List[dict]  # 按日期统计的实践数据


# 分页模型
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)
    search: Optional[str] = None
    status: Optional[ActionStatus] = None
    tags: Optional[List[str]] = None


class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    size: int
    pages: int
