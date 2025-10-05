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
    PARTIAL = "partial"
    FAIL = "fail"
    SKIPPED = "skipped"


class Frequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DurationType(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    LIFETIME = "lifetime"


class TargetFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


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
    
    # 新增时间管理字段
    duration_type: DurationType = DurationType.SHORT_TERM
    target_duration_days: Optional[int] = Field(None, ge=1, le=3650)  # 1天到10年
    target_frequency: TargetFrequency = TargetFrequency.DAILY
    custom_frequency_days: Optional[int] = Field(None, ge=1, le=365)  # 自定义频率，1-365天
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    @validator('end_date')
    def validate_end_date(cls, v, values):
        if v and 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('结束日期必须晚于开始日期')
        return v
    
    @validator('custom_frequency_days')
    def validate_custom_frequency(cls, v, values):
        if 'target_frequency' in values and values['target_frequency'] == TargetFrequency.CUSTOM:
            if not v:
                raise ValueError('自定义频率必须指定天数')
        return v


class ActionUpdate(BaseModel):
    action_text: Optional[str] = Field(None, min_length=5)
    tags: Optional[List[str]] = None
    frequency: Optional[Frequency] = None
    status: Optional[ActionStatus] = None
    
    # 新增时间管理字段
    duration_type: Optional[DurationType] = None
    target_duration_days: Optional[int] = Field(None, ge=1, le=3650)
    target_frequency: Optional[TargetFrequency] = None
    custom_frequency_days: Optional[int] = Field(None, ge=1, le=365)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ActionResponse(BaseModel):
    id: int
    book_title: str
    source_excerpt: str
    action_text: str
    tags: List[str]
    frequency: str
    status: str
    
    # 新增时间管理字段（可选，用于向后兼容）
    duration_type: Optional[str] = "short_term"
    target_duration_days: Optional[int] = None
    target_frequency: Optional[str] = None
    custom_frequency_days: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
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


# 时间维度分析模型
class DurationAnalytics(BaseModel):
    """时间维度分析数据"""
    short_term_actions: int
    long_term_actions: int
    lifetime_actions: int
    short_term_completion_rate: float
    long_term_completion_rate: float
    lifetime_completion_rate: float


class StreakAnalytics(BaseModel):
    """坚持度分析数据"""
    current_streak_days: int
    longest_streak_days: int
    total_streak_days: int
    streak_actions: List[dict]  # 每个行动项的坚持度数据


class TimeTrendAnalytics(BaseModel):
    """时间趋势分析数据"""
    daily_completion_rate: List[dict]  # 每日完成率
    weekly_completion_rate: List[dict]  # 每周完成率
    monthly_completion_rate: List[dict]  # 每月完成率
    frequency_success_rate: dict  # 不同频率的成功率


class ActionMilestone(BaseModel):
    """行动里程碑"""
    action_id: int
    action_text: str
    milestone_type: str  # "first_completion", "week_streak", "month_streak", "target_achieved"
    achieved_date: date
    description: str


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
