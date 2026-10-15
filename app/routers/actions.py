from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
import json
from datetime import date, datetime, timedelta

from app.database import get_db
from app.habit_service import sync_practice_event
from app.models import User, Action, PracticeLog, SelfTalkReminderSetting, SelfTalkReminderLog
from app.schemas import (
    ActionCreate, ActionUpdate, ActionResponse, 
    PaginationParams, PaginatedResponse, ActionStatus,
    PracticeLogCreate, PracticeLogResponse,
)
from app.auth import get_current_active_user
from app.config import settings
from app.ai_quota import get_quota_status
from app.self_talk.reminder_service import ReminderService

router = APIRouter(prefix="/actions", tags=["行动项管理"])


def autofill_action_end_date(action: Action) -> None:
    """完成天数/坚持天数已填、开始日期已有时，自动写出结束日期 = 开始 + 天数。"""
    if getattr(action, "end_date", None) or not getattr(action, "start_date", None):
        return
    if getattr(action, "duration_type", None) == "lifetime":
        return
    days = None
    if getattr(action, "action_type", None) == "trigger":
        days = getattr(action, "custom_frequency_days", None)
    else:
        days = getattr(action, "target_duration_days", None)
    try:
        days = int(days) if days is not None else 0
    except (TypeError, ValueError):
        days = 0
    if days < 1:
        return
    action.end_date = action.start_date + timedelta(days=days)


@router.get("/ai-quota")
async def get_ai_quota(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return get_quota_status(db, current_user)


@router.post("/", response_model=ActionResponse, status_code=status.HTTP_201_CREATED)
async def create_action(
    action_data: ActionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """手动创建行动项（无需 AI 抽取）"""
    excerpt = (action_data.source_excerpt or "").strip()
    if not excerpt:
        excerpt = action_data.action_text[:200]

    db_action = Action(
        user_id=current_user.id,
        book_title=action_data.book_title.strip(),
        source_excerpt=excerpt,
        action_text=action_data.action_text.strip(),
        tags=json.dumps(action_data.tags or [], ensure_ascii=False),
        frequency=action_data.frequency.value,
        duration_type=action_data.duration_type.value,
        target_duration_days=action_data.target_duration_days,
        target_frequency=action_data.target_frequency.value if action_data.target_frequency else None,
        custom_frequency_days=action_data.custom_frequency_days,
        start_date=action_data.start_date or date.today(),
        end_date=action_data.end_date,
    )
    autofill_action_end_date(db_action)
    db.add(db_action)
    db.commit()
    db.refresh(db_action)
    await trigger_after_new_action_reminder(current_user, db)
    return ActionResponse.model_validate(db_action)


@router.get("/", response_model=PaginatedResponse)
async def get_actions(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    status_filter: Optional[ActionStatus] = Query(None, alias="status", description="状态筛选"),
    action_type: Optional[str] = Query(None, description="行动类型筛选"),
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
    
    # 行动类型过滤
    if action_type:
        query = query.filter(Action.action_type == action_type)
    
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

    # 记录原始状态，用于检查是否变为完成状态
    previous_status = action.status

    action.status = new_status.value
    db.commit()
    db.refresh(action)

    # 如果行动项变为完成状态，触发行动完成提醒
    if new_status.value == "done" and previous_status != "done":
        await trigger_after_action_reminder(action_id, current_user, db)

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
    db.flush()
    sync_practice_event(db, current_user.id, practice_log)
    
    # 情境型一次成功即可归档；习惯要长期做，不能因为今天做成了就标完成
    if practice_data.result.value == "success" and action.action_type != "habit":
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
    
    # 特殊处理tags字段：列表转JSON字符串
    if 'tags' in update_data and isinstance(update_data['tags'], list):
        update_data['tags'] = json.dumps(update_data['tags'], ensure_ascii=False)
    
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
    autofill_action_end_date(action)
    
    db.commit()
    db.refresh(action)
    
    return action


@router.delete("/{action_id}")
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
    
    return {"message": "已删除"}


@router.get("/{action_id}/practice-logs", response_model=PaginatedResponse)
async def get_action_practice_logs(
    action_id: int,
    size: int = Query(1000, ge=1, le=10000, description="返回记录数"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取指定行动项的实践记录。

    统一返回 { items, total, page, size, pages }。桌面 WebView 可能缓存旧页面，
    旧代码会读 response.items.length；如果这里仍返回裸数组，弹窗就会报错。
    """
    action = db.query(Action).filter(
        Action.id == action_id,
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).first()
    
    if not action:
        raise HTTPException(status_code=404, detail="行动项不存在")
    
    practice_logs = db.query(PracticeLog).filter(
        PracticeLog.action_id == action_id,
        PracticeLog.user_id == current_user.id,
        PracticeLog.deleted_at.is_(None)
    ).order_by(desc(PracticeLog.date)).limit(size).all()

    items = [PracticeLogResponse.from_orm(log).dict() for log in practice_logs]
    total = len(items)
    return PaginatedResponse(
        items=items,
        total=total,
        page=1,
        size=size,
        pages=1 if total else 0,
    )


# ============= 提醒触发函数 =============

async def trigger_after_action_reminder(action_id: int, current_user: User, db: Session):
    """触发行动完成提醒"""
    try:
        # 获取用户提醒设置
        setting = db.query(SelfTalkReminderSetting).filter(
            SelfTalkReminderSetting.user_id == current_user.id
        ).first()

        if not setting or not setting.is_enabled or not setting.after_action_reminder:
            return  # 未启用提醒

        # 检查3小时内是否已经发送过行动提醒（避免过于频繁）
        three_hours_ago = datetime.now() - timedelta(hours=3)
        recent_reminder = db.query(SelfTalkReminderLog).filter(
            and_(
                SelfTalkReminderLog.user_id == current_user.id,
                SelfTalkReminderLog.reminder_type.in_(["after_action", "after_new_action"]),
                SelfTalkReminderLog.triggered_at >= three_hours_ago
            )
        ).first()

        if recent_reminder:
            return  # 3小时内已发送过提醒

        title, message = ReminderService.get_reminder_message("after_action", current_user.name)
        ReminderService.dispatch_notifications(
            db, current_user.id, setting, "after_action", title, message
        )

    except Exception as e:
        # 提醒失败不影响主业务流程
        print(f"触发行动完成提醒失败: {e}")


async def trigger_after_new_action_reminder(current_user: User, db: Session):
    """触发新行动添加提醒"""
    try:
        # 获取用户提醒设置
        setting = db.query(SelfTalkReminderSetting).filter(
            SelfTalkReminderSetting.user_id == current_user.id
        ).first()

        if not setting or not setting.is_enabled or not setting.after_new_action_reminder:
            return  # 未启用提醒

        # 检查3小时内是否已经发送过行动提醒
        three_hours_ago = datetime.now() - timedelta(hours=3)
        recent_reminder = db.query(SelfTalkReminderLog).filter(
            and_(
                SelfTalkReminderLog.user_id == current_user.id,
                SelfTalkReminderLog.reminder_type.in_(["after_action", "after_new_action"]),
                SelfTalkReminderLog.triggered_at >= three_hours_ago
            )
        ).first()

        if recent_reminder:
            return  # 3小时内已发送过提醒

        title, message = ReminderService.get_reminder_message("after_new_action", current_user.name)
        ReminderService.dispatch_notifications(
            db, current_user.id, setting, "after_new_action", title, message
        )

    except Exception as e:
        # 提醒失败不影响主业务流程
        print(f"触发新行动提醒失败: {e}")
