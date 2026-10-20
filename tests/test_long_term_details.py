"""Behavior tests for detailed ledgers, privacy, migration and calendar accounting."""
import json
import io
import zipfile
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import project_models  # noqa: F401
from app.auth import get_current_active_user
from app.backup import build_backup_zip
from app.database import Base, get_db
from app.models import User, TimeLogNode, LongTermDailyRecord, LongTermLedgerDay
from app.routers import long_term as old
from app.routers import long_term_details as ledger

DAY = date(2026, 10, 20)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def person(db, name="alice"):
    user = User(email=name + "@example.test", name=name, password_hash="test")
    db.add(user)
    db.commit()
    return user


def activity(id="reading-1", category="reading", **kwargs):
    values = dict(id=id, category=category, title="书籍", seconds=1800)
    values.update(kwargs)
    return ledger.Activity(**values)


def expense(id="expense-1", **kwargs):
    return ledger.Expense(**dict(dict(id=id, category="food", amount_cents=1234), **kwargs))


def save(db, user, day=DAY, revision=0, activities=(), expenses=(), **kwargs):
    return ledger.save_day(ledger.LedgerInput(revision=revision, activities=list(activities), expenses=list(expenses), **kwargs),
                           day=day, user=user, db=db)


def node(db, user, day=DAY, seconds=600):
    item = TimeLogNode(user_id=user.id, log_date=day, logged_at=datetime(day.year, day.month, day.day, 10),
                       label="阅读片段", duration_seconds=seconds)
    db.add(item)
    db.commit()
    return item


def settings_body(db, user, **kwargs):
    data = ledger.prefs(db, user.id)
    data.pop("topics")
    data.update(kwargs)
    return ledger.PreferencesInput.model_validate(data)


def test_all_boards_topics_money_and_refunds_reconcile_in_every_period(db):
    user = person(db)
    activities = [
        activity(reading_kind="nonfiction", primary_topic="science", topics=["history", "psychology"]),
        activity("reading-2", reading_kind="fiction", primary_topic="literature", seconds=1200),
        activity("fitness", "fitness", title="跑步", seconds=1800, note="运动后很舒畅"),
        activity("friends", "friends", title="帮朋友搬家", seconds=3600),
        activity("family", "family", title="一起吃饭", seconds=2700),
        activity("writing", "writing", title="构思与修订", seconds=900, words=0),
        activity("work", "work", title="整理方案", seconds=3600),
        activity("relax", "relaxation", title="刷手机", seconds=600, unplanned=True),
        activity("invest", "investment", title="标的 A", seconds=0, amount_cents=10000),
    ]
    receipts = [
        expense(amount_cents=20000, activity_id="family", group_id="receipt"),
        expense("expense-2", category="shopping", amount_cents=5000, group_id="receipt"),
        expense("refund", kind="refund", amount_cents=3000),
    ]
    save(db, user, activities=activities, expenses=receipts, expense_confirmed=True, day_confirmed=True)
    for period in ("day", "week", "month", "quarter", "year"):
        report = ledger.report_payload(db, user.id, period, DAY, now=DAY)
        assert report["money_cents"] == 22000
        assert report["expense_cents"] == 25000
        assert report["refund_cents"] == 3000
        assert report["expense_categories"]["food"]["net_cents"] == 17000
        assert sum(v["net_cents"] for v in report["expense_categories"].values()) == report["money_cents"]
        assert sum(v["seconds"] for v in report["topics"].values()) == report["total_seconds"]["reading"] == 3000
        assert report["secondary_topics"] == {"history": 1, "psychology": 1}
        assert report["unplanned_seconds"] == 600
        assert report["total_seconds"]["relaxation"] == 600
        assert report["total_seconds"]["investment"] == 0
        assert report["investment_cents"] == 10000
        assert report["counts"]["writing"] == 1 and report["words"] == 0
        assert report["expense_confirmed_days"] == 1
    report = ledger.report_payload(db, user.id, "month", DAY, now=DAY)
    assert report["elapsed_days"] == 20
    assert report["recorded_days"] == 1
    assert len(report["activities"]) == 9
    assert report["expenses"][0]["activity_id"] == "family"


