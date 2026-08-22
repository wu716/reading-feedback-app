# -*- coding: utf-8 -*-
"""
Self-talk 提醒服务
处理定时任务、通知发送等核心逻辑
"""
import json
import logging
import smtplib
from datetime import datetime, timedelta, date, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import (
    User, SelfTalk, SelfTalkReminderSetting,
    SelfTalkReminderLog, Action, PracticeLog, DailyTodo
)

BEIJING_TZ = ZoneInfo("Asia/Shanghai")

logger = logging.getLogger(__name__)


class ReminderService:
    """提醒服务类"""
    
    @staticmethod
    def get_or_create_setting(db: Session, user_id: int) -> SelfTalkReminderSetting:
        """获取或创建用户的提醒设置"""
        setting = db.query(SelfTalkReminderSetting).filter(
            SelfTalkReminderSetting.user_id == user_id
        ).first()
        
        if not setting:
            # 创建默认设置
            setting = SelfTalkReminderSetting(
                user_id=user_id,
                is_enabled=True,
                daily_reminder_enabled=False,
                after_action_reminder=True,
                after_new_action_reminder=True,
                inactive_days_threshold=3,
                browser_notification=True,
                email_notification=True
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)
            logger.info(f"为用户 {user_id} 创建默认提醒设置")
        
        return setting
    
    @staticmethod
    def should_remind_today(setting: SelfTalkReminderSetting) -> bool:
        """判断今天是否应该提醒"""
        if not setting.is_enabled or not setting.daily_reminder_enabled:
            return False
        
        try:
            reminder_days = json.loads(setting.reminder_days)
            today_weekday = datetime.now().weekday()
            # 转换：Python的weekday()是0=周一，我们需要0=周日
            today_index = (today_weekday + 1) % 7
            return today_index in reminder_days
        except Exception as e:
            logger.error(f"解析提醒日期失败: {e}")
            return False
    
    @staticmethod
    def check_inactive_users(db: Session) -> List[int]:
        """检查长期未做 self-talk 的用户"""
        inactive_user_ids = []
        
        # 获取所有启用了非活跃提醒的用户
        settings = db.query(SelfTalkReminderSetting).filter(
            SelfTalkReminderSetting.is_enabled == True
        ).all()
        
        for setting in settings:
            threshold_days = setting.inactive_days_threshold
            threshold_date = datetime.now() - timedelta(days=threshold_days)
            
            # 查询最后一次 self-talk 记录
            last_self_talk = db.query(SelfTalk).filter(
                and_(
                    SelfTalk.user_id == setting.user_id,
                    SelfTalk.deleted_at.is_(None)
                )
            ).order_by(SelfTalk.created_at.desc()).first()
            
            # 如果没有记录或最后记录早于阈值时间
            if not last_self_talk or last_self_talk.created_at < threshold_date:
                # 检查今天是否已经发送过非活跃提醒
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                existing_log = db.query(SelfTalkReminderLog).filter(
                    and_(
                        SelfTalkReminderLog.user_id == setting.user_id,
                        SelfTalkReminderLog.reminder_type == "inactive",
                        SelfTalkReminderLog.triggered_at >= today_start
                    )
                ).first()
                
                if not existing_log:
                    inactive_user_ids.append(setting.user_id)
        
        return inactive_user_ids
    
    @staticmethod
    def log_reminder(
        db: Session, 
        user_id: int, 
        reminder_type: str,
        notification_method: str = "both",
        detail: Optional[str] = None,
    ) -> SelfTalkReminderLog:
        """记录提醒日志"""
        log = SelfTalkReminderLog(
            user_id=user_id,
            reminder_type=reminder_type,
            notification_method=notification_method,
            detail=detail,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
    
    @staticmethod
    def send_browser_notification(user_id: int, message: str, title: str = "Self-talk 提醒"):
        """发送浏览器通知（返回通知数据，前端负责显示）"""
        return {
            "type": "browser_notification",
            "title": title,
            "message": message,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def send_email_notification(
        db: Session,
        user_id: int,
        subject: str,
        content: str,
    ) -> bool:
        """发送邮件通知（同步，供定时任务与 API 共用）"""
        try:
            from app.config import settings

            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.email:
                logger.warning(f"用户 {user_id} 没有邮箱地址")
                return False

            if not settings.SMTP_HOST:
                logger.warning("邮件服务未配置（SMTP_HOST 为空）")
                return False

            msg = MIMEMultipart()
            msg["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
            msg["To"] = user.email
            msg["Subject"] = subject

            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #667eea;">📚 读书反馈提醒</h2>
                <p>{content}</p>
                <hr>
                <p style="color: #666; font-size: 12px;">
                    这是来自读书反馈应用的自动提醒邮件。请登录应用记录你的践行。
                </p>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(f"邮件发送成功: {user.email}")
            return True

        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            return False

    @staticmethod
    def dispatch_notifications(
        db: Session,
        user_id: int,
        setting: SelfTalkReminderSetting,
        reminder_type: str,
        title: str,
        message: str,
        detail: Optional[str] = None,
    ) -> None:
        """记录应用内提醒，并按设置额外发送邮件。邮件关闭时不影响应用内提醒。"""
        if setting.browser_notification and setting.email_notification:
            method = "both"
        elif setting.browser_notification:
            method = "browser"
        elif setting.email_notification:
            method = "email"
        else:
            method = "in_app"

        ReminderService.log_reminder(db, user_id, reminder_type, method, detail=detail)

        if setting.email_notification:
            ReminderService.send_email_notification(db, user_id, title, message)
    
    @staticmethod
    def get_reminder_message(reminder_type: str, user_name: str = "用户", detail: Optional[str] = None) -> tuple:
        """获取提醒消息内容"""
        if reminder_type == "todo":
            return ("待办提醒", detail or f"{user_name}，你有一条待办到点了。")
        messages = {
            "daily": (
                "每日提醒",
                f"你好 {user_name}！该做今天的 Self-talk 啦~ 记录下你的思考和感悟吧！"
            ),
            "after_action": (
                "行动完成提醒",
                f"{user_name}，恭喜完成行动项！花几分钟做个 Self-talk，反思一下收获吧！"
            ),
            "after_new_action": (
                "新行动添加提醒",
                f"{user_name}，新的行动项已添加！要不要录个 Self-talk 说说你的想法？"
            ),
            "inactive": (
                "长期未记录提醒",
                f"{user_name}，已经好几天没做 Self-talk 了！快来记录下最近的思考吧~"
            ),
            "action_practice": (
                "行动践行提醒",
                f"{user_name}，你有行动项尚未按频率践行，请登录应用完成今日/本期践行记录。"
            ),
        }
        return messages.get(reminder_type, ("提醒", "该做 Self-talk 了！"))

    @staticmethod
    def _action_is_overdue(action: Action, last_practice: Optional[date], today: date) -> bool:
        """判断行动是否逾期未践行"""
        freq = action.target_frequency or action.frequency or "daily"
        if last_practice is None:
            return True

        days_since = (today - last_practice).days
        if freq == "daily":
            return days_since >= 1
        if freq == "weekly":
            return days_since >= 7
        if freq == "monthly":
            return days_since >= 30
        if freq == "custom" and action.custom_frequency_days:
            return days_since >= action.custom_frequency_days
        return days_since >= 1


# 定时任务函数
def check_daily_reminders(db: Session):
    """检查并发送每日提醒"""
    logger.info("开始检查每日提醒...")
    
    try:
        now = datetime.now()
        current_time = now.time()
        
        # 获取所有启用了每日提醒的设置
        settings = db.query(SelfTalkReminderSetting).filter(
            and_(
                SelfTalkReminderSetting.is_enabled == True,
                SelfTalkReminderSetting.daily_reminder_enabled == True
            )
        ).all()
        
        reminded_count = 0
        
        for setting in settings:
            # 检查今天是否应该提醒
            if not ReminderService.should_remind_today(setting):
                continue
            
            # 检查提醒时间
            if not setting.daily_reminder_time:
                continue
            
            try:
                reminder_time = datetime.strptime(setting.daily_reminder_time, "%H:%M:%S").time()
            except:
                try:
                    reminder_time = datetime.strptime(setting.daily_reminder_time, "%H:%M").time()
                except:
                    logger.error(f"无效的提醒时间格式: {setting.daily_reminder_time}")
                    continue
            
            # 判断当前时间是否接近提醒时间（允许5分钟误差）
            time_diff = abs(
                (current_time.hour * 60 + current_time.minute) - 
                (reminder_time.hour * 60 + reminder_time.minute)
            )
            
            if time_diff <= 5:  # 5分钟内
                # 检查今天是否已经发送过
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                existing_log = db.query(SelfTalkReminderLog).filter(
                    and_(
                        SelfTalkReminderLog.user_id == setting.user_id,
                        SelfTalkReminderLog.reminder_type == "daily",
                        SelfTalkReminderLog.triggered_at >= today_start
                    )
                ).first()
                
                if not existing_log:
                    user = db.query(User).filter(User.id == setting.user_id).first()
                    if user:
                        title, message = ReminderService.get_reminder_message("daily", user.name)
                        ReminderService.dispatch_notifications(
                            db, setting.user_id, setting, "daily", title, message
                        )
                        reminded_count += 1
                        logger.info(f"已为用户 {user.name} 发送每日提醒")
        
        logger.info(f"每日提醒检查完成，共发送 {reminded_count} 条提醒")
        
    except Exception as e:
        logger.error(f"检查每日提醒时出错: {e}")
        import traceback
        traceback.print_exc()


def check_inactive_reminders(db: Session):
    """检查并发送非活跃用户提醒"""
    logger.info("开始检查非活跃用户...")
    
    try:
        inactive_user_ids = ReminderService.check_inactive_users(db)
        
        for user_id in inactive_user_ids:
            user = db.query(User).filter(User.id == user_id).first()
            setting = db.query(SelfTalkReminderSetting).filter(
                SelfTalkReminderSetting.user_id == user_id
            ).first()
            
            if user and setting:
                title, message = ReminderService.get_reminder_message("inactive", user.name)
                ReminderService.dispatch_notifications(
                    db, user_id, setting, "inactive", title, message
                )
                logger.info(f"已为非活跃用户 {user.name} 发送提醒")
        
        logger.info(f"非活跃用户检查完成，共发送 {len(inactive_user_ids)} 条提醒")
        
    except Exception as e:
        logger.error(f"检查非活跃用户时出错: {e}")
        import traceback
        traceback.print_exc()


def check_action_practice_reminders(db: Session):
    """检查逾期未践行的行动项，发送提醒（邮件 + 浏览器轮询）"""
    logger.info("开始检查行动践行提醒...")
    today = datetime.now().date()
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    reminded_users = set()

    try:
        active_actions = db.query(Action).filter(
            Action.deleted_at.is_(None),
            Action.status.in_(["todo", "in_progress"]),
        ).all()

        for action in active_actions:
            setting = db.query(SelfTalkReminderSetting).filter(
                SelfTalkReminderSetting.user_id == action.user_id,
                SelfTalkReminderSetting.is_enabled == True,
            ).first()
            if not setting:
                continue

            last_log = (
                db.query(PracticeLog)
                .filter(
                    PracticeLog.action_id == action.id,
                    PracticeLog.deleted_at.is_(None),
                )
                .order_by(PracticeLog.date.desc())
                .first()
            )
            last_date = last_log.date if last_log else None

            if not ReminderService._action_is_overdue(action, last_date, today):
                continue

            existing = db.query(SelfTalkReminderLog).filter(
                SelfTalkReminderLog.user_id == action.user_id,
                SelfTalkReminderLog.reminder_type == "action_practice",
                SelfTalkReminderLog.triggered_at >= today_start,
            ).first()
            if existing or action.user_id in reminded_users:
                continue

            user = db.query(User).filter(User.id == action.user_id).first()
            if not user or not user.is_active:
                continue

            title, base_message = ReminderService.get_reminder_message("action_practice", user.name)
            message = (
                f"{base_message}<br><br>"
                f"待践行行动：<strong>{action.action_text[:80]}</strong>"
                f"{'…' if len(action.action_text) > 80 else ''}"
            )
            ReminderService.dispatch_notifications(
                db, user.id, setting, "action_practice", title, message
            )
            reminded_users.add(user.id)
            logger.info(f"已为用户 {user.name} 发送行动践行提醒（行动 ID {action.id}）")

        logger.info(f"行动践行提醒检查完成，共提醒 {len(reminded_users)} 位用户")

    except Exception as e:
        logger.error(f"检查行动践行提醒时出错: {e}")
        import traceback
        traceback.print_exc()


def _todo_due_at(todo: DailyTodo) -> Optional[datetime]:
    raw = (todo.remind_time or "").strip()
    if not raw:
        return None
    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return datetime.combine(todo.todo_date, time(hour, minute), tzinfo=BEIJING_TZ)
    except Exception:
        return None


def check_todo_reminders(db: Session, user_id: Optional[int] = None) -> int:
    """把已到期的待办写成提醒日志，供页面轮询和系统通知使用。"""
    now = datetime.now(BEIJING_TZ)
    query = db.query(DailyTodo).filter(
        DailyTodo.deleted_at.is_(None),
        DailyTodo.completed == False,
        DailyTodo.remind_time.isnot(None),
        DailyTodo.reminded_at.is_(None),
    )
    if user_id is not None:
        query = query.filter(DailyTodo.user_id == user_id)

    fired = 0
    for todo in query.all():
        due = _todo_due_at(todo)
        if due is None or now < due:
            continue
        user = db.query(User).filter(User.id == todo.user_id).first()
        if not user or not user.is_active:
            continue
        setting = ReminderService.get_or_create_setting(db, todo.user_id)
        if not setting.is_enabled:
            continue
        title, message = ReminderService.get_reminder_message("todo", user.name, todo.text)
        ReminderService.dispatch_notifications(
            db, todo.user_id, setting, "todo", title, message, detail=todo.text
        )
        todo.reminded_at = datetime.now(BEIJING_TZ)
        fired += 1
    if fired:
        db.commit()
        logger.info("已触发 %s 条待办提醒", fired)
    return fired

