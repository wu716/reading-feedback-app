"""Registration accepts either contact method without consuming invites on errors."""

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import InviteCode, User
from app.routers.auth import router as auth_router, settings


def make_app(monkeypatch):
    monkeypatch.setattr(settings, "registration_open", True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(InviteCode(code="7314", plan="free", expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
        db.commit()

    app = FastAPI()
    app.include_router(auth_router, prefix="/api")

    def db_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    return engine, TestClient(app)


def signup(client, account, *, field="account", ip="198.51.100.10"):
    return client.post(
        "/api/auth/register",
        json={field: account, "name": "测试用户", "password": "testing123", "invite_code": "7314"},
        headers={"X-Forwarded-For": ip},
    )


def test_email_registration_and_login(monkeypatch):
    engine, client = make_app(monkeypatch)
    try:
        created = signup(client, "  Reader@Example.com  ")
        assert created.status_code == 201, created.text
        assert created.json()["email"] == "reader@example.com"
        assert created.json()["phone"] is None
        assert client.post(
            "/api/auth/login",
            json={"account": "READER@example.com", "password": "testing123"},
            headers={"X-Forwarded-For": "198.51.100.11"},
        ).status_code == 200
    finally:
        client.close()
        engine.dispose()


def test_phone_registration_and_login(monkeypatch):
    engine, client = make_app(monkeypatch)
    try:
        created = signup(client, "13900000000", ip="198.51.100.12")
        assert created.status_code == 201, created.text
        assert created.json()["phone"] == "13900000000"
        assert created.json()["email"] is None
        assert client.post(
            "/api/auth/login",
            json={"account": "13900000000", "password": "testing123"},
            headers={"X-Forwarded-For": "198.51.100.13"},
        ).status_code == 200
    finally:
        client.close()
        engine.dispose()


def test_duplicate_email_and_invalid_account_keep_invite_available(monkeypatch):
    engine, client = make_app(monkeypatch)
    try:
        with Session(engine) as db:
            db.add(User(email="reader@example.com", name="Existing", password_hash="unused"))
            db.commit()
        duplicate = signup(client, "Reader@EXAMPLE.com", ip="198.51.100.14")
        assert duplicate.status_code == 400
        assert duplicate.json()["detail"] == "该邮箱已注册"
        invalid = signup(client, "bad@email", ip="198.51.100.15")
        assert invalid.status_code == 400
        with Session(engine) as db:
            assert db.query(InviteCode).filter_by(code="7314").one().used_at is None
        created = signup(client, "new@example.com", field="email", ip="198.51.100.16")
        assert created.status_code == 201, created.text
    finally:
        client.close()
        engine.dispose()
