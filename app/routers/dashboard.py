from typing import List, Dict, Any
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc

from app.database import get_db
from app.models import User, Action, PracticeLog
from app.schemas import DashboardStats, ActionResponse, DurationAnalytics, StreakAnalytics, TimeTrendAnalytics
from app.auth import get_current_active_user
from app.config import settings

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
        try:
            # 解析 JSON 格式的标签
            import json
            tags = json.loads(action.tags) if isinstance(action.tags, str) else action.tags
            if isinstance(tags, list):
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue
    
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
        try:
            # 解析 JSON 格式的标签
            import json
            tags = json.loads(action.tags) if isinstance(action.tags, str) else action.tags
            if isinstance(tags, list):
                for tag in tags:
                    if tag not in tag_groups:
                        tag_groups[tag] = []
                    tag_groups[tag].append(action)
        except (json.JSONDecodeError, TypeError):
            continue
    
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


@router.get("/duration-analytics", response_model=DurationAnalytics)
async def get_duration_analytics(
    db: Session = Depends(get_db)
):
    """获取时间维度分析数据"""
    # 根据认证配置确定用户ID
    if settings.REQUIRE_AUTH:
        # 认证开启时，需要获取当前用户
        # 这里需要从请求中获取用户信息，暂时返回空数据
        return DurationAnalytics(
            short_term_actions=0,
            long_term_actions=0,
            lifetime_actions=0,
            short_term_completion_rate=0.0,
            long_term_completion_rate=0.0,
            lifetime_completion_rate=0.0
        )
    else:
        # 认证关闭时，查询所有用户的数据
        user_id_filter = None
    
    # 统计各类型行动项数量（向后兼容）
    short_term_query = db.query(Action).filter(
        or_(Action.duration_type == "short_term", Action.duration_type.is_(None)),
        Action.deleted_at.is_(None)
    )
    
    if user_id_filter is not None:
        short_term_query = short_term_query.filter(Action.user_id == user_id_filter)
    
    short_term_actions = short_term_query.count()
    
    long_term_query = db.query(Action).filter(
        Action.duration_type == "long_term",
        Action.deleted_at.is_(None)
    )
    
    if user_id_filter is not None:
        long_term_query = long_term_query.filter(Action.user_id == user_id_filter)
    
    long_term_actions = long_term_query.count()
    
    lifetime_query = db.query(Action).filter(
        Action.duration_type == "lifetime",
        Action.deleted_at.is_(None)
    )
    
    if user_id_filter is not None:
        lifetime_query = lifetime_query.filter(Action.user_id == user_id_filter)
    
    lifetime_actions = lifetime_query.count()
    
    # 计算各类型完成率
    def calculate_completion_rate(duration_type: str) -> float:
        total_query = db.query(Action).filter(
            Action.duration_type == duration_type,
            Action.deleted_at.is_(None)
        )
        
        if user_id_filter is not None:
            total_query = total_query.filter(Action.user_id == user_id_filter)
        
        total = total_query.count()
        
        if total == 0:
            return 0.0
        
        completed_query = db.query(Action).filter(
            Action.duration_type == duration_type,
            Action.status == "done",
            Action.deleted_at.is_(None)
        )
        
        if user_id_filter is not None:
            completed_query = completed_query.filter(Action.user_id == user_id_filter)
        
        completed = completed_query.count()
        
        return (completed / total) * 100
    
    return DurationAnalytics(
        short_term_actions=short_term_actions,
        long_term_actions=long_term_actions,
        lifetime_actions=lifetime_actions,
        short_term_completion_rate=calculate_completion_rate("short_term"),
        long_term_completion_rate=calculate_completion_rate("long_term"),
        lifetime_completion_rate=calculate_completion_rate("lifetime")
    )


@router.get("/streak-analytics", response_model=StreakAnalytics)
async def get_streak_analytics(
    db: Session = Depends(get_db)
):
    """获取坚持度分析数据"""
    # 根据认证配置确定用户ID
    if settings.REQUIRE_AUTH:
        # 认证开启时，需要获取当前用户
        # 这里需要从请求中获取用户信息，暂时返回空数据
        return StreakAnalytics(
            current_streak_days=0,
            longest_streak_days=0,
            total_streak_days=0,
            streak_actions=[]
        )
    else:
        # 认证关闭时，查询所有用户的数据
        user_id_filter = None
    
    # 获取所有行动项及其实践记录
    actions_query = db.query(Action).filter(
        Action.deleted_at.is_(None)
    )
    
    if user_id_filter is not None:
        actions_query = actions_query.filter(Action.user_id == user_id_filter)
    
    actions = actions_query.all()
    
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


