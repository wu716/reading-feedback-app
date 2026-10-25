"""Server-verified commitment changes. Visibility is an interaction signal, not proof of attention."""
import hashlib
import json
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.models import DailyTask
from app.project_models import (Goal, Project, ProjectStage, ProjectTask, PracticeEvent, StageCommitment, StageCommitmentDraft, CommitmentAdjustment,
                                StartCondition, TaskDependency, WorkSession)
from app.practice_service import dumps, lock_user, owner, recorded_minutes

COMMITMENT_TEXT = "当前列表是本阶段的执行承诺。严格执行有助于集中投入、完成关键工作，并检验原先的计划是否合理。后续想法先放入下一阶段，避免不断打断当前任务。"


def current_stage(db, project_id):
    return db.query(ProjectStage).filter_by(project_id=project_id, state="current").filter(ProjectStage.deleted_at.is_(None)).first()


def commitment(db, user_id, stage_id):
    return db.query(StageCommitment).filter_by(user_id=user_id, stage_id=stage_id).order_by(StageCommitment.id.desc()).first()


def task_scope(db, user_id, stage_id):
    return db.query(ProjectTask).filter_by(user_id=user_id, stage_id=stage_id).filter(ProjectTask.deleted_at.is_(None)).order_by(ProjectTask.id).all()


def owned_current_stage(db, user_id, stage_id):
    stage = db.get(ProjectStage, stage_id)
    if not stage or stage.user_id != user_id or stage.deleted_at is not None:
        raise HTTPException(404, "阶段不存在")
    owner(db, user_id, "project", stage.project_id)
    if stage.state != "current":
        raise HTTPException(409, "只能填写当前阶段的承诺")
    return stage


def draft(db, user_id, stage_id):
    return db.query(StageCommitmentDraft).filter_by(user_id=user_id, stage_id=stage_id).first()


def stage_snapshot(db, user_id, stage):
    project = db.get(Project, stage.project_id)
    tasks = task_scope(db, user_id, stage.id)
    return {"outcome": project.outcome, "tasks": [{"id": t.id, "title": t.title,
        "criteria": t.acceptance_criteria, "estimate": t.estimated_minutes} for t in tasks], "notice": COMMITMENT_TEXT}


def commit_stage(db, user_id, stage, *, statement=None):
    previous = commitment(db, user_id, stage.id)
    # Automatic scope versions carry only already-confirmed text, never a draft.
    if statement is None:
        statement = json.loads(previous.snapshot_json).get("statement", "") if previous else ""
    row = StageCommitment(user_id=user_id, project_id=stage.project_id, stage_id=stage.id,
        snapshot_json=dumps(stage_snapshot(db, user_id, stage) | {"statement": statement}))
    db.add(row); db.flush()
    return row


def guard_scope(db, user_id, task, *, include_completed=False):
    """Only actual shrinking/moving is guarded. Text, day placement and rotation stay free."""
    stage = db.get(ProjectStage, task.stage_id) if task.stage_id else None
    if stage and stage.state == "current" and (include_completed or task.state not in ("completed", "cancelled")) and commitment(db, user_id, stage.id):
        raise HTTPException(409, "这会改变已开始的当前承诺。请在项目的“调整当前承诺”中预览后果并完成30秒暂停；旧客户端请刷新。")


def record_scope_addition(db, user_id, task):
    stage = db.get(ProjectStage, task.stage_id) if task.stage_id else None
    if stage and stage.state == "current" and commitment(db, user_id, stage.id):
        db.flush()
        commit_stage(db, user_id, stage)


