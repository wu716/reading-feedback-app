"""Server-owned slice deadlines and execution preferences."""
from datetime import datetime, timedelta

from app.models import User
from app.project_models import ExecutionPlan, WorkSession


def budget_seconds(row):
    return row.planned_seconds or (row.planned_minutes or 20) * 60


def settle_expired(db, user_id, now=None):
    """Settle at server deadlines, automatically resting but never starting unattended work."""
    db.query(User).filter(User.id == user_id).with_for_update().first()
    now = now or datetime.utcnow()
    for row in db.query(WorkSession).filter(
        WorkSession.user_id == user_id, WorkSession.source == "timer", WorkSession.ended_at.is_(None)
    ).all():
        deadline = row.started_at + timedelta(seconds=budget_seconds(row))
        if now >= deadline:
            row.ended_at = deadline
            if row.kind == "work":
                plan = execution_plan(db, user_id)
                rest_end = deadline + timedelta(minutes=plan.break_minutes)
                db.add(WorkSession(
                    user_id=user_id, kind="break", source="timer", label="自动休息",
                    started_at=deadline, ended_at=rest_end if now >= rest_end else None,
                    planned_minutes=plan.break_minutes, planned_seconds=plan.break_minutes * 60,
                ))
                plan.paused_session_id = None
                plan.remaining_seconds = None
    db.flush()


def execution_plan(db, user_id):
    plan = db.get(ExecutionPlan, user_id)
    if plan is None:
        plan = ExecutionPlan(user_id=user_id, queue_json="[]", work_minutes=20, break_minutes=5)
        db.add(plan)
        db.flush()
    return plan
