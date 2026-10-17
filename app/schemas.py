from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, validator

# 用户相关模型
class UserCreate(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    name: str = Field(..., min_length=2, max_length=20)
    password: str = Field(..., min_length=6, max_length=100)
    invite_code: str = Field(..., min_length=4, max_length=8)

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('密码至少6位')
        return v


class UserLogin(BaseModel):
    password: str
    account: Optional[str] = None
    email: Optional[str] = None

    @property
    def login_id(self) -> str:
        return (self.account or self.email or "").strip()


class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    real_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    plan: str
    plan_label: str = "体验"
    plan_expires_at: Optional[date] = None
    phone_verified: bool = False
    is_owner: bool = False
    phone_bound: bool = False

    model_config = ConfigDict(from_attributes=True)


class PhoneBind(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)


class PasswordChange(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=100)
    new_password: str = Field(..., min_length=6, max_length=100)


class EmailBind(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    current_password: str = Field(..., min_length=1, max_length=100)


class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)


class PasswordResetConfirm(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6, max_length=100)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=6)
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            import re
            if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]+$', v):
                raise ValueError('昵称只能包含中文、英文、数字')
        return v


# 认证相关模型
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int  # 秒


class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    token_version: int = 0
