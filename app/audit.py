# -*- coding: utf-8 -*-
"""站长可查的操作日志。写失败不影响主流程。"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog

logger = logging.getLogger(__name__)


def write_audit(
    db: Session,
    action: str,
    *,
    actor_user_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    ip: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    try:
        db.add(
            AuditLog(
                action=action,
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                ip=(ip or "")[:64],
                detail=(detail or "")[:500] or None,
            )
        )
        db.commit()
    except Exception as exc:
        logger.warning("写入操作日志失败: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
