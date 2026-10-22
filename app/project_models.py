"""Project and time tracking tables. Legacy rows are kept in their original tables."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class Goal(Base):
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    horizon_end = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=False)
    outcome = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    # NULL means a legacy project whose formal start was never recorded.
    execution_state = Column(String(20), nullable=True)
    started_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class ProjectStage(Base):
    __tablename__ = "project_stages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    state = Column(String(20), nullable=False, default="next")
    closed_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)


class ProjectTask(Base):
    __tablename__ = "project_tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    stage_id = Column(Integer, ForeignKey("project_stages.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    state = Column(String(20), nullable=False, default="todo")
    familiarity = Column(String(20), nullable=True)
    execution_role = Column(String(20), nullable=False, default="formal")
    original_estimate_minutes = Column(Integer, nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    goal_reason = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    rehearsal_note = Column(Text, nullable=True)
    steps_json = Column(Text, nullable=False, default="[]")
    blocker_note = Column(Text, nullable=True)
    outcome_note = Column(Text, nullable=True)
    variance_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("original_estimate_minutes IS NULL OR original_estimate_minutes >= 0", name="ck_project_task_initial_estimate"),
        CheckConstraint("estimated_minutes IS NULL OR estimated_minutes >= 0", name="ck_project_task_estimate"),
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="RESTRICT"), nullable=False)
    prerequisite_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (
        UniqueConstraint("task_id", "prerequisite_id", name="uq_task_dependency"),
        CheckConstraint("task_id <> prerequisite_id", name="ck_task_dependency_not_self"),
    )


class TaskChecklistItem(Base):
    __tablename__ = "task_checklist_items"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    text = Column(String(500), nullable=False)
    done = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)


class WorkSession(Base):
    __tablename__ = "work_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_task_id = Column(Integer, ForeignKey("project_tasks.id", ondelete="RESTRICT"), nullable=True, index=True)
    daily_task_id = Column(Integer, ForeignKey("daily_tasks.id", ondelete="SET NULL"), nullable=True)
    time_log_node_id = Column(Integer, ForeignKey("time_log_nodes.id", ondelete="SET NULL"), nullable=True)
    label = Column(String(500), nullable=True)
    kind = Column(String(20), nullable=False, default="work")
    source = Column(String(20), nullable=False, default="timer")
    # UTC stored without offset; API accepts offset-aware inputs and emits Z.
    started_at = Column(DateTime(timezone=False), nullable=False)
    ended_at = Column(DateTime(timezone=False), nullable=True)
    planned_minutes = Column(Integer, nullable=True)
    planned_seconds = Column(Integer, nullable=True)
    correction_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="ck_work_session_interval"),
        Index("ix_work_session_user_start", "user_id", "started_at"),
    )


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    queue_json = Column(Text, nullable=False, default="[]")
    work_minutes = Column(Integer, nullable=False, default=20)
    break_minutes = Column(Integer, nullable=False, default=5)
    paused_session_id = Column(Integer, ForeignKey("work_sessions.id"), nullable=True)
    remaining_seconds = Column(Integer, nullable=True)


class TimeActivityAssessment(Base):
    __tablename__ = "time_activity_assessments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    work_session_id = Column(Integer, ForeignKey("work_sessions.id", ondelete="RESTRICT"), nullable=False, unique=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="SET NULL"), nullable=True)
    goal_title_snapshot = Column(String(200), nullable=True)
    importance = Column(String(20), nullable=True)
    interesting = Column(Boolean, nullable=True)
    note = Column(Text, nullable=True)
    assessed_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("importance IS NULL OR importance IN ('unimportant', 'ordinary', 'important')", name="ck_activity_importance"),)


class ProcessTemplate(Base):
    __tablename__ = "process_templates"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    steps_json = Column(Text, nullable=False, default="[]")
    checklist_json = Column(Text, nullable=False, default="[]")
    common_problems = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class StartCondition(Base):
    """Explicit conditions; polymorphic references are validated by the service."""
    __tablename__ = "start_conditions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_kind = Column(String(20), nullable=False)
    owner_id = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    kind = Column(String(20), nullable=False)
    strength = Column(String(20), nullable=False, default="required")
    check_at = Column(String(20), nullable=False, default="start")
    target_kind = Column(String(20), nullable=True)
    target_id = Column(Integer, nullable=True)
    required_state = Column(String(20), nullable=True)
    not_before = Column(DateTime(timezone=False), nullable=True)
    confirmation = Column(String(20), nullable=False, default="unknown")
    evidence = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    removed_at = Column(DateTime(timezone=False), nullable=True)
    __table_args__ = (
        Index("ix_start_condition_owner", "user_id", "owner_kind", "owner_id"),
        CheckConstraint("owner_kind IN ('project', 'task', 'daily')", name="ck_condition_owner_kind"),
        CheckConstraint("strength IN ('required', 'reminder')", name="ck_condition_strength"),
    )


class ExecutionConditionEvent(Base):
    """Append-only condition, dependency, and project lifecycle history."""
    __tablename__ = "execution_condition_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_kind = Column(String(20), nullable=False)
    owner_id = Column(Integer, nullable=False)
    condition_id = Column(Integer, ForeignKey("start_conditions.id", ondelete="RESTRICT"), nullable=True)
    action = Column(String(40), nullable=False)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    __table_args__ = (Index("ix_condition_event_owner", "user_id", "owner_kind", "owner_id"),)
