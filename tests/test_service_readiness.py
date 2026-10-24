from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from app import health


def client_for_probe():
    app = FastAPI()
    app.include_router(health.router)
    return TestClient(app)


def test_ready_queries_database_without_creating_tables(monkeypatch):
    probe = create_engine("sqlite://", poolclass=StaticPool,
                          connect_args={"check_same_thread": False})
    monkeypatch.setattr(health, "readiness_engine", lambda: probe)
    with client_for_probe() as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}
    assert response.headers["cache-control"] == "no-store"
    with probe.connect() as connection:
        assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all() == []
    probe.dispose()


def test_unavailable_database_returns_503_without_secrets(monkeypatch):
    class BrokenProbe:
        def connect(self):
            raise OperationalError("SELECT 1", {}, RuntimeError("synthetic-secret-must-not-leak"))
    monkeypatch.setattr(health, "readiness_engine", lambda: BrokenProbe())
    with client_for_probe() as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": "unavailable"}}
    assert "synthetic-secret" not in response.text


def test_recovered_database_becomes_ready_on_next_probe(monkeypatch):
    probe = create_engine("sqlite://", poolclass=StaticPool,
                          connect_args={"check_same_thread": False})
    class IntermittentProbe:
        attempts = 0
        def connect(self):
            self.attempts += 1
            if self.attempts == 1:
                raise OperationalError("SELECT 1", {}, RuntimeError("unavailable"))
            return probe.connect()
    source = IntermittentProbe()
    monkeypatch.setattr(health, "readiness_engine", lambda: source)
    with client_for_probe() as client:
        assert client.get("/ready").status_code == 503
        assert client.get("/ready").status_code == 200
    probe.dispose()
