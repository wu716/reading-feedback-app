# 开发专用路由，只在开发环境启用
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import os

from app.database import get_db
from app.dev_tools import dev_check, get_all_data_for_development, get_user_data_for_development

# 只在开发环境注册路由
if os.getenv("ENV", "development") == "development":
    router = APIRouter(prefix="/dev", tags=["开发工具"])
else:
    router = APIRouter(prefix="/dev", tags=["开发工具"], include_in_schema=False)

@router.get("/data/all")
async def get_all_data_dev(db: Session = Depends(get_db)):
    """获取所有数据（开发环境专用）"""
    return get_all_data_for_development(db)

@router.get("/data/user/{user_id}")
async def get_user_data_dev(user_id: int, db: Session = Depends(get_db)):
    """获取特定用户数据（开发环境专用）"""
    return get_user_data_for_development(user_id, db)

@router.get("/env")
async def get_environment():
    """获取当前环境信息"""
    return {
        "environment": os.getenv("ENV", "development"),
        "debug": os.getenv("DEBUG", "True") == "True"
    }
