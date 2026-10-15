from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text

from app import database, models, project_models  # register all models


class AdditiveMigrationTests(TestCase):
    def test_legacy_rows_survive_idempotent_project_schema_upgrade(self):
        engine = create_engine("sqlite:///:memory:")
        new_tables = {"goals", "projects", "project_stages", "project_tasks", "task_dependencies",
                      "task_checklist_items", "work_sessions", "time_activity_assessments", "process_templates"}
        database.Base.metadata.create_all(engine, tables=[
            table for table in database.Base.metadata.sorted_tables
            if table.name not in new_tables | {"daily_tasks"}
        ])
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE daily_tasks (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, task_date DATE NOT NULL, text TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))"))
            conn.execute(text("INSERT INTO users (id,email,name,password_hash,capture_kind) VALUES (1,'old@example.test','旧用户','x','moment')"))
            conn.execute(text("INSERT INTO daily_tasks (id,user_id,task_date,text) VALUES (9,1,'2026-10-15','原日程')"))
            conn.execute(text("INSERT INTO reading_entries (id,user_id,entry_date,content) VALUES (8,1,'2026-01-01','旧阅读')"))
            conn.execute(text("INSERT INTO daily_todos (id,user_id,todo_date,text,completed) VALUES (7,1,'2026-10-15','原待办',0)"))
        with patch.object(database, "engine", engine):
            database.ensure_schema()
            database.ensure_schema()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT text,project_task_id FROM daily_tasks WHERE id=9")).one(), ("原日程", None))
            self.assertEqual(conn.execute(text("SELECT content FROM reading_entries WHERE id=8")).scalar(), "旧阅读")
            self.assertEqual(conn.execute(text("SELECT text FROM daily_todos WHERE id=7")).scalar(), "原待办")
        self.assertTrue(new_tables.issubset(set(inspect(engine).get_table_names())))
        engine.dispose()
