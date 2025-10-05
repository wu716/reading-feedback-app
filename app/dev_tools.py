# 开发工具模块，只在开发环境可用
import os
from fastapi import HTTPException
from sqlalchemy.orm import Session

def dev_check():
    """检查是否在开发环境"""
    return os.getenv("ENV", "development") == "development"

def get_all_data_for_development(db: Session):
    """开发环境下获取所有数据（仅限开发环境使用）"""
    if not dev_check():
        raise HTTPException(status_code=403, detail="仅限开发环境使用")
    
    # 返回所有用户数据（开发环境专用）
    from app.models import User, Action, PracticeLog
    return {
        "users": db.query(User).all(),
        "actions": db.query(Action).all(),
        "practice_logs": db.query(PracticeLog).all()
    }

def get_user_data_for_development(user_id: int, db: Session):
    """开发环境下获取特定用户数据"""
    if not dev_check():
        raise HTTPException(status_code=403, detail="仅限开发环境使用")
    
    from app.models import User, Action, PracticeLog
    return {
        "user": db.query(User).filter(User.id == user_id).first(),
        "actions": db.query(Action).filter(Action.user_id == user_id).all(),
        "practice_logs": db.query(PracticeLog).filter(PracticeLog.user_id == user_id).all()
    }
