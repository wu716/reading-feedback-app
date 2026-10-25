"""Stage-to-day contracts use isolated synthetic SQLite data only."""
import io
import unittest
import zipfile
from datetime import datetime

import test_projects as fixture
from app.models import DailyTask, User
from app.project_models import ProjectTask, WorkSession
from app.stage_schedule_models import DailyProjectPlan


class StageScheduleTests(unittest.TestCase):
    setUp = fixture.ProjectFlowTests.setUp
    tearDown = fixture.ProjectFlowTests.tearDown
    req = fixture.ProjectFlowTests.req
    project = fixture.ProjectFlowTests.project
    task = fixture.ProjectFlowTests.task

    def request(self, method, path, body=None, user=1):
        return self.client.request(method, '/api/schedule' + path, json=body, headers={'X-Test-User': str(user)})

    def plan(self, stage, task=None, day='2026-10-24', key='one', **changes):
        item = {'item_key': 'item', 'project_task_id': task['id'] if task else None,
                'text': '今天完成前半部分', 'estimated_minutes': 45, 'difficulty': 'difficult',
                'importance': 'important', 'familiarity': 'unfamiliar', **changes}
        response = self.request('POST', f"/project-stages/{stage['id']}", {'task_date': day, 'request_key': key, 'items': [item]})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['tasks'][-1]

    def test_edit_day_scope_and_attributes_preserves_source_and_other_days(self):
        _, project, stage = self.project()
        source = self.task(project, stage, '整项任务', 180)
        first = self.plan(stage, source)
        second = self.plan(stage, source, day='2026-10-25', key='two')
        changed = self.request('PATCH', f"/tasks/{first['id']}", {'text': '今天只做第一步', 'estimated_minutes': 20, 'familiarity': 'familiar'})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()['tasks'][0]['estimated_minutes'], 20)
        self.assertEqual(self.req('PATCH', f"/practice/tasks/daily/{first['id']}/attributes", {'difficulty': 'simple'}).status_code, 200)
        with self.Session() as db:
            self.assertEqual((db.get(ProjectTask, source['id']).title, db.get(ProjectTask, source['id']).estimated_minutes), ('整项任务', 180))
            self.assertEqual(db.get(DailyTask, second['id']).text, '今天完成前半部分')
        self.req('PATCH', f"/tasks/{source['id']}", {'title': '项目的新名称'})
        preserved = self.request('GET', '?task_date=2026-10-24').json()['tasks'][0]
        self.assertEqual(preserved['text'], '今天只做第一步')
        self.assertEqual(preserved['project_day_plan']['task_title'], '整项任务')
        self.assertEqual(preserved['practice']['difficulty'], 'simple')

    def test_daily_completion_feedback_and_project_acceptance_are_separate(self):
        _, project, stage = self.project()
        source = self.task(project, stage, '整项任务', 120)
        daily = self.plan(stage, source)
        response = self.req('POST', f"/practice/tasks/daily/{daily['id']}/feedback", {
            'actual_minutes': 50, 'basis': 'self_report', 'result': 'completed', 'feedback_date': '2026-10-24'})
        self.assertEqual(response.status_code, 200, response.text)
        with self.Session() as db:
            self.assertTrue(db.get(DailyTask, daily['id']).completed)
            self.assertEqual(db.get(ProjectTask, source['id']).state, 'todo')
            self.assertEqual(db.query(WorkSession).count(), 0)
        tomorrow = self.plan(stage, source, day='2026-10-25', key='two')
        result = self.req('POST', f"/tasks/{source['id']}/finish", {'result': 'completed'})
        self.assertEqual(result.status_code, 200, result.text)
        with self.Session() as db:
            self.assertFalse(db.get(DailyTask, tomorrow['id']).completed)
        done = self.request('PATCH', f"/tasks/{tomorrow['id']}", {'completed': True})
        self.assertEqual(done.status_code, 200, done.text)

    def test_retry_same_day_dedup_and_new_task_creation_are_atomic(self):
        _, project, stage = self.project()
        first = self.plan(stage)
        second = self.plan(stage)
        self.assertEqual(first['id'], second['id'])
        with self.Session() as db:
            self.assertEqual(db.query(ProjectTask).filter_by(project_id=project['id']).count(), 1)
        source = {'id': first['project_task_id']}
        again = self.plan(stage, source, key='different')
        self.assertEqual(first['id'], again['id'])
        bad = self.request('POST', f"/project-stages/{stage['id']}", {'task_date': '2026-10-24', 'request_key': 'bad',
            'items': [{'item_key': 'new', 'text': '不应部分创建'}, {'item_key': 'missing', 'text': 'missing', 'project_task_id': 987654}]})
        self.assertEqual(bad.status_code, 409, bad.text)
        with self.Session() as db:
            self.assertEqual(db.query(ProjectTask).filter_by(project_id=project['id']).count(), 1)

    def test_readiness_keeps_dependencies_and_next_stage_handover(self):
        _, project, stage = self.project()
        prior = self.task(project, stage, '前置')
        blocked = self.task(project, stage, '后置')
        self.req('POST', f"/tasks/{blocked['id']}/dependencies", {'prerequisite_id': prior['id']})
        daily = self.plan(stage, blocked)
        self.assertFalse(daily['readiness']['can_start'])
        self.assertEqual(self.request('PATCH', f"/tasks/{daily['id']}", {'completed': True}).status_code, 409)
        self.assertEqual(self.req('POST', '/sessions/start', {'daily_task_id': daily['id'], 'planned_minutes': 5}).status_code, 409)
        next_stage = next(s for s in self.req('GET', '/overview').json()['projects'][0]['stages'] if s['state'] == 'next')
        upcoming = self.task(project, next_stage, '下阶段任务')
        planned = self.plan(next_stage, upcoming, key='next')
        self.assertFalse(planned['readiness']['can_start'])

    def test_preview_previous_progress_and_account_isolation(self):
        _, project, stage = self.project()
        source = self.task(project, stage, '持续推进')
        previous = self.plan(stage, source)
        self.request('PATCH', f"/tasks/{previous['id']}", {'note': '已经做到第二段'})
        source_view = self.req('GET', '/overview').json()['projects'][0]['tasks'][0]
        self.assertEqual(source_view['daily_progress'][0]['note'], '已经做到第二段')
        response = self.request('GET', f"/project-stages/{stage['id']}?task_date=2026-10-25")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['tasks'][0]['previous_progress']['note'], '已经做到第二段')
        self.assertEqual(self.request('GET', '/project-stages', user=2).json()['projects'], [])
        self.assertEqual(self.request('GET', f"/project-stages/{stage['id']}?task_date=2026-10-25", user=2).status_code, 404)
        self.assertEqual(self.request('PATCH', f"/tasks/{previous['id']}", {'text': '越权'}, user=2).status_code, 404)

    def test_today_ledger_splits_at_beijing_midnight_without_double_counting(self):
        _, project, stage = self.project()
        source = self.task(project, stage, '跨天任务', 90)
        self.plan(stage, source, day='2026-10-23', key='prior')
        self.plan(stage, source, day='2026-10-24', key='current')
        with self.Session() as db:
            db.add(WorkSession(user_id=1, project_task_id=source['id'], kind='work', source='manual',
                started_at=datetime(2026, 10, 23, 15, 50), ended_at=datetime(2026, 10, 23, 16, 20)))
            db.commit()
        prior = self.request('GET', '?task_date=2026-10-23').json()['tasks'][0]
        current = self.request('GET', '?task_date=2026-10-24').json()['tasks'][0]
        self.assertEqual((prior['actual_minutes'], current['actual_minutes']), (10, 20))
        self.assertEqual(current['project_day_plan']['project_actual_minutes'], 30)

    def test_split_and_remove_keep_source_and_history(self):
        _, project, stage = self.project()
        source = self.task(project, stage, '阶段大任务')
        daily = self.plan(stage, source)
        split = self.request('POST', '/tasks', {'task_date': '2026-10-24', 'text': '更小的一步', 'parent_id': daily['id']})
        self.assertEqual(split.status_code, 200, split.text)
        child = split.json()['tasks'][0]['children'][0]
        self.assertEqual(child['project_task_id'], source['id'])
        self.assertIsNotNone(child['project_day_plan'])
        self.assertEqual(self.request('PATCH', f"/tasks/{child['id']}", {'completed': True}).status_code, 200)
        removed = self.request('DELETE', f"/tasks/{daily['id']}")
        self.assertEqual(removed.status_code, 200, removed.text)
        with self.Session() as db:
            self.assertIsNone(db.get(ProjectTask, source['id']).deleted_at)

    def test_export_contains_scope_metadata_and_backup(self):
        from app.user_export import build_user_export_zip
        from app.backup import build_backup_zip
        _, _, stage = self.project()
        self.plan(stage)
        with self.Session() as db:
            personal = zipfile.ZipFile(io.BytesIO(build_user_export_zip(db, db.get(User, 1))))
            self.assertTrue(any('daily_project_plans' in name for name in personal.namelist()))
            backup = zipfile.ZipFile(io.BytesIO(build_backup_zip(db)))
            self.assertIn('daily_project_plans.csv', backup.namelist())

    def test_draft_retry_rejects_changed_payload_and_old_stage(self):
        _, project, stage = self.project()
        source = self.task(project, stage, '原任务')
        self.plan(stage, source)
        changed = self.request('POST', f"/project-stages/{stage['id']}", {'task_date':'2026-10-24', 'request_key':'one',
            'items':[{'item_key':'item','project_task_id':source['id'],'text':'不同的内容'}]})
        self.assertEqual(changed.status_code, 409, changed.text)
        next_stage = next(s for s in self.req('GET','/overview').json()['projects'][0]['stages'] if s['state']=='next')
        # Simulate a separately approved project revision while a daily draft is open.
        with self.Session() as db:
            db.get(ProjectTask, source['id']).stage_id = next_stage['id']
            db.commit()
        stale = self.request('POST', f"/project-stages/{stage['id']}", {'task_date':'2026-10-25','request_key':'stale',
            'items':[{'item_key':'item','project_task_id':source['id'],'text':'旧阶段草稿'}]})
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_work_snapshot_uses_daily_attributes_and_feedback_uses_scheduled_date(self):
        import json
        _, project, stage = self.project()
        source = self.task(project, stage, '持续任务', 180)
        daily = self.plan(stage, source)
        started = self.req('POST','/sessions/start',{'daily_task_id':daily['id'],'planned_minutes':5})
        self.assertEqual(started.status_code,200,started.text)
        with self.Session() as db:
            snapshot = json.loads(db.get(WorkSession,started.json()['id']).practice_snapshot_json)
            self.assertEqual((snapshot['kind'],snapshot['id'],snapshot['difficulty']),('daily',daily['id'],'difficult'))
        response = self.req('POST',f"/practice/tasks/daily/{daily['id']}/feedback",{'result':'partial','actual_minutes':15,'basis':'self_report'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['feedback']['feedback_date'],'2026-10-24')

    def test_additive_schema_registration_preserves_old_rows(self):
        from unittest.mock import patch
        from app.database import ensure_schema
        _, project, stage = self.project()
        source = self.task(project,stage,'旧任务',60)
        DailyProjectPlan.__table__.drop(self.engine)
        with patch('app.database.engine', self.engine):
            ensure_schema()
        with self.Session() as db:
            self.assertEqual(db.get(ProjectTask,source['id']).title,'旧任务')
            self.assertEqual(db.query(DailyProjectPlan).count(),0)

    def test_execution_complete_finishes_daily_goal_not_the_project_task(self):
        from zoneinfo import ZoneInfo
        _, project, stage = self.project()
        source = self.task(project, stage, '跨多天的项目任务', 180)
        day = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        daily = self.plan(stage, source, day=day)
        started = self.req('POST', '/sessions/start', {'daily_task_id':daily['id'],'planned_minutes':20})
        self.assertEqual(started.status_code,200,started.text)
        finished = self.req('POST', f"/sessions/{started.json()['id']}/complete")
        self.assertEqual(finished.status_code,200,finished.text)
        with self.Session() as db:
            self.assertTrue(db.get(DailyTask,daily['id']).completed)
            self.assertEqual(db.get(ProjectTask,source['id']).state,'todo')
