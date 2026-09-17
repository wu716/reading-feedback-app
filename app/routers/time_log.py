# -*- coding: utf-8 -*-
"""时间日志：点击时间节点，记录上一段做了什么。"""
from datetime import date, datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import DailyTask, TimeLogNode, User

router = APIRouter(prefix="/time-log", tags=["时间日志"])
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_today() -> date:
    return datetime.now(BEIJING_TZ).date()


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def parse_day(value: Optional[date]) -> date:
    return value or beijing_today()


class NodeCreate(BaseModel):
    label: Optional[str] = Field(None, max_length=500)
    task_id: Optional[int] = None
    log_date: Optional[date] = None
    logged_at: Optional[datetime] = None

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class NodeUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=500)
    task_id: Optional[int] = None
    clear_task: bool = False

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()


class NodeOut(BaseModel):
    id: int
    log_date: date
    logged_at: datetime
    label: Optional[str] = None
    duration_seconds: int
    task_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class DayLogOut(BaseModel):
    date: date
    total_seconds: int
    nodes: List[NodeOut]


class DaySummary(BaseModel):
    date: date
    count: int


class RecentDaysOut(BaseModel):
    days: List[DaySummary]


def is_written_node(node: TimeLogNode) -> bool:
    """没写下内容、也没关联行动的节点不进入每日日志。"""
    return bool((node.label or "").strip()) or node.task_id is not None


def calendar_day(value: datetime) -> date:
    return ensure_aware(value).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=BEIJING_TZ)
    return start, start + timedelta(days=1)


def belongs_to_day(node: TimeLogNode, day: date) -> bool:
    """log_date 写错时，仍按北京时间的 logged_at 认到当天，避免看起来像被删。"""
    if node.log_date == day:
        return True
    if node.logged_at is None:
        return False
    return calendar_day(node.logged_at) == day


def live_nodes(db: Session, user_id: int, day: date) -> List[TimeLogNode]:
    start, end = day_bounds(day)
    return (
        db.query(TimeLogNode)
        .filter(
            TimeLogNode.user_id == user_id,
            TimeLogNode.deleted_at.is_(None),
            or_(
                TimeLogNode.log_date == day,
                and_(TimeLogNode.logged_at >= start, TimeLogNode.logged_at < end),
            ),
        )
        .order_by(TimeLogNode.logged_at.asc(), TimeLogNode.id.asc())
        .all()
    )


def visible_nodes(db: Session, user_id: int, day: date) -> List[TimeLogNode]:
    return [node for node in live_nodes(db, user_id, day) if is_written_node(node)]


def get_node_or_404(db: Session, user_id: int, node_id: int) -> TimeLogNode:
    node = (
        db.query(TimeLogNode)
        .filter(
            TimeLogNode.id == node_id,
            TimeLogNode.user_id == user_id,
            TimeLogNode.deleted_at.is_(None),
        )
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="时间节点不存在")
    return node


