from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text

from app import database, models, project_models  # register all models


class AdditiveMigrationTests(TestCase):
    def test_commitment_draft_upgrade_preserves_legacy_snapshots_without_inventing_text(self):
        engine = create_engine("sqlite:///:memory:")
        database.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE stage_commitment_drafts"))
            conn.execute(text("INSERT INTO users (id,email,name,password_hash,capture_kind) VALUES (1,'commitment@test','旧用户','x','moment')"))
            conn.execute(text("INSERT INTO projects (id,user_id,title,status) VALUES (1,1,'原项目','active')"))
            conn.execute(text("INSERT INTO project_stages (id,user_id,project_id,title,position,state) VALUES (1,1,1,'原阶段',0,'current')"))
            conn.execute(text("INSERT INTO stage_commitments (id,user_id,project_id,stage_id,snapshot_json,created_at) VALUES (1,1,1,1,:snapshot,'2026-10-23 09:00:00')"), {"snapshot": '{"outcome":"原交付","tasks":[]}'})
        with patch.object(database, "engine", engine):
            database.ensure_schema(); database.ensure_schema()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT snapshot_json FROM stage_commitments WHERE id=1")).scalar(), '{"outcome":"原交付","tasks":[]}')
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM stage_commitment_drafts")).scalar(), 0)
        engine.dispose()

    def test_practice_upgrade_keeps_work_checklist_and_unknown_history(self):
        engine = create_engine("sqlite:///:memory:")
        database.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            for table, column in [("work_sessions", "practice_snapshot_json"),
                                  ("task_checklist_items", "purpose"), ("task_checklist_items", "not_applicable_reason")]:
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
            conn.execute(text("INSERT INTO users (id,email,name,password_hash,capture_kind) VALUES (1,'practice@test','旧用户','x','moment')"))
            conn.execute(text("INSERT INTO projects (id,user_id,title,status) VALUES (1,1,'原项目','active')"))
            conn.execute(text("INSERT INTO project_tasks (id,user_id,project_id,title,state,execution_role,steps_json,original_estimate_minutes,estimated_minutes,rehearsal_note) VALUES (1,1,1,'原任务','partial','formal','[]',30,45,'原笔记')"))
            conn.execute(text("INSERT INTO task_checklist_items (id,user_id,task_id,text,done,position) VALUES (1,1,1,'原检查',1,3)"))
            conn.execute(text("INSERT INTO work_sessions (id,user_id,project_task_id,kind,source,started_at,ended_at) VALUES (1,1,1,'work','manual','2026-10-21 15:50:00','2026-10-21 16:10:00')"))
        with patch.object(database, "engine", engine):
            database.ensure_schema(); database.ensure_schema()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT original_estimate_minutes,estimated_minutes,rehearsal_note FROM project_tasks")).one(), (30,45,"原笔记"))
            self.assertEqual(conn.execute(text("SELECT text,done,position,purpose,not_applicable_reason FROM task_checklist_items")).one(), ("原检查",1,3,"delivery",None))
            self.assertIsNone(conn.execute(text("SELECT practice_snapshot_json FROM work_sessions")).scalar())
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM task_practices")).scalar(),0)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM stage_commitments")).scalar(),0)
        engine.dispose()

    def test_condition_upgrade_preserves_unknown_start_and_existing_task_facts(self):
        engine = create_engine("sqlite:///:memory:")
        database.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE projects DROP COLUMN execution_state"))
            conn.execute(text("ALTER TABLE projects DROP COLUMN started_at"))
            conn.execute(text("ALTER TABLE project_tasks DROP COLUMN execution_role"))
            conn.execute(text("INSERT INTO users (id,email,name,password_hash,capture_kind) VALUES (1,'legacy@example.test','旧用户','x','moment')"))
            conn.execute(text("INSERT INTO projects (id,user_id,title,status) VALUES (1,1,'旧项目','active')"))
            conn.execute(text("INSERT INTO project_tasks (id,user_id,project_id,title,state,steps_json,original_estimate_minutes,estimated_minutes,rehearsal_note) VALUES (1,1,1,'旧任务','partial','[]',30,45,'原始预演')"))
        with patch.object(database, "engine", engine):
            database.ensure_schema()
            database.ensure_schema()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT execution_state,started_at,status FROM projects WHERE id=1")).one(), (None, None, "active"))
            self.assertEqual(conn.execute(text("SELECT state,original_estimate_minutes,estimated_minutes,rehearsal_note,execution_role FROM project_tasks WHERE id=1")).one(), ("partial", 30, 45, "原始预演", "formal"))
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM start_conditions")).scalar(), 0)
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM execution_condition_events")).scalar(), 0)
        engine.dispose()

    def test_existing_work_intervals_survive_seconds_column_upgrade(self):
        engine = create_engine("sqlite:///:memory:")
        database.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE work_sessions DROP COLUMN planned_seconds"))
            conn.execute(text("INSERT INTO users (id,email,name,password_hash,capture_kind) VALUES (1,'timer@example.test','旧用户','x','moment')"))
            conn.execute(text("INSERT INTO work_sessions (id,user_id,kind,source,started_at,ended_at,planned_minutes) VALUES (8,1,'work','timer','2026-10-19 09:00:00','2026-10-19 09:20:00',20)"))
        with patch.object(database, "engine", engine):
            database.ensure_schema()
            database.ensure_schema()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT planned_minutes,planned_seconds FROM work_sessions WHERE id=8")).one(), (20, None))
        engine.dispose()

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
            self.assertEqual(conn.execute(text("SELECT legacy_todo_id,steps_json,checklist_json,acceptance_criteria FROM daily_tasks WHERE id=9")).one(), (None, None, None, None))
            self.assertEqual(conn.execute(text("SELECT content FROM reading_entries WHERE id=8")).scalar(), "旧阅读")
            self.assertEqual(conn.execute(text("SELECT text FROM daily_todos WHERE id=7")).scalar(), "原待办")
        self.assertTrue(new_tables.issubset(set(inspect(engine).get_table_names())))
        engine.dispose()
