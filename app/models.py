from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Date
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
    password_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # 软删除
    plan = Column(String(50), default="free")
    
    # 关系
    actions = relationship("Action", back_populates="user", cascade="all, delete-orphan")
    practice_logs = relationship("PracticeLog", back_populates="user", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    ai_advice_sessions = relationship("AIAdviceSession", back_populates="user", cascade="all, delete-orphan")


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
    target_frequency = Column(String(50), nullable=True)   # "daily", "weekly", "monthly", "custom"
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


class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan = Column(String(50), nullable=False)  # free, premium, pro
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="subscription")


class AnonymizedData(Base):
    """匿名化数据表，用于保留用户删除后的统计数据"""
    __tablename__ = "anonymized_data"
    
    id = Column(Integer, primary_key=True, index=True)
    original_user_id = Column(Integer, nullable=False)  # 原始用户ID（已删除）
    data_type = Column(String(50), nullable=False)  # action, practice_log, etc.
    anonymized_data = Column(Text, nullable=False)  # JSON 格式的匿名化数据
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    anonymized_at = Column(DateTime(timezone=True), server_default=func.now())


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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User")


class SelfTalkReminderLog(Base):
    """Self-talk 提醒日志表"""
    __tablename__ = "self_talk_reminder_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reminder_type = Column(String(50), nullable=False)  # "daily", "after_action", "inactive", "after_new_action"
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    action_taken = Column(Boolean, default=False)  # 用户是否响应提醒做了 self-talk
    notification_method = Column(String(20), nullable=True)  # "browser", "email", "both"
    
    # 关系
    user = relationship("User")