"""Data contracts for the unified schedule and reusable process instances."""
import unittest
from datetime import date

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_active_user
from app.database import Base, get_db
from app.models import DailyTask, DailyTodo, User
from app.routers.projects import router as projects_router
from app.routers.schedule import router as schedule_router
from app.routers.today import router as today_router


class WorkspaceScheduleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            db.add_all([User(id=i, email=f"user{i}@example.test", name=f"User {i}", password_hash="unused") for i in (1, 2)])
            db.commit()
        app = FastAPI()
        for router in (projects_router, schedule_router, today_router):
            app.include_router(router, prefix="/api")

        def session():
            with self.Session() as db:
                yield db

        def user(request: Request):
            with self.Session() as db:
                return db.get(User, int(request.headers.get("X-Test-User", "1")))

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[get_current_active_user] = user
        self.client = TestClient(app)
        self.day = date.today().isoformat()

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def req(self, method, path, body=None, user=1):
        return self.client.request(method, "/api" + path, json=body, headers={"X-Test-User":str(user)})

    def schedule(self):
        response = self.req("GET", f"/schedule?task_date={self.day}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["tasks"]

    def test_legacy_import_is_idempotent_and_does_not_merge_same_text(self):
        with self.Session() as db:
            db.add_all([DailyTodo(user_id=1, text="same", todo_date=date.today(), remind_time="08:30", completed=True),
                        DailyTodo(user_id=1, text="same", todo_date=date.today(), completed=False),
                        DailyTodo(user_id=2, text="private", todo_date=date.today())])
            db.commit()
        first = self.schedule()
        self.assertEqual(len(first), 2)
        self.assertEqual([row["id"] for row in first], [row["id"] for row in self.schedule()])
        self.assertEqual(first[0]["remind_time"], "08:30")
        self.assertTrue(first[0]["completed"])
        with self.Session() as db:
            self.assertEqual(db.query(DailyTodo).count(), 3)
            self.assertEqual(db.query(DailyTask).count(), 2)

    def test_schedule_and_legacy_client_share_edit_completion_reminders_and_delete(self):
        todo = self.req("POST", "/today/todos", {"text":"old","todo_date":self.day,"remind_time":"09:10"}).json()
        task = self.schedule()[0]
        edited = self.req("PATCH", f"/schedule/tasks/{task['id']}", {"text":"renamed","remind_time":"10:20"})
        self.assertEqual(edited.status_code, 200, edited.text)
        legacy = self.req("GET", f"/today/todos?todo_date={self.day}").json()[0]
        self.assertEqual((legacy["id"], legacy["text"], legacy["remind_time"]), (todo["id"], "renamed", "10:20"))
        completed = self.req("PATCH", f"/today/todos/{todo['id']}", {"completed":True})
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertTrue(self.schedule()[0]["completed"])
        self.assertEqual(self.req("PATCH", f"/schedule/tasks/{task['id']}", {"text":"stolen"},user=2).status_code, 404)
        self.req("DELETE", f"/schedule/tasks/{task['id']}")
        self.assertEqual(self.schedule(), [])
        self.assertEqual(self.req("GET", f"/today/todos?todo_date={self.day}").json(), [])
        with self.Session() as db:
            self.assertIsNotNone(db.get(DailyTodo,todo["id"]).deleted_at)

    def test_new_schedule_reminder_uses_original_alarm_api_and_cancels_cleanly(self):
        task = self.req("POST", "/schedule/tasks", {"text":"new","task_date":self.day}).json()["tasks"][0]
        self.req("PATCH", f"/schedule/tasks/{task['id']}", {"remind_time":"11:20"})
        alarms = self.req("GET", "/today/todos/scheduled").json()
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]["text"], "new")
        self.req("PATCH", f"/schedule/tasks/{task['id']}", {"remind_time":None})
        self.assertEqual(self.req("GET", "/today/todos/scheduled").json(), [])
        self.assertEqual(len(self.schedule()), 1)

    def test_old_completion_cannot_bypass_new_conditions(self):
        todo = self.req("POST", "/today/todos", {"text":"needs resource","todo_date":self.day}).json()
        task = self.schedule()[0]
        condition = self.req("POST", f"/projects/conditions/daily/{task['id']}",
            {"kind":"resource","title":"required material","strength":"required","check_at":"delivery"})
        self.assertEqual(condition.status_code,200,condition.text)
        result = self.req("PATCH", f"/today/todos/{todo['id']}", {"completed":True})
        self.assertEqual(result.status_code,409,result.text)
        self.assertFalse(self.schedule()[0]["completed"])

    def test_template_to_schedule_is_an_independent_complete_snapshot(self):
        template = self.req("POST", "/projects/templates", {"title":"publish","steps":["draft","review"],
            "checklist":["open attachment"],"common_problems":"missing file","acceptance_criteria":"usable"}).json()
        applied = self.req("POST", f"/projects/templates/{template['id']}/schedule", {"task_date":self.day})
        self.assertEqual(applied.status_code,200,applied.text)
        task = self.schedule()[0]
        self.assertEqual(task["steps"],["draft","review"])
        self.assertEqual(task["checklist"],[{"text":"open attachment","done":False}])
        self.req("PATCH",f"/schedule/tasks/{task['id']}",{"checklist_done":[True]})
        self.req("PUT",f"/projects/templates/{template['id']}",{"title":"new template","steps":["changed"],"checklist":[]})
        preserved = self.schedule()[0]
        self.assertEqual(preserved["steps"],task["steps"])
        self.assertTrue(preserved["checklist"][0]["done"])
        self.assertEqual(preserved["acceptance_criteria"],"usable")
        self.assertEqual(self.req("POST",f"/projects/templates/{template['id']}/schedule",{"task_date":self.day},user=2).status_code,404)
        project = self.req("POST","/projects",{"title":"promote snapshot"}).json()
        promoted = self.req("POST",f"/projects/daily/{task['id']}/project",{"project_id":project["id"]})
        self.assertEqual(promoted.status_code,200,promoted.text)
        self.assertEqual(promoted.json()["steps"],["draft","review"])
        self.assertTrue(promoted.json()["checklist"][0]["done"])
        self.assertEqual(promoted.json()["acceptance_criteria"],"usable")

    def test_project_acceptance_and_rename_reach_old_reminder_clients(self):
        todo = self.req("POST","/today/todos",{"text":"linked","todo_date":self.day,"remind_time":"23:10"}).json()
        daily = self.schedule()[0]
        project = self.req("POST","/projects",{"title":"delivery"}).json()
        self.req("POST",f"/projects/{project['id']}/execution-state",{"state":"started","reason":"ready"})
        task = self.req("POST",f"/projects/daily/{daily['id']}/project",{"project_id":project["id"]}).json()
        renamed = self.req("PATCH",f"/projects/tasks/{task['id']}",{"title":"renamed project task"})
        self.assertEqual(renamed.status_code,200,renamed.text)
        self.assertEqual(self.req("GET","/today/todos/scheduled").json()[0]["text"],"renamed project task")
        accepted = self.req("POST",f"/projects/tasks/{task['id']}/finish",{"result":"completed","outcome_note":"delivered"})
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertTrue(self.schedule()[0]["completed"])
        self.assertEqual(self.req("GET","/today/todos/scheduled").json(),[])
