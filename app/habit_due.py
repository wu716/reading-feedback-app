# -*- coding: utf-8 -*-
"""日程页该提醒哪些行动：只看起止日期和频率，不打扰已排进日程的。"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional


WEEKEND = {5, 6}
REASON = {
    "daily": "每天",
    "weekly": "周末",
    "monthly": "本月",
    "quarterly": "本季度",
    "custom": "按间隔",
    "window": "这段时间",
    "open": "还未排进今天",
}


@dataclass
class Suggestion:
    action_id: int
    text: str
    frequency: str
    reason: str


def normalize_text(text: Optional[str]) -> str:
    return "".join((text or "").split()).casefold()


def as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def in_window(action, day: date) -> bool:
    start = as_date(getattr(action, "start_date", None))
    end = as_date(getattr(action, "end_date", None))
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


def window_bounds(action, fallback_day: date):
    start = as_date(getattr(action, "start_date", None)) or fallback_day
    end = as_date(getattr(action, "end_date", None)) or date(fallback_day.year + 50, 12, 31)
    return start, end


def parse_freq(action) -> str:
    raw = (
        getattr(action, "target_frequency", None)
        or getattr(action, "frequency", None)
        or "daily"
    )
    return str(raw).lower()


def action_type_of(action) -> str:
    return (getattr(action, "action_type", None) or "trigger").lower()


def week_bounds(day: date):
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def month_bounds(day: date):
    return date(day.year, day.month, 1), date(day.year, day.month, monthrange(day.year, day.month)[1])


def quarter_bounds(day: date):
    start_month = ((day.month - 1) // 3) * 3 + 1
    start = date(day.year, start_month, 1)
    end_month = start_month + 2
    return start, date(day.year, end_month, monthrange(day.year, end_month)[1])


def weekend_days(start: date, end: date) -> List[date]:
    if end < start:
        return []
    days = []
    cursor = start
    one = timedelta(days=1)
    while cursor <= end:
        if cursor.weekday() in WEEKEND:
            days.append(cursor)
        cursor += one
    return days


def first_and_last_weekend(start: date, end: date) -> set:
    days = weekend_days(start, end)
    if not days:
        return {end} if start <= end else set()
    due = set(days[:2])
    due.update(days[-2:])
    return due


def covers_action(task, action) -> bool:
    if getattr(task, "action_id", None) == getattr(action, "id", None):
        return True
    return normalize_text(getattr(task, "text", None)) == normalize_text(
        getattr(action, "action_text", None)
    )


def period_has_task(tasks: Iterable, action, start: date, end: date) -> bool:
    for task in tasks:
        task_day = as_date(getattr(task, "task_date", None))
        if not task_day or task_day < start or task_day > end:
            continue
        if covers_action(task, action):
            return True
    return False


def origin_date(action, day: date) -> date:
    start = as_date(getattr(action, "start_date", None))
    if start:
        return start
    created = as_date(getattr(action, "created_at", None))
    return created or day


def reason_for(freq: str, custom_days: Optional[int], window_only: bool) -> str:
    if window_only:
        return REASON["window"]
    if freq == "custom" and custom_days:
        return f"每{custom_days}天"
    return REASON.get(freq, REASON["daily"])


def is_candidate(action, day: date, scheduled) -> bool:
    if (getattr(action, "status", None) or "todo") == "done":
        return False
    if getattr(action, "deleted_at", None):
        return False
    if not in_window(action, day):
        return False
    if any(as_date(getattr(task, "task_date", None)) == day and covers_action(task, action) for task in scheduled):
        return False
    return True


def is_due(action, day: date, scheduled) -> bool:
    if not is_candidate(action, day, scheduled):
        return False

    kind = action_type_of(action)
    freq = parse_freq(action)
    win_start, win_end = window_bounds(action, day)

    if kind != "habit":
        # 情境型只在有截止日期时算「到期」：这段时间要做完。只有开始日不够。
        return bool(getattr(action, "end_date", None))

    if freq == "weekly":
        week_start, week_end = week_bounds(day)
        if period_has_task(scheduled, action, week_start, week_end):
            return False
        sat = week_start + timedelta(days=5)
        sun = week_start + timedelta(days=6)
        weekend_in_window = (in_window(action, sat) or in_window(action, sun))
        if weekend_in_window:
            return day.weekday() in WEEKEND
        return True

    if freq == "monthly":
        month_start, month_end = month_bounds(day)
        if period_has_task(scheduled, action, month_start, month_end):
            return False
        lo = max(win_start, month_start)
        hi = min(win_end, month_end)
        return day in first_and_last_weekend(lo, hi)

    if freq == "quarterly":
        q_start, q_end = quarter_bounds(day)
        if period_has_task(scheduled, action, q_start, q_end):
            return False
        lo = max(win_start, q_start)
        hi = min(win_end, q_end)
        return day in first_and_last_weekend(lo, hi)

    if freq == "custom":
        interval = int(getattr(action, "custom_frequency_days", None) or 0)
        if interval < 1:
            return True
        delta = (day - origin_date(action, day)).days
        return delta >= 0 and delta % interval == 0

    return True


def to_suggestion(action, frequency: str, reason: str) -> Optional[Suggestion]:
    text = (getattr(action, "action_text", None) or "").strip()
    if not text:
        return None
    return Suggestion(
        action_id=action.id,
        text=text,
        frequency=frequency,
        reason=reason,
    )


def is_filler(action, day: date, scheduled) -> bool:
    """没标成习惯、也没设结束日时，写日程仍提一句，避免页面空白。到期日之外的习惯不塞进来。"""
    if not is_candidate(action, day, scheduled):
        return False
    if is_due(action, day, scheduled):
        return False
    return action_type_of(action) != "habit"


def suggest_for_day(actions: Iterable, scheduled: Iterable, day: date) -> List[Suggestion]:
    due: List[Suggestion] = []
    extra: List[Suggestion] = []
    for action in actions:
        kind = action_type_of(action)
        freq = parse_freq(action)
        window_only = kind != "habit"
        if is_due(action, day, scheduled):
            item = to_suggestion(
                action,
                freq if not window_only else "window",
                reason_for(freq, getattr(action, "custom_frequency_days", None), window_only),
            )
            if item:
                due.append(item)
        elif is_filler(action, day, scheduled):
            item = to_suggestion(action, "open", REASON["open"])
            if item:
                extra.append(item)
    rank = {"daily": 0, "custom": 1, "weekly": 2, "monthly": 3, "quarterly": 4, "window": 5, "open": 6}
    due.sort(key=lambda item: (rank.get(item.frequency, 9), item.action_id))
    items = due[:]
    if len(items) < 3:
        items.extend(extra[: 12 - len(items)])
    return items[:12]