def resolve_task_id(db: Session, user_id: int, task_id: Optional[int], day: date) -> Optional[int]:
    if task_id is None:
        return None
    task = (
        db.query(DailyTask)
        .filter(
            DailyTask.id == task_id,
            DailyTask.user_id == user_id,
            DailyTask.deleted_at.is_(None),
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="行动不存在")
    if task.task_date != day:
        raise HTTPException(status_code=400, detail="只能关联当天的行动")
    return task.id


def day_payload(db: Session, user: User, day: date) -> DayLogOut:
    nodes = visible_nodes(db, user.id, day)
    return DayLogOut(
        date=day,
        total_seconds=sum(n.duration_seconds or 0 for n in nodes),
        nodes=nodes,
    )


def ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def resolve_logged_at(value: Optional[datetime], now: datetime) -> datetime:
    if value is None:
        return now
    at = ensure_aware(value)
    if at > now:
        return now
    return at


def soft_delete_node(node: TimeLogNode) -> None:
    """用户数据只标记删除，不从数据库抹掉。"""
    if node.deleted_at is None:
        node.deleted_at = beijing_now()


def purge_unwritten_drafts(db: Session, user_id: int, day: date) -> None:
    for draft in live_nodes(db, user_id, day):
        if is_written_node(draft):
            continue
        soft_delete_node(draft)
    db.flush()


def recompute_day_durations(db: Session, user_id: int, day: date) -> None:
    """删除中间节点后，按剩余节点重算每段时长，让合计仍连续。"""
    previous = None
    for node in visible_nodes(db, user_id, day):
        if previous is None:
            node.duration_seconds = 0
        else:
            delta = ensure_aware(node.logged_at) - ensure_aware(previous.logged_at)
            node.duration_seconds = max(0, int(delta.total_seconds()))
        previous = node
    db.flush()


def remove_node(db: Session, node: TimeLogNode, user_id: int) -> date:
    day = node.log_date
    soft_delete_node(node)
    db.flush()
    recompute_day_durations(db, user_id, day)
    return day


@router.get("/recent-days", response_model=RecentDaysOut)
async def list_recent_days(
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    start_day = beijing_today() - timedelta(days=days - 1)
    start_at, _ = day_bounds(start_day)
    rows = (
        db.query(TimeLogNode)
        .filter(
            TimeLogNode.user_id == current_user.id,
            TimeLogNode.deleted_at.is_(None),
            or_(TimeLogNode.log_date >= start_day, TimeLogNode.logged_at >= start_at),
        )
        .all()
    )
    counts: dict[date, int] = {}
    for node in rows:
        if not is_written_node(node):
            continue
        seen = {node.log_date}
        if node.logged_at is not None:
            seen.add(calendar_day(node.logged_at))
        for day in seen:
            if day >= start_day:
                counts[day] = counts.get(day, 0) + 1
    return RecentDaysOut(
        days=[DaySummary(date=day, count=counts[day]) for day in sorted(counts, reverse=True)]
    )


@router.get("", response_model=DayLogOut)
async def get_day_log(
    log_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return day_payload(db, current_user, parse_day(log_date))


@router.post("/nodes", response_model=NodeOut)
async def punch_node(
    body: NodeCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    now = beijing_now()
    stamped = resolve_logged_at(body.logged_at, now)
    day = parse_day(body.log_date) if body.log_date else calendar_day(stamped)
    purge_unwritten_drafts(db, current_user.id, day)
    last = visible_nodes(db, current_user.id, day)
    previous = last[-1] if last else None
    duration = 0
    if previous:
        delta = stamped - ensure_aware(previous.logged_at)
        duration = max(0, int(delta.total_seconds()))
    node = TimeLogNode(
        user_id=current_user.id,
        log_date=day,
        logged_at=stamped,
        label=body.label,
        duration_seconds=duration,
        task_id=resolve_task_id(db, current_user.id, body.task_id, day),
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@router.patch("/nodes/{node_id}", response_model=NodeOut)
@router.post("/nodes/{node_id}", response_model=NodeOut)
async def update_node(
    node_id: int,
    body: NodeUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    node = get_node_or_404(db, current_user.id, node_id)
    if body.label is not None:
        node.label = body.label or None
    if body.clear_task:
        node.task_id = None
    elif body.task_id is not None:
        node.task_id = resolve_task_id(db, current_user.id, body.task_id, node.log_date)
    if not is_written_node(node):
        remove_node(db, node, current_user.id)
        db.commit()
        raise HTTPException(status_code=400, detail="没有写下内容，未记入日志")
    db.commit()
    db.refresh(node)
    return node


@router.delete("/nodes/{node_id}", response_model=DayLogOut)
async def delete_node(
    node_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    node = get_node_or_404(db, current_user.id, node_id)
    day = remove_node(db, node, current_user.id)
    db.commit()
    return day_payload(db, current_user, day)
