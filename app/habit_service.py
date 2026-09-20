# -*- coding: utf-8 -*-
"""Shared habit-program operations used by schedule, practice, and Capture."""
from datetime import date, datetime, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import HabitEvent, HabitProgram


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
OUTCOME_RANK = {"missed": 0, "partial": 1, "completed": 2}


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def beijing_today() -> date:
    return beijing_now().date()


def get_active_program(db: Session, user_id: int) -> Optional[HabitProgram]:
    return (
        db.query(HabitProgram)
        .filter(
            HabitProgram.user_id == user_id,
            HabitProgram.status == "active",
            HabitProgram.deleted_at.is_(None),
        )
        .order_by(HabitProgram.id.desc())
        .first()
    )


def get_active_program_for_action(
    db: Session,
    user_id: int,
    action_id: Optional[int],
) -> Optional[HabitProgram]:
    if not action_id:
        return None
    return (
        db.query(HabitProgram)
        .filter(
            HabitProgram.user_id == user_id,
            HabitProgram.action_id == action_id,
            HabitProgram.status == "active",
            HabitProgram.deleted_at.is_(None),
        )
        .order_by(HabitProgram.id.desc())
        .first()
    )


def _source_event(
    db: Session,
    program_id: int,
    source_kind: str,
    source_id: int,
) -> Optional[HabitEvent]:
    return (
        db.query(HabitEvent)
        .filter(
            HabitEvent.habit_program_id == program_id,
            HabitEvent.source_kind == source_kind,
            HabitEvent.source_id == source_id,
        )
        .order_by(HabitEvent.id.desc())
        .first()
    )


def add_capture_signal(
    db: Session,
    program: HabitProgram,
    source_kind: str,
    source_id: int,
    event_date: date,
) -> HabitEvent:
    event = _source_event(db, program.id, source_kind, source_id)
    if event:
        event.deleted_at = None
        event.event_date = event_date
        event.event_type = "signal"
        event.outcome = None
        return event
    event = HabitEvent(
        user_id=program.user_id,
        habit_program_id=program.id,
        event_date=event_date,
        event_type="signal",
        source_kind=source_kind,
        source_id=source_id,
    )
    db.add(event)
    return event


def sync_schedule_event(db: Session, user_id: int, task, completed: bool) -> None:
    program = get_active_program_for_action(db, user_id, getattr(task, "action_id", None))
    if not program:
        return
    event = _source_event(db, program.id, "daily_task", task.id)
    if not completed:
        if event:
            event.deleted_at = beijing_now()
        return
    if not event:
        event = HabitEvent(
            user_id=user_id,
            habit_program_id=program.id,
            source_kind="daily_task",
            source_id=task.id,
        )
        db.add(event)
    event.deleted_at = None
    event.event_date = task.task_date
    event.event_type = "execution"
    event.outcome = "completed"


def sync_practice_event(db: Session, user_id: int, practice_log) -> None:
    program = get_active_program_for_action(db, user_id, getattr(practice_log, "action_id", None))
    if not program or not getattr(practice_log, "id", None):
        return
    event = _source_event(db, program.id, "practice", practice_log.id)
    if getattr(practice_log, "deleted_at", None):
        if event:
            event.deleted_at = beijing_now()
        return
    if not event:
        event = HabitEvent(
            user_id=user_id,
            habit_program_id=program.id,
            source_kind="practice",
            source_id=practice_log.id,
        )
        db.add(event)
    result = str(getattr(practice_log, "result", "") or "")
    event.deleted_at = None
    event.event_date = practice_log.date
    event.event_type = "practice"
    event.outcome = {
        "success": "completed",
        "partial": "partial",
        "fail": "missed",
        "skipped": "missed",
    }.get(result, "missed")
    event.note = getattr(practice_log, "notes", None)


def summarize_events(
    events: Iterable[HabitEvent],
    target_days: int,
    today: Optional[date] = None,
    days: int = 7,
) -> dict:
    """Summarize distinct behavior days so duplicate sources never inflate progress."""
    end = today or beijing_today()
    start = end - timedelta(days=max(1, days) - 1)
    outcomes = {}
    efforts = []
    urges = []
    signal_count = 0

    for event in events:
        if getattr(event, "deleted_at", None):
            continue
        event_day = getattr(event, "event_date", None)
        if not event_day or event_day < start or event_day > end:
            continue
        if getattr(event, "event_type", None) == "signal":
            signal_count += 1
            continue
        outcome = getattr(event, "outcome", None)
        if outcome in OUTCOME_RANK:
            previous = outcomes.get(event_day)
            if previous is None or OUTCOME_RANK[outcome] > OUTCOME_RANK[previous]:
                outcomes[event_day] = outcome
        effort = getattr(event, "effort", None)
        urge = getattr(event, "urge", None)
        if effort is not None:
            efforts.append(int(effort))
        if urge is not None:
            urges.append(int(urge))

    def average(values):
        return round(sum(values) / len(values), 1) if values else None

    return {
        "period_start": start,
        "period_end": end,
        "target_days": max(1, min(7, int(target_days or 1))),
        "completed_days": sum(1 for value in outcomes.values() if value == "completed"),
        "partial_days": sum(1 for value in outcomes.values() if value == "partial"),
        "missed_days": sum(1 for value in outcomes.values() if value == "missed"),
        "signal_count": signal_count,
        "average_effort": average(efforts),
        "average_urge": average(urges),
        "today_outcome": outcomes.get(end),
    }