def test_legacy_projection_preserves_amounts_and_sources_without_double_counting(db):
    user = person(db)
    n = node(db, user)
    legacy_body = old.DailyInput(
        manual_minutes={k: 20 if k == "reading" else 5 if k == "investment" else 0 for k in old.CATEGORIES},
        attention_items=[old.AttentionItem(name="手机", minutes=10)],
        money_yuan="12.34", investment_yuan="100",
    )
    old.save_day(legacy_body, day=DAY, user=user, db=db)
    old.set_node_category(n.id, old.ClassificationInput(category="reading"), user=user, db=db)
    raw_before = db.query(LongTermDailyRecord).first().manual_minutes_json
    projected = ledger.get_day(day=DAY, user=user, db=db)
    assert projected["summary"]["total_seconds"]["reading"] == 1800
    assert projected["legacy_investment_seconds"] == 300
    assert projected["expenses"][0]["category"] == "unclassified"
    activities = [ledger.Activity.model_validate({k: v for k, v in a.items() if k != "source_missing"}) for a in projected["activities"]]
    result = save(db, user, activities=activities, expenses=[ledger.Expense.model_validate(e) for e in projected["expenses"]],
                  legacy_attention=projected["legacy_attention"], expense_confirmed=True)
    assert result["summary"]["money_cents"] == 1234
    assert result["summary"]["total_seconds"]["reading"] == 1800
    assert db.query(LongTermDailyRecord).first().manual_minutes_json == raw_before
    assert old.daily_payload(db, user.id, DAY)["total_seconds"]["reading"] == 1800
    with pytest.raises(HTTPException) as error:
        old.save_day(legacy_body, day=DAY, user=user, db=db)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        old.set_node_category(n.id, old.ClassificationInput(category="work"), user=user, db=db)


def test_source_is_live_unique_and_private_and_deleted_source_keeps_description(db):
    alice, bob = person(db), person(db, "bob")
    n, other = node(db, alice), node(db, bob)
    with pytest.raises(HTTPException):
        save(db, alice, activities=[activity(source_node_id=other.id)])
    with pytest.raises(HTTPException):
        save(db, alice, day=DAY+timedelta(days=1), activities=[activity(source_node_id=n.id)])
    with pytest.raises(ValidationError):
        ledger.LedgerInput(revision=0, activities=[activity(source_node_id=n.id), activity("second",source_node_id=n.id)])
    saved = save(db, alice, activities=[activity(source_node_id=n.id, seconds=12345)])
    assert saved["activities"][0]["seconds"] == 600
    n.duration_seconds = 1200
    db.commit()
    assert ledger.get_day(day=DAY,user=alice,db=db)["summary"]["total_seconds"]["reading"] == 1200
    n.deleted_at = datetime.now()
    db.commit()
    result = ledger.get_day(day=DAY,user=alice,db=db)
    assert result["activities"][0]["title"] == "书籍"
    assert result["activities"][0]["source_missing"] is True
    assert result["summary"]["total_seconds"]["reading"] == 0
    assert result["summary"]["counts"]["reading"] == 0
    assert not ledger.get_day(day=DAY,user=bob,db=db)["activities"]
    assert not ledger.recent(user=bob,db=db)["items"]


def test_concurrent_updates_reject_stale_payload_and_keep_latest_data(db):
    user=person(db)
    save(db,user,activities=[activity()])
    with pytest.raises(HTTPException) as error:
        save(db,user,activities=[activity(seconds=999)])
    assert error.value.status_code == 409
    save(db,user,revision=1,activities=[activity(seconds=2400)])
    with pytest.raises(HTTPException):
        save(db,user,revision=1,activities=[activity(seconds=100)])
    assert ledger.get_day(day=DAY,user=user,db=db)["summary"]["total_seconds"]["reading"] == 2400


def test_validation_rejects_invalid_refs_money_and_time_overflow(db):
    user=person(db)
    with pytest.raises(ValidationError):
        ledger.LedgerInput(revision=0,expenses=[expense(activity_id="foreign")])
    for invalid in (0,-1,1.2,True,100000000001):
        with pytest.raises(ValidationError):
            expense(amount_cents=invalid)
    with pytest.raises(ValidationError):
        activity("invest","investment",amount_cents=100)
    with pytest.raises(ValidationError):
        activity(primary_topic="unknown")
    with pytest.raises(HTTPException):
        save(db,user,activities=[activity(seconds=86400),activity("extra",seconds=60)])
    assert not db.query(LongTermLedgerDay).count()
    with pytest.raises(HTTPException):
        save(db,user,expenses=[expense(category="foreign-category")])
    with pytest.raises(HTTPException):
        save(db,user,legacy_attention=[{"name":"新增","minutes":10}])


def test_zero_and_missing_and_refund_day_are_distinct(db):
    user=person(db)
    save(db,user,expenses=[],expense_confirmed=True)
    save(db,user,day=DAY-timedelta(days=1),activities=[activity()],expense_confirmed=False)
    save(db,user,day=DAY-timedelta(days=2),expenses=[expense(kind="refund",amount_cents=1000)])
    report=ledger.report_payload(db,user.id,"month",DAY,now=DAY)
    assert report["expense_confirmed_days"] == 1
    assert report["recorded_days"] == 3
    assert report["money_cents"] == -1000
    assert report["days"][-1]["expense_confirmed"] is True
    assert report["days"][-2]["expense_confirmed"] is False
    assert report["days"][0]["recorded"] is False


