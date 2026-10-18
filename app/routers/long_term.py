"""Long-term activity and expense ledger. All dates use the Beijing calendar."""
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import LongTermDailyRecord, LongTermNodeCategory, TimeLogNode, User
from app.routers.time_log import beijing_today, visible_nodes

router = APIRouter(prefix="/long-term", tags=["长期目标追踪"])
CATEGORIES = ("reading", "fitness", "friends", "family", "investment", "writing", "work", "relaxation")
Category = Literal["reading", "fitness", "friends", "family", "investment", "writing", "work", "relaxation"]


class AttentionItem(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    minutes: int = Field(ge=0, le=1440)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("注意力开销项目不能为空")
        return value


class DailyInput(BaseModel):
    manual_minutes: dict[Category, int]
    attention_items: list[AttentionItem] = Field(min_length=1)
    money_yuan: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    investment_yuan: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)

    @field_validator("manual_minutes")
    @classmethod
    def check_minutes(cls, values: dict) -> dict:
        if set(values) != set(CATEGORIES) or any(type(v) is not int or v < 0 or v > 1440 for v in values.values()):
            raise ValueError("八类补录时间都必须填写 0 到 1440 分钟")
        if sum(values.values()) > 1440:
            raise ValueError("一天的补录时间不能超过 1440 分钟")
        return values

    @field_validator("attention_items")
    @classmethod
    def check_attention(cls, items: list[AttentionItem]) -> list[AttentionItem]:
        if len(items) > 30 or sum(item.minutes for item in items) > 1440:
            raise ValueError("注意力开销项目过多或总时长超过一天")
        if len({item.name for item in items}) != len(items):
            raise ValueError("注意力开销项目名称不能重复")
        return items


class ClassificationInput(BaseModel):
    category: Category | None = None


def cents(value: Decimal) -> int:
    return int(value * 100)


def record_for(db: Session, user_id: int, day: date):
    return db.query(LongTermDailyRecord).filter_by(user_id=user_id, record_date=day).first()


def check_total_increase(previous_seconds: int, next_seconds: int):
    # Existing over-limit records must remain editable while their time is reduced.
    if next_seconds > 86400 and next_seconds > previous_seconds:
        raise HTTPException(400, "日志归类与手动补录合计超过一天，请检查是否重复记录")


def classified_nodes(db: Session, user_id: int, start: date, end: date):
    nodes = db.query(TimeLogNode).filter(
        TimeLogNode.user_id == user_id,
        TimeLogNode.log_date >= start,
        TimeLogNode.log_date <= end,
        TimeLogNode.deleted_at.is_(None),
    ).all()
    ids = [node.id for node in nodes]
    assignments = {} if not ids else {
        row.node_id: row.category for row in db.query(LongTermNodeCategory).filter(
            LongTermNodeCategory.user_id == user_id, LongTermNodeCategory.node_id.in_(ids)
        ).all()
    }
    return nodes, assignments


def daily_payload(db: Session, user_id: int, day: date):
    record = record_for(db, user_id, day)
    nodes, assignments = classified_nodes(db, user_id, day, day)
    # Present only written nodes, in the same order as the time log.
    visible = {node.id for node in visible_nodes(db, user_id, day)}
    totals = {category: 0 for category in CATEGORIES}
    node_rows = []
    for node in sorted(nodes, key=lambda row: (row.logged_at, row.id)):
        if node.id not in visible:
            continue
        category = assignments.get(node.id)
        seconds = max(0, node.duration_seconds or 0)
        if category in totals:
            totals[category] += seconds
        node_rows.append({"id": node.id, "label": node.label or "关联行动", "seconds": seconds, "category": category})
    manual = json.loads(record.manual_minutes_json) if record else {key: 0 for key in CATEGORIES}
    attention = json.loads(record.attention_items_json) if record else []
    return {
        "date": day.isoformat(), "recorded": bool(record),
        "manual_minutes": manual, "automatic_seconds": totals,
        "total_seconds": {key: totals[key] + manual.get(key, 0) * 60 for key in CATEGORIES},
        "attention_items": attention,
        "attention_minutes": sum(item["minutes"] for item in attention),
        "money_cents": record.money_cents if record else None,
        "investment_cents": record.investment_cents if record else None,
        "nodes": node_rows,
    }


