"""Daily project scopes are additive; legacy linked tasks retain their semantics."""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from app.database import Base
from app.models import DailyTask


class DailyProjectPlan(Base):
    __tablename__ = "daily_project_plans"
    daily_task_id = Column(Integer, ForeignKey("daily_tasks.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_date = Column(Date, nullable=False)
    # These IDs and names describe the source at planning time, including after a move/deletion.
    project_id = Column(Integer, nullable=False)
    stage_id = Column(Integer, nullable=False)
    project_title = Column(String(200), nullable=False)
    stage_title = Column(String(200), nullable=False)
    task_title = Column(String(500), nullable=False)
    source_estimate_minutes = Column(Integer, nullable=True)
    request_key = Column(String(80), nullable=False)
    item_key = Column(String(80), nullable=False)
    request_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "request_key", "item_key", name="uq_daily_project_plan_request"),)


def day_plan(db, user_id, daily_id):
    row = db.get(DailyProjectPlan, daily_id)
    return row if row and row.user_id == user_id else None


def legacy_daily_filter(user_id):
    """Exclude daily scopes from legacy project rename/acceptance propagation."""
    return ~DailyTask.id.in_(select(DailyProjectPlan.daily_task_id).where(DailyProjectPlan.user_id == user_id))


def require_scope_completion_ready(db, user_id, daily):
    from app.project_models import ProjectTask
    from app.start_conditions import require_ready
    source = db.get(ProjectTask, daily.project_task_id) if daily.project_task_id else None
    if source and source.user_id == user_id and source.deleted_at is None and source.state == "completed":
        return  # An accepted source may still have an unconfirmed daily result.
    require_ready(db, user_id, "daily", daily.id, purpose="start")