def project_scope_snapshot(db, user_id, project):
    tasks = db.query(ProjectTask).filter_by(user_id=user_id).order_by(ProjectTask.id).all()
    projects = db.query(Project).filter_by(user_id=user_id).order_by(Project.id).all()
    goals = db.query(Goal).filter_by(user_id=user_id).order_by(Goal.id).all()
    daily = db.query(DailyTask).filter_by(user_id=user_id).order_by(DailyTask.id).all()
    conditions = db.query(StartCondition).filter_by(user_id=user_id).order_by(StartCondition.id).all()
    dependencies = db.query(TaskDependency).filter_by(user_id=user_id).order_by(TaskDependency.id).all()
    graph = {}
    def connect(a, b):
        graph.setdefault(a, set()).add(b); graph.setdefault(b, set()).add(a)
    for t in tasks: connect(("task", t.id), ("project", t.project_id))
    for p in projects:
        if p.goal_id: connect(("project", p.id), ("goal", p.goal_id))
    for d in daily:
        if d.project_task_id: connect(("daily", d.id), ("task", d.project_task_id))
        if d.parent_id: connect(("daily", d.id), ("daily", d.parent_id))
    for d in dependencies: connect(("task", d.task_id), ("task", d.prerequisite_id))
    for c in conditions:
        if c.target_kind and c.removed_at is None: connect((c.owner_kind, c.owner_id), (c.target_kind, c.target_id))
    related, pending = {("project", project.id)}, [("project", project.id)]
    while pending:
        for node in graph.get(pending.pop(), ()):
            if node not in related: related.add(node); pending.append(node)
    tasks = [t for t in tasks if ("task", t.id) in related]
    projects = [p for p in projects if ("project", p.id) in related]
    daily = [d for d in daily if ("daily", d.id) in related]
    conditions = [c for c in conditions if (c.owner_kind, c.owner_id) in related]
    dependencies = [d for d in dependencies if ("task", d.task_id) in related]
    sessions = [s for s in db.query(WorkSession).filter_by(user_id=user_id).order_by(WorkSession.id)
                if ("task", s.project_task_id) in related or ("daily", s.daily_task_id) in related]
    day_plans = {}
    for e in db.query(PracticeEvent).filter(PracticeEvent.user_id == user_id, PracticeEvent.event_type == "day_plan",
            PracticeEvent.record_date.in_({d.task_date for d in daily})).order_by(PracticeEvent.id.desc()):
        day_plans.setdefault(str(e.record_date), {"id": e.id, "data": json.loads(e.payload_json)})
    return {"project": project.id, "outcome": project.outcome,
        "stages": [{"id": s.id, "state": s.state, "deleted": s.deleted_at, "commitment": (c.id if (c := commitment(db, user_id, s.id)) else None),
                    "draft_revision": (d.revision if (d := draft(db, user_id, s.id)) else 0)}
                   for s in db.query(ProjectStage).filter_by(project_id=project.id).order_by(ProjectStage.id)],
        "tasks": [{"id": t.id, "stage": t.stage_id, "state": t.state, "deleted": t.deleted_at,
            "title": t.title, "estimate": t.estimated_minutes, "criteria": t.acceptance_criteria} for t in tasks],
        "projects": [{"id": p.id, "state": p.execution_state, "outcome": p.outcome, "goal_id": p.goal_id, "deleted": p.deleted_at} for p in projects],
        "goals": [{"id": g.id, "title": g.title, "deadline": g.horizon_end, "status": g.status} for g in goals if ("goal", g.id) in related],
        "daily": [{"id": d.id, "parent": d.parent_id, "task": d.project_task_id, "date": d.task_date, "title": d.text, "completed": d.completed, "deleted": d.deleted_at} for d in daily],
        "sessions": [{"id": s.id, "start": s.started_at, "end": s.ended_at, "kind": s.kind} for s in sessions],
        "day_plans": day_plans,
        "conditions": [{c.name: getattr(row, c.name) for c in StartCondition.__table__.columns} for row in conditions],
        "dependencies": [(d.id, d.task_id, d.prerequisite_id) for d in dependencies]}


def fingerprint(db, user_id, project):
    return hashlib.sha256(dumps(project_scope_snapshot(db, user_id, project)).encode()).hexdigest()


