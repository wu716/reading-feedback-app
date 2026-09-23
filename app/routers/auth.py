from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import smtplib
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.accounts import (
    find_active_phone,
    placeholder_email,
    user_to_public_dict,
    validate_phone,
    validate_real_name,
)
from app.audit import write_audit
from app.auth import (
    authenticate_user,
    bump_token_version,
    get_current_active_user,
    get_password_hash,
    issue_user_token,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import AuthCode, InviteCode, Subscription, User
from app.plans import PLAN_FREE, apply_plan, plan_catalog, resolve_user_plan
from app.rate_limit import (
    clear_rate_hits,
    client_ip,
    guard_rate_limit,
    record_rate_hit,
    seconds_until_slot,
)
from app.schemas import EmailBind, PasswordChange, PasswordResetConfirm, PasswordResetRequest, PhoneBind, Token, UserCreate, UserLogin, UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["认证"])

INVITE_FAIL_LIMIT = 5
INVITE_FAIL_WINDOW = 3600
LOGIN_FAIL_LIMIT = 8
LOGIN_FAIL_WINDOW = 900
LOGIN_HOURLY_LIMIT = 20
LOGIN_HOURLY_WINDOW = 3600
REGISTER_LIMIT = 8
REGISTER_WINDOW = 3600
CODE_EXPIRE_MINUTES = 10


def _normalize_email(value: str) -> str:
    email = (value or '').strip().lower()
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        raise HTTPException(status_code=400, detail='请填写有效的邮箱地址')
    return email


def _send_code_email(email: str, code: str, purpose: str) -> bool:
    if not settings.SMTP_HOST:
        return False
    subject = '书然邮箱绑定验证码' if purpose == 'bind_email' else '书然重置密码验证码'
    msg = MIMEText(f'你的{subject}是：{code}\n验证码 10 分钟内有效。如非本人操作，请忽略此邮件。', 'plain', 'utf-8')
    msg['From'] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    msg['To'] = email
    msg['Subject'] = subject
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        return False


def _issue_code(db: Session, email: str, purpose: str) -> str:
    db.query(AuthCode).filter(AuthCode.email == email, AuthCode.purpose == purpose, AuthCode.used_at.is_(None)).update({'used_at': datetime.now(timezone.utc)})
    code = f'{secrets.randbelow(1000000):06d}'
    db.add(AuthCode(email=email, purpose=purpose, code_hash=hashlib.sha256(code.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRE_MINUTES)))
    db.commit()
    return code


def _consume_code(db: Session, email: str, purpose: str, code: str) -> bool:
    row = db.query(AuthCode).filter(AuthCode.email == email, AuthCode.purpose == purpose, AuthCode.used_at.is_(None)).order_by(AuthCode.id.desc()).first()
    now = datetime.now(timezone.utc)
    if not row or row.expires_at < now or row.attempts >= 5:
        return False
    row.attempts += 1
    valid = secrets.compare_digest(row.code_hash, hashlib.sha256(code.encode()).hexdigest())
    if valid:
        row.used_at = now
    db.commit()
    return valid


def _guard_invite_attempts(ip: str) -> None:
    guard_rate_limit(
        f"invite:{ip}",
        INVITE_FAIL_LIMIT,
        INVITE_FAIL_WINDOW,
        "邀请码尝试过多，请稍后再试",
    )


def _record_invite_fail(ip: str) -> None:
    record_rate_hit(f"invite:{ip}")


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

    ip = client_ip(request)
    guard_rate_limit(f"register:{ip}", REGISTER_LIMIT, REGISTER_WINDOW, "注册次数过多，请稍后再试")
    record_rate_hit(f"register:{ip}")
    invite = _consume_invite_code(db, user.invite_code, ip)
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
    write_audit(db, "register", actor_user_id=db_user.id, ip=ip, detail=phone)
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


