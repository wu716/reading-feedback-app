"""Real router contracts using only synthetic in-memory business rows."""
import io
import json
import unittest
import zipfile
from datetime import datetime, timedelta

import test_projects as fixture
from app import commitment_service
from app.models import DailyTask, DailyTodo, SelfTalkReminderLog, User
from app.project_models import (
    Project, ProjectStage, ProjectTask, ProjectDeletion, ExecutionPlan, WorkSession,
    ProcessTemplate, Goal, StartCondition, PlanningCycle, FeedbackOccurrence, FeedbackDelivery,
)
from app.practice_service import today


class ProjectDeletionTests(unittest.TestCase):
    setUp = fixture.ProjectFlowTests.setUp
    tearDown = fixture.ProjectFlowTests.tearDown
    req = fixture.ProjectFlowTests.req
    task = fixture.ProjectFlowTests.task

    def fresh(self, title="整理资料"):
        p = self.req("POST", "", {"title": title}).json()
        data = next(item for item in self.req("GET", "/overview").json()["projects"] if item["id"] == p["id"])
        return p, data["stages"][0], data["stages"][1]

    def preview(self, kind, target_id):
        r = self.req("POST", "/deletions/preview", {"kind": kind, "target_id": target_id})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def confirm(self, row, reason=""):
        return self.req("POST", f"/deletions/{row['id']}/confirm", {"reason": reason})

    def delete(self, kind, target_id):
        row = self.preview(kind, target_id)
        self.assertFalse(row["impact"]["requires_wait"])
        r = self.confirm(row)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def restore(self, row, **fields):
        return self.req("POST", f"/deletions/{row['id']}/restore", fields)

    def credit(self, row):
        with self.Session() as db:
            batch = db.get(ProjectDeletion, row["id"])
            start = datetime.utcnow()
            for second in range(32):
                commitment_service.heartbeat(db, batch, "deletion-window-123456", True, start + timedelta(seconds=second))
            db.commit()

    def test_task_deletion_keeps_work_completed_daily_and_independent_records(self):
        project, stage, _ = self.fresh()
        task = self.task(project, stage, "扫描合同")
        with self.Session() as db:
            todo = DailyTodo(user_id=1, text="扫描合同", completed=False, todo_date=today(), remind_time="20:00")
            db.add(todo); db.flush()
            parent = DailyTask(user_id=1, text="扫描合同", task_date=today(), project_task_id=task["id"], legacy_todo_id=todo.id)
            db.add(parent); db.flush()
            child = DailyTask(user_id=1, text="分卷扫描", task_date=today(), parent_id=parent.id)
            completed_child = DailyTask(user_id=1, text="已扫描第一页", task_date=today(), parent_id=parent.id, completed=True)
            completed = DailyTask(user_id=1, text="昨天完成的扫描", task_date=today()-timedelta(days=1), project_task_id=task["id"], completed=True)
            independent = DailyTask(user_id=1, text="取快递", task_date=today())
            db.add_all([child, completed_child, completed, independent]); db.flush()
            work = WorkSession(user_id=1, project_task_id=task["id"], daily_task_id=parent.id, label="扫描合同", kind="work", source="timer",
                started_at=datetime.utcnow()-timedelta(minutes=40), ended_at=datetime.utcnow()-timedelta(minutes=5), planned_minutes=40)
            db.add(work); db.flush()
            db.add(ExecutionPlan(user_id=1, queue_json=json.dumps([f"project:{task['id']}", f"daily:{child.id}", f"daily:{independent.id}"]),
                work_minutes=20, break_minutes=5, paused_session_id=work.id, remaining_seconds=300))
            db.commit()
            ids = parent.id, child.id, completed.id, independent.id, todo.id
        row = self.delete("task", task["id"])
        self.assertEqual(row["impact"]["daily"], 2)
        self.assertEqual(row["impact"]["sessions"], 1)
        sessions = self.req("GET", "/sessions").json()["items"]
        self.assertEqual(sessions[0]["duration_minutes"], 35)
        self.assertTrue(sessions[0]["source_deleted"])
        # Reading a schedule imports old todos; deletion must not resurrect either identity.
        response = self.client.get("/api/schedule", params={"task_date": str(today())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("已扫描第一页", [t["text"] for t in response.json()["tasks"]])
        history = self.client.get("/api/schedule", params={"task_date": str(today()-timedelta(days=1))})
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()["tasks"][0]["text"], "昨天完成的扫描")
        with self.Session() as db:
            for row_id in ids[:2]: self.assertIsNotNone(db.get(DailyTask, row_id).deleted_at)
            for row_id in ids[2:4]: self.assertIsNone(db.get(DailyTask, row_id).deleted_at)
            self.assertIsNotNone(db.get(DailyTodo, ids[4]).deleted_at)
            self.assertIsNone(db.get(DailyTodo, ids[4]).remind_time)
            plan = db.get(ExecutionPlan, 1)
            self.assertEqual(json.loads(plan.queue_json), [f"daily:{ids[3]}"])
            self.assertIsNone(plan.paused_session_id)
        self.assertEqual(self.restore(row).status_code, 200)
        trash = self.req("GET", "/deletions").json()["items"]
        self.assertEqual(len(trash[0]["pending_daily"]), 2)
        self.assertIsNotNone(trash[0]["restored_at"])
        self.assertEqual(self.restore(row, with_daily=True).status_code, 200)
        self.assertEqual(self.req("GET", "/deletions").json()["items"], [])
        with self.Session() as db:
            self.assertIsNone(db.get(DailyTodo, ids[4]).remind_time)
            self.assertEqual(json.loads(db.get(ExecutionPlan, 1).queue_json), [f"daily:{ids[3]}"])

    def test_stage_restoration_does_not_resurrect_a_previously_deleted_task(self):
        p, stage, following = self.fresh()
        first = self.task(p, following, "先前单独删除")
        second = self.task(p, following, "随阶段删除")
        earlier = self.delete("task", first["id"])
        batch = self.delete("stage", following["id"])
        self.assertEqual(batch["impact"]["tasks"], 1)
        self.assertEqual(self.restore(earlier).status_code, 409)
        self.assertEqual(self.restore(batch).status_code, 200)
        with self.Session() as db:
            self.assertIsNotNone(db.get(ProjectTask, first["id"]).deleted_at)
            self.assertIsNone(db.get(ProjectTask, second["id"]).deleted_at)
            self.assertEqual(db.get(ProjectStage, stage["id"]).state, "current")
        self.assertEqual(self.restore(earlier).status_code, 200)

    def test_project_deletion_keeps_goals_templates_feedback_and_cancels_outbox(self):
        p, stage, _ = self.fresh()
        task = self.task(p, stage, "原任务")
        with self.Session() as db:
            goal = Goal(user_id=1, title="独立目标")
            template = ProcessTemplate(user_id=1, title="通用流程")
            db.add_all([goal, template]); db.flush()
            db.get(Project, p["id"]).goal_id = goal.id
            cycle = PlanningCycle(user_id=1, project_id=p["id"], start_date=today(), end_date=today(), horizon="week", expected_result="整理好", plan_json="{}")
            db.add(cycle); db.flush()
            occurrence = FeedbackOccurrence(user_id=1, project_id=p["id"], cycle_id=cycle.id, due_date=today(), reminders_enabled=True, requirement_json='{"reminders":true}')
            log = SelfTalkReminderLog(user_id=1, reminder_type="project_feedback")
            db.add_all([occurrence, log]); db.flush()
            delivery = FeedbackDelivery(user_id=1, event_key="delete-test", occurrence_id=occurrence.id, log_id=log.id, title="原提醒", message="原消息", email_status="pending")
            db.add(delivery); db.commit()
            ids = occurrence.id, log.id, goal.id, template.id
        batch = self.delete("project", p["id"])
        self.assertEqual(self.req("GET", "/overview").json()["projects"], [])
        with self.Session() as db:
            self.assertFalse(db.get(FeedbackOccurrence, ids[0]).reminders_enabled)
            self.assertIsNotNone(db.get(SelfTalkReminderLog, ids[1]).dismissed_at)
            self.assertEqual(db.query(FeedbackDelivery).one().email_status, "cancelled")
            self.assertIsNone(db.get(Goal, ids[2]).deleted_at)
            self.assertIsNone(db.get(ProcessTemplate, ids[3]).deleted_at)
            self.assertEqual(db.query(FeedbackOccurrence).count(), 1)
        self.assertEqual(self.restore(batch).status_code, 200)
        with self.Session() as db:
            self.assertIsNone(db.get(ProjectTask, task["id"]).deleted_at)
            self.assertFalse(db.get(FeedbackOccurrence, ids[0]).reminders_enabled)

    def test_external_project_and_task_conditions_block_deletion_and_never_auto_satisfy(self):
        first, stage, _ = self.fresh("原项目")
        target = self.task(first, stage, "原成果")
        other, other_stage, _ = self.fresh("后续项目")
        dependent = self.task(other, other_stage, "等成果")
        for kind, target_id in [("task", target["id"]), ("project", first["id"])]:
            result = self.req("POST", f"/conditions/task/{dependent['id']}", {"title": "需要原成果", "kind": kind, "target_id": target_id})
            self.assertEqual(result.status_code, 200, result.text)
        preview = self.preview("project", first["id"])
        self.assertEqual(len(preview["impact"]["affected"]), 2)
        self.assertEqual(self.confirm(preview).status_code, 409)
        with self.Session() as db:
            self.assertIsNone(db.get(Project, first["id"]).deleted_at)
            for c in db.query(StartCondition): c.removed_at = datetime.utcnow()
            db.commit()
        self.assertEqual(self.confirm(preview).status_code, 409)  # changed preview must be reviewed again
        self.assertEqual(self.confirm(self.preview("project", first["id"])).status_code, 200)

    def test_started_commitment_requires_stop_reason_server_pause_and_idempotency(self):
        p, stage, _ = self.fresh()
        task = self.task(p, stage, "正式工作")
        self.assertEqual(self.req("POST", f"/{p['id']}/execution-state", {"state": "started", "reason": "条件已具备"}).status_code, 200)
        work = self.req("POST", "/sessions/start", {"project_task_id": task["id"]}).json()
        first = self.preview("task", task["id"])
        self.assertTrue(first["impact"]["requires_wait"])
        self.assertEqual(first["impact"]["running"][0]["id"], work["id"])
        self.assertEqual(self.confirm(first, "条件改变").status_code, 409)
        self.req("POST", f"/sessions/{work['id']}/stop", {})
        row = self.preview("task", task["id"])
        self.assertNotEqual(row["id"], first["id"])
        self.assertEqual(self.confirm(row, "条件改变").status_code, 409)
        self.credit(row)
        self.assertEqual(self.confirm(row, " ").status_code, 409)
        self.assertEqual(self.confirm(row, "条件改变").status_code, 200)
        sessions = self.req("GET", "/sessions").json()["items"]
        self.assertEqual(sessions[0]["label"], "正式工作")
        self.assertTrue(sessions[0]["source_deleted"])
        self.assertEqual(self.confirm(row, "重复点击").status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.get(ProjectDeletion, row["id"]).reason, "条件改变")
            self.assertEqual(db.query(WorkSession).count(), 1)
            self.assertIsNotNone(db.get(WorkSession, work["id"]).ended_at)

    def test_hidden_time_gaps_and_other_windows_do_not_credit_the_pause(self):
        p, stage, _ = self.fresh()
        self.task(p, stage, "正式工作")
        self.req("POST", f"/{p['id']}/execution-state", {"state": "started", "reason": "开始"})
        row = self.preview("project", p["id"])
        with self.Session() as db:
            item = db.get(ProjectDeletion, row["id"])
            start = datetime.utcnow()
            commitment_service.heartbeat(db, item, "window-one-token-123", True, start)
            commitment_service.heartbeat(db, item, "window-one-token-123", False, start+timedelta(seconds=2))
            commitment_service.heartbeat(db, item, "window-one-token-123", True, start+timedelta(seconds=100))
            self.assertEqual(item.elapsed_ms, 0)
            with self.assertRaises(Exception):
                commitment_service.heartbeat(db, item, "window-two-token-456", True, start+timedelta(seconds=101))
        self.assertEqual(self.req("POST", f"/deletions/{row['id']}/visible", {"token": "window-one-token-123", "visible": True}, user=2).status_code, 404)

    def test_changed_scope_cannot_be_confirmed_from_an_old_preview(self):
        p, stage, _ = self.fresh()
        self.task(p, stage, "原任务")
        row = self.preview("project", p["id"])
        self.task(p, stage, "刚刚新增")
        self.assertEqual(self.confirm(row).status_code, 409)
        with self.Session() as db: self.assertIsNone(db.get(Project, p["id"]).deleted_at)

    def test_recovery_of_past_schedules_is_atomic_and_requires_a_new_date(self):
        p, stage, _ = self.fresh()
        task = self.task(p, stage, "过去的任务")
        with self.Session() as db:
            todo = DailyTodo(user_id=1, text="过去的任务", todo_date=today()-timedelta(days=3), remind_time="08:00")
            db.add(todo); db.flush()
            d = DailyTask(user_id=1, project_task_id=task["id"], text="过去的任务", task_date=todo.todo_date, legacy_todo_id=todo.id)
            db.add(d); db.commit(); daily_id,todo_id=d.id,todo.id
        row = self.delete("task", task["id"])
        self.assertEqual(self.restore(row, with_daily=True).status_code, 400)
        with self.Session() as db: self.assertIsNotNone(db.get(ProjectTask, task["id"]).deleted_at)
        self.assertEqual(self.restore(row, with_daily=True, past_date=str(today())).status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.get(DailyTask, daily_id).task_date, today())
            self.assertEqual(db.get(DailyTodo, todo_id).todo_date, today())
            self.assertIsNone(db.get(DailyTodo, todo_id).remind_time)

    def test_restore_current_stage_requires_explicit_resolution_of_conflict(self):
        p, stage, following = self.fresh()
        self.task(p, stage, "草稿任务")
        row = self.delete("stage", stage["id"])
        activated = self.req("POST", f"/stages/{following['id']}/activate", {"decision": "close", "reason": "原阶段已删除，核对新范围"})
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertEqual(self.restore(row).status_code, 409)
        self.assertEqual(self.restore(row, stage_as_next=True).status_code, 200)
        with self.Session() as db:
            self.assertEqual(db.get(ProjectStage, stage["id"]).state, "next")
            self.assertEqual(db.query(ProjectStage).filter_by(project_id=p["id"], state="current").filter(ProjectStage.deleted_at.is_(None)).count(), 1)

    def test_account_boundaries_parent_recovery_and_portable_archives(self):
        p, stage, _ = self.fresh()
        task = self.task(p, stage, "自己的任务")
        self.assertEqual(self.req("POST", "/deletions/preview", {"kind": "project", "target_id": p["id"]}, user=2).status_code, 404)
        child = self.delete("task", task["id"])
        parent = self.delete("project", p["id"])
        self.assertEqual(self.restore(child).status_code, 409)
        for action in ("confirm", "restore"):
            self.assertEqual(self.req("POST", f"/deletions/{parent['id']}/{action}", {}, user=2).status_code, 404)
        self.assertEqual(self.req("GET", "/deletions", user=2).json()["items"], [])
        with self.Session() as db:
            from app.backup import build_backup_zip
            from app.user_export import build_user_export_zip
            archive = zipfile.ZipFile(io.BytesIO(build_backup_zip(db)))
            self.assertIn("project_deletions.csv", archive.namelist())
            own = zipfile.ZipFile(io.BytesIO(build_user_export_zip(db, db.get(User, 1))))
            other = zipfile.ZipFile(io.BytesIO(build_user_export_zip(db, db.get(User, 2))))
            self.assertEqual(len(json.loads(own.read("project_deletions.json"))), 2)
            self.assertEqual(json.loads(other.read("project_deletions.json")), [])
        self.assertEqual(self.restore(parent).status_code, 200)
        with self.Session() as db: self.assertIsNotNone(db.get(ProjectTask, task["id"]).deleted_at)

    def test_deleted_stage_rejects_stale_task_creation_and_template_targets(self):
        p, _, following = self.fresh()
        self.delete("stage", following["id"])
        result = self.req("POST", f"/{p['id']}/tasks", {"title": "旧页面新增", "stage_id": following["id"]})
        self.assertEqual(result.status_code, 404)

    def test_many_past_occurrences_can_recover_separately_without_duplicate_dates(self):
        from sqlalchemy.orm import sessionmaker
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        p, stage, _ = self.fresh()
        task = self.task(p, stage, "每天原计划")
        with self.Session() as db:
            rows = [DailyTask(user_id=1, project_task_id=task["id"], task_date=today()-timedelta(days=i), text="每天原计划") for i in (2, 3)]
            db.add_all(rows); db.commit(); ids=[d.id for d in rows]
        batch = self.delete("task", task["id"])
        self.assertEqual(self.restore(batch, with_daily=True, past_date=str(today())).status_code, 409)
        with self.Session() as db:
            self.assertIsNotNone(db.get(ProjectTask, task["id"]).deleted_at)
            self.assertTrue(all(db.get(DailyTask, i).deleted_at is not None for i in ids))
        response = self.restore(batch, with_daily=True, daily_ids=[ids[0]], daily_dates={str(ids[0]): str(today())})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["pending_daily"]), 1)
        response = self.restore(batch, with_daily=True, daily_ids=[ids[1]], daily_dates={str(ids[1]): str(today()+timedelta(days=1))})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["pending_daily"], [])
        self.assertEqual(self.restore(batch, with_daily=True).status_code, 200)


class DeletionMigrationTests(unittest.TestCase):
    def test_additive_idempotent_upgrade_preserves_stage_and_history(self):
        from sqlalchemy import create_engine, text
        from unittest.mock import patch
        from app import database
        engine = create_engine("sqlite:///:memory:")
        database.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE project_deletions"))
            conn.execute(text("ALTER TABLE project_stages DROP COLUMN deleted_at"))
            conn.execute(text("INSERT INTO users (id,email,name,password_hash,capture_kind) VALUES (1,'old@test','旧用户','unused','moment')"))
            conn.execute(text("INSERT INTO projects (id,user_id,title,status) VALUES (1,1,'原项目','active')"))
            conn.execute(text("INSERT INTO project_stages (id,user_id,project_id,title,position,state) VALUES (1,1,1,'原阶段',7,'current')"))
        with patch.object(database, "engine", engine): database.ensure_schema(); database.ensure_schema()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT title,position,state,deleted_at FROM project_stages")).one(), ("原阶段", 7, "current", None))
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM project_deletions")).scalar(), 0)
        engine.dispose()
