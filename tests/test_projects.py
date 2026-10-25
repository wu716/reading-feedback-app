"""Contract tests for project boundaries and actual time accounting."""

import unittest
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_active_user
from app.database import Base, get_db
from app.models import DailyTask, User  # register legacy tables and DailyTask
from app.project_models import ProcessTemplate, ProjectTask, WorkSession  # register new tables
from app.routers.projects import router
from app.routers.schedule import router as schedule_router


class ProjectFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            db.add_all([
                User(id=1, email="first@example.test", name="First", password_hash="unused"),
                User(id=2, email="second@example.test", name="Second", password_hash="unused"),
            ])
            db.commit()
        app = FastAPI()
        app.include_router(router, prefix="/api")
        app.include_router(schedule_router, prefix="/api")

        def session_override():
            with self.Session() as db:
                yield db

        def user_override(request: Request):
            with self.Session() as db:
                return db.query(User).filter(User.id == int(request.headers.get("X-Test-User", "1"))).first()

        app.dependency_overrides[get_db] = session_override
        app.dependency_overrides[get_current_active_user] = user_override
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def req(self, method, path, body=None, user=1):
        return self.client.request(method, "/api/projects" + path, json=body, headers={"X-Test-User": str(user)})

    def project(self, estimate=None):
        goal = self.req("POST", "/goals", {"title": "交出初稿"}).json()
        project = self.req("POST", "", {"title": "论文", "goal_id": goal["id"]}).json()
        started = self.req("POST", f"/{project['id']}/execution-state", {"state": "started", "reason": "测试项目已具备开始条件"})
        self.assertEqual(started.status_code, 200, started.text)
        overview = self.req("GET", "/overview").json()["projects"][0]
        current = next(stage for stage in overview["stages"] if stage["state"] == "current")
        return goal, project, current

    def task(self, project, stage, title, estimate=None):
        response = self.req("POST", f"/{project['id']}/tasks", {"title": title, "stage_id": stage["id"], "estimated_minutes": estimate})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_dependencies_block_and_reject_cycles_and_other_users(self):
        goal, project, stage = self.project()
        a = self.task(project, stage, "A")
        b = self.task(project, stage, "B")
        c = self.task(project, stage, "C")
        self.assertEqual(self.req("POST", f"/tasks/{b['id']}/dependencies", {"prerequisite_id": a["id"]}).status_code, 200)
        overview = self.req("GET", "/overview").json()["projects"][0]
        by_id = {task["id"]: task for task in overview["tasks"]}
        self.assertEqual(by_id[b["id"]]["blocked_by"], [a["id"]])
        self.assertTrue(by_id[c["id"]]["can_start"])
        self.assertEqual(self.req("POST", f"/tasks/{a['id']}/dependencies", {"prerequisite_id": b["id"]}).status_code, 400)
        self.assertEqual(self.req("POST", f"/tasks/{b['id']}/finish", {"result": "completed"}).status_code, 409)
        self.assertEqual(self.req("POST", f"/tasks/{a['id']}/finish", {"result": "completed"}).status_code, 200)
        self.assertTrue(next(t for t in self.req("GET", "/overview").json()["projects"][0]["tasks"] if t["id"] == b["id"])["can_start"])
        self.assertEqual(self.req("POST", f"/tasks/{b['id']}/dependencies", {"prerequisite_id": a["id"]}, user=2).status_code, 404)
        self.assertEqual(self.req("POST", "", {"title": "越权", "goal_id": goal["id"]}, user=2).status_code, 404)

    def test_work_intervals_estimate_and_reflection(self):
        goal, project, stage = self.project()
        a = self.task(project, stage, "A", 40)
        b = self.task(project, stage, "B", 20)
        base = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)

        def manual(task_id, start, minutes, kind="work"):
            result = self.req("POST", "/sessions/manual", {
                "project_task_id": task_id, "kind": kind,
                "started_at": (base + timedelta(minutes=start)).isoformat(),
                "ended_at": (base + timedelta(minutes=start+minutes)).isoformat(),
            })
            self.assertEqual(result.status_code, 200, result.text)
            return result.json()

        first = manual(a["id"], 0, 20)
        manual(None, 20, 5, "break")
        manual(b["id"], 25, 20)
        manual(a["id"], 45, 20)
        overlap = self.req("POST", "/sessions/manual", {
            "project_task_id": a["id"], "started_at": (base+timedelta(minutes=10)).isoformat(),
            "ended_at": (base+timedelta(minutes=30)).isoformat(),
        })
        self.assertEqual(overlap.status_code, 409)
        tasks = {t["id"]: t for t in self.req("GET", "/overview").json()["projects"][0]["tasks"]}
        self.assertEqual(tasks[a["id"]]["actual_minutes"], 40)
        self.assertEqual(tasks[b["id"]]["actual_minutes"], 20)
        self.assertEqual(tasks[a["id"]]["difference_minutes"], 0)
        self.req("PATCH", f"/tasks/{a['id']}", {"estimated_minutes": 60})
        task = next(t for t in self.req("GET", "/overview").json()["projects"][0]["tasks"] if t["id"] == a["id"])
        self.assertEqual((task["original_estimate_minutes"], task["estimated_minutes"]), (40, 60))
        assessment = self.req("PUT", f"/sessions/{first['id']}/assessment", {"goal_id": goal["id"], "importance": "important", "interesting": True})
        self.assertEqual(assessment.status_code, 200)
        self.req("PATCH", f"/goals/{goal['id']}", {"title": "改名后的目标"})
        history = self.req("GET", "/sessions").json()["items"]
        self.assertEqual(next(s for s in history if s["id"] == first["id"])["assessment"]["goal_title_snapshot"], "交出初稿")
        self.assertIsNone(next(s for s in history if s["id"] != first["id"])["assessment"])
        self.assertEqual(self.req("PUT", f"/sessions/{first['id']}/assessment", {"goal_id": goal["id"], "importance": "important"}, user=2).status_code, 404)

    def test_timer_deadline_survives_closed_browser_and_infers_project_link(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A", 20)
        daily = self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-19"}).json()
        session = self.req("POST", "/sessions/start", {"daily_task_id": daily["id"], "planned_minutes": 20}).json()
        self.assertEqual(session["project_task_id"], task["id"])
        with self.Session() as db:
            db.get(WorkSession, session["id"]).started_at = datetime.utcnow() - timedelta(hours=3)
            db.commit()
        result = next(s for s in self.req("GET", "/sessions").json()["items"] if s["id"] == session["id"])
        self.assertEqual(result["duration_minutes"], 20)
        self.assertIsNotNone(result["ended_at"])
        self.assertEqual(self.req("GET", "/overview").json()["projects"][0]["tasks"][0]["actual_minutes"], 20)
        # The next task starts only after a deliberate action, and idle hours are uncounted.
        items = self.req("GET", "/sessions").json()["items"]
        self.assertEqual(len(items), 2)
        rest = next(s for s in items if s["kind"] == "break")
        self.assertEqual(rest["started_at"], result["ended_at"])
        self.assertEqual(rest["duration_minutes"], 5)
        self.assertEqual(self.req("POST", "/sessions/start", {"daily_task_id": daily["id"]}).status_code, 200)

    def test_automatic_break_is_anchored_idempotent_and_can_end_early(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A")
        self.req("PUT", "/execution", {"queue": [], "work_minutes": 20, "break_minutes": 7})
        work = self.req("POST", "/sessions/start", {"project_task_id": task["id"], "planned_minutes": 20}).json()
        with self.Session() as db:
            db.get(WorkSession, work["id"]).started_at = datetime.utcnow() - timedelta(minutes=22)
            db.commit()
        first = self.req("GET", "/sessions").json()["items"]
        second = self.req("GET", "/sessions").json()["items"]
        self.assertEqual(len(first), 2)
        self.assertEqual([s["id"] for s in first], [s["id"] for s in second])
        rest = next(s for s in second if s["kind"] == "break")
        ended = next(s for s in second if s["kind"] == "work")
        self.assertEqual(rest["started_at"], ended["ended_at"])
        self.assertEqual(rest["planned_minutes"], 7)
        self.assertIsNone(rest["ended_at"])
        self.assertEqual(self.req("POST", f"/sessions/{rest['id']}/stop", {}).status_code, 200)
        self.assertFalse(any(s["ended_at"] is None for s in self.req("GET", "/sessions").json()["items"]))

    def test_manual_early_stop_does_not_create_a_break(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A")
        work = self.req("POST", "/sessions/start", {"project_task_id": task["id"], "planned_minutes": 20}).json()
        self.assertEqual(self.req("POST", f"/sessions/{work['id']}/stop", {}).status_code, 200)
        self.assertEqual(len(self.req("GET", "/sessions").json()["items"]), 1)

    def test_pause_resume_preserves_remaining_budget_and_excludes_gap(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A")
        started = self.req("POST", "/sessions/start", {"project_task_id": task["id"], "planned_minutes": 20}).json()
        with self.Session() as db:
            db.get(WorkSession, started["id"]).started_at = datetime.utcnow() - timedelta(minutes=5)
            db.commit()
        self.assertEqual(self.req("POST", f"/sessions/{started['id']}/stop", {"pause": True}).status_code, 200)
        plan = self.req("GET", "/execution").json()
        self.assertTrue(898 <= plan["remaining_seconds"] <= 900)
        resumed = self.req("POST", "/execution/resume", {}).json()
        self.assertEqual(resumed["planned_seconds"], plan["remaining_seconds"])
        self.assertIsNone(self.req("GET", "/execution").json()["paused"])
        self.assertEqual(self.req("POST", "/execution/resume", {}).status_code, 409)
        self.assertEqual(self.req("POST", "/sessions/start", {"project_task_id": task["id"]}).status_code, 409)

    def test_queue_is_server_owned_deduplicated_and_user_scoped(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A")
        daily = self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-19"}).json()
        payload = {"queue": [f"daily:{daily['id']}", f"project:{task['id']}"], "work_minutes": 25, "break_minutes": 7}
        saved = self.req("PUT", "/execution", payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        restored = self.req("GET", "/execution").json()
        self.assertEqual(restored["queue"], [f"daily:{daily['id']}"])
        self.assertEqual((restored["work_minutes"], restored["break_minutes"]), (25, 7))
        self.assertEqual(self.req("GET", "/execution", user=2).json()["queue"], [])
        self.assertEqual(self.req("PUT", "/execution", payload, user=2).status_code, 404)

    def test_schedule_links_are_idempotent_and_completion_returns_to_schedule(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A")
        scheduled = self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-19"}).json()
        again = self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-19"}).json()
        self.assertEqual(scheduled["id"], again["id"])
        self.req("POST", f"/tasks/{task['id']}/finish", {"result": "completed"})
        day = self.client.get("/api/schedule?task_date=2026-10-19").json()["tasks"]
        self.assertEqual(len(day), 1)
        self.assertEqual((day[0]["project_title"], day[0]["completed"]), ("论文", True))
        self.assertEqual(self.req("POST", "/sessions/start", {"daily_task_id": day[0]["id"]}).status_code, 409)
        self.req("POST", f"/tasks/{task['id']}/finish", {"result": "rework"})
        self.assertFalse(self.client.get("/api/schedule?task_date=2026-10-19").json()["tasks"][0]["completed"])

    def test_finishing_a_running_task_stops_timer_and_title_edits_stay_linked(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A")
        daily = self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-19"}).json()
        self.req("PATCH", f"/tasks/{task['id']}", {"title": "项目改名"})
        day = self.client.get("/api/schedule?task_date=2026-10-19").json()["tasks"][0]
        self.assertEqual(day["text"], "项目改名")
        changed = self.client.patch(f"/api/schedule/tasks/{daily['id']}", json={"text": "日程改名"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.req("GET", "/overview").json()["projects"][0]["tasks"][0]["title"], "日程改名")
        self.req("POST", "/sessions/start", {"daily_task_id": daily["id"]})
        finished = self.req("POST", f"/tasks/{task['id']}/finish", {"result": "completed"})
        self.assertEqual(finished.status_code, 200, finished.text)
        self.assertIsNotNone(self.req("GET", "/sessions").json()["items"][0]["ended_at"])

    def test_legacy_daily_only_sessions_contribute_without_rewriting_history(self):
        _, project, stage = self.project()
        task = self.task(project, stage, "A")
        daily = self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-19"}).json()
        with self.Session() as db:
            db.add(WorkSession(user_id=1, daily_task_id=daily["id"], project_task_id=None, kind="work", source="manual",
                started_at=datetime(2026, 10, 18, 9), ended_at=datetime(2026, 10, 18, 9, 15)))
            db.commit()
        overview = self.req("GET", "/overview").json()["projects"][0]["tasks"][0]
        day = self.client.get("/api/schedule?task_date=2026-10-19").json()["tasks"][0]
        self.assertEqual((overview["actual_minutes"], day["actual_minutes"]), (15, 15))
        with self.Session() as db:
            self.assertIsNone(db.query(WorkSession).one().project_task_id)

    def test_promoting_daily_keeps_time_history_and_checks_ownership(self):
        with self.Session() as db:
            daily = DailyTask(user_id=1, task_date=date(2026, 10, 19), text="日程里的写作", estimated_minutes=30)
            db.add(daily); db.commit(); daily_id = daily.id
        _, project, stage = self.project()
        end = datetime.now(timezone.utc) - timedelta(hours=1)
        manual = self.req("POST", "/sessions/manual", {"daily_task_id": daily_id,
            "started_at": (end - timedelta(minutes=10)).isoformat(), "ended_at": end.isoformat()})
        self.assertEqual(manual.status_code, 200, manual.text)
        task = self.req("POST", f"/daily/{daily_id}/project", {"project_id": project["id"]}).json()
        self.assertEqual(task["actual_minutes"], 10)
        self.assertEqual(task["title"], "日程里的写作")
        self.assertEqual(self.req("POST", f"/daily/{daily_id}/project", {"project_id": project["id"]}).json()["id"], task["id"])
        self.assertEqual(self.req("POST", f"/daily/{daily_id}/project", {"project_id": project["id"]}, user=2).status_code, 404)

    def test_blank_template_is_copied_into_editable_task(self):
        _, project, stage = self.project()
        template = self.req("POST", "/templates", {"title": "提交初稿", "steps": ["写目录"], "checklist": ["导出 PDF"], "acceptance_criteria": "能打开"}).json()
        task = self.req("POST", f"/templates/{template['id']}/instantiate", {"project_id": project["id"], "stage_id": stage["id"]}).json()
        self.assertEqual(task["steps"], ["写目录"])
        self.assertEqual(task["checklist"][0]["text"], "导出 PDF")
        self.req("PUT", f"/templates/{template['id']}", {"title": "新版", "steps": ["写摘要"], "checklist": [], "acceptance_criteria": "新标准"})
        stored = next(t for t in self.req("GET", "/overview").json()["projects"][0]["tasks"] if t["id"] == task["id"])
        self.assertEqual(stored["steps"], ["写目录"])
        self.assertEqual(stored["acceptance_criteria"], "能打开")
        self.assertEqual(self.req("POST", f"/templates/{template['id']}/instantiate", {"project_id": project["id"]}, user=2).status_code, 404)

    def test_project_task_can_be_scheduled_without_changing_existing_daily_tasks(self):
        with self.Session() as db:
            db.add(DailyTask(user_id=1, task_date=date(2026, 10, 15), text="原本的简单日程"))
            db.commit()
        _, project, stage = self.project()
        task = self.task(project, stage, "项目下一步", 35)
        result = self.req("POST", f"/tasks/{task['id']}/schedule", {"task_date": "2026-10-15"})
        self.assertEqual(result.status_code, 200, result.text)
        with self.Session() as db:
            rows = db.query(DailyTask).order_by(DailyTask.id).all()
            self.assertEqual((rows[0].text, rows[0].project_task_id), ("原本的简单日程", None))
            self.assertEqual((rows[1].text, rows[1].project_task_id, rows[1].estimated_minutes),
                             ("项目下一步", task["id"], 35))
        schedule = self.client.get("/api/schedule?task_date=2026-10-15", headers={"X-Test-User": "1"})
        self.assertEqual(schedule.status_code, 200, schedule.text)
        self.assertEqual([item["project_task_id"] for item in schedule.json()["tasks"]], [None, task["id"]])
        started = self.req("POST", "/sessions/start", {"daily_task_id": rows[0].id})
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual((started.json()["project_task_id"], started.json()["daily_task_id"]), (None, rows[0].id))


if __name__ == "__main__":
    unittest.main()
