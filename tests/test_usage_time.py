from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import get_current_active_user, get_current_owner
from app.database import Base, get_db
from app.models import DailyAppUsage, User
from app.routers.owner import router as owner_router
from app.routers.usage_time import router as usage_router
from app.usage_time import clear_stale_usage_pulses, purge_expired_usage, record_active_pulse

BEIJING = ZoneInfo("Asia/Shanghai")


def make_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            User(id=1, email="2721095772@qq.com", name="Owner", password_hash="unused"),
            User(id=2, email="reader@example.test", name="Reader", phone="13800000002", password_hash="unused"),
            User(id=3, email="deleted@example.test", name="Deleted", password_hash="unused", deleted_at=datetime.now(BEIJING)),
        ])
        db.commit()
    return engine


def test_pulses_merge_overlapping_sessions_and_split_at_beijing_midnight():
    engine = make_db()
    try:
        with Session(engine) as db:
            before_midnight = datetime(2026, 10, 25, 23, 59, 45, tzinfo=BEIJING)
            record_active_pulse(db, 2, before_midnight)
            record_active_pulse(db, 2, before_midnight + timedelta(seconds=20))
            record_active_pulse(db, 2, before_midnight + timedelta(seconds=40))
            db.commit()

            rows = db.query(DailyAppUsage).filter_by(user_id=2).order_by(DailyAppUsage.usage_date).all()
            assert [(row.usage_date, row.active_seconds) for row in rows] == [
                (date(2026, 10, 25), 15),
                (date(2026, 10, 26), 25),
            ]
    finally:
        engine.dispose()


def test_long_pulse_gap_is_not_counted_and_stale_pulse_timestamp_is_cleared():
    engine = make_db()
    try:
        now = datetime(2026, 10, 26, 12, 0, tzinfo=BEIJING)
        with Session(engine) as db:
            record_active_pulse(db, 2, now)
            record_active_pulse(db, 2, now + timedelta(seconds=60))
            record_active_pulse(db, 2, now + timedelta(seconds=90))
            db.commit()

            row = db.query(DailyAppUsage).filter_by(user_id=2, usage_date=now.date()).one()
            assert row.active_seconds == 30
            assert clear_stale_usage_pulses(db, now + timedelta(seconds=136)) == 1
            db.commit()
            db.refresh(row)
            assert row.last_pulse_at is None
    finally:
        engine.dispose()


def test_visible_resume_resets_baseline_without_counting_background_time():
    engine = make_db()
    try:
        now = datetime(2026, 10, 26, 12, 0, tzinfo=BEIJING)
        with Session(engine) as db:
            record_active_pulse(db, 2, now)
            record_active_pulse(db, 2, now + timedelta(seconds=30))
            record_active_pulse(db, 2, now + timedelta(seconds=40), reset_baseline=True)
            record_active_pulse(db, 2, now + timedelta(seconds=70))
            db.commit()
            row = db.query(DailyAppUsage).filter_by(user_id=2, usage_date=now.date()).one()
            assert row.active_seconds == 60
    finally:
        engine.dispose()


def test_retention_keeps_today_and_previous_89_days_only():
    engine = make_db()
    today = date(2026, 10, 26)
    try:
        with Session(engine) as db:
            db.add_all([
                DailyAppUsage(user_id=2, usage_date=today - timedelta(days=90), active_seconds=60),
                DailyAppUsage(user_id=2, usage_date=today - timedelta(days=89), active_seconds=60),
                DailyAppUsage(user_id=2, usage_date=today, active_seconds=60),
            ])
            db.commit()
            assert purge_expired_usage(db, today) == 1
            db.commit()
            dates = [row[0] for row in db.query(DailyAppUsage.usage_date).order_by(DailyAppUsage.usage_date).all()]
            assert dates == [today - timedelta(days=89), today]
    finally:
        engine.dispose()


def test_pulse_requires_login_and_owner_report_only_shows_live_users():
    engine = make_db()
    app = FastAPI()
    app.include_router(owner_router)
    app.include_router(usage_router, prefix="/api")

    def db_override():
        with Session(engine) as db:
            yield db

    def owner_override(request: Request, db: Session = Depends(get_db)):
        if request.headers.get("X-Test-Owner") != "1":
            raise HTTPException(status_code=403, detail="仅站长可访问")
        return db.get(User, 1)

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_owner] = owner_override
    client = TestClient(app)
    try:
        unauthenticated = client.post("/api/usage/pulse")
        assert unauthenticated.status_code in (401, 403)
        app.dependency_overrides[get_current_active_user] = lambda: User(
            id=2, email="reader@example.test", name="Reader", password_hash="unused"
        )
        assert client.post("/api/usage/pulse").status_code == 204
        with Session(engine) as db:
            today = datetime.now(BEIJING).date()
            current = db.query(DailyAppUsage).filter_by(user_id=2, usage_date=today).one()
            current.active_seconds = 3600
            db.add(DailyAppUsage(user_id=3, usage_date=today, active_seconds=900))
            db.commit()

        assert client.get("/owner/usage?days=7").status_code == 403
        response = client.get("/owner/usage?days=7", headers={"X-Test-Owner": "1"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["retention_days"] == 90
        assert body["selected_summary"]["active_seconds"] >= 3600
        assert body["users"][0]["account"] == "13800000002"
        assert all("deleted@example.test" not in row["account"] for row in body["users"])
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