@router.get("/time-trends", response_model=TimeTrendAnalytics)
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


@router.get("/stats/comprehensive")
async def get_comprehensive_stats(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取综合统计数据"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # 情境触发型统计
    trigger_logs = db.query(PracticeLog).join(Action).filter(
        PracticeLog.user_id == current_user.id,
        Action.action_type == "trigger",
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None),
        Action.deleted_at.is_(None)
    ).all()
    
    trigger_success_logs = [log for log in trigger_logs if log.result == "success"]
    trigger_total_attempts = len(trigger_logs)
    trigger_success_rate = round((len(trigger_success_logs) / trigger_total_attempts * 100) if trigger_total_attempts > 0 else 0, 2)
    
    # 习惯养成型统计
    habit_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.action_type == "habit",
        Action.deleted_at.is_(None)
    ).all()
    
    habit_logs = db.query(PracticeLog).join(Action).filter(
        PracticeLog.user_id == current_user.id,
        Action.action_type == "habit",
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None),
        Action.deleted_at.is_(None)
    ).all()
    
    # 计算习惯完成天数
    habit_days_count = len(set([log.date for log in habit_logs if log.result == "success"]))
    habit_completion_rate = round((habit_days_count / days * 100) if days > 0 else 0, 2)
    
    # 计算最长连续天数
    longest_streak = 0
    for action in habit_actions:
        action_logs = db.query(PracticeLog).filter(
            PracticeLog.action_id == action.id,
            PracticeLog.result == "success",
            PracticeLog.deleted_at.is_(None)
        ).order_by(PracticeLog.date).all()
        
        if action_logs:
            current_streak = 1
            max_streak = 1
            for i in range(1, len(action_logs)):
                if (action_logs[i].date - action_logs[i-1].date).days == 1:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 1
            longest_streak = max(longest_streak, max_streak)
    
    # 趋势数据（按周）
    trend_data = []
    num_weeks = max(days // 7, 1)
    for i in range(num_weeks):
        week_start = start_date + timedelta(days=i*7)
        week_end = min(week_start + timedelta(days=6), end_date)
        
        week_logs = [log for log in trigger_logs + habit_logs 
                    if week_start <= log.date <= week_end]
        week_success = [log for log in week_logs if log.result == "success"]
        
        trend_data.append({
            "date": week_start.strftime("%m/%d"),
            "trigger_rate": round((len([l for l in week_success if l.action.action_type == "trigger"]) / 
                                 len([l for l in week_logs if l.action.action_type == "trigger"]) * 100) 
                                if len([l for l in week_logs if l.action.action_type == "trigger"]) > 0 else 0, 1),
            "habit_rate": round((len([l for l in week_success if l.action.action_type == "habit"]) / 
                               len([l for l in week_logs if l.action.action_type == "habit"]) * 100) 
                              if len([l for l in week_logs if l.action.action_type == "habit"]) > 0 else 0, 1)
        })
    
    # 按标签统计触发型行动项的分类
    import json
    trigger_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.action_type == "trigger",
        Action.deleted_at.is_(None)
    ).all()
    
    category_distribution = {}
    for action in trigger_actions:
        try:
            tags = json.loads(action.tags) if isinstance(action.tags, str) else action.tags
            if isinstance(tags, list) and tags:
                tag = tags[0]  # 使用第一个标签作为分类
                if tag not in category_distribution:
                    category_distribution[tag] = 0
                category_distribution[tag] += 1
        except (json.JSONDecodeError, TypeError):
            continue
    
    # 转换为数组格式
    category_list = [
        {"category": cat, "count": count}
        for cat, count in category_distribution.items()
    ]
    
    # 计算总行动项数量
    total_actions_count = len(trigger_actions) + len(habit_actions)
    
    # 调试日志
    print(f"=== 综合统计调试信息 ===")
    print(f"触发型行动项数量: {len(trigger_actions)}")
    print(f"习惯型行动项数量: {len(habit_actions)}")
    print(f"总行动项数量: {total_actions_count}")
    print(f"触发型实践记录数: {trigger_total_attempts}")
    print(f"习惯型完成天数: {habit_days_count}")
    
    return {
        "trigger": {
            "overall_success_rate": trigger_success_rate,
            "total_attempts": trigger_total_attempts,
            "success_count": len(trigger_success_logs),
            "category_distribution": category_list,  # 返回数组格式
            "total_trigger_actions": len(trigger_actions)  # 添加触发型行动项总数
        },
        "habit": {
            "overall_completion_rate": habit_completion_rate,
            "completed_days": habit_days_count,
            "longest_streak": longest_streak,
            "total_habits": len(habit_actions)
        },
        "trend_data": trend_data,
        "total_actions": total_actions_count,  # 添加总行动项数量
        "period_days": days
    }


