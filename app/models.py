from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, date
import uuid

from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    real_name = Column(String(100), nullable=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    phone_verified = Column(Boolean, default=False)
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # 软删除
    plan = Column(String(50), default="free")
    plan_expires_at = Column(Date, nullable=True)
    token_version = Column(Integer, default=0)
    capture_kind = Column(String(20), nullable=False, default="moment")
    
    # 关系
    actions = relationship("Action", back_populates="user", cascade="all, delete-orphan")
    practice_logs = relationship("PracticeLog", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    ai_advice_sessions = relationship("AIAdviceSession", back_populates="user", cascade="all, delete-orphan")
    daily_todos = relationship("DailyTodo", back_populates="user", cascade="all, delete-orphan")
    daily_tasks = relationship("DailyTask", back_populates="user", cascade="all, delete-orphan")
    daily_schedules = relationship("DailySchedule", back_populates="user", cascade="all, delete-orphan")
    future_actions = relationship("FutureAction", back_populates="user", cascade="all, delete-orphan")
    ideas = relationship("Idea", back_populates="user", cascade="all, delete-orphan")
    time_log_nodes = relationship(
        "TimeLogNode",
        back_populates="user",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    reading_entries = relationship("ReadingEntry", back_populates="user", cascade="all, delete-orphan")
    self_talk_playback_logs = relationship(
        "SelfTalkPlaybackLog", back_populates="user", cascade="all, delete-orphan"
    )
    habit_programs = relationship("HabitProgram", back_populates="user", cascade="all, delete-orphan")
    habit_events = relationship("HabitEvent", back_populates="user", cascade="all, delete-orphan")
    used_invite_codes = relationship("InviteCode", back_populates="used_by_user")


class AuthCode(Base):
    """绑定邮箱和重置密码使用的一次性验证码。"""
    __tablename__ = "auth_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    purpose = Column(String(30), nullable=False, index=True)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Action(Base):
    __tablename__ = "actions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_title = Column(String(255), nullable=False)
    source_excerpt = Column(Text, nullable=False)
    action_text = Column(Text, nullable=False)
    tags = Column(Text, default="[]")  # JSON 字符串存储标签
    frequency = Column(String(50), default="daily")  # daily, weekly, monthly
    status = Column(String(20), default="todo")  # todo, in_progress, done
    action_type = Column(String(20), default="trigger")  # trigger（情境触发型）, habit（习惯养成型）
    
    # 新增时间管理字段（可选，用于向后兼容）
    duration_type = Column(String(20), nullable=True, default="short_term")  # "short_term", "long_term", "lifetime"
    target_duration_days = Column(Integer, nullable=True)  # 目标持续天数（短期/长期）
    target_frequency = Column(String(50), nullable=True)   # "daily", "weekly", "monthly", "quarterly", "custom"
    custom_frequency_days = Column(Integer, nullable=True) # 自定义频率（每X天一次）
    start_date = Column(Date, nullable=True)               # 行动开始日期
    end_date = Column(Date, nullable=True)                 # 行动结束日期（如果有）
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # 软删除
    
    # 关系
    user = relationship("User", back_populates="actions")
    practice_logs = relationship("PracticeLog", back_populates="action", cascade="all, delete-orphan")
    self_talks = relationship("SelfTalk", back_populates="action")
    ai_advice_sessions = relationship("AIAdviceSession", back_populates="action")
    habit_programs = relationship("HabitProgram", back_populates="action")


class PracticeLog(Base):
    __tablename__ = "practice_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_id = Column(Integer, ForeignKey("actions.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    result = Column(String(20), nullable=False)  # success, fail, skipped
    notes = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)  # 1-5 评分
    attempt_number = Column(Integer, nullable=True)  # 情境型行动的尝试次数
    success_score = Column(Integer, nullable=True)  # 成功分数
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # 软删除
    
    # 关系
    user = relationship("User", back_populates="practice_logs")
    action = relationship("Action", back_populates="practice_logs")


class HabitProgram(Base):
    """A focused behavior-change experiment. Only one is active per user."""
    __tablename__ = "habit_programs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action_id = Column(Integer, ForeignKey("actions.id", ondelete="SET NULL"), nullable=True, index=True)
    mode = Column(String(20), nullable=False, default="build")  # build, break
    title = Column(String(120), nullable=False)
    anchor_text = Column(Text, nullable=False)
    minimum_action = Column(Text, nullable=True)
    replacement_action = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    target_days_per_week = Column(Integer, nullable=False, default=5)
    status = Column(String(20), nullable=False, default="active")  # active, paused, completed
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="habit_programs")
    action = relationship("Action", back_populates="habit_programs")
    events = relationship("HabitEvent", back_populates="program", cascade="all, delete-orphan")


class HabitEvent(Base):
    """Append-only evidence from check-ins, schedules, practice, or Capture."""
    __tablename__ = "habit_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    habit_program_id = Column(
        Integer,
        ForeignKey("habit_programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_date = Column(Date, nullable=False, index=True)
    event_type = Column(String(30), nullable=False)  # check_in, execution, practice, signal
    outcome = Column(String(20), nullable=True)  # completed, partial, missed
    effort = Column(Integer, nullable=True)
    urge = Column(Integer, nullable=True)
    barrier = Column(String(120), nullable=True)
    note = Column(Text, nullable=True)
    source_kind = Column(String(30), nullable=True)
    source_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="habit_events")
    program = relationship("HabitProgram", back_populates="events")


class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan = Column(String(50), nullable=False)  # free, monthly, semester
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="subscription")