def preview(db, user_id, project_id, plan):
    lock_user(db, user_id)
    _, project = owner(db, user_id, "project", project_id)
    stage = current_stage(db, project.id)
    if not stage: raise HTTPException(409, "没有当前阶段")
    from app.execution_service import settle_expired
    settle_expired(db, user_id)
    if db.query(WorkSession).filter_by(user_id=user_id, kind="work", ended_at=None).first():
        raise HTTPException(409, "请先明确暂停或结束工作片，再预览调整；等待时间不计入工作实耗")
    target_id = plan.get("target_stage_id")
    if target_id:
        target = db.get(ProjectStage, target_id)
        if not target or target.user_id != user_id or target.project_id != project.id or target.state != "next":
            raise HTTPException(400, "目标必须是本项目的下一阶段")
    unfinished = [t for t in task_scope(db, user_id, stage.id) if t.state not in ("completed", "cancelled")]
    actions = plan["dispositions"]
    action_map = {i["task_id"]: i["action"] for i in actions}
    if len(action_map) != len(actions) or set(action_map) != {t.id for t in unfinished}:
        raise HTTPException(400, "请逐项处理当前阶段每个未完成任务：保留推进、延期或取消")
    if not target_id and not any(a != "retain" for a in action_map.values()) and not plan.get("changes"):
        raise HTTPException(400, "方案没有改变，可以直接继续当前列表")
    for change in plan.get("changes", []):
        if change["kind"] == "commitment_statement":
            value = change["value"].strip()
            if not value or len(value) > 2000:
                raise HTTPException(400, "承诺文字须为1至2000字")
            if sum(c["kind"] == "commitment_statement" for c in plan["changes"]) > 1:
                raise HTTPException(400, "每次只能提交一份承诺文字")
            old = commitment(db, user_id, stage.id)
            if not target_id and old and value == json.loads(old.snapshot_json).get("statement", "") and len(plan["changes"]) == 1 and all(a == "retain" for a in action_map.values()):
                raise HTTPException(400, "承诺文字和任务范围没有变化，可以继续当前承诺")
            change["value"] = value
        elif change["kind"] == "task_criteria":
            _, t = owner(db, user_id, "task", change["id"])
            if t.stage_id != stage.id: raise HTTPException(400, "只能调整当前范围的完成标准")
        elif change["kind"] == "condition_remove":
            c = db.get(StartCondition, change["id"])
            if not c or c.user_id != user_id or c.removed_at: raise HTTPException(404, "条件不存在")
            ckind, own = owner(db, user_id, c.owner_kind, c.owner_id)
            if not ((ckind == "project" and own.id == project.id) or (ckind == "task" and own.project_id == project.id)):
                raise HTTPException(400, "条件不属于本项目")
        elif change["kind"] == "dependency_remove":
            d = db.get(TaskDependency, change["id"])
            if not d or d.user_id != user_id or d.project_id != project.id: raise HTTPException(404, "前置关系不存在")
        elif change["kind"] != "project_outcome": raise HTTPException(400, "不支持的范围变更")
    relevant = {t.id for t in unfinished}
    affected = []
    for d in db.query(TaskDependency).filter_by(user_id=user_id):
        if d.prerequisite_id in relevant:
            t = db.get(ProjectTask, d.task_id)
            affected.append({"kind": "task", "id": t.id, "title": t.title, "reason": f"仍需前置任务 #{d.prerequisite_id} 完成"})
    for c in db.query(StartCondition).filter(StartCondition.user_id == user_id, StartCondition.removed_at.is_(None)):
        if (c.target_kind == "task" and c.target_id in relevant) or (c.target_kind == "project" and c.target_id == project.id):
            affected.append({"kind": c.owner_kind, "id": c.owner_id, "title": c.title, "reason": "前置状态仍需实际满足；调整不会自动满足依赖"})
    # Follow downstream relationships as well as the immediately referenced edge.
    reverse = {}
    for d in db.query(TaskDependency).filter_by(user_id=user_id):
        reverse.setdefault(("task", d.prerequisite_id), set()).add(("task", d.task_id))
    for c in db.query(StartCondition).filter(StartCondition.user_id == user_id, StartCondition.removed_at.is_(None)):
        if c.target_kind in ("task", "project"):
            reverse.setdefault((c.target_kind, c.target_id), set()).add((c.owner_kind, c.owner_id))
    for t in db.query(ProjectTask).filter_by(user_id=user_id, execution_role="formal"):
        if t.project_id != project.id:
            reverse.setdefault(("project", t.project_id), set()).add(("task", t.id))
    pending = [("task", t.id) for t in unfinished] + [("project", project.id)]
    seen_nodes, named = set(pending), {(a["kind"], a["id"]) for a in affected}
    while pending:
        source = pending.pop()
        for node in reverse.get(source, ()):
            if node in seen_nodes: continue
            seen_nodes.add(node); pending.append(node)
            model = {"task": ProjectTask, "project": Project, "daily": DailyTask}.get(node[0])
            item = db.get(model, node[1]) if model else None
            if item and item.user_id == user_id and (node not in named):
                named.add(node)
                affected.append({"kind": node[0], "id": node[1], "title": getattr(item, "title", None) or item.text,
                    "reason": "处于下游依赖链；前置仍需实际完成或验收，取消和延期不会自动解除依赖"})
    impact = {"notice": COMMITMENT_TEXT, "question": "这次调整是因为条件确实变化，还是因为当前任务遇到了困难？",
        "unfinished": [{"id": t.id, "title": t.title, "action": action_map[t.id], "criteria": t.acceptance_criteria,
            "scheduled_dates": [str(d[0]) for d in db.query(DailyTask.task_date).filter(DailyTask.user_id == user_id,
                DailyTask.project_task_id == t.id, DailyTask.deleted_at.is_(None)).distinct().order_by(DailyTask.task_date)],
            "estimate": t.estimated_minutes, "recorded_minutes": recorded_minutes(db, user_id, "task", t.id)} for t in unfinished],
        "affected": affected, "delivery": project.outcome,
        "goal_deadline": str(db.get(Goal, project.goal_id).horizon_end or "未定") if project.goal_id else "未关联目标期限",
        "delivery_impact": "延期或取消的未完成项不计为完成；请核对以上交付与验收内容是否需要缩减。",
        "budget": "原预计合计 %s 分钟；%s 项未估时。日期和剩余预算需重新估计，不能据此推算确定延误天数。" % (
            sum(t.estimated_minutes or 0 for t in unfinished), sum(t.estimated_minutes is None for t in unfinished)),
        "history": "已投入时间、已有结果与任务身份保留。频繁调整可能增加重新进入任务的成本，使重要而困难的工作被持续推迟。",
        "changes": plan.get("changes", [])}
    scope_snapshot = project_scope_snapshot(db, user_id, project)
    impact["day_plans"] = scope_snapshot["day_plans"]
    encoded, fp = dumps(plan), hashlib.sha256(dumps(scope_snapshot).encode()).hexdigest()
    existing = db.query(CommitmentAdjustment).filter_by(user_id=user_id, project_id=project.id,
        stage_id=stage.id, plan_json=encoded, fingerprint=fp, confirmed_at=None).order_by(CommitmentAdjustment.id.desc()).first()
    if existing: return existing
    scope_changes = any(c["kind"] != "commitment_statement" for c in plan.get("changes", []))
    must_wait = bool(commitment(db, user_id, stage.id) and (unfinished or scope_changes))
    row = CommitmentAdjustment(user_id=user_id, project_id=project.id, stage_id=stage.id,
        plan_json=encoded, impact_json=dumps(impact | {"requires_wait": must_wait}), fingerprint=fp, elapsed_ms=0)
    db.add(row); db.flush(); return row


