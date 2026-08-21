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
    """用 JWT 解析当前用户。"""
    credentials_exception = _auth_exception()
    token_data = verify_token(token, credentials_exception)
    user = db.query(User).filter(
        User.email == token_data.email,
        User.deleted_at.is_(None),
    ).first()
    if user is None:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("用户不存在或已被删除: %s", token_data.email)
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
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
        return token_data
    except JWTError as e:
        # 记录具体的JWT错误类型
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"JWT验证失败: {e}")
        raise credentials_exception


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """验证用户"""
    user = db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


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
