"""Daily completion, account separation, and report aggregation."""
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import project_models  # noqa: F401 - register existing tables
from app.database import Base
from app.models import LongTermNodeCategory, TimeLogNode, User
from app.routers.long_term import DailyInput, AttentionItem, daily_payload, get_report, save_day, set_node_category, ClassificationInput, period_bounds
from app.routers.time_log import BEIJING_TZ


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def person(db, email):
    user = User(email=email, name=email, password_hash="test")
    db.add(user)
    db.commit()
    return user


def body(reading=0):
    return DailyInput(
        manual_minutes={key: (reading if key == "reading" else 0) for key in (
            "reading", "fitness", "friends", "family", "investment", "writing", "work", "relaxation"
        )},
        attention_items=[AttentionItem(name="刷手机", minutes=15)],
        money_yuan=Decimal("12.34"), investment_yuan=Decimal("100.00"),
    )


def test_daily_requires_explicit_expenses():
    data = body().model_dump()
    del data["money_yuan"]
    with pytest.raises(ValidationError):
        DailyInput.model_validate(data)
    data = body().model_dump()
    data["attention_items"] = []
    with pytest.raises(ValidationError):
        DailyInput.model_validate(data)


def test_manual_and_classified_time_report_without_cross_account_leak(db):
    alice, bob = person(db, "alice@example.com"), person(db, "bob@example.com")
    day = date(2026, 10, 18)
    node = TimeLogNode(user_id=alice.id, log_date=day, logged_at=datetime(2026, 10, 18, 10, tzinfo=BEIJING_TZ), label="读书", duration_seconds=1800)
    db.add(node)
    db.commit()
    result = save_day(body(reading=20), day=day, user=alice, db=db)
    assert result["total_seconds"]["reading"] == 1200
    result = set_node_category(node.id, ClassificationInput(category="reading"), user=alice, db=db)
    assert result["total_seconds"]["reading"] == 3000
    report = get_report("week", anchor=day, user=alice, db=db)
    assert report["recorded_days"] == 1
    assert report["total_seconds"]["reading"] == 3000
    assert report["attention_by_name"] == {"刷手机": 15}
    assert report["money_cents"] == 1234
    assert report["investment_cents"] == 10000
    assert daily_payload(db, bob.id, day)["recorded"] is False
    assert get_report("week", anchor=day, user=bob, db=db)["total_seconds"]["reading"] == 0


def test_calendar_period_boundaries():
    assert period_bounds("week", date(2026, 10, 18)) == (date(2026, 10, 12), date(2026, 10, 18))
    assert period_bounds("month", date(2026, 12, 18)) == (date(2026, 12, 1), date(2026, 12, 31))
    assert period_bounds("quarter", date(2026, 12, 18)) == (date(2026, 10, 1), date(2026, 12, 31))


def test_classification_limits_daily_time_and_allows_repairing_existing_overflow(db):
    user = person(db, "time-limit@example.com")
    day = date(2026, 10, 18)
    node = TimeLogNode(user_id=user.id, log_date=day, logged_at=datetime(2026, 10, 18, 10, tzinfo=BEIJING_TZ), label="读书", duration_seconds=1800)
    db.add(node)
    db.commit()
    save_day(body(reading=1430), day=day, user=user, db=db)

    with pytest.raises(HTTPException) as error:
        set_node_category(node.id, ClassificationInput(category="reading"), user=user, db=db)
    assert error.value.status_code == 400
    assert db.query(LongTermNodeCategory).filter_by(node_id=node.id).first() is None

    save_day(body(reading=1410), day=day, user=user, db=db)
    result = set_node_category(node.id, ClassificationInput(category="reading"), user=user, db=db)
    assert result["total_seconds"]["reading"] == 86400

    # A legacy record or subsequently extended log can already exceed the limit.
    node.duration_seconds = 3600
    db.commit()
    result = save_day(body(reading=1400), day=day, user=user, db=db)
    assert result["total_seconds"]["reading"] == 1460 * 60
    with pytest.raises(HTTPException):
        save_day(body(reading=1405), day=day, user=user, db=db)
    assert daily_payload(db, user.id, day)["manual_minutes"]["reading"] == 1400

    result = set_node_category(node.id, ClassificationInput(category=None), user=user, db=db)
    assert result["total_seconds"]["reading"] == 1400 * 60