@router.get("/day")
def get_day(day: date = Query(default=None), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return daily_payload(db, user.id, day or beijing_today())


@router.put("/day")
def save_day(body: DailyInput, day: date = Query(...), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    nodes, assignments = classified_nodes(db, user.id, day, day)
    automatic_seconds = sum(max(0, node.duration_seconds or 0) for node in nodes if assignments.get(node.id) in CATEGORIES)
    record = record_for(db, user.id, day)
    previous_manual = json.loads(record.manual_minutes_json) if record else {}
    check_total_increase(
        automatic_seconds + sum(previous_manual.values()) * 60,
        automatic_seconds + sum(body.manual_minutes.values()) * 60,
    )
    if record is None:
        record = LongTermDailyRecord(user_id=user.id, record_date=day)
        db.add(record)
    record.manual_minutes_json = json.dumps(body.manual_minutes)
    record.attention_items_json = json.dumps([item.model_dump() for item in body.attention_items], ensure_ascii=False)
    record.money_cents = cents(body.money_yuan)
    record.investment_cents = cents(body.investment_yuan)
    db.commit()
    return daily_payload(db, user.id, day)


@router.put("/nodes/{node_id}/category")
def set_node_category(node_id: int, body: ClassificationInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    node = db.query(TimeLogNode).filter_by(id=node_id, user_id=user.id, deleted_at=None).first()
    if node is None or not (node.label or "").strip() and node.task_id is None:
        raise HTTPException(404, "时间日志节点不存在")
    assignment = db.query(LongTermNodeCategory).filter_by(node_id=node_id, user_id=user.id).first()
    nodes, assignments = classified_nodes(db, user.id, node.log_date, node.log_date)
    record = record_for(db, user.id, node.log_date)
    manual = json.loads(record.manual_minutes_json) if record else {}
    previous_seconds = sum(manual.values()) * 60 + sum(
        max(0, item.duration_seconds or 0) for item in nodes if assignments.get(item.id) in CATEGORIES
    )
    next_seconds = previous_seconds + max(0, node.duration_seconds or 0) * (
        int(body.category in CATEGORIES) - int(assignments.get(node.id) in CATEGORIES)
    )
    check_total_increase(previous_seconds, next_seconds)
    if body.category is None:
        if assignment:
            db.delete(assignment)
    elif assignment:
        assignment.category = body.category
    else:
        db.add(LongTermNodeCategory(user_id=user.id, node_id=node_id, category=body.category))
    db.commit()
    return daily_payload(db, user.id, node.log_date)


def period_bounds(period: str, anchor: date) -> tuple[date, date]:
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = anchor.replace(day=1)
        next_month = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start, next_month - timedelta(days=1)
    if period == "quarter":
        first_month = ((anchor.month - 1) // 3) * 3 + 1
        start = anchor.replace(month=first_month, day=1)
        next_start = start.replace(year=start.year + 1, month=1) if first_month == 10 else start.replace(month=first_month + 3)
        return start, next_start - timedelta(days=1)
    return anchor, anchor


@router.get("/report")
def get_report(period: Literal["day", "week", "month", "quarter"], anchor: date = Query(default=None), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    start, end = period_bounds(period, anchor or beijing_today())
    rows = db.query(LongTermDailyRecord).filter(
        LongTermDailyRecord.user_id == user.id,
        LongTermDailyRecord.record_date >= start,
        LongTermDailyRecord.record_date <= end,
    ).order_by(LongTermDailyRecord.record_date).all()
    nodes, assignments = classified_nodes(db, user.id, start, end)
    totals = {key: 0 for key in CATEGORIES}
    attention_by_name = {}
    days = {}
    for row in rows:
        manual = json.loads(row.manual_minutes_json)
        for key in CATEGORIES:
            totals[key] += manual.get(key, 0) * 60
        attention = json.loads(row.attention_items_json)
        for item in attention:
            attention_by_name[item["name"]] = attention_by_name.get(item["name"], 0) + item["minutes"]
        days[row.record_date.isoformat()] = {
            "date": row.record_date.isoformat(), "attention_minutes": sum(item["minutes"] for item in attention),
            "money_cents": row.money_cents, "investment_cents": row.investment_cents,
        }
    for node in nodes:
        category = assignments.get(node.id)
        if category in totals and ((node.label or "").strip() or node.task_id is not None):
            totals[category] += max(0, node.duration_seconds or 0)
    return {
        "period": period, "start": start.isoformat(), "end": end.isoformat(),
        "recorded_days": len(rows), "total_days": (end - start).days + 1,
        "total_seconds": totals,
        "attention_minutes": sum(day["attention_minutes"] for day in days.values()),
        "attention_by_name": attention_by_name,
        "money_cents": sum(day["money_cents"] for day in days.values()),
        "investment_cents": sum(day["investment_cents"] for day in days.values()),
        "days": list(days.values()),
    }
