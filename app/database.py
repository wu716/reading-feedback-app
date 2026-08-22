import logging

from sqlalchemy import create_engine, MetaData, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

logger = logging.getLogger(__name__)

if settings.is_production:
    DATABASE_URL = settings.effective_database_url
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
else:
    DATABASE_URL = "sqlite:///./app.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
metadata = MetaData()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)


def ensure_schema():
    """为已有数据库补齐新增列。create_all 不会 ALTER 旧表。"""
    create_tables()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    def add_column(table, column, ddl):
        if table not in existing_tables:
            return
        cols = {c["name"] for c in inspector.get_columns(table)}
        if column in cols:
            return
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        logger.info("已为 %s 添加列 %s", table, column)

    add_column("daily_todos", "remind_time", "remind_time VARCHAR(8)")
    add_column("daily_todos", "reminded_at", "reminded_at TIMESTAMP")
    add_column("self_talk_reminder_logs", "detail", "detail TEXT")