class InviteCode(Base):
    """一次性四位邀请码。"""
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(4), unique=True, index=True, nullable=False)
    plan = Column(String(50), nullable=False, default="free")
    note = Column(String(100), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    used_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    used_by_user = relationship("User", back_populates="used_invite_codes")


class AnonymizedData(Base):
    """匿名化数据表，用于保留用户删除后的统计数据"""
    __tablename__ = "anonymized_data"
    
    id = Column(Integer, primary_key=True, index=True)
    original_user_id = Column(Integer, nullable=False)  # 原始用户ID（已删除）
    data_type = Column(String(50), nullable=False)  # action, practice_log, etc.
    anonymized_data = Column(Text, nullable=False)  # JSON 格式的匿名化数据
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    anonymized_at = Column(DateTime(timezone=True), server_default=func.now())


class DailyTodo(Base):
    """用户每日待办"""
    __tablename__ = "daily_todos"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    completed = Column(Boolean, default=False)
    todo_date = Column(Date, nullable=False, index=True)
    remind_time = Column(String(8), nullable=True)
    reminded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="daily_todos")


class DailyTask(Base):
    """每日行动：清单底稿，也可进入流程设计。"""
    __tablename__ = "daily_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("daily_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    task_date = Column(Date, nullable=False, index=True)
    text = Column(Text, nullable=False)
    completed = Column(Boolean, default=False)
    note = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    priority = Column(Integer, nullable=False, default=0)  # 0普通，1重要，2最高
    flow_order = Column(Integer, nullable=False, default=0)  # 跨父任务的执行阶段顺序
    familiarity = Column(String(20), nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    parallel_group = Column(Integer, nullable=True)
    action_id = Column(Integer, ForeignKey("actions.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="daily_tasks")
    parent = relationship("DailyTask", remote_side=[id], backref="children")


class DailySchedule(Base):
    """某日是否已走出当日流程。"""
    __tablename__ = "daily_schedules"
    __table_args__ = (
        UniqueConstraint("user_id", "schedule_date", name="uq_daily_schedule_user_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    schedule_date = Column(Date, nullable=False, index=True)
    designed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="daily_schedules")


class FutureAction(Base):
    """还没规划、但想做的行动。不进当天日程，也不提醒。"""
    __tablename__ = "future_actions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="future_actions")


class Idea(Base):
    """突然记下的灵感。不进时刻，也不进待办。"""
    __tablename__ = "ideas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="ideas")


class TimeLogNode(Base):
    """时间节点：点击记下此刻，并填写上一段做了什么。"""
    __tablename__ = "time_log_nodes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    log_date = Column(Date, nullable=False, index=True)
    logged_at = Column(DateTime(timezone=True), nullable=False)
    label = Column(Text, nullable=True)
    duration_seconds = Column(Integer, default=0)
    task_id = Column(Integer, ForeignKey("daily_tasks.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="time_log_nodes")


class ReadingEntry(Base):
    """阅读记录（内容、笔记、时长）"""
    __tablename__ = "reading_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    reflection = Column(Text, nullable=True)
    duration_minutes = Column(Integer, default=0)
    entry_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="reading_entries")


class SelfTalkPlaybackLog(Base):
    """Self-talk 播放记录"""
    __tablename__ = "self_talk_playback_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    self_talk_id = Column(Integer, ForeignKey("self_talks.id", ondelete="CASCADE"), nullable=False)
    play_date = Column(Date, nullable=False, index=True)
    duration_seconds = Column(Integer, default=0)
    loops_completed = Column(Integer, default=1)
    loop_mode = Column(String(20), default="once")
    loop_target = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="self_talk_playback_logs")
    self_talk = relationship("SelfTalk", back_populates="playback_logs")


class SelfTalk(Base):
    """Self-talk 模块数据表"""
    __tablename__ = "self_talks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_id = Column(Integer, ForeignKey("actions.id"), nullable=True)  # 可选，关联读书行动项
    audio_path = Column(Text, nullable=False)  # 本地音频文件路径
    transcript = Column(Text, nullable=True)  # 转写文字
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # 软删除
    
    # 关系
    user = relationship("User")
    action = relationship("Action")
    playback_logs = relationship("SelfTalkPlaybackLog", back_populates="self_talk")


class AIAdviceSession(Base):
    """AI建议会话表"""
    __tablename__ = "ai_advice_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_id = Column(Integer, ForeignKey("actions.id", ondelete="CASCADE"), nullable=False)
    model_type = Column(String(20), default="deepseek-chat")
    web_search_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关系
    user = relationship("User", back_populates="ai_advice_sessions")
    action = relationship("Action", back_populates="ai_advice_sessions")
    messages = relationship("AIAdviceMessage", back_populates="session", cascade="all, delete-orphan")


class AIAdviceMessage(Base):
    """AI建议消息表"""
    __tablename__ = "ai_advice_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("ai_advice_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    thinking_process = Column(Text, nullable=True)
    web_search_results = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)
    model_used = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关系
    session = relationship("AIAdviceSession", back_populates="messages")


class SelfTalkReminderSetting(Base):
    """Self-talk 提醒设置表"""
    __tablename__ = "self_talk_reminder_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    is_enabled = Column(Boolean, default=True)
    
    # 时间型提醒
    daily_reminder_enabled = Column(Boolean, default=False)
    daily_reminder_time = Column(String(8), nullable=True)  # "20:00:00" 格式
    reminder_days = Column(Text, default="[0,1,2,3,4,5,6]")  # JSON: 周日到周六 [0-6]
    
    # 行为触发型提醒
    after_action_reminder = Column(Boolean, default=True)  # 完成行动后提醒
    after_new_action_reminder = Column(Boolean, default=True)  # 添加新行动后提醒
    inactive_days_threshold = Column(Integer, default=3)  # 多少天未记录时提醒
    
    # 通知方式
    browser_notification = Column(Boolean, default=True)
    email_notification = Column(Boolean, default=True)

    reading_reminder_enabled = Column(Boolean, default=False)
    reading_reminder_time = Column(String(8), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User")


class SelfTalkReminderLog(Base):
    """Self-talk 提醒日志表"""
    __tablename__ = "self_talk_reminder_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reminder_type = Column(String(50), nullable=False)  # "daily", "after_action", "inactive", "after_new_action", "todo"
    detail = Column(Text, nullable=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    action_taken = Column(Boolean, default=False)  # 用户是否响应提醒做了 self-talk
    notification_method = Column(String(20), nullable=True)  # "browser", "email", "both"
    
    # 关系
    user = relationship("User")


class AiCallLog(Base):
    """用户每日 AI 调用记录，用于额度控制"""
    __tablename__ = "ai_call_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(50), nullable=False, default="generic")
    call_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """登录、开通、导出等操作记录。"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    actor_user_id = Column(Integer, nullable=True, index=True)
    target_user_id = Column(Integer, nullable=True)
    ip = Column(String(64), nullable=True)
    detail = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
