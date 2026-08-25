from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Subscription
from app.schemas import UserCreate, UserLogin, UserResponse, Token, UserUpdate
from app.auth import authenticate_user, create_access_token, get_password_hash, get_current_active_user
from app.config import settings

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """用户注册"""
    if not settings.is_registration_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前未开放公开注册，请使用已有账号登录，或向管理员索取邀请码"
        )
    expected_invite = (settings.invite_code or "").strip()
    if expected_invite and (user.invite_code or "").strip() != expected_invite:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="邀请码不正确"
        )

    # 检查邮箱是否已存在
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )
    
    # 创建新用户
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        name=user.name,
        password_hash=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # 创建免费订阅
    subscription = Subscription(
        user_id=db_user.id,
        plan="free",
        start_date=db_user.created_at.date()
    )
    db.add(subscription)
    db.commit()
    
    return db_user


@router.get("/register-config")
async def register_config():
    """前端用于显示注册入口 / 邀请码输入框"""
    return {
        "open": settings.is_registration_allowed,
        "invite_required": bool((settings.invite_code or "").strip()),
    }


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    user = authenticate_user(db, user_credentials.email, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    expires_in = int(access_token_expires.total_seconds())

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """获取当前用户信息"""
    return current_user


@router.delete("/me")
async def delete_current_user(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """删除当前用户（软删除 + 匿名化）"""
    from app.anonymization import anonymize_user_data_on_deletion
    
    # 进行匿名化处理
    anonymize_user_data_on_deletion(db, current_user.id)
    
    # 软删除用户
    from datetime import datetime
    current_user.deleted_at = datetime.utcnow()
    current_user.is_active = False
    db.commit()
    
    return {"message": "已删除"}


@router.put("/profile", response_model=UserResponse)
async def update_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新用户个人信息"""
    # 检查昵称是否重复（如果提供了新昵称）
    if user_update.name is not None:
        existing_user = db.query(User).filter(
            User.name == user_update.name,
            User.id != current_user.id,
            User.deleted_at.is_(None)
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该昵称已被使用"
            )
        
        # 更新昵称
        current_user.name = user_update.name
    
    db.commit()
    db.refresh(current_user)
    
    return current_user