def adjustment_payload(row):
    requires_wait = json.loads(row.impact_json).get("requires_wait", True)
    return {"id": row.id, "project_id": row.project_id, "stage_id": row.stage_id,
        "plan": json.loads(row.plan_json), "impact": json.loads(row.impact_json),
        "elapsed_ms": row.elapsed_ms, "remaining_seconds": max(0, (30000 - row.elapsed_ms + 999) // 1000) if requires_wait else 0,
        "confirmed": row.confirmed_at is not None, "result": json.loads(row.result_json or "{}")}


def owned_adjustment(db, user_id, adjustment_id):
    row = db.get(CommitmentAdjustment, adjustment_id)
    if not row or row.user_id != user_id: raise HTTPException(404, "调整不存在")
    return row


def verify_unchanged(db, row):
    if row.fingerprint != fingerprint(db, row.user_id, db.get(Project, row.project_id)):
        raise HTTPException(409, "任务、条件或依赖已变化，请重新展示后果并等待；原调整记录保留")


def heartbeat(db, row, token, visible, now=None):
    now = now or datetime.utcnow()
    if row.confirmed_at: return
    verify_unchanged(db, row)
    if not json.loads(row.impact_json).get("requires_wait", True): return
    if db.query(WorkSession).filter_by(user_id=row.user_id, kind="work", ended_at=None).first():
        row.last_visible_at = None
        raise HTTPException(409, "工作计时已恢复，请先暂停；等待不与工作同时计时")
    if row.lease_token and row.lease_token != token and row.last_visible_at and now - row.last_visible_at < timedelta(seconds=4):
        raise HTTPException(409, "另一个页面正在展示此调整，请在同一个页面完成")
    if not visible:
        # No credit for the interval ending with a hidden signal.
        if row.lease_token == token: row.last_visible_at = None
        return
    if row.lease_token == token and row.last_visible_at:
        delta = (now - row.last_visible_at).total_seconds()
        # A long gap is not evidence of continuous visible presentation.
        if 0 <= delta <= 2.5:
            row.elapsed_ms = min(30000, row.elapsed_ms + int(delta * 1000))
    row.lease_token, row.last_visible_at = token, now


def confirm(db, row, reason):
    if row.confirmed_at: return json.loads(row.result_json)
    verify_unchanged(db, row)
    if json.loads(row.impact_json).get("requires_wait", True) and row.elapsed_ms < 30000:
        raise HTTPException(409, "后果说明的前台暂停尚未满30秒")
    if not reason.strip(): raise HTTPException(400, "请说明本次调整原因")
    if db.query(WorkSession).filter_by(user_id=row.user_id, kind="work", ended_at=None).first():
        raise HTTPException(409, "请先暂停工作计时")
    plan = json.loads(row.plan_json)
    project = db.get(Project, row.project_id)
    current = db.get(ProjectStage, row.stage_id)
    had_commitment = commitment(db, row.user_id, current.id) is not None
    target = db.get(ProjectStage, plan["target_stage_id"]) if plan.get("target_stage_id") else None
    following = db.query(ProjectStage).filter(ProjectStage.project_id == project.id, ProjectStage.state == "next",
        ProjectStage.deleted_at.is_(None),
        ProjectStage.id != (target.id if target else -1)).order_by(ProjectStage.position).first()
    if following is None and (target or any(d["action"] == "defer" for d in plan["dispositions"])):
        following = ProjectStage(user_id=row.user_id, project_id=project.id, title="下一阶段", state="next",
            position=max((s.position for s in db.query(ProjectStage).filter_by(project_id=project.id)), default=0) + 1)
        db.add(following); db.flush()
    for d in plan["dispositions"]:
        t = db.get(ProjectTask, d["task_id"])
        if d["action"] == "cancel": t.state = "cancelled"
        elif d["action"] == "defer": t.stage_id = following.id
        elif target: t.stage_id = target.id
    from app.start_conditions import record_event
    for change in plan.get("changes", []):
        if change["kind"] == "project_outcome": project.outcome = change["value"]
        elif change["kind"] == "task_criteria": db.get(ProjectTask, change["id"]).acceptance_criteria = change["value"]
        elif change["kind"] == "condition_remove":
            c = db.get(StartCondition, change["id"])
            c.removed_at = datetime.utcnow()
            record_event(db, row.user_id, c.owner_kind, c.owner_id, "condition_removed", reason=reason, condition_id=c.id)
        elif change["kind"] == "dependency_remove":
            d = db.get(TaskDependency, change["id"])
            record_event(db, row.user_id, "task", d.task_id, "dependency_removed", before={"prerequisite_id": d.prerequisite_id}, reason=reason)
            db.delete(d)
    db.flush()
    if target:
        from app.start_conditions import require_ready
        require_ready(db, row.user_id, "project", project.id)
        # Evaluate the final proposed scope, including retained tasks and any
        # explicitly documented condition changes, in this same transaction.
        require_stage_ready(db, row.user_id, target)
    if target:
        current.state, current.closed_at, current.closed_reason = "closed", datetime.utcnow(), reason
        target.state = "current"
    db.flush()
    statement = next((c["value"] for c in plan.get("changes", []) if c["kind"] == "commitment_statement"), None)
    if not had_commitment and statement is not None:
        saved = draft(db, row.user_id, (target or current).id)
        if saved is None:
            saved = StageCommitmentDraft(user_id=row.user_id, stage_id=(target or current).id, revision=0)
            db.add(saved)
        saved.statement, saved.revision, saved.updated_at = statement, saved.revision + 1, datetime.utcnow()
    new_commit = commit_stage(db, row.user_id, target or current, statement=statement) if had_commitment else None
    row.reason, row.confirmed_at, row.last_visible_at = reason, datetime.utcnow(), None
    result = {"current_stage_id": (target or current).id, "commitment_id": new_commit.id if new_commit else None, "dispositions": plan["dispositions"]}
    row.result_json = dumps(result)
    return result


def require_stage_ready(db, user_id, target):
    from app.start_conditions import active_conditions, evaluate_condition
    ids = {t.id for t in task_scope(db, user_id, target.id)}
    for t in task_scope(db, user_id, target.id):
        if t.state in ("completed", "cancelled"): continue
        conditions = [evaluate_condition(db, c) for c in active_conditions(db, user_id, "task", t.id)]
        blockers = [b for b in conditions if b["strength"] == "required" and b["check_at"] in ("start", "throughout")
                    and not b["satisfied"] and not (b["target_kind"] == "task" and b["target_id"] in ids)]
        for d in db.query(TaskDependency).filter_by(user_id=user_id, task_id=t.id):
            p = db.get(ProjectTask, d.prerequisite_id)
            if d.prerequisite_id not in ids and (not p or p.deleted_at or p.state != "completed"):
                blockers.append({"title": f"前置任务 #{d.prerequisite_id} 尚未完成或已移除"})
        if blockers: raise HTTPException(409, {"message": "下一阶段仍有未满足的必要条件", "task": t.title, "blockers": json.loads(dumps(blockers))})
