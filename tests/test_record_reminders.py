"""Daily record delivery, opt-in migration and account-scoped reminder behavior."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import database, project_models  # noqa: F401
from app.auth import get_current_user
from app.database import Base, get_db
from app.models import User, SelfTalkReminderSetting, SelfTalkReminderLog, DailyTodo
from app.routers import self_talk_reminders as routes, long_term_details as ledger
from app.self_talk import reminder_service as service


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="daily@example.test", name="记录用户", password_hash="test")
        other = User(email="other@example.test", name="另一用户", password_hash="test")
        db.add_all([user, other]); db.commit()
        identity = {"user": user}
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: identity["user"]
        with patch.object(service.ReminderService, "send_email_notification", return_value=True) as mail:
            with TestClient(app) as client:
                yield db, user, other, identity, client, mail
    engine.dispose()


def enable(db, user, **overrides):
    setting = service.ReminderService.get_or_create_setting(db, user.id)
    setting.record_reminder_enabled = True
    for key, value in overrides.items():
        setattr(setting, key, value)
    db.commit()
    return setting


def due_now():
    return datetime.now(service.BEIJING_TZ).replace(hour=21, minute=0, second=0, microsecond=0)


def confirm(db, user, day, **overrides):
    payload = dict(day_confirmed=True, attention_confirmed=True, expense_confirmed=True)
    payload.update(overrides)
    current = ledger.get_day(day=day, user=user, db=db)
    return ledger.save_day(ledger.LedgerInput(revision=current["revision"], **payload), day=day, user=user, db=db)


def test_defaults_and_legacy_preferences_do_not_opt_users_in(ctx):
    db, user, _, _, client, mail = ctx
    setting = service.ReminderService.get_or_create_setting(db, user.id)
    setting.daily_reminder_enabled = True
    setting.daily_reminder_time = "08:00"
    db.commit()
    response = client.get("/api/reminders/settings")
    assert response.status_code == 200
    assert response.json()["record_reminder_enabled"] is False
    assert response.json()["record_reminder_time"] == "21:00"
    assert not service.check_record_reminders(db, now=due_now())
    mail.assert_not_called()


def test_blocked_reminder_query_does_not_block_async_health(ctx, monkeypatch):
    _, _, _, _, client, _ = ctx
    entered, release = Event(), Event()

    def slow_status(*args):
        entered.set()
        assert release.wait(3)
        return {"record_date": datetime.now(service.BEIJING_TZ).date(), "record_complete": False}

    monkeypatch.setattr(routes, "record_status", slow_status)
    async def health_probe():
        return {"ok": True}

    client.app.add_api_route("/health-probe", health_probe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(client.get, "/api/reminders/settings")
        assert entered.wait(2)
        probe = pool.submit(client.get, "/health-probe")
        try:
            assert probe.result(timeout=1).json() == {"ok": True}
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 200


def test_settings_read_commits_expired_timer_settlement(ctx):
    from app.project_models import WorkSession

    db, user, _, _, client, _ = ctx
    row = WorkSession(user_id=user.id, kind="work", source="timer", label="到期工作片",
                      started_at=datetime.utcnow() - timedelta(minutes=30), planned_minutes=20)
    db.add(row)
    db.commit()
    session_id = row.id
    deadline = row.started_at + timedelta(minutes=20)
    assert client.get("/api/reminders/settings").status_code == 200
    db.rollback()
    db.expire_all()
    assert db.get(WorkSession, session_id).ended_at == deadline
    assert db.query(WorkSession).filter_by(user_id=user.id, kind="break").count() == 1
    assert client.get("/api/reminders/settings").status_code == 200
    assert db.query(WorkSession).filter_by(user_id=user.id, kind="break").count() == 1


@pytest.mark.parametrize("value", ["24:00", "21:60", "9:00", "", "21:00:00", "noon"])
def test_invalid_times_are_rejected_without_changing_settings(ctx, value):
    _, _, _, _, client, _ = ctx
    assert client.post("/api/reminders/settings", json={"record_reminder_time": value}).status_code == 422


def test_settings_roundtrip_and_partial_updates_preserve_preferences(ctx):
    _, _, _, _, client, _ = ctx
    response = client.post("/api/reminders/settings", json={"record_reminder_enabled": True, "record_reminder_time": "22:15"})
    assert response.status_code == 200
    assert response.json()["record_reminder_time"] == "22:15"
    client.post("/api/reminders/settings", json={"email_notification": False})
    data = client.patch("/api/reminders/settings", json={"browser_notification": False}).json()
    assert data["record_reminder_enabled"] and data["record_reminder_time"] == "22:15"
    assert data["email_notification"] is False


def test_due_time_and_atomic_once_per_day_claim_survive_reopening_and_toggling(ctx):
    db, user, _, _, _, mail = ctx
    setting = enable(db, user)
    now = due_now()
    assert service.check_record_reminders(db, now=now - timedelta(minutes=1)) == 0
    assert service.check_record_reminders(db, now=now.astimezone(timezone.utc)) == 1
    assert service.check_record_reminders(db, now=now + timedelta(minutes=1)) == 0
    setting.record_reminder_enabled = False; db.commit()
    setting.record_reminder_enabled = True; setting.record_reminder_time = "20:00"; db.commit()
    assert service.check_record_reminders(db, now=now) == 0
    assert service.check_record_reminders(db, now=now + timedelta(days=1)) == 1
    assert db.query(SelfTalkReminderLog).count() == 2
    assert mail.call_count == 2


def test_only_all_confirmed_sections_suppress_the_reminder_and_accounts_are_isolated(ctx):
    db, user, other, _, _, _ = ctx
    enable(db, user); enable(db, other)
    now = due_now()
    confirm(db, user, now.date())
    confirm(db, other, now.date(), expense_confirmed=False)
    assert service.check_record_reminders(db, now=now) == 1
    assert db.query(SelfTalkReminderLog).filter_by(reminder_type="daily_record").one().user_id == other.id


@pytest.mark.parametrize("field", ["is_enabled", "is_active"])
def test_disabled_reminders_and_inactive_accounts_are_skipped(ctx, field):
    db, user, _, _, _, _ = ctx
    setting = enable(db, user)
    setattr(user if field == "is_active" else setting, field, False); db.commit()
    assert service.check_record_reminders(db, now=due_now()) == 0


def test_pending_opens_today_hides_completed_and_stale_records_and_scopes_dismiss(ctx, monkeypatch):
    db, user, other, identity, client, _ = ctx
    enable(db, user, browser_notification=False, email_notification=False)
    now = due_now()
    monkeypatch.setattr(routes, "check_record_reminders", lambda db, user_id: service.check_record_reminders(db, user_id, now=now))
    first = client.get("/api/reminders/pending").json()
    notice = first["notifications"][0]
    assert first["pending_count"] == 1
    assert notice["action_url"] == "/static/index.html?record=today#daily-feedback"
    assert notice["system_notification"] is False
    identity["user"] = other
    assert client.post(f'/api/reminders/dismiss/{notice["log_id"]}').status_code == 404
    assert not client.get("/api/reminders/pending").json()["notifications"]
    identity["user"] = user
    confirm(db, user, now.date())
    reports = client.get("/api/reminders/pending").json()["notifications"]
    assert {n["reminder_type"] for n in reports} == {"feedback_report"}
    for report in reports:
        assert client.post(f'/api/reminders/dismiss/{report["log_id"]}').status_code == 200
    assert not client.get("/api/reminders/pending").json()["notifications"]
    assert client.get("/api/reminders/settings").json()["record_complete"] is True
    confirm(db, user, now.date(), expense_confirmed=False)
    assert client.get("/api/reminders/pending").json()["pending_count"] == 1
    assert client.post(f'/api/reminders/dismiss/{notice["log_id"]}?action_taken=true').status_code == 200
    assert not client.get("/api/reminders/pending").json()["notifications"]
    log = db.get(SelfTalkReminderLog, notice["log_id"])
    log.dismissed_at = None; log.action_taken = False
    log.detail = (now.date() - timedelta(days=1)).isoformat(); db.commit()
    assert not client.get("/api/reminders/pending").json()["notifications"]


def test_daily_and_todo_reminders_coexist_and_old_daily_logs_stay_hidden(ctx, monkeypatch):
    db, user, _, _, client, _ = ctx
    enable(db, user)
    now = due_now()
    db.add(DailyTodo(user_id=user.id, todo_date=now.date() - timedelta(days=1), text="已有待办", remind_time="08:00"))
    db.add(SelfTalkReminderLog(user_id=user.id, reminder_type="daily", detail="旧功能")); db.commit()
    monkeypatch.setattr(routes, "check_record_reminders", lambda db, user_id: service.check_record_reminders(db, user_id, now=now))
    assert {n["reminder_type"] for n in client.get("/api/reminders/pending").json()["notifications"]} == {"todo", "daily_record"}
    assert {n["reminder_type"] for n in client.get("/api/reminders/logs").json()["logs"]} == {"todo", "daily_record"}


def test_additive_migration_preserves_old_preferences_and_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for name in ("record_reminder_enabled", "record_reminder_time", "record_reminded_on"):
            conn.execute(text(f"ALTER TABLE self_talk_reminder_settings DROP COLUMN {name}"))
        conn.execute(text("INSERT INTO users (id,email,name,password_hash,capture_kind) VALUES (1,'old@example.test','旧用户','x','moment')"))
        conn.execute(text("INSERT INTO self_talk_reminder_settings (user_id,is_enabled,daily_reminder_enabled,daily_reminder_time) VALUES (1,1,1,'08:00')"))
    with patch.object(database, "engine", engine):
        database.ensure_schema(); database.ensure_schema()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT daily_reminder_enabled,daily_reminder_time,record_reminder_enabled,record_reminder_time,record_reminded_on FROM self_talk_reminder_settings")).one() == (1, "08:00", 0, "21:00", None)
    engine.dispose()
