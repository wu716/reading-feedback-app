"""Detailed private ledgers, additive legacy projection, and calendar reports."""
import json
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import LongTermDailyRecord, LongTermLedgerDay, LongTermNodeCategory, LongTermPreferences, TimeLogNode, User
from app.plans import PAID_PLANS, effective_plan_key
from app.routers.time_log import beijing_today

router = APIRouter(prefix="/long-term/details", tags=["长期目标明细"])
CATEGORIES = ("reading", "fitness", "friends", "family", "investment", "writing", "work", "relaxation")
Category = Literal["reading", "fitness", "friends", "family", "investment", "writing", "work", "relaxation"]
Period = Literal["day", "week", "month", "quarter", "year"]
TOPICS = {
    "literature": "文学与语言", "history": "历史与传记", "philosophy": "哲学与思想",
    "psychology": "心理与自我认识", "society": "社会与文化", "science": "自然科学",
    "technology": "技术与工程", "business": "商业与经济", "arts": "艺术与审美",
    "health": "健康与生活", "education": "教育与成长", "other": "其他主题", "unclassified": "未分类",
}
DEFAULT_EXPENSES = {
    "food": "餐饮", "transport": "交通", "housing": "居住与水电",
    "shopping": "日用购物", "learning": "学习成长", "health": "医疗健康",
    "entertainment": "娱乐休闲", "social": "社交人情", "other": "其他", "unclassified": "历史未分类",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Activity(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    category: Category
    title: str = Field(default="", max_length=200)
    seconds: int = Field(default=0, ge=0, le=86400, strict=True)
    source_node_id: int | None = Field(default=None, gt=0, strict=True)
    reading_kind: Literal["fiction", "nonfiction", "unclassified"] = "unclassified"
    primary_topic: str = "unclassified"
    topics: list[str] = Field(default_factory=list, max_length=5)
    note: str = Field(default="", max_length=3000)
    words: int | None = Field(default=None, ge=0, le=10000000, strict=True)
    amount_cents: int = Field(default=0, ge=0, le=100000000000, strict=True)
    unplanned: bool = False

    @model_validator(mode="after")
    def semantics(self):
        if self.primary_topic not in TOPICS or any(t not in TOPICS for t in self.topics):
            raise ValueError("请选择已有阅读主题")
        if len(set(self.topics)) != len(self.topics):
            raise ValueError("补充主题不能重复")
        if self.category == "investment":
            if self.seconds or self.source_node_id or self.unplanned:
                raise ValueError("定投只记录标的和金额，不计时")
            if not self.title or not self.amount_cents:
                raise ValueError("定投请填写标的和正数金额")
        elif self.amount_cents:
            raise ValueError("只有定投填写投入金额；消费请记入消费明细")
        if self.category != "writing" and self.words is not None:
            raise ValueError("只有写作填写字数")
        if self.category != "reading" and not self.title:
            raise ValueError("请填写具体活动内容")
        return self


class Expense(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    category: str = Field(min_length=1, max_length=60)
    kind: Literal["expense", "refund"] = "expense"
    amount_cents: int = Field(ge=1, le=100000000000, strict=True)
    note: str = Field(default="", max_length=500)
    activity_id: str | None = Field(default=None, max_length=100)
    group_id: str | None = Field(default=None, max_length=100)


class LegacyAttention(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    minutes: int = Field(ge=0, le=1440, strict=True)


class LedgerInput(StrictModel):
    revision: int = Field(ge=0, strict=True)
    activities: list[Activity] = Field(default_factory=list, max_length=300)
    expenses: list[Expense] = Field(default_factory=list, max_length=300)
    expense_confirmed: bool = False
    day_confirmed: bool = False
    attention_items: list[LegacyAttention] = Field(default_factory=list, max_length=30)
    attention_confirmed: bool = False
    # Read compatibility for clients that still send the old field name.
    legacy_attention: list[LegacyAttention] = Field(default_factory=list, max_length=30)

    @model_validator(mode="before")
    @classmethod
    def map_legacy_attention(cls, value):
        if isinstance(value, dict):
            if "attention_items" not in value and "legacy_attention" in value:
                value = {**value, "attention_items": value["legacy_attention"]}
            if "attention_confirmed" not in value:
                value = {**value, "attention_confirmed": bool(value.get("attention_items"))}
        return value

    @model_validator(mode="after")
    def references(self):
        ids = [a.id for a in self.activities]
        expense_ids = [e.id for e in self.expenses]
        nodes = [a.source_node_id for a in self.activities if a.source_node_id]
        if len(set(ids)) != len(ids) or len(set(expense_ids)) != len(expense_ids) or len(set(nodes)) != len(nodes):
            raise ValueError("一条活动、账目或时间日志只能计入一次")
        if any(e.activity_id and e.activity_id not in ids for e in self.expenses):
            raise ValueError("关联活动必须属于当天，请先解除关联再移除活动")
        names = [item.name for item in self.attention_items]
        if len(set(names)) != len(names):
            raise ValueError("注意力浪费项目名称不能重复")
        if sum(item.minutes for item in self.attention_items) > 1440:
            raise ValueError("注意力浪费合计不能超过 1440 分钟")
        return self


class ExpenseCategory(StrictModel):
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=30)
    archived: bool = False


class Target(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    category: Literal["reading", "fitness", "friends", "family", "investment", "writing", "work", "relaxation", "expense"]
    metric: Literal["seconds", "count", "words", "cents"]
    target: int = Field(gt=0, le=100000000000, strict=True)
    period: Literal["week", "month", "quarter", "year"]
    reading_kind: Literal["fiction", "nonfiction", "unclassified"] | None = None
    topic: str | None = None
    expense_category: str | None = None
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def valid_target(self):
        allowed = {"expense": {"cents"}, "investment": {"cents", "count"}, "writing": {"seconds", "words", "count"}}
        if self.metric not in allowed.get(self.category, {"seconds", "count"}):
            raise ValueError("目标单位与板块不匹配")
        if self.topic is not None and self.topic not in TOPICS:
            raise ValueError("目标主题不存在")
        if self.category != "reading" and (self.topic is not None or self.reading_kind is not None):
            raise ValueError("阅读筛选只能用于读书目标")
        if self.category != "expense" and self.expense_category is not None:
            raise ValueError("消费分类只能用于预算")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class PreferencesInput(StrictModel):
    revision: int = Field(ge=0, strict=True)
    expense_categories: list[ExpenseCategory] = Field(min_length=1, max_length=40)
    goals: list[Target] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def unique(self):
        for rows in (self.expense_categories, self.goals):
            if len({r.id for r in rows}) != len(rows):
                raise ValueError("设置中不能有重复编号")
        if len({c.name for c in self.expense_categories}) != len(self.expense_categories):
            raise ValueError("消费类别名称不能重复")
        codes = {c.id for c in self.expense_categories}
        if any(g.expense_category is not None and g.expense_category not in codes for g in self.goals):
            raise ValueError("预算分类不存在")
        return self


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def prefs(db, user_id):
    row = db.query(LongTermPreferences).filter_by(user_id=user_id).first()
    result = json.loads(row.payload_json) if row else {
        "expense_categories": [{"id": k, "name": v, "archived": False} for k, v in DEFAULT_EXPENSES.items()],
        "goals": [],
    }
    return {**result, "revision": row.revision if row else 0, "topics": TOPICS}


def calendar_bounds(period, anchor):
    if period == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    if period == "quarter":
        start = date(anchor.year, ((anchor.month - 1) // 3) * 3 + 1, 1)
        following = date(start.year + 1, 1, 1) if start.month == 10 else date(start.year, start.month + 3, 1)
        return start, following - timedelta(days=1)
    if period == "month":
        start = anchor.replace(day=1)
        following = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
        return start, following - timedelta(days=1)
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    return anchor, anchor


def read_range(db, user_id, start, end):
    """Four bounded queries; all tables always scoped to the current user."""
    if end < start:
        return []
    old = {r.record_date: r for r in db.query(LongTermDailyRecord).filter(
        LongTermDailyRecord.user_id == user_id, LongTermDailyRecord.record_date.between(start, end)).all()}
    ledgers = {r.record_date: r for r in db.query(LongTermLedgerDay).filter(
        LongTermLedgerDay.user_id == user_id, LongTermLedgerDay.record_date.between(start, end)).all()}
    nodes = db.query(TimeLogNode).filter(
        TimeLogNode.user_id == user_id, TimeLogNode.log_date.between(start, end),
        TimeLogNode.deleted_at.is_(None)).order_by(TimeLogNode.logged_at, TimeLogNode.id).all()
    nodes = [n for n in nodes if (n.label or "").strip() or n.task_id is not None]
    assignments = {a.node_id: a.category for a in db.query(LongTermNodeCategory).filter(
        LongTermNodeCategory.user_id == user_id, LongTermNodeCategory.node_id.in_([n.id for n in nodes])).all()} if nodes else {}
    by_day = {}
    for node in nodes:
        by_day.setdefault(node.log_date, []).append(node)
    result = []
    day = start
    while day <= end:
        row = ledgers.get(day)
        source = by_day.get(day, [])
        available = {n.id: n for n in source}
        legacy = old.get(day)
        data = json.loads(row.payload_json) if row else {
            "activities": [], "expenses": [], "expense_confirmed": bool(legacy),
            "day_confirmed": bool(legacy), "attention_items": [],
            "attention_confirmed": bool(legacy), "legacy_attention": [],
        }
        legacy_investment_seconds = 0
        if legacy:
            manual = json.loads(legacy.manual_minutes_json)
            legacy_investment_seconds = manual.get("investment", 0) * 60
        if not row:
            if legacy:
                for category in CATEGORIES:
                    if category != "investment" and manual.get(category, 0):
                        data["activities"].append(Activity(id=f"legacy-{category}", category=category,
                            title="历史汇总（可补充明细）", seconds=manual[category] * 60).model_dump())
                if legacy.investment_cents:
                    data["activities"].append(Activity(id="legacy-investment", category="investment",
                        title="历史未注明标的", amount_cents=legacy.investment_cents).model_dump())
                if legacy.money_cents:
                    data["expenses"].append(Expense(id="legacy-expense", category="unclassified",
                        amount_cents=legacy.money_cents, note="历史消费总额，可拆分补充分类").model_dump())
                data["attention_items"] = [a for a in json.loads(legacy.attention_items_json) if a["minutes"]]
                data["legacy_attention"] = data["attention_items"]
                data["attention_confirmed"] = True
            for node in source:
                category = assignments.get(node.id)
                if category == "investment":
                    legacy_investment_seconds += max(0, node.duration_seconds or 0)
                elif category in CATEGORIES:
                    data["activities"].append(Activity(id=f"node-{node.id}", category=category,
                        title=node.label or "关联行动", source_node_id=node.id).model_dump())
        if "attention_items" not in data:
            data["attention_items"] = data.get("legacy_attention", [])
        if "attention_confirmed" not in data:
            data["attention_confirmed"] = bool(data["attention_items"]) or bool(legacy)
        data.setdefault("legacy_attention", [])
        for activity in data["activities"]:
            activity["source_missing"] = False
            if activity.get("source_node_id"):
                node = available.get(activity["source_node_id"])
                activity["seconds"] = max(0, node.duration_seconds or 0) if node else 0
                activity["source_missing"] = node is None
        result.append({
            **data, "date": day.isoformat(), "revision": row.revision if row else 0,
            "recorded": bool(row or legacy), "legacy_investment_seconds": legacy_investment_seconds,
            "nodes": [{"id": n.id, "title": n.label or "关联行动", "seconds": max(0, n.duration_seconds or 0)} for n in source],
        })
        day += timedelta(days=1)
    return result


def aggregate(days):
    totals = {k: 0 for k in CATEGORIES}
    counts = {k: 0 for k in CATEGORIES}
    reading = {k: {"seconds": 0, "count": 0} for k in ("fiction", "nonfiction", "unclassified")}
    topics, secondary, expenses, investments, projects, attention = {}, {}, {}, {}, {}, {}
    activities, transactions = [], []
    words = unplanned = old_attention = missing = 0
    for day in days:
        for a in day["activities"]:
            item = {**a, "date": day["date"]}
            activities.append(item)
            key = a["category"]
            # A removed source retains its description but contributes neither time nor a session.
            if a.get("source_missing"):
                missing += 1
                continue
            counts[key] += 1
            seconds = a["seconds"] if key != "investment" else 0
            totals[key] += seconds
            projects.setdefault(key, {})
            group = projects[key].setdefault(a["title"] or "未填写名称", {"seconds": 0, "count": 0, "words": 0})
            group["seconds"] += seconds
            group["count"] += 1
            group["words"] += a.get("words") or 0
            if key == "writing":
                words += a.get("words") or 0
            if a.get("unplanned"):
                unplanned += seconds
            if key == "reading":
                reading[a["reading_kind"]]["seconds"] += seconds
                reading[a["reading_kind"]]["count"] += 1
                topic = topics.setdefault(a["primary_topic"], {"seconds": 0, "count": 0})
                topic["seconds"] += seconds
                topic["count"] += 1
                for extra in set(a.get("topics", [])) - {a["primary_topic"]}:
                    secondary[extra] = secondary.get(extra, 0) + 1
            if key == "investment":
                investments[a["title"] or "未注明标的"] = investments.get(a["title"] or "未注明标的", 0) + a["amount_cents"]
        for e in day["expenses"]:
            transactions.append({**e, "date": day["date"]})
            group = expenses.setdefault(e["category"], {"expense_cents": 0, "refund_cents": 0, "net_cents": 0, "count": 0})
            group[f'{e["kind"]}_cents'] += e["amount_cents"]
            group["net_cents"] += e["amount_cents"] * (-1 if e["kind"] == "refund" else 1)
            group["count"] += 1
        for item in day["attention_items"]:
            attention[item["name"]] = attention.get(item["name"], 0) + item["minutes"]
        for item in day["legacy_attention"]:
            old_attention += item["minutes"] * 60
    spend = sum(e["expense_cents"] for e in expenses.values())
    refunds = sum(e["refund_cents"] for e in expenses.values())
    return {
        "total_seconds": totals, "counts": counts, "words": words,
        "reading": reading, "topics": topics, "secondary_topics": secondary,
        "expense_categories": expenses, "expense_cents": spend, "refund_cents": refunds,
        "money_cents": spend - refunds, "investment_cents": sum(investments.values()),
        "investments": investments, "activity_groups": projects,
        "unplanned_seconds": unplanned, "legacy_attention_seconds": old_attention,
        "attention_minutes": sum(attention.values()), "attention_waste_minutes": sum(attention.values()),
        "attention_by_name": attention,
        "attention_confirmed_days": sum(d["attention_confirmed"] for d in days),
        "source_missing_count": missing, "activities": activities, "expenses": transactions,
        "activity_record_count": len(activities), "expense_record_count": len(transactions),
        "recorded_days": sum(d["recorded"] for d in days),
        "expense_confirmed_days": sum(d["expense_confirmed"] for d in days),
        "day_confirmed_days": sum(d["day_confirmed"] for d in days),
    }


def conflict():
    raise HTTPException(409, "这份记录已在其他页面更新。草稿已保留，请重新读取后核对，避免覆盖较新的记录。")


@router.get("/day")
def get_day(day: date = Query(default=None), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    day = day or beijing_today()
    payload = read_range(db, user.id, day, day)[0]
    return {**payload, "summary": aggregate([payload])}


@router.put("/day")
def save_day(body: LedgerInput, day: date = Query(...), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    previous = read_range(db, user.id, day, day)[0]
    if previous["revision"] != body.revision:
        conflict()
    nodes = {n["id"]: n for n in previous["nodes"]}
    existing = {a["id"]: a for a in previous["activities"]}
    data = body.model_dump(exclude={"revision", "legacy_attention"})
    for activity in data["activities"]:
        source_id = activity["source_node_id"]
        if source_id:
            if source_id not in nodes:
                old = existing.get(activity["id"])
                if not old or old.get("source_node_id") != source_id:
                    raise HTTPException(400, "只能关联当前账号当天的时间日志")
                activity["seconds"] = 0
            else:
                activity["seconds"] = nodes[source_id]["seconds"]
    old_total = sum(a["seconds"] for a in previous["activities"])
    new_total = sum(a["seconds"] for a in data["activities"])
    if new_total > 86400 and new_total > old_total:
        raise HTTPException(400, "当天累计超过 24 小时，请检查重复录入")
    valid_categories = {c["id"]: c for c in prefs(db, user.id)["expense_categories"]}
    old_expenses = {e["id"]: e for e in previous["expenses"]}
    for expense in data["expenses"]:
        category = valid_categories.get(expense["category"])
        if category is None:
            raise HTTPException(400, "消费分类不存在")
        if category["archived"] and old_expenses.get(expense["id"], {}).get("category") != expense["category"]:
            raise HTTPException(400, "停用的分类不能用于新账目，请选择有效分类")
    # Old clients may still submit the legacy alias; allow unchanged data and deletion only.
    old_attention = {(a["name"], a["minutes"]) for a in previous["legacy_attention"]}
    if any((a["name"], a["minutes"]) not in old_attention for a in body.legacy_attention):
        raise HTTPException(400, "旧版注意力记录不能新增，请使用新的注意力开销字段")
    try:
        if body.revision:
            changed = db.query(LongTermLedgerDay).filter_by(user_id=user.id, record_date=day, revision=body.revision).update({
                "payload_json": dumps(data), "revision": body.revision + 1}, synchronize_session=False)
            if changed != 1:
                db.rollback()
                conflict()
        else:
            db.add(LongTermLedgerDay(user_id=user.id, record_date=day, revision=1, payload_json=dumps(data)))
        db.commit()
    except IntegrityError:
        db.rollback()
        conflict()
    return get_day(day=day, user=user, db=db)


@router.get("/preferences")
def get_preferences(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return {**prefs(db, user.id), "premium_locked": effective_plan_key(user) not in PAID_PLANS}


@router.put("/preferences")
def save_preferences(body: PreferencesInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    previous = prefs(db, user.id)
    if previous["revision"] != body.revision:
        conflict()
    previous_goals = [Target.model_validate(goal).model_dump(mode="json") for goal in previous["goals"]]
    requested_goals = [goal.model_dump(mode="json") for goal in body.goals]
    if effective_plan_key(user) not in PAID_PLANS and requested_goals != previous_goals:
        raise HTTPException(403, "长期目标页的复盘目标与消费预算需要有效月卡或学期卡；消费分类仍可免费修改")
    old_ids = {c["id"] for c in previous["expense_categories"]}
    new_ids = {c.id for c in body.expense_categories}
    if not old_ids <= new_ids:
        raise HTTPException(400, "请停用分类，保留历史账目的分类编号")
    if any(c.id == "unclassified" and (c.archived or c.name != DEFAULT_EXPENSES["unclassified"]) for c in body.expense_categories):
        raise HTTPException(400, "历史未分类用于兼容旧账目，请保留")
    data = body.model_dump(mode="json", exclude={"revision"})
    try:
        if body.revision:
            changed = db.query(LongTermPreferences).filter_by(user_id=user.id, revision=body.revision).update({
                "payload_json": dumps(data), "revision": body.revision + 1}, synchronize_session=False)
            if changed != 1:
                db.rollback()
                conflict()
        else:
            db.add(LongTermPreferences(user_id=user.id, revision=1, payload_json=dumps(data)))
        db.commit()
    except IntegrityError:
        db.rollback()
        conflict()
    return get_preferences(user=user, db=db)


@router.get("/recent")
def recent(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    rows = db.query(LongTermLedgerDay).filter_by(user_id=user.id).order_by(LongTermLedgerDay.record_date.desc()).limit(60).all()
    items, seen = [], set()
    for row in rows:
        for a in reversed(json.loads(row.payload_json)["activities"]):
            identity = (a["category"], a["title"])
            if a["title"] and identity not in seen:
                seen.add(identity)
                items.append({k: a[k] for k in ("category", "title", "reading_kind", "primary_topic", "topics")})
    return {"items": items[:120]}


def target_progress(goal, days):
    category, metric = goal["category"], goal["metric"]
    if category == "expense":
        return sum(e["amount_cents"] * (-1 if e["kind"] == "refund" else 1)
                   for d in days for e in d["expenses"]
                   if not goal.get("expense_category") or goal["expense_category"] == e["category"])
    items = [a for d in days for a in d["activities"] if a["category"] == category and not a.get("source_missing")
             and (not goal.get("reading_kind") or a["reading_kind"] == goal["reading_kind"])
             and (not goal.get("topic") or a["primary_topic"] == goal["topic"])]
    if metric == "count":
        return len(items)
    field = "amount_cents" if metric == "cents" else metric
    return sum(a.get(field) or 0 for a in items)


def report_payload(db, user_id, period, anchor, now=None):
    now = now or beijing_today()
    start, end = calendar_bounds(period, anchor)
    effective_end = min(end, now)
    days = read_range(db, user_id, start, effective_end)
    summary = aggregate(days)
    preferences = prefs(db, user_id)
    previous_start, previous_end = calendar_bounds(period, start - timedelta(days=1))
    elapsed = max(0, (effective_end - start).days + 1)
    comparison_length = min(elapsed, (previous_end - previous_start).days + 1)
    compared_end = start + timedelta(days=comparison_length - 1)
    previous_compared_end = previous_start + timedelta(days=comparison_length - 1)
    comparison_days = read_range(db, user_id, previous_start, previous_compared_end)
    current_comparison = aggregate(days[:comparison_length])
    previous_comparison = aggregate(comparison_days)
    goal_rows = []
    range_cache = {(start, effective_end): days}
    for goal in preferences["goals"]:
        goal_start, goal_end = calendar_bounds(goal["period"], anchor)
        active_start = max(goal_start, date.fromisoformat(goal["start_date"]))
        active_end = min(goal_end, now, date.fromisoformat(goal["end_date"]) if goal.get("end_date") else goal_end)
        if active_end < active_start:
            continue
        if (active_start, active_end) not in range_cache:
            range_cache[(active_start, active_end)] = read_range(db, user_id, active_start, active_end)
        goal_days = range_cache[(active_start, active_end)]
        goal_rows.append({
            **goal, "start": active_start.isoformat(), "end": active_end.isoformat(),
            "period_end": goal_end.isoformat(), "actual": target_progress(goal, goal_days),
            "confirmed_days": sum(d["expense_confirmed"] if goal["category"] == "expense" else d["day_confirmed"] for d in goal_days),
            "elapsed_days": len(goal_days),
        })
    def compact(data):
        return {k: data[k] for k in ("total_seconds", "counts", "words", "money_cents", "expense_cents", "refund_cents",
                                     "investment_cents", "recorded_days", "expense_confirmed_days", "day_confirmed_days", "topics",
                                     "activity_record_count", "expense_record_count", "attention_waste_minutes",
                                     "attention_confirmed_days")}
    buckets = {}
    for d in days:
        key = d["date"][:7] if period in ("quarter", "year") else d["date"]
        buckets.setdefault(key, []).append(d)
    return {
        **summary, "period": period, "start": start.isoformat(), "end": end.isoformat(),
        "effective_end": effective_end.isoformat() if elapsed else None,
        "total_days": (end - start).days + 1, "elapsed_days": elapsed,
        "expense_category_names": {c["id"]: c["name"] for c in preferences["expense_categories"]},
        "topic_names": TOPICS, "goals": goal_rows,
        "days": [{"date": d["date"], "recorded": d["recorded"], "expense_confirmed": d["expense_confirmed"],
                  "attention_confirmed": d["attention_confirmed"],
                  "day_confirmed": d["day_confirmed"], "money_cents": stats["money_cents"],
                  "investment_cents": stats["investment_cents"],
                  "attention_minutes": stats["attention_waste_minutes"],
                  "attention_waste_minutes": stats["attention_waste_minutes"]} for d in days for stats in [aggregate([d])]],
        "trend": [{"label": key, **compact(aggregate(value))} for key, value in buckets.items()],
        "comparison": {
            "days": comparison_length, "start": start.isoformat(), "end": compared_end.isoformat() if comparison_length else None,
            "previous_start": previous_start.isoformat(),
            "previous_end": previous_compared_end.isoformat() if comparison_length else None,
            "current": compact(current_comparison), "previous": compact(previous_comparison),
        },
    }


@router.get("/report")
def get_report(period: Period = "day", anchor: date = Query(default=None), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return report_for_user(db, user, period, anchor or beijing_today())


def report_for_user(db: Session, user: User, period: Period, anchor: date) -> dict:
    """Enforce the same report boundary for the current and legacy API routes."""
    paid = effective_plan_key(user) in PAID_PLANS
    if period in ("month", "quarter", "year") and not paid:
        raise HTTPException(403, "月报、季报和年报需要有效月卡或学期卡")
    result = report_payload(db, user.id, period, anchor)
    result["premium_locked"] = not paid
    if not paid:
        # Daily and weekly totals stay free. Full records are available from /day
        # and the account export; app-generated deep analysis requires a paid plan.
        result.update({
            "topics": {}, "secondary_topics": {}, "investments": {},
            "activity_groups": {}, "activities": [], "expenses": [],
            "goals": [], "trend": [], "comparison": None,
        })
    return result

