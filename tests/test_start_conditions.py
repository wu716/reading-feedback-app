"""Execution gates must hold across legacy, project and ordinary daily entries."""
import io
import json
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone

from app.backup import build_backup_zip
from app.models import DailyTask, User
from app.project_models import ExecutionConditionEvent, Project, ProjectTask, WorkSession
from app.user_export import build_user_export_zip
import test_projects as project_fixture


class StartConditionTests(unittest.TestCase):
    setUp = project_fixture.ProjectFlowTests.setUp
    tearDown = project_fixture.ProjectFlowTests.tearDown
    req = project_fixture.ProjectFlowTests.req
    project = project_fixture.ProjectFlowTests.project
    task = project_fixture.ProjectFlowTests.task

    def condition(self, owner_kind, row_id, **fields):
        response = self.req("POST", f"/conditions/{owner_kind}/{row_id}", {"title": "文件齐全", "kind": "resource", **fields})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def daily(self):
        with self.Session() as db:
            row = DailyTask(user_id=1, task_date=date(2026, 10, 22), text="普通任务")
            db.add(row); db.commit()
            return row.id

    def ready(self, kind, row_id):
        response = self.req("GET", f"/readiness/{kind}/{row_id}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm(self, condition, confirmation="met", **fields):
        body = {key: condition[key] for key in ("title", "kind", "strength", "check_at", "target_id", "required_state", "confirmation", "evidence")}
        body.update({"confirmation": confirmation, "evidence": "已检查文件", "reason": "核对实际情况", **fields})
        return self.req("PUT", f"/conditions/{condition['id']}", body)

    def test_preparation_is_explicit_and_old_projects_remain_usable(self):
        p = self.req("POST", "", {"title": "新项目"}).json()
        formal = self.req("POST", f"/{p['id']}/tasks", {"title": "写正文"}).json()
        prep = self.req("POST", f"/{p['id']}/tasks", {"title": "收集文件", "execution_role": "preparation"}).json()
        self.assertFalse(self.ready("task", formal["id"])["can_start"])
        self.assertTrue(self.ready("task", prep["id"])["can_start"])
        c = self.condition("project", p["id"])
        self.assertEqual(self.req("POST", f"/{p['id']}/execution-state", {"state": "started", "reason": "开始"}).status_code, 409)
        self.assertTrue(self.ready("task", prep["id"])["can_start"])
        self.assertEqual(self.confirm(c).status_code, 200)
        self.assertEqual(self.req("POST", f"/{p['id']}/execution-state", {"state": "started", "reason": "条件已具备"}).status_code, 200)
        self.assertTrue(self.ready("task", formal["id"])["can_start"])
        with self.Session() as db:
            legacy = Project(user_id=1, title="旧项目")
            db.add(legacy); db.flush()
            task = ProjectTask(user_id=1, project_id=legacy.id, title="旧任务")
            db.add(task); db.commit(); task_id = task.id
            self.assertIsNone(legacy.execution_state)
            self.assertIsNone(legacy.started_at)
        self.assertTrue(self.ready("task", task_id)["can_start"])
        self.assertFalse(self.ready("task", task_id)["configured"])

    def test_daily_conditions_start_complete_and_scheduled_project_share_identity(self):
        daily_id = self.daily()
        c = self.condition("daily", daily_id)
        self.assertEqual(self.req("POST", "/sessions/start", {"daily_task_id": daily_id}).status_code, 409)
        self.assertEqual(self.client.patch(f"/api/schedule/tasks/{daily_id}", json={"completed": True}).status_code, 409)
        day = self.client.get("/api/schedule?task_date=2026-10-22").json()
        self.assertFalse(day["tasks"][0]["readiness"]["can_start"])
        self.assertEqual(self.confirm(c).status_code, 200)
        _, p, _ = self.project()
        promoted = self.req("POST", f"/daily/{daily_id}/project", {"project_id": p["id"]}).json()
        self.assertTrue(self.ready("task", promoted["id"])["can_start"])
        self.assertEqual(len(self.ready("task", promoted["id"])["conditions"]), 1)
        self.assertEqual(self.confirm(c, "unmet").status_code, 200)
        self.assertEqual(self.req("POST", "/sessions/start", {"project_task_id": promoted["id"]}).status_code, 409)
        self.assertEqual(self.req("POST", "/sessions/start", {"daily_task_id": daily_id}).status_code, 409)
        self.assertEqual(len(self.req("GET", f"/conditions/task/{promoted['id']}/history").json()["items"]), 3)

    def test_switch_is_atomic_and_resume_rechecks_revoked_conditions(self):
        _, p, stage = self.project()
        a, b = self.task(p, stage, "A"), self.task(p, stage, "B")
        c = self.condition("task", b["id"])
        active = self.req("POST", "/sessions/start", {"project_task_id": a["id"]}).json()
        switched = self.req("POST", "/sessions/switch", {"from_session_id": active["id"], "project_task_id": b["id"]})
        self.assertEqual(switched.status_code, 409)
        self.assertIsNone(self.req("GET", "/sessions").json()["items"][0]["ended_at"])
        self.assertEqual(self.confirm(c).status_code, 200)
        result = self.req("POST", "/sessions/switch", {"from_session_id": active["id"], "project_task_id": b["id"]})
        self.assertEqual(result.status_code, 200, result.text)
        active = result.json()["started"]
        self.assertEqual(self.req("POST", f"/sessions/{active['id']}/stop", {"pause": True}).status_code, 200)
        self.assertEqual(self.confirm(c, "unmet").status_code, 200)
        self.assertEqual(self.req("POST", "/execution/resume").status_code, 409)
        self.assertIsNotNone(self.req("GET", "/execution").json()["paused"])

    def test_project_dependency_requires_delivery_and_reopening_invalidates_it(self):
        _, p, stage = self.project()
        task = self.task(p, stage, "交付物")
        q = self.req("POST", "", {"title": "后续项目"}).json()
        self.condition("project", q["id"], kind="project", target_id=p["id"], required_state="accepted")
        self.assertFalse(self.ready("project", q["id"])["can_start"])
        self.assertEqual(self.req("POST", f"/{p['id']}/execution-state", {"state": "delivered", "reason": "交付"}).status_code, 409)
        self.req("POST", f"/tasks/{task['id']}/finish", {"result": "completed"})
        self.assertEqual(self.req("POST", f"/{p['id']}/execution-state", {"state": "delivered", "reason": "文件已交付"}).status_code, 200)
        self.assertFalse(self.ready("project", q["id"])["can_start"])
        self.assertEqual(self.req("POST", f"/{p['id']}/execution-state", {"state": "accepted", "reason": "逐项验收通过"}).status_code, 200)
        self.assertTrue(self.ready("project", q["id"])["can_start"])
        self.assertEqual(self.req("POST", f"/tasks/{task['id']}/finish", {"result": "rework", "outcome_note": "需修订论据"}).status_code, 200)
        self.assertFalse(self.ready("project", q["id"])["can_start"])

    def test_mixed_cycles_cross_project_tasks_duplicates_and_cross_user_refs(self):
        _, p, stage = self.project()
        a = self.task(p, stage, "A")
        _, q, other_stage = self.project()
        b = self.task(q, other_stage, "B")
        edge = {"title": "先交付项目B", "kind": "project", "target_id": q["id"]}
        self.assertEqual(self.req("POST", f"/conditions/project/{p['id']}", edge).status_code, 200)
        # B's task inherits B's start, and B's delivery includes its tasks.
        cycle = self.req("POST", f"/conditions/task/{b['id']}", {"title": "等待A", "kind": "task", "target_id": a["id"]})
        self.assertEqual(cycle.status_code, 400, cycle.text)
        self.assertEqual(self.req("POST", f"/conditions/project/{p['id']}", edge).status_code, 400)
        self.assertEqual(self.req("POST", f"/conditions/project/{q['id']}", {**edge, "target_id": q["id"]}).status_code, 400)
        self.assertEqual(self.req("POST", f"/conditions/project/{p['id']}", edge, user=2).status_code, 404)
        own_p = self.req("POST", "", {"title": "用户二"}, user=2).json()
        self.assertEqual(self.req("POST", f"/conditions/project/{own_p['id']}", edge, user=2).status_code, 404)
        self.assertEqual(self.req("GET", f"/readiness/task/{a['id']}", user=2).status_code, 404)
        self.assertEqual(self.req("GET", f"/conditions/task/{a['id']}/history", user=2).status_code, 404)

    def test_manual_not_applicable_and_automatic_conditions_cannot_be_forged(self):
        daily_id = self.daily()
        c = self.condition("daily", daily_id)
        response = self.confirm(c, "not_applicable", evidence="")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.ready("daily", daily_id)["can_start"])
        self.assertEqual(self.confirm(c, "not_applicable").status_code, 200)
        self.assertTrue(self.ready("daily", daily_id)["can_start"])
        _, p, stage = self.project()
        task = self.task(p, stage, "未完成")
        fake = self.req("POST", f"/conditions/daily/{daily_id}", {"title": "伪造", "kind": "task", "target_id": task["id"], "confirmation": "met"})
        self.assertEqual(fake.status_code, 400)

    def test_date_delivery_constraints_and_reminders_have_distinct_effects(self):
        daily_id = self.daily()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        c = self.condition("daily", daily_id, kind="time", not_before=future)
        self.assertFalse(self.ready("daily", daily_id)["can_start"])
        self.req("POST", f"/conditions/{c['id']}/remove", {"reason": "日期条件已调整"})
        self.condition("daily", daily_id, title="提交前核对", kind="constraint", check_at="delivery")
        self.assertTrue(self.ready("daily", daily_id)["can_start"])
        self.assertEqual(self.client.patch(f"/api/schedule/tasks/{daily_id}", json={"completed": True}).status_code, 409)
        self.condition("daily", daily_id, title="注意场地限制", strength="reminder")
        self.assertEqual(self.req("POST", "/sessions/start", {"daily_task_id": daily_id}).status_code, 409)
        self.assertEqual(self.req("POST", "/sessions/start", {"daily_task_id": daily_id, "acknowledge_reminders": True}).status_code, 200)

    def test_blocked_actual_work_is_preserved_with_explanation_and_exported(self):
        daily_id = self.daily()
        c = self.condition("daily", daily_id)
        body = {"daily_task_id": daily_id, "started_at": "2026-10-21T09:00:00+08:00", "ended_at": "2026-10-21T09:20:00+08:00"}
        self.assertEqual(self.req("POST", "/sessions/manual", body).status_code, 409)
        saved = self.req("POST", "/sessions/manual", {**body, "correction_note": "昨天确实进行了探索，材料尚未补齐"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["duration_minutes"], 20)
        self.assertEqual(self.req("POST", f"/conditions/{c['id']}/remove", {"reason": "该条件已不适用"}).status_code, 200)
        with self.Session() as db:
            db.add(ExecutionConditionEvent(user_id=2, owner_kind="daily", owner_id=99, action="private", reason="其他用户私有说明")); db.commit()
            self.assertEqual(db.query(WorkSession).count(), 1)
            exported = build_user_export_zip(db, db.get(User, 1))
            backup = build_backup_zip(db)
        with zipfile.ZipFile(io.BytesIO(exported)) as z:
            conditions = json.loads(z.read("start_conditions.json"))
            events = json.loads(z.read("execution_condition_events.json"))
            self.assertIsNotNone(conditions[0]["removed_at"])
            self.assertEqual(len(events), 2)
            self.assertNotIn("其他用户私有说明", z.read("execution_condition_events.json").decode())
        with zipfile.ZipFile(io.BytesIO(backup)) as z:
            self.assertIn("start_conditions.csv", z.namelist())
            self.assertIn("execution_condition_events.csv", z.namelist())

    def test_removed_or_reopened_prerequisite_never_satisfies_dependency(self):
        _, p, stage = self.project()
        a, b = self.task(p, stage, "A"), self.task(p, stage, "B")
        self.req("POST", f"/tasks/{b['id']}/dependencies", {"prerequisite_id": a["id"]})
        self.req("POST", f"/tasks/{a['id']}/finish", {"result": "completed"})
        self.assertTrue(self.ready("task", b["id"])["can_start"])
        self.req("POST", f"/tasks/{a['id']}/finish", {"result": "rework"})
        self.assertFalse(self.ready("task", b["id"])["can_start"])
        with self.Session() as db:
            row = db.get(ProjectTask, a["id"]); row.state = "completed"; row.deleted_at = datetime.now(timezone.utc); db.commit()
        self.assertFalse(self.ready("task", b["id"])["can_start"])
        self.assertEqual(self.req("DELETE", f"/tasks/{b['id']}/dependencies/{a['id']}").status_code, 409)
        self.assertEqual(self.req("DELETE", f"/tasks/{b['id']}/dependencies/{a['id']}?reason=条件变更").status_code, 409)
        self.assertFalse(self.ready("task", b["id"])["can_start"])

    def test_cross_project_task_dependency_and_legacy_edges_share_cycle_validation(self):
        _, p, stage = self.project()
        a, b = self.task(p, stage, "A"), self.task(p, stage, "B")
        _, q, next_stage = self.project()
        c = self.task(q, next_stage, "C")
        self.condition("task", c["id"], kind="task", target_id=b["id"])
        self.condition("task", a["id"], kind="task", target_id=c["id"])
        self.assertFalse(self.ready("task", c["id"])["can_start"])
        # Adding an old-style B -> A edge closes a cross-project mixed cycle.
        self.assertEqual(self.req("POST", f"/tasks/{b['id']}/dependencies", {"prerequisite_id": a["id"]}).status_code, 400)
        self.assertEqual(self.req("POST", f"/tasks/{b['id']}/finish", {"result": "completed"}).status_code, 200)
        self.assertTrue(self.ready("task", c["id"])["can_start"])

    def test_independent_child_can_finish_without_bypassing_container_delivery_gate(self):
        parent_id = self.daily()
        with self.Session() as db:
            child = DailyTask(user_id=1, task_date=date(2026, 10, 22), text="独立步骤", parent_id=parent_id)
            db.add(child); db.commit(); child_id = child.id
        self.condition("daily", parent_id, kind="constraint", check_at="delivery")
        result = self.client.patch(f"/api/schedule/tasks/{child_id}", json={"completed": True})
        self.assertEqual(result.status_code, 200, result.text)
        parent = result.json()["tasks"][0]
        self.assertFalse(parent["completed"])
        self.assertTrue(parent["children"][0]["completed"])
        self.assertEqual(self.client.patch(f"/api/schedule/tasks/{parent_id}", json={"completed": True}).status_code, 409)

    def test_removed_linked_task_stays_visible_as_blocked_without_erasing_daily_history(self):
        _, p, stage = self.project()
        task = self.task(p, stage, "将被移除的任务")
        self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-22"})
        with self.Session() as db:
            db.get(ProjectTask, task["id"]).deleted_at = datetime.now(timezone.utc)
            db.commit()
        result = self.client.get("/api/schedule?task_date=2026-10-22")
        self.assertEqual(result.status_code, 200, result.text)
        row = result.json()["tasks"][0]
        self.assertEqual(row["project_task_id"], task["id"])
        self.assertFalse(row["readiness"]["can_start"])
        self.assertIn("已移除", row["readiness"]["summary"])

    def test_promotion_cannot_create_a_cycle_through_project_delivery(self):
        _, p, _ = self.project()
        _, q, _ = self.project()
        daily_id = self.daily()
        self.condition("project", q["id"], kind="project", target_id=p["id"])
        self.condition("daily", daily_id, kind="project", target_id=q["id"])
        response = self.req("POST", f"/daily/{daily_id}/project", {"project_id": p["id"]})
        self.assertEqual(response.status_code, 400, response.text)
        with self.Session() as db:
            self.assertIsNone(db.get(DailyTask, daily_id).project_task_id)
            self.assertEqual(db.query(ProjectTask).count(), 0)

    def test_delivered_project_can_prepare_again_when_formal_conditions_are_missing(self):
        _, p, _ = self.project()
        self.req("POST", f"/{p['id']}/execution-state", {"state": "delivered", "reason": "本轮已交付"})
        self.condition("project", p["id"], title="新一轮的资料已收到")
        self.assertEqual(self.req("POST", f"/{p['id']}/execution-state", {"state": "started", "reason": "开始下一轮"}).status_code, 409)
        response = self.req("POST", f"/{p['id']}/execution-state", {"state": "preparation", "reason": "下一轮需先筹备新资料"})
        self.assertEqual(response.status_code, 200, response.text)
        prep = self.req("POST", f"/{p['id']}/tasks", {"title": "收集新资料", "execution_role": "preparation"})
        self.assertEqual(prep.status_code, 200, prep.text)
        self.assertTrue(prep.json()["can_start"])
        with self.Session() as db:
            self.assertIsNotNone(db.get(Project, p["id"]).started_at)
