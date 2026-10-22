"""Acceptance contracts for R1-R8; all data is synthetic and lives in memory."""
import io
import json
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import sessionmaker

import test_projects as fixture
from app import commitment_service as commitments
from app.practice_service import training_report
from app.project_models import (TaskPractice, PracticeEvent, WorkSession, ProjectTask,
    ProjectStage, CommitmentAdjustment, StartCondition, StageCommitment)
from app.models import DailyTask


class PlanningPracticeTests(unittest.TestCase):
    def setUp(self):
        fixture.ProjectFlowTests.setUp(self)
        # Match production SessionLocal, rather than relying on implicit flushes.
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
    tearDown = fixture.ProjectFlowTests.tearDown
    req = fixture.ProjectFlowTests.req
    project = fixture.ProjectFlowTests.project
    task = fixture.ProjectFlowTests.task

    def daily(self, estimate=30, text="练习"):
        r = self.client.post('/api/schedule/tasks', json={"text": text, "task_date": "2026-10-22", "estimated_minutes": estimate})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['tasks'][-1]

    def feedback(self, kind, task_id, **changes):
        body = {"result": "completed", "actual_minutes": 45, "basis": "self_report",
                "reason": "漏算检查", "next_estimate": "下次加15分钟核对", **changes}
        return self.req('POST', f'/practice/tasks/{kind}/{task_id}/feedback', body)

    def manual(self, task_id=None, daily_id=None, start="2026-10-21T15:50:00Z", end="2026-10-21T16:10:00Z"):
        r = self.req('POST', '/sessions/manual', {"project_task_id":task_id, "daily_task_id":daily_id,
            "started_at":start, "ended_at":end, "correction_note":"真实补记", "label":"投入"})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def report(self, start="2026-10-22", end="2026-10-22"):
        with self.Session() as db: return training_report(db,1,start,end)

    def test_estimate_feedback_no_fake_interval_and_first_estimate_preserved(self):
        t=self.daily()
        r=self.req('POST',f"/practice/tasks/daily/{t['id']}/estimate",{"minutes":60,"reason":"新发现步骤"})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['original_estimate'],30)
        f=self.feedback('daily',t['id'])
        self.assertEqual(f.status_code,200,f.text)
        self.assertEqual(f.json()['feedback']['difference'],15)
        self.assertEqual(f.json()['feedback']['percent'],50)
        with self.Session() as db: self.assertEqual(db.query(WorkSession).count(),0)
        report=self.report()
        self.assertEqual(report['sample_count'],1)
        self.assertEqual(report['recorded_seconds'],0)

    def test_schedule_creation_saves_design_before_first_work_snapshot(self):
        response = self.client.post('/api/schedule/tasks', json={
            "text":"边写边设置", "task_date":"2026-10-22", "familiarity":"unfamiliar",
            "difficulty":"difficult", "importance":"important", "estimated_minutes":90,
        })
        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()['tasks'][-1]
        self.assertEqual(task['familiarity'], 'unfamiliar')
        self.assertEqual(task['estimated_minutes'], 90)
        state = task['practice']
        self.assertEqual(state['difficulty'], 'difficult')
        self.assertEqual(state['importance'], 'important')
        self.assertEqual(state['initial_importance'], 'important')
        self.assertIsNotNone(state['initial_marked_at'])
        self.assertIsNone(state['reviewed_at'])
        self.assertEqual(state['original_estimate'], 90)
        self.assertEqual(state['estimate_origin'], 'before_start')
        interval = self.manual(daily_id=task['id'])
        with self.Session() as db:
            snapshot = json.loads(db.get(WorkSession, interval['id']).practice_snapshot_json)
        self.assertEqual(snapshot['difficulty'], 'difficult')
        self.assertEqual(snapshot['importance'], 'important')
        self.assertEqual(self.req('GET', f"/practice/tasks/daily/{task['id']}", user=2).status_code, 404)

    def test_schedule_creation_rejects_invalid_design_without_partial_task(self):
        for values in [{"difficulty":"easy"}, {"importance":"highest"}]:
            response = self.client.post('/api/schedule/tasks', json={"text":"无效设计", "task_date":"2026-10-22", **values})
            self.assertEqual(response.status_code, 422, response.text)
        with self.Session() as db:
            self.assertEqual(db.query(DailyTask).count(), 0)
            self.assertEqual(db.query(TaskPractice).count(), 0)
        task = self.daily(None, text="只写文字也能添加")
        self.assertIsNone(task['familiarity'])
        self.assertIsNone(task['practice']['difficulty'])
        self.assertIsNone(task['practice']['importance'])
        self.assertIsNone(task['practice']['initial_marked_at'])

    def test_recorded_20_confirmed_30_not_50_and_beijing_midnight_clip(self):
        t=self.daily()
        self.manual(daily_id=t['id'])
        f=self.feedback('daily',t['id'],actual_minutes=30)
        self.assertEqual(f.status_code,200,f.text)
        self.assertEqual(f.json()['feedback']['recorded_minutes'],20)
        self.assertEqual(f.json()['feedback']['unallocated_difference'],10)
        self.assertEqual(self.report()['recorded_seconds'],600)
        self.assertEqual(self.report('2026-10-21','2026-10-21')['recorded_seconds'],600)
        self.assertEqual(self.req('GET',f"/practice/tasks/daily/{t['id']}").json()['recorded_minutes'],20)
        wrong=self.feedback('daily',t['id'],basis='timer_checked',actual_minutes=30)
        self.assertEqual(wrong.status_code,409)

    def test_partial_rework_scope_zero_and_retrospective_are_distinct(self):
        for estimate,result,scope in [(30,'partial',False),(30,'rework',False),(30,'completed',True),(0,'completed',False),(None,'completed',False)]:
            t=self.daily(estimate)
            f=self.feedback('daily',t['id'],result=result,scope_changed=scope).json()['feedback']
            self.assertFalse(f['comparable'])
            if not estimate:self.assertIsNone(f['percent'])
        t=self.daily(None)
        self.manual(daily_id=t['id'])
        r=self.req('POST',f"/practice/tasks/daily/{t['id']}/estimate",{"minutes":30,"reason":"已做后补填"}).json()
        self.assertEqual(r['estimate_origin'],'retrospective')
        self.assertFalse(self.feedback('daily',t['id']).json()['feedback']['comparable'])

    def test_feedback_corrections_keep_history_one_final_and_experience_link(self):
        t=self.daily();self.feedback('daily',t['id']);self.feedback('daily',t['id'],actual_minutes=50)
        self.assertEqual(len(self.report()['feedback']),1)
        experiences=self.req('GET','/practice/experiences').json()['items']
        self.assertEqual(len(experiences),1)
        other=self.daily(20)
        r=self.req('POST',f"/practice/tasks/daily/{other['id']}/estimate",{"minutes":35,"reason":"确认经验可比，保留核对余量","experience_id":experiences[0]['id']})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.req('POST',f"/practice/tasks/daily/{other['id']}/estimate",{"minutes":30,"reason":"借用他人经验","experience_id":experiences[0]['id']},user=2).status_code,404)

    def test_difficulty_initial_review_and_snapshot_not_rewritten(self):
        t=self.daily()
        path=f"/practice/tasks/daily/{t['id']}"
        self.req('PATCH',path+'/attributes',{"difficulty":"difficult","importance":"important","goal":"当时目标"})
        self.req('POST','/practice/review',{"goal":"当时目标","items":[{"kind":"daily","id":t['id'],"importance":"ordinary"}]})
        self.manual(daily_id=t['id'])
        self.req('PATCH',path+'/attributes',{"difficulty":"simple","importance":"unimportant","goal":"后来目标"})
        state=self.req('GET',path).json()
        self.assertEqual(state['initial_importance'],'important')
        self.assertIsNone(state['reviewed_at'])
        report=self.report()
        self.assertEqual(report['difficult_seconds'],600)
        self.assertEqual(report['work'][0]['planned_importance'],'ordinary')
        self.assertIsNone(report['work'][0]['actual_importance'])
        self.req('POST',path+'/progress',{"date":"2026-10-22","status":"recorded","advanced":"核对资料","blocker":"论证未完成","next_step":"列两条证据","reduce_prompts":True})
        self.assertEqual(self.report()['progress'][0]['advanced'],'核对资料')

    def test_inline_difficulty_patch_preserves_goal_importance_and_review(self):
        t = self.daily()
        path = f"/practice/tasks/daily/{t['id']}/attributes"
        self.req('PATCH', path, {"difficulty":"simple", "importance":"important", "goal":"完成课程"})
        self.req('POST', '/practice/review', {"goal":"完成课程", "items":[{"kind":"daily","id":t['id'],"importance":"ordinary"}]})
        before = self.req('GET', f"/practice/tasks/daily/{t['id']}").json()
        changed = self.req('PATCH', path, {"difficulty":"difficult"})
        self.assertEqual(changed.status_code, 200, changed.text)
        after = changed.json()
        self.assertEqual(after['difficulty'], 'difficult')
        for field in ['importance','initial_importance','initial_marked_at','reviewed_at','goal']:
            self.assertEqual(after[field], before[field])
        cleared = self.req('PATCH', path, {"difficulty":None}).json()
        self.assertIsNone(cleared['difficulty'])
        self.assertEqual(cleared['importance'], 'ordinary')
        self.assertEqual(cleared['goal'], '完成课程')
        self.assertIsNotNone(cleared['reviewed_at'])
        changed_goal = self.req('PATCH', path, {"goal":"新目标"}).json()
        self.assertIsNone(changed_goal['reviewed_at'])
        self.assertEqual(changed_goal['importance'], 'ordinary')

    def test_new_importance_does_not_translate_legacy_priority(self):
        t=self.daily()
        self.client.patch(f"/api/schedule/tasks/{t['id']}",json={"priority":2,"familiarity":"unfamiliar"})
        practice=self.req('GET',f"/practice/tasks/daily/{t['id']}").json()
        self.assertIsNone(practice['difficulty']);self.assertIsNone(practice['importance'])
        bad=self.req('PATCH',f"/practice/tasks/daily/{t['id']}/attributes",{"importance":"highest"})
        self.assertEqual(bad.status_code,422)
        first=self.req('POST','/practice/review',{"goal":"目标","items":[{"kind":"daily","id":t['id'],"importance":"important"}]})
        self.assertEqual(first.status_code,409)

    def test_reflection_unknown_no_and_references_without_double_accounting(self):
        t=self.daily();s=self.manual(daily_id=t['id'])
        day=self.req('GET','/practice/day/2026-10-22').json()
        self.assertIsNone(day['reflection'])
        r=self.req('POST','/practice/day/2026-10-22/reflection',{"answer":"yes","session_ids":[s['id']],"activity":"看有趣资料","minutes":10,"goal":"论文","next_step":"只看相关资料"})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.report()['recorded_seconds'],600)
        self.req('POST','/practice/day/2026-10-22/reflection',{"answer":"no"})
        self.assertEqual(self.report()['reflections']['2026-10-22']['answer'],'no')
        self.assertEqual(self.req('POST','/practice/day/2026-10-22/reflection',{"answer":"yes","session_ids":[s['id']]},user=2).status_code,404)

    def test_feasibility_history_exploration_no_automatic_success(self):
        goal,p,stage=self.project()
        for reason in ['先探索','拿到事实后修订']:
            r=self.req('POST',f"/practice/feasibility/goal/{goal['id']}",{"someone_did_it":True,"small_gap":True,
                "reference":"案例","method":"先试验","reference_time":"三个月","gap":"缺设备","bridge":"借设备","exploration":"先做样机","reason":reason})
            self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(r.json()['history']),2)
        self.assertNotIn('feasible',r.json()['latest'])

    def test_rehearsal_preparation_is_explicit_and_old_note_preserved(self):
        _,p,stage=self.project();t=self.task(p,stage,'预演')
        self.req('PATCH',f"/tasks/{t['id']}",{"rehearsal_note":"原笔记"})
        r=self.req('PUT',f"/practice/tasks/task/{t['id']}/rehearsal",{"first_step":"打开资料","sequence":"先读后核对","preparation":"材料","difficulty":"缺依据","response":"先探索","preparation_action":"checklist"})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['legacy_rehearsal'],'原笔记')
        self.assertEqual(r.json()['checklist'][0]['group'],'preparation')
        s=self.req('POST','/sessions/start',{"project_task_id":t['id']}).json()
        self.assertEqual(s['practice_snapshot']['rehearsal']['first_step'],'打开资料')
        self.assertEqual(self.req('GET','/overview').json()['projects'][0]['tasks'][0]['prerequisite_ids'],[])

    def test_checklist_edit_sort_na_and_completion_exception(self):
        for kind in ['daily','task']:
            if kind=='daily': t=self.daily()
            else:
                _,p,stage=self.project();t=self.task(p,stage,'核对')
            path=f"/practice/tasks/{kind}/{t['id']}"
            r=self.req('PUT',path+'/checklist',{"items":[{"text":"准备","group":"preparation"},{"text":"核对结果","done":True}]}).json()
            items=r['checklist'];items[0]['text']='新准备';items[0]['not_applicable']='本次无须打印'
            payload=[{k:c.get(k) for k in ['id','text','done','group','not_applicable']} for c in reversed(items)]
            self.req('PUT',path+'/checklist',{"items":payload})
            self.assertEqual(self.feedback(kind,t['id']).status_code,200)
        t=self.daily();path=f"/practice/tasks/daily/{t['id']}"
        self.req('PUT',path+'/checklist',{"items":[{"text":"未查"}]})
        self.assertEqual(self.feedback('daily',t['id']).status_code,409)
        self.assertEqual(self.feedback('daily',t['id'],checklist_exception='线上结果已核对，纸质项例外').status_code,200)

    def plan(self,p,stage,task,**kwargs):
        body={"dispositions":[{"task_id":task['id'],"action":"defer"}],**kwargs}
        r=self.req('POST',f"/commitments/projects/{p['id']}/preview",body)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def credit(self,adjustment_id,seconds=31):
        with self.Session() as db:
            row=db.get(CommitmentAdjustment,adjustment_id);base=datetime.utcnow()
            for n in range(seconds+1): commitments.heartbeat(db,row,'single-page-token-123',True,base+timedelta(seconds=n))
            db.commit()

    def test_30_seconds_server_gate_refresh_single_lease_and_hidden_gaps(self):
        _,p,stage=self.project();t=self.task(p,stage,'承诺',30)
        a=self.plan(p,stage,t)
        self.assertEqual(self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"变化"}).status_code,409)
        with self.Session() as db:
            row=db.get(CommitmentAdjustment,a['id']);base=datetime.utcnow()
            commitments.heartbeat(db,row,'single-page-token-123',True,base)
            commitments.heartbeat(db,row,'single-page-token-123',True,base+timedelta(seconds=1))
            self.assertEqual(row.elapsed_ms,1000)
            with self.assertRaises(Exception):commitments.heartbeat(db,row,'another-page-token-123',True,base+timedelta(seconds=2))
            commitments.heartbeat(db,row,'single-page-token-123',False,base+timedelta(seconds=2))
            commitments.heartbeat(db,row,'single-page-token-123',True,base+timedelta(seconds=90))
            self.assertEqual(row.elapsed_ms,1000)
            commitments.heartbeat(db,row,'single-page-token-123',True,base+timedelta(seconds=180))
            self.assertEqual(row.elapsed_ms,1000)
            db.commit()
        restored=self.plan(p,stage,t)
        self.assertEqual(restored['id'],a['id']);self.assertEqual(restored['elapsed_ms'],1000)
        self.credit(a['id'])
        self.assertEqual(self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"  "}).status_code,400)
        first=self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"资源变化，明确延期"})
        self.assertEqual(first.status_code,200,first.text)
        again=self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"重试"})
        self.assertEqual(first.json(),again.json())
        with self.Session() as db:
            self.assertNotEqual(db.get(ProjectTask,t['id']).stage_id,stage['id'])
            self.assertNotEqual(db.get(ProjectTask,t['id']).state,'completed')
            self.assertEqual(db.query(WorkSession).count(),0)

    def test_active_timer_cannot_feed_wait_and_dependency_change_invalidates(self):
        _,p,stage=self.project();t=self.task(p,stage,'A')
        s=self.req('POST','/sessions/start',{"project_task_id":t['id']}).json()
        self.assertEqual(self.req('POST',f"/commitments/projects/{p['id']}/preview",{"dispositions":[{"task_id":t['id'],"action":"defer"}]}).status_code,409)
        self.req('POST',f"/sessions/{s['id']}/stop",{"pause":True})
        a=self.plan(p,stage,t)
        self.req('POST',f"/conditions/task/{t['id']}",{"title":"新收到的条件","kind":"resource"})
        self.assertEqual(self.req('POST',f"/commitments/adjustments/{a['id']}/visible",{"token":"single-page-token-123","visible":True}).status_code,409)
        revised=self.plan(p,stage,t);self.assertNotEqual(revised['id'],a['id']);self.assertEqual(revised['elapsed_ms'],0)

    def test_legacy_scope_endpoints_guarded_next_stage_blocked_and_conditions_still_apply(self):
        _,p,stage=self.project();t=self.task(p,stage,'A')
        next_stage=next(s for s in self.req('GET','/overview').json()['projects'][0]['stages'] if s['state']=='next')
        future=self.task(p,next_stage,'B')
        self.assertEqual(self.req('POST','/sessions/start',{"project_task_id":future['id']}).status_code,409)
        self.assertEqual(self.req('PATCH',f"/tasks/{t['id']}",{"stage_id":next_stage['id']}).status_code,409)
        self.assertEqual(self.req('PATCH',f"/tasks/{t['id']}",{"acceptance_criteria":"缩小"}).status_code,409)
        self.assertEqual(self.req('POST',f"/stages/{next_stage['id']}/activate",{"decision":"adjust"}).status_code,409)
        self.req('POST',f"/conditions/task/{future['id']}",{"title":"等待文件","kind":"resource"})
        a=self.plan(p,stage,t,target_stage_id=next_stage['id']);self.credit(a['id'])
        self.assertEqual(self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"提前切换"}).status_code,409)
        with self.Session() as db:
            self.assertEqual(db.get(ProjectTask,t['id']).stage_id,stage['id'])
            self.assertEqual(db.query(ProjectStage).filter_by(project_id=p['id']).count(),2)

    def test_normal_handover_no_wait_closed_history_and_new_next(self):
        _,p,stage=self.project();t=self.task(p,stage,'A')
        self.feedback('task',t['id'])
        next_stage=next(s for s in self.req('GET','/overview').json()['projects'][0]['stages'] if s['state']=='next')
        r=self.req('POST',f"/stages/{next_stage['id']}/activate",{"decision":"close"})
        self.assertEqual(r.status_code,200,r.text)
        states=[s['state'] for s in self.req('GET','/overview').json()['projects'][0]['stages']]
        self.assertEqual(sorted(states),['closed','current','next'])

    def test_complete_cycle_review_and_next_choice_with_evidence(self):
        _,p,stage=self.project();t=self.task(p,stage,'A',30)
        c=self.req('POST',f"/practice/projects/{p['id']}/cycles",{"start_date":"2026-10-20","end_date":"2026-10-26","horizon":"week","expected_result":"交出资料表","available_minutes":20,"task_ids":[t['id']]}).json()
        self.assertTrue(any('超过' in s for s in c['suggestions']))
        self.manual(task_id=t['id']);self.feedback('task',t['id'],result='partial')
        r=self.req('POST',f"/practice/cycles/{c['id']}/review",{"actual_result":"得到资料表，论证待做","unforeseen":"新依赖","conditions":"等待回复","goal_help":"资料有用","next_changes":"先核对证据","horizon_decision":"shorten","reason":"可用时间较少"})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['review']['evidence']['actual_interval_minutes'],20)
        n=self.req('POST',f"/practice/projects/{p['id']}/cycles",{"start_date":"2026-10-27","end_date":"2026-10-29","horizon":"custom","expected_result":"核对证据","task_ids":[t['id']],"previous_cycle_id":c['id']})
        self.assertEqual(n.status_code,200,n.text)

    def test_project_daily_identity_promotion_and_export_history(self):
        t=self.daily();self.feedback('daily',t['id'],result='partial')
        _,p,stage=self.project()
        promoted=self.req('POST',f"/daily/{t['id']}/project",{"project_id":p['id']}).json()
        self.assertEqual(len([e for e in self.req('GET',f"/practice/tasks/task/{promoted['id']}").json()['history'] if e['type']=='feedback']),1)
        with self.Session() as db:
            from app.user_export import build_user_export_zip
            from app.backup import build_backup_zip
            from app.models import User
            archive=zipfile.ZipFile(io.BytesIO(build_user_export_zip(db,db.get(User,1))))
            self.assertIn('practice_events.json',archive.namelist())
            self.assertIn('stage_commitments.json',archive.namelist())
            rows=json.loads(archive.read('practice_events.json'))
            self.assertTrue(all(r['user_id']==1 for r in rows))
            backup=zipfile.ZipFile(io.BytesIO(build_backup_zip(db)))
            self.assertIn('commitment_adjustments.csv',backup.namelist())

    def test_legacy_daily_completion_settles_running_work_and_pending_feedback_visible(self):
        t=self.daily()
        s=self.req('POST','/sessions/start',{"daily_task_id":t['id']}).json()
        r=self.client.patch(f"/api/schedule/tasks/{t['id']}",json={"completed":True})
        self.assertEqual(r.status_code,200,r.text)
        with self.Session() as db:
            self.assertIsNotNone(db.get(WorkSession,s['id']).ended_at)
        self.assertTrue(any(t['id']==r['id'] for r in self.report()['awaiting_feedback']))

    def test_goal_revision_retains_actual_goal_snapshot_and_records_stop_reason(self):
        goal,p,stage=self.project();t=self.task(p,stage,'目标判断')
        s=self.manual(task_id=t['id'])
        self.req('PUT',f"/sessions/{s['id']}/assessment",{"goal_id":goal['id'],"importance":"important","interesting":True})
        r=self.req('POST',f"/practice/goals/{goal['id']}/revise",{"title":"探索更小目标","horizon_end":"2026-11-01","status":"stopped","reason":"现有资源不足，先停止此目标"})
        self.assertEqual(r.status_code,200,r.text)
        data=self.req('GET',f"/practice/feasibility/goal/{goal['id']}").json()
        self.assertEqual(data['status'],'stopped');self.assertEqual(data['revisions'][0]['data']['before']['title'],'交出初稿')
        self.assertEqual(self.report()['work'][0]['goal'],'交出初稿')

    def test_recorded_scope_change_excluded_without_relying_on_checkbox(self):
        _,p,stage=self.project();t=self.task(p,stage,'范围',30)
        a=self.plan(p,stage,t,dispositions=[{"task_id":t['id'],"action":"retain"}],
                    changes=[{"kind":"task_criteria","id":t['id'],"value":"缩小到只交付资料表"}])
        self.credit(a['id'])
        self.assertEqual(self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"范围变化"}).status_code,200)
        f=self.feedback('task',t['id']).json()['feedback']
        self.assertTrue(f['scope_changed']);self.assertFalse(f['comparable'])

    def test_cancel_not_complete_and_delivery_needs_explicit_revised_outcome(self):
        _,p,stage=self.project();t=self.task(p,stage,'取消范围')
        a=self.plan(p,stage,t,dispositions=[{"task_id":t['id'],"action":"cancel"}]);self.credit(a['id'])
        self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"外部条件改变"})
        r=self.req('POST',f"/{p['id']}/execution-state",{"state":"delivered","reason":"核对交付"})
        self.assertEqual(r.status_code,409)
        a=self.req('POST',f"/commitments/projects/{p['id']}/preview",{"dispositions":[],"changes":[{"kind":"project_outcome","value":"仅交付已有的筹备设计，明确撤销后续制作"}]}).json()
        self.assertEqual(a['elapsed_ms'],0);self.credit(a['id'])
        self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"明确调整后的真实交付范围"})
        r=self.req('POST',f"/{p['id']}/execution-state",{"state":"delivered","reason":"调整后的设计结果已交付"})
        self.assertEqual(r.status_code,200,r.text)
        with self.Session() as db:self.assertEqual(db.get(ProjectTask,t['id']).state,'cancelled')

    def test_historical_feedback_and_daily_reviews_keep_date_context(self):
        t=self.daily();self.feedback('daily',t['id'],result='partial',feedback_date='2026-10-20')
        self.feedback('daily',t['id'],result='completed',feedback_date='2026-10-22')
        self.assertEqual(self.report('2026-10-20','2026-10-20')['feedback'][0]['result'],'partial')
        self.req('PATCH',f"/practice/tasks/daily/{t['id']}/attributes",{"importance":"important","goal":"当天目标"})
        self.req('POST','/practice/review',{"goal":"当天目标","task_date":"2026-10-21","items":[{"kind":"daily","id":t['id'],"importance":"important"}]})
        current=self.req('GET','/practice/day/2026-10-22').json()
        self.assertIsNone(current['tasks'][0]['reviewed_at'])
        self.assertEqual(self.report('2026-10-21','2026-10-21')['planning_reviews'][0]['goal'],'当天目标')

    def test_draft_adjustments_do_not_wait_or_invent_formal_commitment(self):
        p=self.req('POST','',{"title":"草稿"}).json()
        stage=next(s for s in self.req('GET','/overview').json()['projects'][0]['stages'] if s['state']=='current')
        t=self.task(p,stage,'先整理草稿')
        a=self.plan(p,stage,t)
        self.assertFalse(a['impact']['requires_wait'])
        r=self.req('POST',f"/commitments/adjustments/{a['id']}/confirm",{"reason":"整理尚未开始的草稿"})
        self.assertEqual(r.status_code,200,r.text)
        self.assertIsNone(r.json()['commitment_id'])

    def test_retained_task_and_internal_dependency_enter_next_stage_atomically(self):
        _,p,stage=self.project();a=self.task(p,stage,'先做A')
        target=next(s for s in self.req('GET','/overview').json()['projects'][0]['stages'] if s['state']=='next')
        b=self.task(p,target,'再做B')
        self.req('POST',f"/tasks/{b['id']}/dependencies",{"prerequisite_id":a['id']})
        plan=self.plan(p,stage,a,target_stage_id=target['id'],dispositions=[{"task_id":a['id'],"action":"retain"}])
        self.credit(plan['id'])
        r=self.req('POST',f"/commitments/adjustments/{plan['id']}/confirm",{"reason":"把仍需继续的A与B一起交接"})
        self.assertEqual(r.status_code,200,r.text)
        tasks=self.req('GET','/overview').json()['projects'][0]['tasks']
        self.assertEqual({t['stage_id'] for t in tasks},{target['id']})
        self.assertTrue(next(t for t in tasks if t['id']==a['id'])['can_start'])
        self.assertFalse(next(t for t in tasks if t['id']==b['id'])['can_start'])

    def test_unrelated_edit_keeps_pause_but_related_deadline_invalidates(self):
        goal,p,stage=self.project();t=self.task(p,stage,'当前承诺')
        a=self.plan(p,stage,t)
        other=self.req('POST','',{"title":"无关项目"}).json()
        other_stage=next(s for s in self.req('GET','/overview').json()['projects'][0]['stages'] if s['state']=='current')
        self.task(other,other_stage,'无关事项')
        r=self.req('POST',f"/commitments/adjustments/{a['id']}/visible",{"token":"single-page-token-123","visible":True})
        self.assertEqual(r.status_code,200,r.text)
        self.req('POST',f"/practice/goals/{goal['id']}/revise",{"title":"交出初稿","horizon_end":"2026-11-05","reason":"重新核对实际期限"})
        r=self.req('POST',f"/commitments/adjustments/{a['id']}/visible",{"token":"single-page-token-123","visible":True})
        self.assertEqual(r.status_code,409)

    def test_daily_budget_separate_from_cumulative_task_estimate(self):
        _,p,stage=self.project();t=self.task(p,stage,'跨日任务',120)
        self.req('POST',f"/tasks/{t['id']}/schedule",{"task_date":"2026-10-22"})
        r=self.req('POST','/practice/day/2026-10-22/plan',{"goal":"先完成一部分","available_minutes":40,
            "allocations":[{"kind":"task","id":t['id'],"minutes":30}]})
        self.assertEqual(r.status_code,200,r.text)
        data=self.req('GET','/practice/day/2026-10-22').json()
        self.assertEqual(data['plan']['planned_minutes'],30)
        self.assertEqual(data['tasks'][0]['estimated_minutes'],120)
        self.assertEqual(self.report()['day_plans']['2026-10-22']['allocations'][0]['title'],'跨日任务')
        self.req('POST',f"/practice/tasks/task/{t['id']}/estimate",{"minutes":150,"reason":"补充核对步骤"})
        schedule=self.client.get('/api/schedule?task_date=2026-10-22').json()
        self.assertEqual(schedule['tasks'][0]['estimated_minutes'],150)
        self.assertEqual(self.req('GET','/practice/day/2026-10-22').json()['plan']['planned_minutes'],30)
