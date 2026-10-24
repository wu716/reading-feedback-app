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
    purpose = Column(String(20), nullable=False, default="delivery")
    not_applicable_reason = Column(Text, nullable=True)


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
    practice_snapshot_json = Column(Text, nullable=True)
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


class TaskPractice(Base):
    """One learning identity per real task, never per scheduled appearance."""
    __tablename__ = "task_practices"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    owner_kind = Column(String(20), nullable=False)
    owner_id = Column(Integer, nullable=False)
    original_estimate = Column(Integer, nullable=True)
    estimate_origin = Column(String(20), nullable=True)
    difficulty = Column(String(20), nullable=True)
    importance = Column(String(20), nullable=True)
    initial_importance = Column(String(20), nullable=True)
    initial_marked_at = Column(DateTime, nullable=True)
    goal_snapshot = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    rehearsal_json = Column(Text, nullable=False, default="{}")
    __table_args__ = (UniqueConstraint("user_id", "owner_kind", "owner_id", name="uq_task_practice_owner"),)


class PracticeEvent(Base):
    """Append-only estimates, judgements, feedback, feasibility and reflections."""
    __tablename__ = "practice_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    owner_kind = Column(String(20), nullable=False)
    owner_id = Column(Integer, nullable=False)
    event_type = Column(String(40), nullable=False)
    record_date = Column(Date, nullable=False)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (Index("ix_practice_event_owner", "user_id", "owner_kind", "owner_id", "event_type"),)


class PlanningCycle(Base):
    __tablename__ = "planning_cycles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    horizon = Column(String(20), nullable=False)
    expected_result = Column(Text, nullable=False)
    available_minutes = Column(Integer, nullable=True)
    plan_json = Column(Text, nullable=False)
    review_json = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    previous_cycle_id = Column(Integer, ForeignKey("planning_cycles.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class StageCommitmentDraft(Base):
    """Server-saved, unconfirmed writing; never implicitly promoted by starting work."""
    __tablename__ = "stage_commitment_drafts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    stage_id = Column(Integer, ForeignKey("project_stages.id"), nullable=False, unique=True)
    statement = Column(Text, nullable=False, default="")
    revision = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class StageCommitment(Base):
    __tablename__ = "stage_commitments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    stage_id = Column(Integer, ForeignKey("project_stages.id"), nullable=False, index=True)
    snapshot_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CommitmentAdjustment(Base):
    __tablename__ = "commitment_adjustments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    stage_id = Column(Integer, ForeignKey("project_stages.id"), nullable=False)
    plan_json = Column(Text, nullable=False)
    impact_json = Column(Text, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    elapsed_ms = Column(Integer, nullable=False, default=0)
    lease_token = Column(String(100), nullable=True)
    last_visible_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackOccurrence(Base):
    """A dated delivery obligation. Its requirement is an immutable plan snapshot."""
    __tablename__ = "feedback_occurrences"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey("planning_cycles.id"), nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    deadline = Column(String(5), nullable=False, default="21:00")
    remind_at = Column(String(5), nullable=False, default="20:00")
    reminders_enabled = Column(Boolean, nullable=False, default=False)
    requirement_json = Column(Text, nullable=False)
    skipped_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("cycle_id", "due_date", name="uq_feedback_cycle_date"),)


class FeedbackSubmission(Base):
    __tablename__ = "feedback_submissions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    occurrence_id = Column(Integer, ForeignKey("feedback_occurrences.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    content_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="submitted")
    review_note = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("occurrence_id", "version", name="uq_feedback_submission_version"),)


class FeedbackAttachment(Base):
    __tablename__ = "feedback_attachments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(250), nullable=False)
    storage_key = Column(String(80), nullable=False, unique=True)
    size = Column(Integer, nullable=False)
    content_type = Column(String(120), nullable=False)
    submission_id = Column(Integer, ForeignKey("feedback_submissions.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class FeedbackReport(Base):
    __tablename__ = "feedback_reports"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    period = Column(String(10), nullable=False)
    anchor = Column(Date, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    digest = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "period", "anchor", "revision", name="uq_feedback_report_revision"),)


class FeedbackDelivery(Base):
    """Durable email outbox; in-app / native delivery uses the existing reminder log."""
    __tablename__ = "feedback_deliveries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_key = Column(String(160), nullable=False, unique=True)
    occurrence_id = Column(Integer, ForeignKey("feedback_occurrences.id"), nullable=True)
    log_id = Column(Integer, ForeignKey("self_talk_reminder_logs.id"), nullable=True)
    title = Column(String(250), nullable=False)
    message = Column(Text, nullable=False)
    email_status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    last_error = Column(String(300), nullable=True)


class ReaderPairing(Base):
    __tablename__ = "reader_pairings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    remote_request_id = Column(String(100), nullable=False)
    receiver_subject = Column(String(100), nullable=False)
    nonce_cipher = Column(Text, nullable=True)
    source_instance_id = Column(String(100), nullable=False)
    preview_json = Column(Text, nullable=True)


class ReaderReceiverAccount(Base):
    __tablename__ = "reader_receiver_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    subject = Column(String(100), nullable=False, unique=True)


class ReaderBinding(Base):
    __tablename__ = "reader_bindings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_instance_id = Column(String(100), nullable=False)
    source_user_id = Column(String(200), nullable=False)
    source_label = Column(String(200), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    detail_started_on = Column(Date, nullable=True)
    baseline_json = Column(Text, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    credential_cipher = Column(Text, nullable=True)
    remote_grant_id = Column(String(100), nullable=True)
    receiver_subject = Column(String(100), nullable=True)
    authorized_from = Column(Date, nullable=True)
    cursor = Column(Text, nullable=True)
    high_watermark = Column(Integer, nullable=False, default=0)
    sync_status = Column(String(30), nullable=False, default="pending")
    sync_error = Column(String(300), nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("source_instance_id", "source_user_id", name="uq_reader_source_account"),)


class ReaderReadingDay(Base):
    __tablename__ = "reader_reading_days"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    binding_id = Column(Integer, ForeignKey("reader_bindings.id"), nullable=False)
    record_date = Column(Date, nullable=False)
    revision = Column(Integer, nullable=False)
    digest = Column(String(64), nullable=False)
    books_json = Column(Text, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("binding_id", "record_date", name="uq_reader_binding_date"),)
