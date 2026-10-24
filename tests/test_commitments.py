"""Synthetic, in-memory contracts for writing and preserving stage commitments."""
import io
import json
import unittest
import zipfile
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

import test_projects as fixture
from app import commitment_service as svc
from app.project_models import StageCommitment, StageCommitmentDraft, CommitmentAdjustment, ProjectTask, WorkSession


class CommitmentWritingTests(unittest.TestCase):
    def setUp(self):
        fixture.ProjectFlowTests.setUp(self)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
    tearDown = fixture.ProjectFlowTests.tearDown
    req = fixture.ProjectFlowTests.req
    project = fixture.ProjectFlowTests.project
    task = fixture.ProjectFlowTests.task

    def overview(self, project_id):
        response = self.req('GET', f'/commitments/projects/{project_id}')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def fresh(self):
        project = self.req('POST', '', {'title': '文献综述', 'outcome': '有出处的提纲'}).json()
        return project, self.overview(project['id'])['current_stage_id']

    def confirm(self, project_id, statement):
        data = self.overview(project_id)
        return self.req('POST', f"/commitments/stages/{data['current_stage_id']}/start", {
            'statement': statement, 'draft_revision': (data['draft'] or {}).get('revision', 0),
            'base_commitment_id': data['commitment']['id'] if data['commitment'] else None})

    def credit(self, adjustment_id):
        with self.Session() as db:
            row = db.get(CommitmentAdjustment, adjustment_id)
            start = datetime.utcnow()
            for second in range(32):
                svc.heartbeat(db, row, 'writing-page-lease-123', True, start + timedelta(seconds=second))
            db.commit()

    def test_draft_survives_reopening_without_confirming_and_is_account_scoped(self):
        project, stage_id = self.fresh()
        path = f'/commitments/stages/{stage_id}/draft'
        saved = self.req('PUT', path, {'statement': '先整理文献，再列提纲', 'revision': 0})
        self.assertEqual(saved.status_code, 200, saved.text)
        restored = self.overview(project['id'])
        self.assertEqual(restored['draft']['statement'], '先整理文献，再列提纲')
        self.assertIsNone(restored['commitment'])
        self.assertEqual(restored['history'], [])
        self.assertEqual(self.req('PUT', path, {'statement': '越权', 'revision': 1}, user=2).status_code, 404)
        self.assertEqual(self.req('GET', f"/commitments/projects/{project['id']}", user=2).status_code, 404)
        self.assertEqual(self.req('POST', f'/commitments/stages/{stage_id}/start', {'statement': '越权'}, user=2).status_code, 404)

    def test_stale_draft_cannot_overwrite_another_page_and_input_limits_are_enforced(self):
        project, stage_id = self.fresh()
        path = f'/commitments/stages/{stage_id}/draft'
        self.req('PUT', path, {'statement': '第一页面保存', 'revision': 0})
        self.assertEqual(self.req('PUT', path, {'statement': '第二页面的旧内容', 'revision': 0}).status_code, 409)
        self.assertEqual(self.req('POST', f'/commitments/stages/{stage_id}/start', {'statement': '旧确认', 'draft_revision': 0}).status_code, 409)
        self.assertEqual(self.overview(project['id'])['draft']['statement'], '第一页面保存')
        self.assertEqual(self.req('PUT', path, {'statement': '字' * 2001, 'revision': 1}).status_code, 422)
        self.assertEqual(self.confirm(project['id'], '   ').status_code, 400)
        self.assertIsNone(self.overview(project['id'])['commitment'])

    def test_confirmation_freezes_text_scope_and_is_idempotent(self):
        project, stage_id = self.fresh()
        self.task(project, {'id': stage_id}, '整理5篇文献', 50)
        self.req('PUT', f'/commitments/stages/{stage_id}/draft', {'statement': '先整理文献', 'revision': 0})
        response = self.confirm(project['id'], '  先整理文献，再列提纲  ')
        self.assertEqual(response.status_code, 200, response.text)
        first = self.overview(project['id'])
        self.assertEqual(first['commitment']['snapshot']['statement'], '先整理文献，再列提纲')
        self.assertEqual(first['commitment']['snapshot']['tasks'][0]['estimate'], 50)
        self.assertEqual(first['commitment']['snapshot']['outcome'], '有出处的提纲')
        self.assertEqual(self.confirm(project['id'], '先整理文献，再列提纲').json(), response.json())
        self.assertEqual(len(self.overview(project['id'])['history']), 1)
        self.assertEqual(self.req('PUT', f'/commitments/stages/{stage_id}/draft', {'statement': '直接覆盖', 'revision': 1}).status_code, 409)
        self.assertEqual(self.confirm(project['id'], '直接覆盖').status_code, 409)
        with self.Session() as db: self.assertEqual(db.query(WorkSession).count(), 0)

    def test_legacy_scope_can_gain_text_as_a_new_version_without_rewriting_history(self):
        _, project, stage = self.project()
        task = self.task(project, stage, '原任务', 30)
        with self.Session() as db:
            old = svc.commitment(db, 1, stage['id'])
            payload = json.loads(old.snapshot_json)
            payload.pop('statement', None)
            old.snapshot_json = json.dumps(payload, ensure_ascii=False)
            db.commit()
            old_id, original = old.id, old.snapshot_json
        response = self.confirm(project['id'], '先完成原任务，再考虑扩展')
        self.assertEqual(response.status_code, 200, response.text)
        data = self.overview(project['id'])
        self.assertEqual(data['commitment']['snapshot']['statement'], '先完成原任务，再考虑扩展')
        self.assertEqual(data['commitment']['snapshot']['tasks'][0]['id'], task['id'])
        with self.Session() as db: self.assertEqual(db.get(StageCommitment, old_id).snapshot_json, original)

    def test_automatic_project_start_never_confirms_draft_and_added_tasks_preserve_confirmed_text(self):
        project, stage_id = self.fresh()
        self.req('PUT', f'/commitments/stages/{stage_id}/draft', {'statement': '尚待核对的草稿', 'revision': 0})
        start = self.req('POST', f"/{project['id']}/execution-state", {'state': 'started', 'reason': '条件已具备'})
        self.assertEqual(start.status_code, 200, start.text)
        data = self.overview(project['id'])
        self.assertEqual(data['commitment']['snapshot']['statement'], '')
        self.assertEqual(data['draft']['statement'], '尚待核对的草稿')
        self.assertEqual(self.confirm(project['id'], '正式确认的承诺').status_code, 200)
        self.task(project, {'id': stage_id}, '新增但不丢承诺', 20)
        self.assertEqual(self.overview(project['id'])['commitment']['snapshot']['statement'], '正式确认的承诺')

    def test_scope_change_between_viewing_and_confirmation_requires_rechecking(self):
        _, project, stage = self.project()
        old = self.overview(project['id'])['commitment']['id']
        self.task(project, stage, '新增范围', 20)
        response = self.req('POST', f"/commitments/stages/{stage['id']}/start", {'statement': '确认旧页面', 'base_commitment_id': old})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(self.overview(project['id'])['commitment']['snapshot']['statement'])

    def test_adjustment_requires_existing_pause_and_preserves_original_and_reason(self):
        _, project, stage = self.project()
        task = self.task(project, stage, '提纲', 40)
        self.confirm(project['id'], '先写完提纲')
        before = self.overview(project['id'])['commitment']
        preview = self.req('POST', f"/commitments/projects/{project['id']}/preview", {
            'dispositions': [{'task_id': task['id'], 'action': 'defer'}],
            'changes': [{'kind': 'commitment_statement', 'value': '先补足材料，再核对提纲安排'}]})
        self.assertEqual(preview.status_code, 200, preview.text)
        adjustment = preview.json()
        self.assertTrue(adjustment['impact']['requires_wait'])
        path = f"/commitments/adjustments/{adjustment['id']}/confirm"
        self.assertEqual(self.req('POST', path, {'reason': '材料不足'}).status_code, 409)
        self.credit(adjustment['id'])
        self.assertEqual(self.req('POST', path, {'reason': '材料不足'}).status_code, 200)
        after = self.overview(project['id'])
        self.assertEqual(after['commitment']['snapshot']['statement'], '先补足材料，再核对提纲安排')
        self.assertEqual(after['adjustments'][0]['reason'], '材料不足')
        old = next(row for row in after['history'] if row['id'] == before['id'])
        self.assertEqual(old['snapshot'], before['snapshot'])
        with self.Session() as db:
            self.assertEqual(db.get(ProjectTask, task['id']).state, 'todo')
            self.assertNotEqual(db.get(ProjectTask, task['id']).stage_id, stage['id'])

    def test_normal_handover_does_not_copy_text_into_a_different_stage(self):
        _, project, stage = self.project()
        self.confirm(project['id'], '只针对当前阶段')
        overview = self.req('GET', '/overview').json()['projects'][0]
        target = next(row for row in overview['stages'] if row['state'] == 'next')
        result = self.req('POST', f"/stages/{target['id']}/activate", {'decision': 'close', 'reason': '本阶段已核对'})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.overview(project['id'])['commitment']['snapshot']['statement'], '')
        self.assertEqual(self.req('PUT', f"/commitments/stages/{stage['id']}/draft", {'statement': '旧阶段', 'revision': 0}).status_code, 409)

    def test_adjusting_an_unstarted_draft_saves_text_without_inventing_a_confirmation(self):
        project, stage_id = self.fresh()
        preview = self.req('POST', f"/commitments/projects/{project['id']}/preview", {
            'dispositions': [], 'changes': [{'kind': 'commitment_statement', 'value': '先探索，再确认范围'}]})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertFalse(preview.json()['impact']['requires_wait'])
        result = self.req('POST', f"/commitments/adjustments/{preview.json()['id']}/confirm", {'reason': '整理草稿'})
        self.assertEqual(result.status_code, 200, result.text)
        data = self.overview(project['id'])
        self.assertIsNone(data['commitment'])
        self.assertEqual(data['draft']['statement'], '先探索，再确认范围')

    def test_no_unfinished_work_means_text_revision_does_not_force_a_pause(self):
        _, project, stage = self.project()
        self.confirm(project['id'], '已完成本轮范围')
        preview = self.req('POST', f"/commitments/projects/{project['id']}/preview", {
            'dispositions': [], 'changes': [{'kind': 'commitment_statement', 'value': '本轮结果已核对，准备交接'}]})
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertFalse(preview.json()['impact']['requires_wait'])
        result = self.req('POST', f"/commitments/adjustments/{preview.json()['id']}/confirm", {'reason': '已完成后核对'})
        self.assertEqual(result.status_code, 200, result.text)

    def test_drafts_and_confirmed_versions_are_in_backup_and_private_export(self):
        project, stage_id = self.fresh()
        self.req('PUT', f'/commitments/stages/{stage_id}/draft', {'statement': '自己的草稿', 'revision': 0})
        with self.Session() as db:
            from app.models import User
            from app.backup import build_backup_zip
            from app.user_export import build_user_export_zip
            backup = zipfile.ZipFile(io.BytesIO(build_backup_zip(db)))
            self.assertIn('stage_commitment_drafts.csv', backup.namelist())
            mine = zipfile.ZipFile(io.BytesIO(build_user_export_zip(db, db.get(User, 1))))
            self.assertEqual(json.loads(mine.read('stage_commitment_drafts.json'))[0]['statement'], '自己的草稿')
            other = zipfile.ZipFile(io.BytesIO(build_user_export_zip(db, db.get(User, 2))))
            self.assertEqual(json.loads(other.read('stage_commitment_drafts.json')), [])
