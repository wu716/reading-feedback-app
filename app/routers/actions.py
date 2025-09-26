from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import json

from app.database import get_db
from app.models import User, Action
from app.schemas import (
    ActionCreate, ActionUpdate, ActionResponse, 
    PaginationParams, PaginatedResponse, ActionStatus,
    NotesUpload, NotesUploadResponse,
    PracticeLogCreate, PracticeLogResponse
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
                frequency=action_item.frequency.value
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
            query = query.filter(Action.tags.overlap(tag_list))
    
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
    
    # 创建实践记录
    from app.models import PracticeLog
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
    
    # 更新字段
    update_data = action_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(action, field, value)
    
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
    action.deleted_at = db.query(Action).filter(Action.id == action_id).first().created_at
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
        for tag in action.tags:
            tag_stats[tag] = tag_stats.get(tag, 0) + 1
    
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
