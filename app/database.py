import logging

from sqlalchemy import create_engine, MetaData, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

if settings.is_production:
    DATABASE_URL = settings.effective_database_url
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
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
        pool_pre_ping=True,
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
    """幂等增量升级；本轮 DDL 在一个事务内完成，不重写旧业务行。"""
    from app import models, project_models, stage_schedule_models  # noqa: F401 - register every table

    with engine.begin() as conn:
        Base.metadata.create_all(bind=conn)
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        def add_column(table, column, ddl):
            if table not in existing_tables:
                return
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column in cols:
                return
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
            inspector.clear_cache()
            logger.info("已为 %s 添加列 %s", table, column)

        add_column("daily_todos", "remind_time", "remind_time VARCHAR(8)")
        add_column("daily_todos", "reminded_at", "reminded_at TIMESTAMP")
        add_column("daily_todos", "deleted_at", "deleted_at TIMESTAMP")
        add_column("daily_todos", "updated_at", "updated_at TIMESTAMP")
        add_column("reading_entries", "deleted_at", "deleted_at TIMESTAMP")
        add_column("daily_tasks", "note", "note TEXT")
        add_column("daily_tasks", "action_id", "action_id INTEGER")
        add_column("daily_tasks", "priority", "priority INTEGER DEFAULT 0")
        add_column("daily_tasks", "flow_order", "flow_order INTEGER DEFAULT 0")
        add_column("daily_tasks", "project_task_id", "project_task_id INTEGER REFERENCES project_tasks(id) ON DELETE SET NULL")
        add_column("daily_tasks", "legacy_todo_id", "legacy_todo_id INTEGER REFERENCES daily_todos(id) ON DELETE SET NULL")
        for column in ("steps_json", "checklist_json", "common_problems", "acceptance_criteria"):
            add_column("daily_tasks", column, f"{column} TEXT")
        add_column("work_sessions", "planned_seconds", "planned_seconds INTEGER")
        add_column("work_sessions", "practice_snapshot_json", "practice_snapshot_json TEXT")
        add_column("task_checklist_items", "purpose", "purpose VARCHAR(20) NOT NULL DEFAULT 'delivery'")
        add_column("task_checklist_items", "not_applicable_reason", "not_applicable_reason TEXT")
        add_column("projects", "execution_state", "execution_state VARCHAR(20)")
        add_column("projects", "started_at", "started_at TIMESTAMP")
        add_column("project_stages", "deleted_at", "deleted_at TIMESTAMP")
        add_column("project_tasks", "execution_role", "execution_role VARCHAR(20) NOT NULL DEFAULT 'formal'")
        if "daily_tasks" in existing_tables:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_daily_tasks_project_task_id ON daily_tasks (project_task_id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_daily_tasks_legacy_todo_id ON daily_tasks (legacy_todo_id)"))
        add_column("self_talk_reminder_logs", "detail", "detail TEXT")
        bool_default = "FALSE" if engine.dialect.name == "postgresql" else "0"
        add_column("self_talk_reminder_settings", "reading_reminder_enabled",
                   f"reading_reminder_enabled BOOLEAN DEFAULT {bool_default}")
        add_column("self_talk_reminder_settings", "reading_reminder_time", "reading_reminder_time VARCHAR(8)")
        add_column("self_talk_reminder_settings", "record_reminder_enabled",
                   f"record_reminder_enabled BOOLEAN DEFAULT {bool_default}")
        add_column("self_talk_reminder_settings", "record_reminder_time", "record_reminder_time VARCHAR(8) DEFAULT '21:00'")
        add_column("self_talk_reminder_settings", "record_reminded_on", "record_reminded_on DATE")
        add_column("ebook_notes", "thought_type", "thought_type VARCHAR(20) DEFAULT 'concept'")
        add_column("ebook_notes", "relation_type", "relation_type VARCHAR(30)")
        add_column("users", "phone", "phone VARCHAR(20)")
        add_column("users", "phone_verified", f"phone_verified BOOLEAN DEFAULT {bool_default}")
        add_column("users", "real_name", "real_name VARCHAR(100)")
        add_column("users", "plan_expires_at", "plan_expires_at DATE")
        add_column("users", "token_version", "token_version INTEGER DEFAULT 0")
        add_column("users", "capture_kind", "capture_kind VARCHAR(20) DEFAULT 'moment'")

    # Older installations may contain duplicate phone values. This legacy index
    # is best effort and intentionally separate from the project migration.
    if "users" in existing_tables:
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)"))
        except Exception as exc:
            logger.warning("创建 users.phone 唯一索引失败: %s", exc)
