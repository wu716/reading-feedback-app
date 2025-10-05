from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
import json
from datetime import date, datetime, timedelta

from app.database import get_db
from app.models import User, Action, PracticeLog
from app.schemas import (
    ActionCreate, ActionUpdate, ActionResponse, 
    PaginationParams, PaginatedResponse, ActionStatus,
    NotesUpload, NotesUploadResponse,
    PracticeLogCreate, PracticeLogResponse,
    DurationAnalytics, StreakAnalytics, TimeTrendAnalytics, ActionMilestone
)
from app.auth import get_current_active_user
from app.ai_service import extract_actions_from_notes, AIExtractionError, AIValidationError

router = APIRouter(prefix="/actions", tags=["行动项管理"])


@router.post("/upload-notes", response_model=NotesUploadResponse)
async def upload_notes(
    notes_data: NotesUpload,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """上传读书笔记并抽取行动项"""
    try:
        # 调用 AI 抽取行动项
        extracted_actions = await extract_actions_from_notes(
            notes_data.content, 
            notes_data.book_title
        )
        
        if not extracted_actions:
            return NotesUploadResponse(
                message="未找到可执行的行动项",
                actions=[],
                total_actions=0
            )
        
        # 保存行动项到数据库
        saved_actions = []
        for action_item in extracted_actions:
            db_action = Action(
                user_id=current_user.id,
                book_title=action_item.book,
                source_excerpt=action_item.excerpt,
                action_text=action_item.action,
                tags=json.dumps(action_item.tags, ensure_ascii=False),  # 转换为JSON字符串
                frequency=action_item.frequency.value,
                # 默认时间管理设置，用户可以稍后修改
                duration_type="short_term",
                target_duration_days=30,  # 默认30天
                target_frequency="daily",
                start_date=date.today()
            )
            db.add(db_action)
            saved_actions.append(db_action)
        
        db.commit()
        
        # 刷新获取 ID
        for action in saved_actions:
            db.refresh(action)
        
        return NotesUploadResponse(
            message=f"成功抽取 {len(saved_actions)} 个行动项",
            actions=[ActionResponse.from_orm(action) for action in saved_actions],
            total_actions=len(saved_actions)
        )
    
    except (AIExtractionError, AIValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"AI 抽取失败: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务器错误: {str(e)}"
        )


@router.get("/", response_model=PaginatedResponse)
async def get_actions(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    status_filter: Optional[ActionStatus] = Query(None, alias="status", description="状态筛选"),
    tags: Optional[str] = Query(None, description="标签筛选，多个用逗号分隔"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取用户的行动项列表"""
    # 构建查询
    query = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    )
    
    # 搜索过滤
    if search:
        query = query.filter(
            or_(
                Action.action_text.contains(search),
                Action.book_title.contains(search),
                Action.source_excerpt.contains(search)
            )
        )
    
    # 状态过滤
    if status_filter:
        query = query.filter(Action.status == status_filter.value)
    
    # 标签过滤
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if tag_list:
            # 使用 LIKE 查询替代 overlap（SQLite 兼容）
            tag_conditions = []
            for tag in tag_list:
                tag_conditions.append(Action.tags.contains(f'"{tag}"'))
            query = query.filter(or_(*tag_conditions))
    
    # 获取总数
    total = query.count()
    
    # 分页
    offset = (page - 1) * size
    actions = query.order_by(Action.created_at.desc()).offset(offset).limit(size).all()
    
    # 计算总页数
    pages = (total + size - 1) // size
    
    return PaginatedResponse(
        items=[ActionResponse.from_orm(action).dict() for action in actions],
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(
    action_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取单个行动项详情"""
    action = db.query(Action).filter(
        Action.id == action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="行动项不存在"
        )
    
    return action


@router.put("/{action_id}/status", response_model=ActionResponse)
async def update_action_status(
    action_id: int,
    new_status: ActionStatus,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新行动项状态"""
    action = db.query(Action).filter(
        Action.id == action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="行动项不存在"
        )
    
    action.status = new_status.value
    db.commit()
    db.refresh(action)
    
    return ActionResponse.from_orm(action).dict()


@router.post("/{action_id}/practice", response_model=PracticeLogResponse)
async def log_practice(
    action_id: int,
    practice_data: PracticeLogCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """记录实践反馈"""
    # 验证行动项是否存在且属于当前用户
    action = db.query(Action).filter(
        Action.id == action_id,
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
        PracticeLog.action_id == action_id,
        PracticeLog.date == practice_data.date,
        PracticeLog.deleted_at.is_(None)
    ).first()
    
    if existing_log:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该行动项在指定日期已有记录"
        )
    
    # 创建实践记录
    practice_log = PracticeLog(
        user_id=current_user.id,
        action_id=action_id,
        date=practice_data.date,
        result=practice_data.result.value,
        notes=practice_data.notes,
        rating=practice_data.rating
    )
    
    db.add(practice_log)
    
    # 如果实践成功，更新行动项状态为已完成
    if practice_data.result.value == "success":
        action.status = "done"
    
    db.commit()
    db.refresh(practice_log)
    
    return PracticeLogResponse.from_orm(practice_log).dict()


@router.put("/{action_id}", response_model=ActionResponse)
async def update_action(
    action_id: int,
    action_update: ActionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """更新行动项"""
    action = db.query(Action).filter(
        Action.id == action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="行动项不存在"
        )
    
    # 更新字段 - 确保正确处理所有时间管理字段
    update_data = action_update.dict(exclude_unset=True)
    
    # 明确更新每个字段
    for field, value in update_data.items():
        if hasattr(action, field):
            setattr(action, field, value)
    
    # 特别处理时间管理字段，确保数据正确保存
    if action_update.duration_type is not None:
        action.duration_type = action_update.duration_type
    if action_update.target_duration_days is not None:
        action.target_duration_days = action_update.target_duration_days
    if action_update.target_frequency is not None:
        action.target_frequency = action_update.target_frequency
    if action_update.custom_frequency_days is not None:
        action.custom_frequency_days = action_update.custom_frequency_days
    if action_update.start_date is not None:
        action.start_date = action_update.start_date
    if action_update.end_date is not None:
        action.end_date = action_update.end_date
    
    db.commit()
    db.refresh(action)
    
    return action


@router.delete("/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action(
    action_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """删除行动项（软删除）"""
    action = db.query(Action).filter(
        Action.id == action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="行动项不存在"
        )
    
    # 软删除
    from datetime import datetime
    action.deleted_at = datetime.utcnow()
    db.commit()
    
    return None


@router.get("/stats/summary")
async def get_actions_summary(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取行动项统计摘要"""
    # 总行动项数
    total_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).count()
    
    # 按状态统计
    status_stats = {}
    for status in ActionStatus:
        count = db.query(Action).filter(
            Action.user_id == current_user.id,
            Action.status == status.value,
            Action.deleted_at.is_(None)
        ).count()
        status_stats[status.value] = count
    
    # 按标签统计
    all_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).all()
    
    tag_stats = {}
    for action in all_actions:
        try:
            # 解析 JSON 格式的标签
            tags = json.loads(action.tags) if isinstance(action.tags, str) else action.tags
            if isinstance(tags, list):
                for tag in tags:
                    tag_stats[tag] = tag_stats.get(tag, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue
    
    # 按书籍统计
    book_stats = {}
    for action in all_actions:
        book = action.book_title
        book_stats[book] = book_stats.get(book, 0) + 1
    
    return {
        "total_actions": total_actions,
        "status_breakdown": status_stats,
        "top_tags": dict(sorted(tag_stats.items(), key=lambda x: x[1], reverse=True)[:10]),
        "top_books": dict(sorted(book_stats.items(), key=lambda x: x[1], reverse=True)[:10])
    }


@router.get("/analytics/duration", response_model=DurationAnalytics)
async def get_duration_analytics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取时间维度分析数据"""
    # 统计各类型行动项数量（向后兼容）
    short_term_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        or_(Action.duration_type == "short_term", Action.duration_type.is_(None)),
        Action.deleted_at.is_(None)
    ).count()
    
    long_term_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.duration_type == "long_term",
        Action.deleted_at.is_(None)
    ).count()
    
    lifetime_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.duration_type == "lifetime",
        Action.deleted_at.is_(None)
    ).count()
    
    # 计算各类型完成率（向后兼容）
    def calculate_completion_rate(duration_type: str) -> float:
        if duration_type == "short_term":
            # 短期行动项包括未设置 duration_type 的记录
            total_filter = or_(Action.duration_type == "short_term", Action.duration_type.is_(None))
            completed_filter = and_(
                or_(Action.duration_type == "short_term", Action.duration_type.is_(None)),
                Action.status == "done"
            )
        else:
            total_filter = Action.duration_type == duration_type
            completed_filter = and_(
                Action.duration_type == duration_type,
                Action.status == "done"
            )
        
        total = db.query(Action).filter(
            Action.user_id == current_user.id,
            total_filter,
            Action.deleted_at.is_(None)
        ).count()
        
        if total == 0:
            return 0.0
        
        completed = db.query(Action).filter(
            Action.user_id == current_user.id,
            completed_filter,
            Action.deleted_at.is_(None)
        ).count()
        
        return (completed / total) * 100
    
    return DurationAnalytics(
        short_term_actions=short_term_actions,
        long_term_actions=long_term_actions,
        lifetime_actions=lifetime_actions,
        short_term_completion_rate=calculate_completion_rate("short_term"),
        long_term_completion_rate=calculate_completion_rate("long_term"),
        lifetime_completion_rate=calculate_completion_rate("lifetime")
    )


@router.get("/analytics/streak", response_model=StreakAnalytics)
async def get_streak_analytics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取坚持度分析数据"""
    # 获取所有行动项及其实践记录
    actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).all()
    
    # 计算每个行动项的坚持度
    streak_actions = []
    current_streak_days = 0
    longest_streak_days = 0
    total_streak_days = 0
    
    for action in actions:
        # 获取该行动项的所有成功实践记录，按日期排序
        practice_logs = db.query(PracticeLog).filter(
            PracticeLog.action_id == action.id,
            PracticeLog.result == "success",
            PracticeLog.deleted_at.is_(None)
        ).order_by(PracticeLog.date).all()
        
        if not practice_logs:
            continue
        
        # 计算连续天数
        consecutive_days = 0
        max_consecutive = 0
        last_date = None
        
        for log in practice_logs:
            log_date = log.date
            
            if last_date is None:
                consecutive_days = 1
            elif (log_date - last_date).days == 1:
                consecutive_days += 1
            else:
                max_consecutive = max(max_consecutive, consecutive_days)
                consecutive_days = 1
            
            last_date = log_date
        
        max_consecutive = max(max_consecutive, consecutive_days)
        
        # 计算当前连续天数（从最后一天开始）
        current_consecutive = 0
        if practice_logs:
            last_log_date = practice_logs[-1].date
            today = date.today()
            
            # 如果最后一天是今天或昨天，计算连续天数
            if (today - last_log_date).days <= 1:
                current_consecutive = consecutive_days
        
        streak_actions.append({
            "action_id": action.id,
            "action_text": action.action_text,
            "current_streak": current_consecutive,
            "longest_streak": max_consecutive,
            "total_practices": len(practice_logs)
        })
        
        current_streak_days = max(current_streak_days, current_consecutive)
        longest_streak_days = max(longest_streak_days, max_consecutive)
        total_streak_days += len(practice_logs)
    
    return StreakAnalytics(
        current_streak_days=current_streak_days,
        longest_streak_days=longest_streak_days,
        total_streak_days=total_streak_days,
        streak_actions=streak_actions
    )


@router.get("/analytics/trends", response_model=TimeTrendAnalytics)
async def get_time_trend_analytics(
    days: int = Query(30, ge=7, le=365, description="分析天数"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取时间趋势分析数据"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # 每日完成率
    daily_stats = db.query(
        PracticeLog.date,
        func.count(PracticeLog.id).label('total'),
        func.sum(func.case([(PracticeLog.result == 'success', 1)], else_=0)).label('success')
    ).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None)
    ).group_by(PracticeLog.date).order_by(PracticeLog.date).all()
    
    daily_completion_rate = []
    for stat in daily_stats:
        completion_rate = (stat.success / stat.total * 100) if stat.total > 0 else 0
        daily_completion_rate.append({
            "date": stat.date.isoformat(),
            "total": stat.total,
            "success": stat.success,
            "completion_rate": round(completion_rate, 2)
        })
    
    # 每周完成率
    weekly_stats = db.query(
        func.strftime('%Y-%W', PracticeLog.date).label('week'),
        func.count(PracticeLog.id).label('total'),
        func.sum(func.case([(PracticeLog.result == 'success', 1)], else_=0)).label('success')
    ).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None)
    ).group_by('week').order_by('week').all()
    
    weekly_completion_rate = []
    for stat in weekly_stats:
        completion_rate = (stat.success / stat.total * 100) if stat.total > 0 else 0
        weekly_completion_rate.append({
            "week": stat.week,
            "total": stat.total,
            "success": stat.success,
            "completion_rate": round(completion_rate, 2)
        })
    
    # 不同频率的成功率
    frequency_stats = db.query(
        Action.target_frequency,
        func.count(PracticeLog.id).label('total'),
        func.sum(func.case([(PracticeLog.result == 'success', 1)], else_=0)).label('success')
    ).join(PracticeLog, Action.id == PracticeLog.action_id).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None),
        Action.deleted_at.is_(None)
    ).group_by(Action.target_frequency).all()
    
    frequency_success_rate = {}
    for stat in frequency_stats:
        success_rate = (stat.success / stat.total * 100) if stat.total > 0 else 0
        frequency_success_rate[stat.target_frequency or 'unknown'] = round(success_rate, 2)
    
    return TimeTrendAnalytics(
        daily_completion_rate=daily_completion_rate,
        weekly_completion_rate=weekly_completion_rate,
        monthly_completion_rate=[],  # 可以后续实现
        frequency_success_rate=frequency_success_rate
    )