@router.get("/stats/trigger-detailed")
async def get_trigger_detailed_stats(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取情境触发型行动项详细统计"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # 情境触发型行动项统计
    trigger_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.action_type == "trigger",
        Action.deleted_at.is_(None)
    ).all()
    
    # 实践记录统计
    trigger_practice_logs = db.query(PracticeLog).join(Action).filter(
        PracticeLog.user_id == current_user.id,
        Action.action_type == "trigger",
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None),
        Action.deleted_at.is_(None)
    ).all()
    
    trigger_success_logs = [log for log in trigger_practice_logs if log.result == "success"]
    total_attempts = len(trigger_practice_logs)
    success_count = len(trigger_success_logs)
    overall_success_rate = round((success_count / total_attempts * 100) if total_attempts > 0 else 0, 2)
    
    # 趋势数据（按日）
    trend_data = []
    current_date = start_date
    while current_date <= end_date:
        day_logs = [log for log in trigger_practice_logs if log.date == current_date]
        day_success = [log for log in day_logs if log.result == "success"]
        
        trend_data.append({
            "date": current_date.strftime("%m/%d"),
            "success_rate": round((len(day_success) / len(day_logs) * 100) if day_logs else 0, 1),
            "total": len(day_logs),
            "success": len(day_success)
        })
        current_date += timedelta(days=1)
    
    # 按标签分类统计
    import json
    category_distribution = {}
    for action in trigger_actions:
        try:
            tags = json.loads(action.tags) if isinstance(action.tags, str) else action.tags
            if isinstance(tags, list) and tags:
                tag = tags[0]  # 使用第一个标签作为分类
                if tag not in category_distribution:
                    category_distribution[tag] = {"total": 0, "success": 0}
                
                action_logs = [log for log in trigger_practice_logs if log.action_id == action.id]
                action_success = [log for log in action_logs if log.result == "success"]
                
                category_distribution[tag]["total"] += len(action_logs)
                category_distribution[tag]["success"] += len(action_success)
        except (json.JSONDecodeError, TypeError):
            continue
    
    # 转换为前端需要的格式
    category_list = [
        {
            "category": cat,
            "count": data["total"],
            "success_rate": round((data["success"] / data["total"] * 100) if data["total"] > 0 else 0, 1)
        }
        for cat, data in category_distribution.items()
    ]
    
    # Top场景（按成功次数排序）
    top_scenarios = []
    for action in trigger_actions:
        action_logs = [log for log in trigger_practice_logs if log.action_id == action.id]
        action_success = [log for log in action_logs if log.result == "success"]
        
        if action_logs:
            top_scenarios.append({
                "action_text": action.action_text[:30] + "..." if len(action.action_text) > 30 else action.action_text,
                "attempts": len(action_logs),  # 修正字段名
                "success_count": len(action_success),
                "success_rate": round((len(action_success) / len(action_logs) * 100), 1)
            })
    
    top_scenarios.sort(key=lambda x: x["success_count"], reverse=True)
    top_scenarios = top_scenarios[:5]  # 只取前5个
    
    # 热力图数据（按星期几统计）
    daily_heatmap = [
        {"day": "周一", "hour": i, "value": 0} for i in range(24)
    ] + [
        {"day": "周二", "hour": i, "value": 0} for i in range(24)
    ] + [
        {"day": "周三", "hour": i, "value": 0} for i in range(24)
    ] + [
        {"day": "周四", "hour": i, "value": 0} for i in range(24)
    ] + [
        {"day": "周五", "hour": i, "value": 0} for i in range(24)
    ] + [
        {"day": "周六", "hour": i, "value": 0} for i in range(24)
    ] + [
        {"day": "周日", "hour": i, "value": 0} for i in range(24)
    ]
    
    return {
        "overall_success_rate": overall_success_rate,
        "total_attempts": total_attempts,
        "success_count": success_count,
        "trend_data": trend_data,
        "category_distribution": category_list,
        "top_scenarios": top_scenarios,
        "daily_heatmap": daily_heatmap,
        "period_days": days
    }


