from typing import List, Dict, Any
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc

from app.database import get_db
from app.models import User, Action, PracticeLog
from app.schemas import DashboardStats, ActionResponse
from app.auth import get_current_active_user

router = APIRouter(prefix="/dashboard", tags=["仪表盘"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取仪表盘统计数据"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # 行动项统计
    total_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).count()
    
    completed_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.status == "done",
        Action.deleted_at.is_(None)
    ).count()
    
    completion_rate = (completed_actions / total_actions * 100) if total_actions > 0 else 0
    
    # 实践日志统计
    total_practice_logs = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None)
    ).count()
    
    success_logs = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.result == "success",
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None)
    ).count()
    
    success_rate = (success_logs / total_practice_logs * 100) if total_practice_logs > 0 else 0
    
    # 最近的行动项
    recent_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).order_by(desc(Action.created_at)).limit(5).all()
    
    # 实践趋势（按周统计）
    practice_trends = []
    for i in range(0, days, 7):
        week_start = start_date + timedelta(days=i)
        week_end = min(week_start + timedelta(days=6), end_date)
        
        week_logs = db.query(PracticeLog).filter(
            PracticeLog.user_id == current_user.id,
            PracticeLog.date >= week_start,
            PracticeLog.date <= week_end,
            PracticeLog.deleted_at.is_(None)
        ).count()
        
        week_success = db.query(PracticeLog).filter(
            PracticeLog.user_id == current_user.id,
            PracticeLog.result == "success",
            PracticeLog.date >= week_start,
            PracticeLog.date <= week_end,
            PracticeLog.deleted_at.is_(None)
        ).count()
        
        practice_trends.append({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "total_logs": week_logs,
            "success_logs": week_success,
            "success_rate": (week_success / week_logs * 100) if week_logs > 0 else 0
        })
    
    return DashboardStats(
        total_actions=total_actions,
        completed_actions=completed_actions,
        completion_rate=round(completion_rate, 2),
        total_practice_logs=total_practice_logs,
        success_rate=round(success_rate, 2),
        recent_actions=[ActionResponse.from_orm(action) for action in recent_actions],
        practice_trends=practice_trends
    )


