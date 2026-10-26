"""Daily, account-level active-time aggregates for the owner dashboard."""
from datetime import date, datetime, time, timedelta
from math import floor
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import DailyAppUsage, User

BEIJING = ZoneInfo("Asia/Shanghai")
USAGE_RETENTION_DAYS = 90
MAX_PULSE_GAP_SECONDS = 45


def beijing_now() -> datetime:
    return datetime.now(BEIJING)


def _beijing_datetime(value: datetime) -> datetime:
    # SQLite drops timezone information for DateTime(timezone=True); those
    # values were written as Beijing wall time by this module.
    return value.replace(tzinfo=BEIJING) if value.tzinfo is None else value.astimezone(BEIJING)


def record_active_pulse(
    db: Session,
    user_id: int,
    now: datetime | None = None,
    *,
    reset_baseline: bool = False,
) -> None:
    """Count elapsed time between recent foreground activity pulses.

    A single per-user heartbeat timestamp makes simultaneous tabs/devices
    contribute the union of their active intervals instead of double-counting.
    Gaps over 45 seconds are treated as inactive or disconnected.
    """
    current = _beijing_datetime(now or beijing_now())
    current_day = current.date()
    # Serialize pulses for this account on PostgreSQL, including the first
    # pulse before its daily aggregate row exists.
    db.query(User.id).filter(User.id == user_id).with_for_update().first()
    latest = (
        db.query(DailyAppUsage)
        .filter(DailyAppUsage.user_id == user_id)
        .order_by(DailyAppUsage.usage_date.desc())
        .with_for_update()
        .first()
    )

    current_row = latest if latest and latest.usage_date == current_day else None
    if current_row is None:
        current_row = DailyAppUsage(user_id=user_id, usage_date=current_day, active_seconds=0)
        db.add(current_row)

    if latest and latest.last_pulse_at and not reset_baseline:
        previous = _beijing_datetime(latest.last_pulse_at)
        elapsed = (current - previous).total_seconds()
        if 0 < elapsed <= MAX_PULSE_GAP_SECONDS:
            seconds = floor(elapsed)
            if previous.date() == current_day:
                current_row.active_seconds = (current_row.active_seconds or 0) + seconds
            else:
                midnight = datetime.combine(current_day, time.min, tzinfo=BEIJING)
                previous_seconds = max(0, min(seconds, floor((midnight - previous).total_seconds())))
                latest.active_seconds = (latest.active_seconds or 0) + previous_seconds
                current_row.active_seconds = (current_row.active_seconds or 0) + (seconds - previous_seconds)

    current_row.last_pulse_at = current


def purge_expired_usage(db: Session, today: date | None = None) -> int:
    """Keep the latest 90 Beijing calendar days, including today."""
    current_day = today or beijing_now().date()
    cutoff = current_day - timedelta(days=USAGE_RETENTION_DAYS - 1)
    return (
        db.query(DailyAppUsage)
        .filter(DailyAppUsage.usage_date < cutoff)
        .delete(synchronize_session=False)
    )


def clear_stale_usage_pulses(db: Session, now: datetime | None = None) -> int:
    """Drop temporary pulse timestamps after a client has gone inactive."""
    cutoff = _beijing_datetime(now or beijing_now()) - timedelta(seconds=MAX_PULSE_GAP_SECONDS)
    return (
        db.query(DailyAppUsage)
        .filter(DailyAppUsage.last_pulse_at.is_not(None), DailyAppUsage.last_pulse_at < cutoff)
        .update({DailyAppUsage.last_pulse_at: None}, synchronize_session=False)
    )
