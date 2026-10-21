"""Paid plan renewals preserve unused time without changing direct plan corrections."""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import project_models  # noqa: F401 - registers related tables
from app.database import Base
from app.models import User
from app import plans


TODAY = date(2026, 10, 21)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(plans, "_today", lambda: TODAY)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def user_with_plan(db, plan, expiry):
    user = User(email="renewal@example.test", name="续费用户", password_hash="test",
                plan=plan, plan_expires_at=expiry)
    db.add(user)
    db.commit()
    return user


@pytest.mark.parametrize(
    "old_plan, old_expiry, next_plan, expected_expiry",
    [
        (plans.PLAN_MONTHLY, TODAY + timedelta(days=8), plans.PLAN_MONTHLY, TODAY + timedelta(days=38)),
        (plans.PLAN_MONTHLY, TODAY + timedelta(days=8), plans.PLAN_SEMESTER, TODAY + timedelta(days=128)),
        (plans.PLAN_SEMESTER, TODAY, plans.PLAN_MONTHLY, TODAY + timedelta(days=30)),
        (plans.PLAN_MONTHLY, TODAY - timedelta(days=1), plans.PLAN_MONTHLY, TODAY + timedelta(days=30)),
        (plans.PLAN_MONTHLY, None, plans.PLAN_MONTHLY, TODAY + timedelta(days=30)),
        (plans.PLAN_FREE, None, plans.PLAN_SEMESTER, TODAY + timedelta(days=120)),
    ],
)
def test_renewal_expiry_persists_and_subscription_agrees(db, old_plan, old_expiry, next_plan, expected_expiry):
    user = user_with_plan(db, old_plan, old_expiry)
    plans.apply_plan(user, next_plan, persist_subscription=False, renew=True)
    plans.sync_subscription(db, user, next_plan)
    db.commit()
    db.expire_all()

    saved = db.get(User, user.id)
    assert saved.plan == next_plan
    assert saved.plan_expires_at == expected_expiry
    assert saved.subscription.plan == next_plan
    assert saved.subscription.end_date == expected_expiry


def test_direct_plan_correction_does_not_add_unused_time(db):
    user = user_with_plan(db, plans.PLAN_MONTHLY, TODAY + timedelta(days=8))
    plans.apply_plan(user, plans.PLAN_SEMESTER, persist_subscription=False)
    plans.sync_subscription(db, user, plans.PLAN_SEMESTER)
    db.commit()

    assert user.plan_expires_at == TODAY + timedelta(days=120)
    assert user.subscription.end_date == user.plan_expires_at


def test_free_plan_clears_expiry_even_if_renew_requested(db):
    user = user_with_plan(db, plans.PLAN_MONTHLY, TODAY + timedelta(days=8))
    plans.apply_plan(user, plans.PLAN_FREE, renew=True)
    db.commit()

    assert user.plan == plans.PLAN_FREE
    assert user.plan_expires_at is None


def test_paid_without_expiry_has_no_paid_rights_and_is_persistently_reconciled(db):
    user = user_with_plan(db, plans.PLAN_MONTHLY, None)
    plans.sync_subscription(db, user, plans.PLAN_MONTHLY)
    db.commit()

    assert plans.effective_plan_key(user) == plans.PLAN_FREE
    assert plans.resolve_user_plan(db, user) == plans.PLAN_FREE
    db.expire_all()

    saved = db.get(User, user.id)
    assert saved.plan == plans.PLAN_FREE
    assert saved.plan_expires_at is None
    assert saved.subscription.plan == plans.PLAN_FREE
    assert saved.subscription.end_date is None


def test_valid_paid_expiry_and_owner_exemption_still_work(db):
    user = user_with_plan(db, plans.PLAN_MONTHLY, TODAY)
    assert plans.effective_plan_key(user) == plans.PLAN_MONTHLY
    assert plans.resolve_user_plan(db, user) == plans.PLAN_MONTHLY

    user.email = "2721095772@qq.com"
    user.plan_expires_at = None
    db.commit()
    assert plans.effective_plan_key(user) == plans.PLAN_SEMESTER
    assert plans.resolve_user_plan(db, user) == plans.PLAN_SEMESTER
