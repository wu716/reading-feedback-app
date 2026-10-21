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
    from app.models import LongTermLedgerDay
    from app.routers.long_term_details import read_range, aggregate
    if db.query(LongTermLedgerDay).filter_by(user_id=user_id, record_date=day).first():
        detail = read_range(db, user_id, day, day)[0]
        summary = aggregate([detail])
        automatic = {key: 0 for key in CATEGORIES}
        manual = {key: 0 for key in CATEGORIES}
        by_node = {}
        for activity in detail["activities"]:
            if activity.get("source_node_id"):
                automatic[activity["category"]] += activity["seconds"]
                by_node[activity["source_node_id"]] = activity["category"]
            else:
                manual[activity["category"]] += activity["seconds"] / 60
        return {
            "date": day.isoformat(), "recorded": True, "manual_minutes": manual,
            "automatic_seconds": automatic, "total_seconds": summary["total_seconds"],
            "attention_items": detail["legacy_attention"], "attention_minutes": summary["attention_minutes"],
            "money_cents": summary["money_cents"], "investment_cents": summary["investment_cents"],
            "nodes": [{"id": n["id"], "label": n["title"], "seconds": n["seconds"], "category": by_node.get(n["id"])} for n in detail["nodes"]],
        }
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
    reject_legacy_write(db, user.id, day)
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
    reject_legacy_write(db, user.id, node.log_date)
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


def reject_legacy_write(db, user_id, day):
    from app.models import LongTermLedgerDay
    if db.query(LongTermLedgerDay).filter_by(user_id=user_id, record_date=day).first():
        raise HTTPException(409, "当天已使用明细记录，请刷新到新版页面后修改")


def period_bounds(period: str, anchor: date) -> tuple[date, date]:
    from app.routers.long_term_details import calendar_bounds
    return calendar_bounds(period, anchor)


@router.get("/report")
def get_report(period: Literal["day", "week", "month", "quarter", "year"], anchor: date = Query(default=None), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.routers.long_term_details import report_for_user
    return report_for_user(db, user, period, anchor or beijing_today())