def _login_too_many_message(key: str, window_sec: int = LOGIN_FAIL_WINDOW) -> str:
    wait = seconds_until_slot(key, window_sec)
    minutes = max(1, (wait + 59) // 60)
    return f"登录尝试过多，请 {minutes} 分钟后再试"


def _login_rate_keys(ip: str, account: str) -> tuple[str, str, str]:
    normalized = account.strip().lower()[:80]
    return f"login:{ip}", f"login-acct:{normalized}", f"login-hour:{ip}"


def _guard_login_attempts(ip: str, account: str) -> None:
    ip_key, acct_key, hour_key = _login_rate_keys(ip, account)
    guard_rate_limit(ip_key, LOGIN_FAIL_LIMIT, LOGIN_FAIL_WINDOW, _login_too_many_message(ip_key))
    guard_rate_limit(acct_key, LOGIN_FAIL_LIMIT, LOGIN_FAIL_WINDOW, _login_too_many_message(acct_key))
    guard_rate_limit(
        hour_key,
        LOGIN_HOURLY_LIMIT,
        LOGIN_HOURLY_WINDOW,
        _login_too_many_message(hour_key, LOGIN_HOURLY_WINDOW),
    )


def _record_login_fail(ip: str, account: str) -> None:
    ip_key, acct_key, hour_key = _login_rate_keys(ip, account)
    record_rate_hit(ip_key)
    record_rate_hit(acct_key)
    record_rate_hit(hour_key)


def _clear_login_fails(ip: str, account: str) -> None:
    ip_key, acct_key, hour_key = _login_rate_keys(ip, account)
    clear_rate_hits(ip_key)
    clear_rate_hits(acct_key)
    clear_rate_hits(hour_key)


@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    """手机号或邮箱 + 密码登录"""
    account = user_credentials.login_id
    ip = client_ip(request)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请填写手机号或邮箱",
        )
    # 先限流再验密：同一 IP / 同一账号短时间试太多次，正确密码也被拦住。
    _guard_login_attempts(ip, account)
    user = authenticate_user(db, account, user_credentials.password)
    if not user:
        _record_login_fail(ip, account)
        write_audit(db, "login_fail", ip=ip, detail=account[:32])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该账户已停用")
    _clear_login_fails(ip, account)

    resolve_user_plan(db, user)
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = issue_user_token(user, expires_delta=access_token_expires)
    expires_in = int(access_token_expires.total_seconds())
    write_audit(db, "login", actor_user_id=user.id, ip=ip)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
    }


@router.post('/email/bind-code')
async def send_bind_email_code(payload: EmailBind, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail='当前密码不正确')
    if db.query(User).filter(User.email == email, User.id != current_user.id, User.deleted_at.is_(None)).first():
        raise HTTPException(status_code=400, detail='该邮箱已被其他账户使用')
    code = _issue_code(db, email, 'bind_email')
    if not _send_code_email(email, code, 'bind_email'):
        raise HTTPException(status_code=503, detail='邮件服务暂不可用，请稍后再试')
    return {'message': '验证码已发送'}


@router.put('/email', response_model=UserResponse)
async def bind_email(payload: EmailBind, code: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail='当前密码不正确')
    if db.query(User).filter(User.email == email, User.id != current_user.id, User.deleted_at.is_(None)).first():
        raise HTTPException(status_code=400, detail='该邮箱已被其他账户使用')
    if not _consume_code(db, email, 'bind_email', code):
        raise HTTPException(status_code=400, detail='验证码错误或已失效')
    current_user.email = email
    db.commit()
    db.refresh(current_user)
    return _as_user_response(current_user)


@router.post('/password-reset/code')
async def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    user = db.query(User).filter(User.email == email, User.deleted_at.is_(None), User.is_active.is_(True)).first()
    if user and not is_placeholder_email_for_reset(user.email):
        code = _issue_code(db, email, 'reset_password')
        _send_code_email(email, code, 'reset_password')
    return {'message': '如果该邮箱已绑定，验证码将发送到邮箱'}


def is_placeholder_email_for_reset(email: str) -> bool:
    return email.lower().endswith('@phone.invalid')


@router.post('/password-reset')
async def reset_password(payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    user = db.query(User).filter(User.email == email, User.deleted_at.is_(None), User.is_active.is_(True)).first()
    if not user or not _consume_code(db, email, 'reset_password', payload.code):
        raise HTTPException(status_code=400, detail='验证码错误或已失效')
    user.password_hash = get_password_hash(payload.new_password)
    bump_token_version(user)
    db.commit()
    write_audit(db, 'password_reset', actor_user_id=user.id, ip=client_ip(request))
    return {'message': '密码已重置，请使用新密码登录'}


@router.put("/password")
async def change_password(
    payload: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")
    current_user.password_hash = get_password_hash(payload.new_password)
    bump_token_version(current_user)
    db.commit()
    db.refresh(current_user)
    write_audit(db, "password_change", actor_user_id=current_user.id, ip=client_ip(request))
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    return {
        "message": "密码已更新，其它设备需要重新登录",
        "access_token": issue_user_token(current_user, expires_delta=access_token_expires),
        "token_type": "bearer",
        "expires_in": int(access_token_expires.total_seconds()),
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
