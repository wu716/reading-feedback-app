from datetime import datetime, timedelta, timezone
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.accounts import (
    find_active_phone,
    placeholder_email,
    user_to_public_dict,
    validate_phone,
    validate_real_name,
)
from app.auth import (
    authenticate_user,
    get_current_active_user,
    get_password_hash,
    issue_user_token,
)
from app.config import settings
from app.database import get_db
from app.models import InviteCode, Subscription, User
from app.plans import PLAN_FREE, apply_plan, plan_catalog, resolve_user_plan
from app.schemas import PhoneBind, Token, UserCreate, UserLogin, UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["认证"])

INVITE_FAIL_LIMIT = 5
INVITE_FAIL_WINDOW = 3600
_invite_fails: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _invite_fail_count(ip: str) -> int:
    now = time.time()
    hits = [t for t in _invite_fails.get(ip, []) if now - t < INVITE_FAIL_WINDOW]
    _invite_fails[ip] = hits
    return len(hits)


def _guard_invite_attempts(ip: str) -> None:
    if _invite_fail_count(ip) >= INVITE_FAIL_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="邀请码尝试过多，请稍后再试",
        )


def _record_invite_fail(ip: str) -> None:
    _invite_fails.setdefault(ip, []).append(time.time())


def _as_user_response(user: User) -> UserResponse:
    return UserResponse(**user_to_public_dict(user))


def _consume_invite_code(db: Session, raw_code: str, ip: str) -> InviteCode:
    _guard_invite_attempts(ip)
    code = (raw_code or "").strip()
    if not code.isdigit() or len(code) != 4:
        _record_invite_fail(ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码不正确")

    now = datetime.now(timezone.utc)
    row = db.query(InviteCode).filter(InviteCode.code == code).first()
    expires_at = row.expires_at if row is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if row is None or row.used_at is not None or expires_at is None or expires_at <= now:
        _record_invite_fail(ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码不正确或已失效")

    updated = (
        db.query(InviteCode)
        .filter(
            InviteCode.id == row.id,
            InviteCode.used_at.is_(None),
            InviteCode.expires_at > now,
        )
        .update({"used_at": now}, synchronize_session=False)
    )
    if updated != 1:
        _record_invite_fail(ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码不正确或已失效")
    db.refresh(row)
    return row


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, request: Request, db: Session = Depends(get_db)):
    """手机号 + 真实姓名 + 一次性邀请码注册。"""
    if not settings.is_registration_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前未开放注册，请使用已有账号登录，或向管理员索取邀请码",
        )

    try:
        phone = validate_phone(user.phone)
        real_name = validate_real_name(user.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if find_active_phone(db, phone):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该手机号已注册")

    invite = _consume_invite_code(db, user.invite_code, _client_ip(request))
    plan_key = invite.plan if invite.plan in ("free", "monthly", "semester") else PLAN_FREE

    email = placeholder_email(phone)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该手机号已注册")

    db_user = User(
        email=email,
        name=real_name,
        real_name=real_name,
        phone=phone,
        phone_verified=False,
        password_hash=get_password_hash(user.password),
        plan=plan_key,
    )
    apply_plan(db_user, plan_key, persist_subscription=False)
    db.add(db_user)
    db.flush()

    invite.used_by_user_id = db_user.id
    start_date = datetime.now(timezone.utc).date()
    if db_user.created_at:
        start_date = db_user.created_at.date()
    subscription = Subscription(
        user_id=db_user.id,
        plan=plan_key,
        start_date=start_date,
        end_date=db_user.plan_expires_at,
    )
    db.add(subscription)
    db.commit()
    db.refresh(db_user)
    return _as_user_response(db_user)


@router.get("/register-config")
async def register_config():
    """前端用于显示注册入口 / 邀请码输入框"""
    return {
        "open": settings.is_registration_allowed,
        "invite_required": True,
    }


@router.get("/plans")
async def list_plans():
    return {"plans": plan_catalog()}


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """手机号或邮箱 + 密码登录"""
    account = user_credentials.login_id
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请填写手机号或邮箱",
        )
    user = authenticate_user(db, account, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    resolve_user_plan(db, user)
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = issue_user_token(user, expires_delta=access_token_expires)
    expires_in = int(access_token_expires.total_seconds())

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """获取当前用户信息"""
    resolve_user_plan(db, current_user)
    return _as_user_response(current_user)


@router.put("/phone", response_model=UserResponse)
async def bind_phone(
    payload: PhoneBind,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """旧邮箱用户绑定手机号（本轮不验证短信）。"""
    try:
        phone = validate_phone(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if current_user.phone == phone:
        return _as_user_response(current_user)

    if find_active_phone(db, phone, exclude_user_id=current_user.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该手机号已被其他账户使用")

    current_user.phone = phone
    current_user.phone_verified = False
    db.commit()
    db.refresh(current_user)
    return _as_user_response(current_user)


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
    
    return _as_user_response(current_user)
