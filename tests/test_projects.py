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
from app.project_models import ProcessTemplate, ProjectTask  # register new tables
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
