"""Someday collection ownership, scheduling and reversible deletion (memory DB only)."""
from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import project_models  # noqa: F401 - register related tables
from app.auth import get_current_active_user
from app.database import Base, get_db
from app.models import DailyTask, FutureAction, User
from app.routers import schedule


class FutureActionTests(TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            db.add_all([User(id=i, name=f'User {i}', email=f'user{i}@example.test', password_hash='unused') for i in (1,2)])
            db.commit()
        app = FastAPI()
        app.include_router(schedule.router, prefix='/api')

        def session():
            with self.Session() as db:
                yield db

        def user(request: Request):
            with self.Session() as db:
                return db.get(User, int(request.headers.get('X-Test-User', '1')))

        app.dependency_overrides[get_db] = session
        app.dependency_overrides[get_current_active_user] = user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def request(self, method, path='', body=None, user=1):
        return self.client.request(method, '/api/schedule/future'+path, json=body, headers={'X-Test-User':str(user)})

    def create(self, value='以后试试陶艺'):
        response = self.request('POST', body={'text':value})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['items'][0]['id']

    def test_collection_does_not_create_schedule_and_preserves_identity(self):
        item = self.create('  原来的想法\n补充说明  ')
        self.assertEqual(self.request('PATCH', f'/{item}', {'text':'修改后的想法'}).status_code, 200)
        row = self.request('GET').json()['items'][0]
        self.assertEqual((row['id'], row['text']), (item, '修改后的想法'))
        with self.Session() as db:
            self.assertEqual(db.query(DailyTask).count(), 0)
        self.assertEqual(self.request('GET', user=2).json()['items'], [])
        self.assertEqual(self.request('PATCH', f'/{item}', {'text':'不能修改'}, user=2).status_code, 404)
        self.assertEqual(self.request('POST', body={'text':'  '}).status_code, 422)
        self.assertEqual(self.request('POST', body={'text':'长'*501}).status_code, 422)

    def test_delete_can_only_be_undone_with_its_current_owner_receipt(self):
        item = self.create()
        deleted = self.request('DELETE', f'/{item}').json()
        token = deleted['undo_token']
        self.assertEqual(deleted['items'], [])
        self.assertEqual(self.request('POST', f'/{item}/restore', {'undo_token':token}, user=2).status_code, 404)
        for invalid in ('invalid', token[:-1]+'X', token.rpartition('|')[0]+'|中文'):
            self.assertEqual(self.request('POST', f'/{item}/restore', {'undo_token':invalid}).status_code, 400)
        restored = self.request('POST', f'/{item}/restore', {'undo_token':token})
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()['items'][0]['id'], item)
        self.assertEqual(self.request('POST', f'/{item}/restore', {'undo_token':token}).status_code, 409)
        self.request('DELETE', f'/{item}')
        self.assertEqual(self.request('POST', f'/{item}/restore', {'undo_token':token}).status_code, 409)

    def test_undo_expires_without_destroying_history(self):
        item = self.create()
        old = schedule.beijing_now() - timedelta(minutes=11)
        with patch.object(schedule, 'beijing_now', return_value=old):
            token = self.request('DELETE', f'/{item}').json()['undo_token']
        self.assertEqual(self.request('POST', f'/{item}/restore', {'undo_token':token}).status_code, 410)
        with self.Session() as db:
            self.assertIsNotNone(db.get(FutureAction, item).deleted_at)

    def test_selected_date_and_schedule_conversion_do_not_reuse_delete_receipt(self):
        item = self.create()
        token = self.request('DELETE', f'/{item}').json()['undo_token']
        self.request('POST', f'/{item}/restore', {'undo_token':token})
        response = self.request('POST', f'/{item}/schedule', {'task_date':'2026-11-07'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['date'], '2026-11-07')
        self.assertEqual(self.request('GET').json()['items'], [])
        self.assertEqual(self.request('POST', f'/{item}/restore', {'undo_token':token}).status_code, 409)
        with self.Session() as db:
            self.assertEqual(db.query(DailyTask).count(), 1)
