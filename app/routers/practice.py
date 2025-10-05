from typing import List, Optional
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.database import get_db
from app.models import User, Action, PracticeLog
from app.schemas import (
    PracticeLogCreate, PracticeLogUpdate, PracticeLogResponse,
    PaginationParams, PaginatedResponse, PracticeResult
)
from app.auth import get_current_active_user

router = APIRouter(prefix="/practice", tags=["实践反馈"])


@router.post("/log", response_model=PracticeLogResponse, status_code=status.HTTP_201_CREATED)
async def create_practice_log(
    log: PracticeLogCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """记录实践反馈"""
    # 验证行动项是否存在且属于当前用户
    action = db.query(Action).filter(
        Action.id == log.action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="行动项不存在"
        )
    
    # 检查是否已有同一天的记录
    existing_log = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.action_id == log.action_id,
        PracticeLog.date == log.date,
        PracticeLog.deleted_at.is_(None)
    ).first()
    
    if existing_log:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该行动项在指定日期已有记录"
        )
    
    # 创建实践日志
    db_log = PracticeLog(
        user_id=current_user.id,
        action_id=log.action_id,
        date=log.date,
        result=log.result.value,
        notes=log.notes,
        rating=log.rating
    )
    
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    
    return db_log


@router.get("/logs", response_model=PaginatedResponse)
async def get_practice_logs(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    action_id: Optional[int] = Query(None, description="行动项ID筛选"),
    result: Optional[PracticeResult] = Query(None, description="结果筛选"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取实践日志列表"""
    # 构建查询
    query = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.deleted_at.is_(None)
    )
    
    # 行动项筛选
    if action_id:
        query = query.filter(PracticeLog.action_id == action_id)
    
    # 结果筛选
    if result:
        query = query.filter(PracticeLog.result == result.value)
    
    # 日期范围筛选
    if start_date:
        query = query.filter(PracticeLog.date >= start_date)
    if end_date:
        query = query.filter(PracticeLog.date <= end_date)
    
    # 获取总数
    total = query.count()
    
    # 分页
    offset = (page - 1) * size
    logs = query.order_by(desc(PracticeLog.date)).offset(offset).limit(size).all()
    
    # 计算总页数
    pages = (total + size - 1) // size
    
    return PaginatedResponse(
        items=[PracticeLogResponse.from_orm(log) for log in logs],
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@router.get("/logs/{log_id}", response_model=PracticeLogResponse)
async def get_practice_log(
    log_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取单个实践日志详情"""
    log = db.query(PracticeLog).filter(
        PracticeLog.id == log_id,
        PracticeLog.user_id == current_user.id,
        PracticeLog.deleted_at.is_(None)
    ).first()
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="实践日志不存在"
        )
    
    return log


@router.put("/logs/{log_id}", response_model=PracticeLogResponse)
async def update_practice_log(
    log_id: int,
    log_update: PracticeLogUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新实践日志"""
    log = db.query(PracticeLog).filter(
        PracticeLog.id == log_id,
        PracticeLog.user_id == current_user.id,
        PracticeLog.deleted_at.is_(None)
    ).first()
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="实践日志不存在"
        )
    
    # 更新字段
    update_data = log_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field == "result" and value:
            setattr(log, field, value.value)
        else:
            setattr(log, field, value)
    
    db.commit()
    db.refresh(log)
    
    return log


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_practice_log(
    log_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """删除实践日志（软删除）"""
    log = db.query(PracticeLog).filter(
        PracticeLog.id == log_id,
        PracticeLog.user_id == current_user.id,
        PracticeLog.deleted_at.is_(None)
    ).first()
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="实践日志不存在"
        )
    
    # 软删除
    from datetime import datetime
    log.deleted_at = datetime.utcnow()
    db.commit()
    
    return None


@router.get("/stats/summary")
async def get_practice_summary(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取实践统计摘要"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # 基础统计
    total_logs = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None)
    ).count()
    
    # 按结果统计
    result_stats = {}
    for result in PracticeResult:
        count = db.query(PracticeLog).filter(
            PracticeLog.user_id == current_user.id,
            PracticeLog.result == result.value,
            PracticeLog.date >= start_date,
            PracticeLog.date <= end_date,
            PracticeLog.deleted_at.is_(None)
        ).count()
        result_stats[result.value] = count
    
    # 计算成功率
    success_count = result_stats.get("success", 0)
    success_rate = (success_count / total_logs * 100) if total_logs > 0 else 0
    
    # 平均评分
    avg_rating = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.rating.isnot(None),
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None)
    ).with_entities(db.func.avg(PracticeLog.rating)).scalar() or 0
    
    # 按日期统计（最近7天）
    recent_days = 7
    recent_start = end_date - timedelta(days=recent_days-1)
    
    daily_stats = []
    for i in range(recent_days):
        current_date = recent_start + timedelta(days=i)
        day_logs = db.query(PracticeLog).filter(
            PracticeLog.user_id == current_user.id,
            PracticeLog.date == current_date,
            PracticeLog.deleted_at.is_(None)
        ).count()
        
        daily_stats.append({
            "date": current_date.isoformat(),
            "count": day_logs
        })
    
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": days
        },
        "total_logs": total_logs,
        "result_breakdown": result_stats,
        "success_rate": round(success_rate, 2),
        "average_rating": round(float(avg_rating), 2),
        "recent_activity": daily_stats
    }


@router.get("/calendar/{year}/{month}")
async def get_practice_calendar(
    year: int,
    month: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取指定月份的实践日历数据"""
    from calendar import monthrange
    
    # 获取月份的第一天和最后一天
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    
    # 查询该月的所有实践日志
    logs = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.date >= first_day,
        PracticeLog.date <= last_day,
        PracticeLog.deleted_at.is_(None)
    ).all()
    
    # 按日期组织数据
    calendar_data = {}
    for log in logs:
        day = log.date.day
        if day not in calendar_data:
            calendar_data[day] = []
        
        calendar_data[day].append({
            "id": log.id,
            "action_id": log.action_id,
            "result": log.result,
            "rating": log.rating,
            "notes": log.notes
        })
    
    return {
        "year": year,
        "month": month,
        "calendar_data": calendar_data
    }