@router.get("/stats/habit-detailed")
async def get_habit_detailed_stats(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """获取习惯养成型行动项详细统计"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # 习惯养成型行动项统计
    habit_actions = db.query(Action).filter(
        Action.user_id == current_user.id,
        Action.action_type == "habit",
        Action.deleted_at.is_(None)
    ).all()
    
    # 实践记录统计
    habit_practice_logs = db.query(PracticeLog).join(Action).filter(
        PracticeLog.user_id == current_user.id,
        Action.action_type == "habit",
        PracticeLog.date >= start_date,
        PracticeLog.date <= end_date,
        PracticeLog.deleted_at.is_(None),
        Action.deleted_at.is_(None)
    ).all()
    
    habit_success_logs = [log for log in habit_practice_logs if log.result == "success"]
    
    # 计算完成天数（成功打卡的天数）
    completed_days = len(set([log.date for log in habit_success_logs]))
    overall_completion_rate = round((completed_days / days * 100) if days > 0 else 0, 2)
    
    # 坚持度统计（连续天数）
    streaks = []
    longest_streak = 0
    
    for action in habit_actions:
        action_logs = db.query(PracticeLog).filter(
            PracticeLog.action_id == action.id,
            PracticeLog.result == "success",
            PracticeLog.deleted_at.is_(None)
        ).order_by(PracticeLog.date).all()
        
        if action_logs:
            # 计算当前连续天数
            current_streak = 1
            max_streak = 1
            
            for i in range(1, len(action_logs)):
                if (action_logs[i].date - action_logs[i-1].date).days == 1:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 1
            
            longest_streak = max(longest_streak, max_streak)
            
            streaks.append({
                "habit": action.action_text[:20] + "..." if len(action.action_text) > 20 else action.action_text,
                "current_streak": current_streak,
                "longest_streak": max_streak
            })
    
    # 日历热力图数据
    calendar_data = []
    current_date = start_date
    while current_date <= end_date:
        day_logs = [log for log in habit_practice_logs if log.date == current_date]
        day_success = [log for log in day_logs if log.result == "success"]
        
        calendar_data.append({
            "date": current_date.strftime("%Y-%m-%d"),
            "value": len(day_success)  # 修正为value字段
        })
        current_date += timedelta(days=1)
    
    # 习惯排名（按完成率）
    habit_rankings = []
    for action in habit_actions:
        action_logs = [log for log in habit_practice_logs if log.action_id == action.id]
        action_success = [log for log in action_logs if log.result == "success"]
        
        if action_logs:
            habit_rankings.append({
                "habit": action.action_text[:30] + "..." if len(action.action_text) > 30 else action.action_text,
                "completion_rate": round((len(action_success) / len(action_logs) * 100), 1),
                "total_days": len(action_logs),
                "completed_days": len(action_success)
            })
    
    habit_rankings.sort(key=lambda x: x["completion_rate"], reverse=True)
    
    # 趋势数据（按周）
    trend_data = []
    num_weeks = max(days // 7, 1)
    for i in range(num_weeks):
        week_start = start_date + timedelta(days=i*7)
        week_end = min(week_start + timedelta(days=6), end_date)
        
        week_logs = [log for log in habit_practice_logs 
                    if week_start <= log.date <= week_end]
        week_success = [log for log in week_logs if log.result == "success"]
        
        # 计算该周成功打卡的天数
        week_success_days = len(set([log.date for log in week_success]))
        week_total_days = (week_end - week_start).days + 1
        
        trend_data.append({
            "week": f"{week_start.strftime('%m/%d')}-{week_end.strftime('%m/%d')}",
            "completion_rate": round((week_success_days / week_total_days * 100), 1),
            "completed_days": week_success_days
        })
    
    # 习惯进度数据（为前端兼容性添加）
    habit_progress = []
    for action in habit_actions:
        action_logs = [log for log in habit_practice_logs if log.action_id == action.id]
        action_success = [log for log in action_logs if log.result == "success"]
        
        if action_logs:
            habit_progress.append({
                "action_text": action.action_text,
                "completed_days": len(action_success),
                "completion_rate": round((len(action_success) / len(action_logs) * 100), 1)
            })
    
    # 周统计数据（为前端兼容性添加）
    weekly_stats = trend_data  # 复用趋势数据
    
    return {
        "overall_completion_rate": overall_completion_rate,
        "completed_days": completed_days,
        "total_days": days,
        "longest_streak": longest_streak,
        "active_habits": len(habit_actions),
        "streaks": streaks,
        "calendar_heatmap": calendar_data,  # 修正字段名
        "habit_rankings": habit_rankings,
        "trend_data": trend_data,
        "habit_progress": habit_progress,  # 添加习惯进度数据
        "weekly_stats": weekly_stats,      # 添加周统计数据
        "period_days": days
    }
