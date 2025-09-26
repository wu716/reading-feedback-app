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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # 软删除
    
    # 关系
    user = relationship("User", back_populates="actions")
    practice_logs = relationship("PracticeLog", back_populates="action", cascade="all, delete-orphan")


class PracticeLog(Base):
    __tablename__ = "practice_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_id = Column(Integer, ForeignKey("actions.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    result = Column(String(20), nullable=False)  # success, fail, skipped
    notes = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)  # 1-5 评分
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
