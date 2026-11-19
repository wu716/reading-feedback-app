"""B03 real API persistence, account isolation, and selected workload contracts."""
import io
import json
import unittest
import zipfile
from datetime import date
from unittest.mock import patch
from sqlalchemy import create_engine, text
import test_workspace_schedule as fixture
from app import database
from app.models import DailyTask
from app.project_models import Project, ProjectTask
from app.user_export import build_user_export_zip


class SchedulePlanningTests(unittest.TestCase):
    setUp = fixture.WorkspaceScheduleTests.setUp
    tearDown = fixture.WorkspaceScheduleTests.tearDown
    req = fixture.WorkspaceScheduleTests.req
    schedule = fixture.WorkspaceScheduleTests.schedule

    def add(self, **values):
        response = self.req('POST', '/schedule/tasks', {'task_date': self.day, 'text': '当天任务', **values})
        self.assertEqual(response.status_code, 200, response.text)
        return max(response.json()['tasks'], key=lambda task: task['id'])

    def test_optional_time_roundtrip_clear_permissions_and_export(self):
        task = self.add(deadline_time='12:00', window_start='09:15', window_end='11:45')
        ident = task['id']
        self.assertEqual(task['window_start'], '09:15')
        response = self.req('PATCH', f'/schedule/tasks/{ident}', {'deadline_time': '13:00', 'core_selected': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.schedule()[0]['window_end'], '11:45')
        self.assertEqual(self.req('PATCH', f'/schedule/tasks/{ident}', {'deadline_time': '14:00'}, user=2).status_code, 404)
        for invalid in ['24:00', '09:60', '9:00', '<svg>', 'tomorrow']:
            self.assertEqual(self.req('PATCH', f'/schedule/tasks/{ident}', {'window_end': invalid}).status_code, 422)
        with self.Session() as db:
            from app.models import User
            data=build_user_export_zip(db, db.get(User, 1))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            rows=json.loads(archive.read('daily_tasks.json'))
            self.assertEqual(rows[0]['deadline_time'], '13:00')
        before=self.schedule()[0]['flow_order']
        self.req('PATCH', f'/schedule/tasks/{ident}', {'deadline_time': None, 'window_start': None, 'window_end': None})
        task=self.schedule()[0]
        self.assertEqual(task['flow_order'], before)
        self.assertIsNone(task['deadline_time'])
        other=self.req('GET', '/schedule?task_date=2026-01-01').json()
        self.assertEqual(other['tasks'], [])

    def test_selected_parent_and_child_count_each_executable_leaf_once(self):
        parent=self.add(estimated_minutes=500)
        pid=parent['id']
        for estimate in (40, None):
            response=self.req('POST', '/schedule/tasks', {'task_date':self.day,'text':'步骤','parent_id':pid,'estimated_minutes':estimate})
            self.assertEqual(response.status_code, 200, response.text)
        child=response.json()['tasks'][0]['children'][0]
        self.req('PATCH', f'/schedule/tasks/{pid}', {'core_selected':True})
        response=self.req('PATCH', f"/schedule/tasks/{child['id']}", {'core_selected':True})
        load=response.json()['core_load']
        self.assertEqual((load['known_minutes'],load['unknown_count'],load['leaf_count']), (40,1,2))

    def test_capacity_patch_preserves_goal_allocations_and_is_account_and_day_scoped(self):
        task=self.add(estimated_minutes=40)
        ident=task['id']
        base=f'/projects/practice/day/{self.day}'
        response=self.req('POST', base+'/plan', {'goal':'保留目标','available_minutes':60,'allocations':[{'kind':'daily','id':ident,'minutes':35}]})
        self.assertEqual(response.status_code, 200, response.text)
        self.req('PATCH', f'/schedule/tasks/{ident}', {'core_selected':True})
        response=self.req('PATCH', base+'/capacity', {'available_minutes':20})
        self.assertEqual(response.status_code, 200, response.text)
        saved=self.req('GET', base).json()['plan']
        self.assertEqual(saved['goal'], '保留目标')
        self.assertEqual(saved['allocations'][0]['minutes'],35)
        load=self.req('GET', f'/schedule?task_date={self.day}').json()['core_load']
        self.assertEqual((load['known_minutes'],load['overload_minutes']), (35,15))
        self.assertEqual(self.req('GET', f'/schedule?task_date={self.day}',user=2).json()['core_load']['available_minutes'],None)
        self.assertEqual(self.req('GET','/schedule?task_date=2026-01-01').json()['core_load']['available_minutes'],None)
        self.req('PATCH', base+'/capacity', {'available_minutes':None})
        self.assertEqual(self.req('GET',base).json()['plan']['goal'],'保留目标')
        self.assertEqual(self.req('PATCH',base+'/capacity',{'available_minutes':1441}).status_code,422)

    def test_legacy_crossday_estimate_is_unknown_until_day_allocation_exists(self):
        with self.Session() as db:
            project=Project(user_id=1,title='跨日项目',status='active');db.add(project);db.flush()
            source=ProjectTask(user_id=1,project_id=project.id,title='整项180分钟',estimated_minutes=180,state='todo');db.add(source);db.flush()
            daily=DailyTask(user_id=1,task_date=date.fromisoformat(self.day),text='旧跨日任务',project_task_id=source.id,core_selected=True,estimated_minutes=180)
            db.add(daily);db.commit();source_id=source.id
        load=self.req('GET',f'/schedule?task_date={self.day}').json()['core_load']
        self.assertEqual((load['known_minutes'],load['unknown_count']),(0,1))
        response=self.req('POST',f'/projects/practice/day/{self.day}/plan',{'allocations':[{'kind':'task','id':source_id,'minutes':25}]})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.req('GET',f'/schedule?task_date={self.day}').json()['core_load']['known_minutes'],25)

    def test_additive_upgrade_keeps_old_rows_and_null_times(self):
        engine=create_engine('sqlite:///:memory:')
        database.Base.metadata.create_all(engine)
        with engine.begin() as conn:
            for field in ('deadline_time','window_start','window_end'):
                conn.execute(text(f'ALTER TABLE daily_tasks DROP COLUMN {field}'))
            conn.execute(text("INSERT INTO users(id,email,name,password_hash,capture_kind) VALUES(1,'legacy@test','旧用户','unused','moment')"))
            conn.execute(text("INSERT INTO daily_tasks(id,user_id,task_date,text,completed,sort_order,priority,flow_order,core_selected) VALUES(1,1,'2026-11-19','原任务',0,4,2,8,1)"))
        with patch.object(database,'engine',engine):
            database.ensure_schema();database.ensure_schema()
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT text,sort_order,flow_order,deadline_time,window_start,window_end FROM daily_tasks')).one(),('原任务',4,8,None,None,None))
        engine.dispose()