def test_category_retirement_keeps_history_and_refuses_new_use(db):
    user=person(db)
    save(db,user,expenses=[expense()])
    p=settings_body(db,user)
    next(c for c in p.expense_categories if c.id=="food").archived=True
    ledger.save_preferences(p,user=user,db=db)
    save(db,user,revision=1,expenses=[expense(amount_cents=2000)])
    with pytest.raises(HTTPException):
        save(db,user,day=DAY+timedelta(days=1),expenses=[expense()])
    assert ledger.report_payload(db,user.id,"day",DAY,now=DAY)["money_cents"] == 2000
    stale=settings_body(db,user); stale.revision=0
    with pytest.raises(HTTPException):
        ledger.save_preferences(stale,user=user,db=db)
    invalid=settings_body(db,user);invalid.expense_categories=[c for c in invalid.expense_categories if c.id!="food"]
    with pytest.raises(HTTPException):
        ledger.save_preferences(invalid,user=user,db=db)


def test_goal_filters_and_budget_and_account_isolation(db):
    user,bob=person(db),person(db,"bob")
    save(db,user,activities=[activity(primary_topic="science",reading_kind="nonfiction"),activity("fiction",reading_kind="fiction")],
         expenses=[expense(amount_cents=1000),expense("refund",kind="refund",amount_cents=200)],expense_confirmed=True)
    goals=[
        ledger.Target(id="g1",category="reading",metric="seconds",target=7200,period="week",
                      topic="science",reading_kind="nonfiction",start_date=DAY),
        ledger.Target(id="g2",category="expense",metric="cents",target=2000,period="month",
                      expense_category="food",start_date=DAY),
    ]
    ledger.save_preferences(settings_body(db,user,goals=goals),user=user,db=db)
    result=ledger.report_payload(db,user.id,"month",DAY,now=DAY)
    assert [g["actual"] for g in result["goals"]] == [1800,800]
    assert result["goals"][1]["confirmed_days"] == 1
    assert not ledger.report_payload(db,bob.id,"month",DAY,now=DAY)["goals"]
    assert not ledger.report_payload(db,bob.id,"month",DAY,now=DAY)["activities"]
    with pytest.raises(ValidationError):
        ledger.Target(id="x",category="expense",metric="seconds",target=1,period="month",start_date=DAY)


def test_calendar_year_leap_and_equal_length_comparison(db):
    user=person(db)
    assert ledger.calendar_bounds("year",date(2024,2,29)) == (date(2024,1,1),date(2024,12,31))
    assert ledger.calendar_bounds("quarter",date(2026,12,31)) == (date(2026,10,1),date(2026,12,31))
    assert ledger.calendar_bounds("week",date(2026,10,18)) == (date(2026,10,12),date(2026,10,18))
    save(db,user,day=date(2026,2,28),expenses=[expense(amount_cents=1000)])
    save(db,user,day=date(2026,3,31),expenses=[expense(amount_cents=5000)])
    report=ledger.report_payload(db,user.id,"month",date(2026,3,31),now=date(2026,3,31))
    assert report["money_cents"] == 5000
    assert report["comparison"]["days"] == 28
    assert report["comparison"]["current"]["money_cents"] == 0
    assert report["comparison"]["previous"]["money_cents"] == 1000
    future=ledger.report_payload(db,user.id,"year",date(2028,1,1),now=DAY)
    assert future["elapsed_days"] == 0 and future["comparison"]["days"] == 0
    assert future["days"] == []


def test_http_payload_validation_and_backup_include_details(db):
    user=person(db)
    app=FastAPI()
    app.include_router(ledger.router,prefix="/api")
    app.dependency_overrides[get_current_active_user]=lambda:user
    app.dependency_overrides[get_db]=lambda:db
    client=TestClient(app)
    assert client.put("/api/long-term/details/day?day=2026-10-20",json={"revision":0,"expenses":[{"id":"x","category":"food","amount_cents":1.5}]}).status_code == 422
    response=client.put("/api/long-term/details/day?day=2026-10-20",json={
        "revision":0,"activities":[activity().model_dump()],"expense_confirmed":True,
    })
    assert response.status_code == 200
    assert response.json()["revision"] == 1
    assert client.get("/api/long-term/details/report?period=year&anchor=2026-10-20").status_code == 200
    with zipfile.ZipFile(io.BytesIO(build_backup_zip(db))) as archive:
        assert "long_term_ledger_days.csv" in archive.namelist()
        assert "long_term_preferences.csv" in archive.namelist()
        assert "书籍" in archive.read("long_term_ledger_days.csv").decode("utf-8-sig")