@router.get("/insights")
async def get_insights(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取用户洞察和建议"""
    insights = []
    
    # 行动项完成率分析
    total_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).count()
    
    if total_actions > 0:
        completed_actions = db.query(Action).filter(
            Action.user_id == current_user.id,
            Action.status == "done",
            Action.deleted_at.is_(None)
        ).count()
        
        completion_rate = completed_actions / total_actions * 100
        
        if completion_rate < 30:
            insights.append({
                "type": "warning",
                "title": "行动项完成率较低",
                "message": f"你的行动项完成率为 {completion_rate:.1f}%，建议专注于完成现有行动项，而不是添加新的。",
                "suggestion": "尝试将大目标分解为小步骤，每天完成一个小任务。"
            })
        elif completion_rate > 80:
            insights.append({
                "type": "success",
                "title": "行动项完成率很高",
                "message": f"你的行动项完成率为 {completion_rate:.1f}%，表现优秀！",
                "suggestion": "继续保持，可以考虑挑战更有难度的行动项。"
            })
    
    # 实践频率分析
    recent_30_days = date.today() - timedelta(days=30)
    recent_logs = db.query(PracticeLog).filter(
        PracticeLog.user_id == current_user.id,
        PracticeLog.date >= recent_30_days,
        PracticeLog.deleted_at.is_(None)
    ).count()
    
    if recent_logs < 5:
        insights.append({
            "type": "info",
            "title": "实践频率较低",
            "message": f"过去30天你只记录了 {recent_logs} 次实践，建议增加实践频率。",
            "suggestion": "尝试每天至少记录一次实践，即使是很小的进步。"
        })
    elif recent_logs > 20:
        insights.append({
            "type": "success",
            "title": "实践频率很高",
            "message": f"过去30天你记录了 {recent_logs} 次实践，非常棒！",
            "suggestion": "继续保持这个节奏，你正在养成很好的习惯。"
        })
    
    # 标签分析
    all_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).all()
    
    tag_counts = {}
    for action in all_actions:
        for tag in action.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    
    if tag_counts:
        top_tag = max(tag_counts, key=tag_counts.get)
        insights.append({
            "type": "info",
            "title": "最关注的领域",
            "message": f"你最关注的领域是「{top_tag}」，共有 {tag_counts[top_tag]} 个相关行动项。",
            "suggestion": f"继续在「{top_tag}」领域深耕，同时也可以尝试其他领域。"
        })
    
    # 成功率分析
    if recent_logs > 0:
        success_logs = db.query(PracticeLog).filter(
            PracticeLog.user_id == current_user.id,
            PracticeLog.result == "success",
            PracticeLog.date >= recent_30_days,
            PracticeLog.deleted_at.is_(None)
        ).count()
        
        success_rate = success_logs / recent_logs * 100
        
        if success_rate < 50:
            insights.append({
                "type": "warning",
                "title": "实践成功率较低",
                "message": f"你的实践成功率为 {success_rate:.1f}%，可能需要调整行动项难度。",
                "suggestion": "尝试将行动项分解为更小的步骤，或者降低执行频率。"
            })
        elif success_rate > 80:
            insights.append({
                "type": "success",
                "title": "实践成功率很高",
                "message": f"你的实践成功率为 {success_rate:.1f}%，表现优秀！",
                "suggestion": "可以尝试挑战更有难度的行动项。"
            })
    
    return {
        "insights": insights,
        "generated_at": datetime.utcnow().isoformat()
    }


@router.get("/goals")
async def get_goals(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取用户目标和建议"""
    # 获取所有行动项
    actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.deleted_at.is_(None)
    ).all()
    
    # 按状态分组
    todo_actions = [a for a in actions if a.status == "todo"]
    in_progress_actions = [a for a in actions if a.status == "in_progress"]
    done_actions = [a for a in actions if a.status == "done"]
    
    # 按频率分组
    daily_actions = [a for a in actions if a.frequency == "daily"]
    weekly_actions = [a for a in actions if a.frequency == "weekly"]
    monthly_actions = [a for a in actions if a.frequency == "monthly"]
    
    # 按标签分组
    tag_groups = {}
    for action in actions:
        for tag in action.tags:
            if tag not in tag_groups:
                tag_groups[tag] = []
            tag_groups[tag].append(action)
    
    return {
        "status_breakdown": {
            "todo": len(todo_actions),
            "in_progress": len(in_progress_actions),
            "done": len(done_actions)
        },
        "frequency_breakdown": {
            "daily": len(daily_actions),
            "weekly": len(weekly_actions),
            "monthly": len(monthly_actions)
        },
        "tag_breakdown": {
            tag: len(actions) for tag, actions in tag_groups.items()
        },
        "recommendations": generate_recommendations(actions, tag_groups)
    }


def generate_recommendations(actions: List[Action], tag_groups: Dict[str, List[Action]]) -> List[Dict[str, str]]:
    """生成个性化建议"""
    recommendations = []
    
    # 如果行动项太少
    if len(actions) < 3:
        recommendations.append({
            "type": "action",
            "title": "增加行动项",
            "message": "你的行动项数量较少，建议上传更多读书笔记来抽取行动项。",
            "priority": "high"
        })
    
    # 如果待办事项太多
    todo_count = len([a for a in actions if a.status == "todo"])
    if todo_count > 10:
        recommendations.append({
            "type": "focus",
            "title": "专注执行",
            "message": f"你有 {todo_count} 个待办行动项，建议选择3-5个最重要的开始执行。",
            "priority": "medium"
        })
    
    # 如果某个标签的行动项太多
    for tag, tag_actions in tag_groups.items():
        if len(tag_actions) > 5:
            recommendations.append({
                "type": "balance",
                "title": "平衡发展",
                "message": f"你在「{tag}」领域有 {len(tag_actions)} 个行动项，建议尝试其他领域。",
                "priority": "low"
            })
    
    return recommendations