@router.get("/milestones", response_model=List[ActionMilestone])
async def get_action_milestones(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取行动里程碑"""
    milestones = []
    
    # 获取所有行动项
    actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).all()
    
    for action in actions:
        # 获取该行动项的所有实践记录
        practice_logs = db.query(PracticeLog).filter(
            PracticeLog.action_id == action.id,
            PracticeLog.deleted_at.is_(None)
        ).order_by(PracticeLog.date).all()
        
        if not practice_logs:
            continue
        
        # 首次完成
        first_success = next((log for log in practice_logs if log.result == 'success'), None)
        if first_success:
            milestones.append(ActionMilestone(
                action_id=action.id,
                action_text=action.action_text,
                milestone_type="first_completion",
                achieved_date=first_success.date,
                description=f"首次完成：{action.action_text}"
            ))
        
        # 连续7天
        success_logs = [log for log in practice_logs if log.result == 'success']
        if len(success_logs) >= 7:
            # 检查是否有连续7天
            consecutive_count = 0
            max_consecutive = 0
            last_date = None
            
            for log in success_logs:
                if last_date is None or (log.date - last_date).days == 1:
                    consecutive_count += 1
                    max_consecutive = max(max_consecutive, consecutive_count)
                else:
                    consecutive_count = 1
                last_date = log.date
            
            if max_consecutive >= 7:
                milestones.append(ActionMilestone(
                    action_id=action.id,
                    action_text=action.action_text,
                    milestone_type="week_streak",
                    achieved_date=success_logs[-1].date,
                    description=f"连续7天坚持：{action.action_text}"
                ))
        
        # 目标达成（如果设置了目标天数）
        if action.target_duration_days and action.start_date:
            target_end_date = action.start_date + timedelta(days=action.target_duration_days)
            if date.today() >= target_end_date:
                success_count = len(success_logs)
                milestones.append(ActionMilestone(
                    action_id=action.id,
                    action_text=action.action_text,
                    milestone_type="target_achieved",
                    achieved_date=target_end_date,
                    description=f"目标达成：{action.action_text} ({success_count}/目标天数)"
                ))
    
    # 按日期排序
    milestones.sort(key=lambda x: x.achieved_date, reverse=True)
    return milestones[:20]  # 返回最近的20个里程碑
