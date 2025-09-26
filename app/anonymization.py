import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import User, Action, PracticeLog, AnonymizedData
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def generate_anonymous_id(user_id: int) -> str:
    """生成匿名ID"""
    salt = "reading_feedback_app_salt_2024"
    return hashlib.sha256(f"{user_id}_{salt}".encode()).hexdigest()[:16]


def anonymize_user_data(user_id: int) -> Dict[str, Any]:
    """匿名化用户数据"""
    anonymous_id = generate_anonymous_id(user_id)
    
    return {
        "anonymous_id": anonymous_id,
        "anonymized_at": datetime.utcnow().isoformat(),
        "data_type": "user_profile"
    }


def anonymize_actions_data(actions: List[Action]) -> List[Dict[str, Any]]:
    """匿名化行动项数据"""
    anonymized_actions = []
    
    for action in actions:
        # 保留统计信息，移除个人标识
        anonymized_action = {
            "book_title": action.book_title,
            "tags": action.tags,
            "frequency": action.frequency,
            "status": action.status,
            "created_at": action.created_at.isoformat() if action.created_at else None,
            "excerpt_length": len(action.source_excerpt),
            "action_length": len(action.action_text)
        }
        anonymized_actions.append(anonymized_action)
    
    return anonymized_actions


def anonymize_practice_logs_data(logs: List[PracticeLog]) -> List[Dict[str, Any]]:
    """匿名化实践日志数据"""
    anonymized_logs = []
    
    for log in logs:
        # 保留统计信息，移除个人标识
        anonymized_log = {
            "result": log.result,
            "rating": log.rating,
            "date": log.date.isoformat() if log.date else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "has_notes": bool(log.notes),
            "notes_length": len(log.notes) if log.notes else 0
        }
        anonymized_logs.append(anonymized_log)
    
    return anonymized_logs


def save_anonymized_data(
    db: Session,
    original_user_id: int,
    data_type: str,
    anonymized_data: Dict[str, Any]
) -> None:
    """保存匿名化数据"""
    try:
        anonymized_record = AnonymizedData(
            original_user_id=original_user_id,
            data_type=data_type,
            anonymized_data=json.dumps(anonymized_data, ensure_ascii=False)
        )
        db.add(anonymized_record)
        db.commit()
        logger.info(f"成功保存匿名化数据: 用户 {original_user_id}, 类型 {data_type}")
    except Exception as e:
        logger.error(f"保存匿名化数据失败: {e}")
        db.rollback()
        raise


def anonymize_user_data_on_deletion(db: Session, user_id: int) -> None:
    """用户删除时进行匿名化处理"""
    try:
        # 获取用户的所有数据
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return
        
        actions = db.query(Action).filter(Action.user_id == user_id).all()
        practice_logs = db.query(PracticeLog).filter(PracticeLog.user_id == user_id).all()
        
        # 匿名化用户数据
        user_data = anonymize_user_data(user_id)
        save_anonymized_data(db, user_id, "user_profile", user_data)
        
        # 匿名化行动项数据
        if actions:
            actions_data = anonymize_actions_data(actions)
            save_anonymized_data(db, user_id, "actions", {
                "count": len(actions_data),
                "actions": actions_data
            })
        
        # 匿名化实践日志数据
        if practice_logs:
            logs_data = anonymize_practice_logs_data(practice_logs)
            save_anonymized_data(db, user_id, "practice_logs", {
                "count": len(logs_data),
                "logs": logs_data
            })
        
        logger.info(f"用户 {user_id} 数据匿名化完成")
        
    except Exception as e:
        logger.error(f"用户数据匿名化失败: {e}")
        raise


def get_anonymized_statistics(db: Session) -> Dict[str, Any]:
    """获取匿名化统计数据"""
    try:
        # 统计用户数量
        user_count = db.query(AnonymizedData).filter(
            AnonymizedData.data_type == "user_profile"
        ).count()
        
        # 统计行动项数量
        actions_data = db.query(AnonymizedData).filter(
            AnonymizedData.data_type == "actions"
        ).all()
        
        total_actions = 0
        for data in actions_data:
            try:
                parsed_data = json.loads(data.anonymized_data)
                total_actions += parsed_data.get("count", 0)
            except:
                continue
        
        # 统计实践日志数量
        logs_data = db.query(AnonymizedData).filter(
            AnonymizedData.data_type == "practice_logs"
        ).all()
        
        total_logs = 0
        for data in logs_data:
            try:
                parsed_data = json.loads(data.anonymized_data)
                total_logs += parsed_data.get("count", 0)
            except:
                continue
        
        return {
            "anonymized_users": user_count,
            "anonymized_actions": total_actions,
            "anonymized_practice_logs": total_logs,
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取匿名化统计失败: {e}")
        return {
            "anonymized_users": 0,
            "anonymized_actions": 0,
            "anonymized_practice_logs": 0,
            "error": str(e)
        }
