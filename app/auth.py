from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import TokenData

# JWT 配置
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def _auth_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def resolve_user_from_access_token(token: str, db: Session) -> User:
    """用 JWT 解析当前用户。新 token 用 user id，旧 token 仍可用邮箱。"""
    credentials_exception = _auth_exception()
    token_data = verify_token(token, credentials_exception)
    user = None
    if token_data.user_id is not None:
        user = db.query(User).filter(
            User.id == token_data.user_id,
            User.deleted_at.is_(None),
        ).first()
    if user is None and token_data.email:
        user = db.query(User).filter(
            User.email == token_data.email,
            User.deleted_at.is_(None),
        ).first()
    if user is None:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("用户不存在或已被删除: %s %s", token_data.user_id, token_data.email)
        raise credentials_exception
    current_version = int(getattr(user, "token_version", 0) or 0)
    if token_data.token_version != current_version:
        logger = __import__("logging").getLogger(__name__)
        logger.info("登录已失效（改密或撤销）: user_id=%s", user.id)
        raise credentials_exception
    return user


def _truncate_password_bytes(password: str) -> bytes:
    """bcrypt 限制密码不超过 72 字节"""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        return password_bytes
    truncated = password_bytes[:72]
    while truncated and truncated[-1] & 0x80 and not (truncated[-1] & 0x40):
        truncated = truncated[:-1]
    return truncated


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(
            _truncate_password_bytes(plain_password),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return bcrypt.hashpw(
        _truncate_password_bytes(password),
        bcrypt.gensalt(),
    ).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)

    # JWT exp 使用 Unix 时间戳，避免时区/序列化导致提前失效
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token(token: str, credentials_exception):
    """验证令牌"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = None
        email = None
        if isinstance(subject, int) or (isinstance(subject, str) and subject.isdigit()):
            user_id = int(subject)
        else:
            email = str(subject)
        version = payload.get("ver", 0)
        try:
            token_version = int(version or 0)
        except (TypeError, ValueError):
            token_version = 0
        return TokenData(user_id=user_id, email=email, token_version=token_version)
    except JWTError as e:
        # 记录具体的JWT错误类型
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"JWT验证失败: {e}")
        raise credentials_exception


def authenticate_user(db: Session, account: str, password: str) -> Optional[User]:
    """用手机号或邮箱验证用户"""
    from app.accounts import find_user_by_account

    user = find_user_by_account(db, account)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_user_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    version = int(getattr(user, "token_version", 0) or 0)
    return create_access_token(
        data={"sub": str(user.id), "ver": version},
        expires_delta=expires_delta,
    )


def bump_token_version(user: User) -> None:
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """获取当前用户"""
    credentials_exception = _auth_exception()
    try:
        return resolve_user_from_access_token(credentials.credentials, db)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"获取当前用户失败: {e}")
        raise credentials_exception


def get_current_user_for_media(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> User:
    """音频播放：Authorization 头或 URL 上的 token 都可以。"""
    raw = credentials.credentials if credentials else None
    if not raw:
        raw = token
    if not raw:
        raise _auth_exception()
    return resolve_user_from_access_token(raw, db)


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def get_current_owner(current_user: User = Depends(get_current_active_user)) -> User:
    from app.plans import is_owner_user

    if not is_owner_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅站长可访问")
    return current_user


def get_current_user_optional(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), db: Session = Depends(get_db)) -> Optional[User]:
    """获取当前用户（可选）- 如果认证关闭则返回None"""
    if not settings.REQUIRE_AUTH:
        # 认证关闭时，返回默认用户或None
        return None
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要认证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return get_current_user(credentials, db)


def get_current_active_user_optional(current_user: Optional[User] = Depends(get_current_user_optional)) -> Optional[User]:
    """获取当前活跃用户（可选）"""
    if current_user is None:
        return None
    
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户账户已被禁用"
        )
    return current_user
