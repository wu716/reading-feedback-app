"""Read-only readiness probe with no migrations or extra background service."""
from functools import lru_cache

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.database import engine

router = APIRouter()


@lru_cache(maxsize=1)
def readiness_engine():
    # Close every probe connection immediately; no extra idle DB connection.
    # Separate short timeouts keep an exhausted application pool from hiding failure.
    connect_args = {}
    if engine.dialect.name == "postgresql":
        connect_args = {"connect_timeout": 3, "options": "-c statement_timeout=2000"}
    elif engine.dialect.name == "sqlite":
        connect_args = {"timeout": 2}
    return create_engine(engine.url, poolclass=NullPool, connect_args=connect_args)


@router.get("/ready", include_in_schema=False)
def readiness():
    # FastAPI runs this synchronous endpoint in its existing thread pool.
    try:
        with readiness_engine().connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        # Never return exception text, hostnames, credentials or database URLs.
        return JSONResponse(
            {"status": "not_ready", "checks": {"database": "unavailable"}},
            status_code=503, headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        {"status": "ready", "checks": {"database": "ok"}},
        headers={"Cache-Control": "no-store"},
    )
