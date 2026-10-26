"""Server-owned slice deadlines and execution preferences."""
from datetime import datetime, timedelta
import json
import math

from app.models import User
from app.project_models import ExecutionPlan, WorkSession


def budget_seconds(row):
    return row.planned_seconds or (row.planned_minutes or 20) * 60


def is_handoff(row):
    return bool(row and json.loads(row.practice_snapshot_json or "{}").get("execution_handoff"))


def finish_with_remainder(db, row, now=None):
    """Close only the performed interval; retain a completed task's unused slice budget."""
    plan = execution_plan(db, row.user_id)
    if row.ended_at is None:
        end = min(now or datetime.utcnow(), row.started_at + timedelta(seconds=budget_seconds(row)))
        row.ended_at = max(end, row.started_at + timedelta(microseconds=1))
        remaining = max(0, budget_seconds(row) - math.ceil((row.ended_at - row.started_at).total_seconds()))
    elif plan.paused_session_id == row.id:
        remaining = plan.remaining_seconds or 0
    else:
        return
    if row.source == "timer" and row.kind == "work" and remaining:
        snapshot = json.loads(row.practice_snapshot_json or "{}")
        snapshot["execution_handoff"] = True
        row.practice_snapshot_json = json.dumps(snapshot, ensure_ascii=False)
        plan.paused_session_id, plan.remaining_seconds = row.id, remaining


def settle_expired(db, user_id, now=None):
    """Settle at server deadlines, automatically resting but never starting unattended work."""
    now = now or datetime.utcnow()
    def active():
        return db.query(WorkSession).filter(
            WorkSession.user_id == user_id, WorkSession.source == "timer", WorkSession.ended_at.is_(None)
        ).all()

    # Ordinary reads must not hold the per-user write lock until request cleanup.
    if not any(now >= row.started_at + timedelta(seconds=budget_seconds(row)) for row in active()):
        db.flush()
        return
    db.query(User).filter(User.id == user_id).with_for_update().first()
    # Another request may have settled the timer while this request waited.
    for row in active():
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
        db.query(User).filter(User.id == user_id).with_for_update().first()
        plan = db.get(ExecutionPlan, user_id)
    if plan is None:
        plan = ExecutionPlan(user_id=user_id, queue_json="[]", work_minutes=20, break_minutes=5)
        db.add(plan)
        db.flush()
    return plan
