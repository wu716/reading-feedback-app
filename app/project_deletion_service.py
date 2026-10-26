"""Recoverable project deletion without rewriting work, feedback or task identity."""
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_

from app import commitment_service as commitments
from app.execution_service import settle_expired
from app.models import DailyTask, SelfTalkReminderLog
from app.project_models import (
    Project, ProjectStage, ProjectTask, ProjectDeletion, TaskDependency,
    StartCondition, WorkSession, ExecutionPlan, FeedbackOccurrence, FeedbackDelivery,
    StageCommitmentDraft, StageCommitment, CommitmentAdjustment, TaskChecklistItem,
)
from app.practice_service import dumps, lock_user, today
from app.schedule_todos import sync_task_reminder
from app.start_conditions import record_event

MODELS = {"project": Project, "stage": ProjectStage, "task": ProjectTask}
LABELS = {"project": "项目", "stage": "阶段", "task": "任务"}


def owned(db, user_id, kind, target_id, *, deleted=False):
    model = MODELS.get(kind)
    row = db.get(model, target_id) if model else None
    if row is None or row.user_id != user_id or (not deleted and row.deleted_at is not None):
        raise HTTPException(404, "内容不存在")
    return row


def batch(db, user_id, batch_id):
    row = db.get(ProjectDeletion, batch_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, "删除记录不存在")
    return row


def marked(item, row):
    value = item.deleted_at
    if value is not None and value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value is not None and value == row.confirmed_at


def live(db, user_id, kind, row_id):
    model = {**MODELS, "daily": DailyTask}.get(kind)
    item = db.get(model, row_id) if model else None
    if item is None or item.user_id != user_id or item.deleted_at is not None:
        return False
    task = db.get(ProjectTask, item.project_task_id) if kind == "daily" and item.project_task_id else item if kind == "task" else None
    if task:
        if task.user_id != user_id or task.deleted_at is not None:
            return False
        project = db.get(Project, task.project_id)
        stage = db.get(ProjectStage, task.stage_id) if task.stage_id else None
        return bool(project and project.user_id == user_id and project.deleted_at is None and (not stage or stage.deleted_at is None))
    return True


def scope(db, user_id, kind, target_id):
    item = owned(db, user_id, kind, target_id)
    project = owned(db, user_id, "project", item.id if kind == "project" else item.project_id)
    stages = db.query(ProjectStage).filter_by(user_id=user_id, project_id=project.id).filter(ProjectStage.deleted_at.is_(None)).all()
    stages = stages if kind == "project" else [item] if kind == "stage" else []
    tasks = db.query(ProjectTask).filter_by(user_id=user_id, project_id=project.id).filter(ProjectTask.deleted_at.is_(None))
    if kind == "stage": tasks = tasks.filter_by(stage_id=item.id)
    if kind == "task": tasks = tasks.filter_by(id=item.id)
    tasks = tasks.order_by(ProjectTask.id).all()
    ids = {t.id for t in tasks}
    all_daily = db.query(DailyTask).filter_by(user_id=user_id).all()
    daily_ids = {d.id for d in all_daily if d.project_task_id in ids}
    # Include descendants, even when only the parent's project identity is stored.
    while True:
        children = {d.id for d in all_daily if d.parent_id in daily_ids}
        if children <= daily_ids: break
        daily_ids |= children
    daily = [d for d in all_daily if d.id in daily_ids and d.deleted_at is None and not d.completed]
    owners = {("task", t.id) for t in tasks} | {("daily", d.id) for d in daily}
    if kind == "project": owners.add(("project", project.id))
    affected = []
    for edge in db.query(TaskDependency).filter_by(user_id=user_id):
        if edge.prerequisite_id in ids and edge.task_id not in ids and live(db, user_id, "task", edge.task_id):
            other = db.get(ProjectTask, edge.task_id)
            affected.append({"kind": "task", "id": other.id, "project_id": other.project_id,
                             "title": other.title, "condition": "任务前置关系"})
    for condition in db.query(StartCondition).filter_by(user_id=user_id).filter(StartCondition.removed_at.is_(None)):
        target = (condition.target_kind, condition.target_id)
        if target in owners and (condition.owner_kind, condition.owner_id) not in owners and live(db, user_id, condition.owner_kind, condition.owner_id):
            model = {"project": Project, "task": ProjectTask, "daily": DailyTask}[condition.owner_kind]
            other = db.get(model, condition.owner_id)
            affected.append({"kind": condition.owner_kind, "id": other.id,
                "project_id": other.id if condition.owner_kind == "project" else getattr(other, "project_id", None),
                "title": getattr(other, "title", None) or other.text, "condition": condition.title})
    requires_wait = any((kind == "stage" or t.state not in ("completed", "cancelled")) and t.stage_id and
        (s := db.get(ProjectStage, t.stage_id)).state == "current" and commitments.commitment(db, user_id, s.id) for t in tasks)
    # Removing an empty confirmed current stage/project also removes the commitment surface.
    requires_wait = bool(requires_wait or any(s.state == "current" and commitments.commitment(db, user_id, s.id) for s in stages))
    sessions = db.query(WorkSession).filter(WorkSession.user_id == user_id,
        or_(WorkSession.project_task_id.in_(ids), WorkSession.daily_task_id.in_(daily_ids))).all()
    running = db.query(WorkSession).filter_by(user_id=user_id, kind="work", ended_at=None).all()
    running = [s for s in running if requires_wait or s in sessions]
    return project, item, stages, tasks, daily, sessions, affected, requires_wait, running


def stage_has_execution(db, user_id, tasks, daily, sessions, stage_id=None):
    """A written plan is not work; any durable progress is work."""
    task_ids = [t.id for t in tasks]
    if stage_id is not None:
        task_ids = [row[0] for row in db.query(ProjectTask.id).filter_by(stage_id=stage_id).all()]
    sessions_exist = bool(sessions or (task_ids and db.query(WorkSession.id).filter(WorkSession.user_id == user_id,
        WorkSession.project_task_id.in_(task_ids), WorkSession.kind == "work").first()))
    completed_daily = bool(task_ids and db.query(DailyTask.id).filter(DailyTask.user_id == user_id,
        DailyTask.project_task_id.in_(task_ids),
        DailyTask.completed.is_(True)).first())
    task_progress = bool(task_ids and db.query(ProjectTask.id).filter(ProjectTask.user_id == user_id,
        ProjectTask.id.in_(task_ids),
        (ProjectTask.state != "todo") | ProjectTask.completed_at.isnot(None) |
        ProjectTask.outcome_note.isnot(None) | ProjectTask.variance_reason.isnot(None)).first())
    checklist_progress = bool(task_ids and db.query(TaskChecklistItem.id).filter(
        TaskChecklistItem.user_id == user_id, TaskChecklistItem.task_id.in_(task_ids),
        TaskChecklistItem.done.is_(True)).first())
    return bool(sessions_exist or completed_daily or checklist_progress or task_progress)


def preview(db, user_id, kind, target_id, *, stage_tasks="delete"):
    lock_user(db, user_id)
    settle_expired(db, user_id)
    project, item, stages, tasks, daily, sessions, affected, wait, running = scope(db, user_id, kind, target_id)
    if kind != "stage" and stage_tasks != "delete":
        raise HTTPException(400, "仅删除阶段时可选择保留任务")
    if stage_tasks not in ("delete", "keep"):
        raise HTTPException(400, "请选择任务去向")
    has_execution = kind == "stage" and stage_has_execution(db, user_id, tasks, daily, sessions, item.id)
    if kind == "stage" and not has_execution:
        wait = False
        running = []
    if has_execution and stage_tasks == "delete":
        stage_tasks = "keep"
    if kind == "stage" and stage_tasks == "keep":
        # Stage identity is removed from the workspace, while task identity survives.
        affected = []
    content = {"project": [project.id] if kind == "project" else [], "stage": [s.id for s in stages],
               "task": [t.id for t in tasks] if stage_tasks == "delete" else [],
               "daily": [d.id for d in daily] if stage_tasks == "delete" else [],
               "retained_task": [t.id for t in tasks] if kind == "stage" and stage_tasks == "keep" else [],
               "hard_stage": kind == "stage"}
    if kind == "stage":
        content["stage_members"] = [row[0] for row in db.query(ProjectTask.id).filter_by(
            user_id=user_id, project_id=project.id, stage_id=item.id).all()]
        content["stage_snapshot"] = {"id": item.id, "user_id": item.user_id, "project_id": item.project_id,
            "title": item.title, "position": item.position, "state": item.state,
            "closed_reason": item.closed_reason, "created_at": item.created_at, "closed_at": item.closed_at}
    impact = {"requires_wait": wait, "notice": commitments.COMMITMENT_TEXT,
        "stages": len(stages), "tasks": len(tasks), "daily": len(daily),
        "stage_tasks": stage_tasks if kind == "stage" else None,
        "stage_has_execution": bool(has_execution),
        "task_titles": [{"id": t.id, "title": t.title} for t in tasks] if kind == "stage" else [],
        "sessions": len([s for s in sessions if s.kind == "work"]),
        "minutes": round(sum((s.ended_at - s.started_at).total_seconds() / 60 for s in sessions if s.kind == "work" and s.ended_at), 1),
        "affected": affected, "running": [{"id": s.id, "title": s.label or "正在进行的工作片"} for s in running]}
    fp = commitments.fingerprint(db, user_id, project)
    row = db.query(ProjectDeletion).filter_by(user_id=user_id, kind=kind, target_id=target_id,
        fingerprint=fp, scope_json=dumps(content), impact_json=dumps(impact), confirmed_at=None).order_by(ProjectDeletion.id.desc()).first()
    if row is None:
        row = ProjectDeletion(user_id=user_id, project_id=project.id, kind=kind, target_id=target_id,
            title=item.title, scope_json=dumps(content), impact_json=dumps(impact), fingerprint=fp)
        db.add(row); db.flush()
    return row


def pending_daily(db, row):
    ids = json.loads(row.scope_json)["daily"]
    return [d for d in db.query(DailyTask).filter(DailyTask.user_id == row.user_id, DailyTask.id.in_(ids)) if marked(d, row)] if row.confirmed_at else []


def payload(db, row):
    impact = json.loads(row.impact_json)
    pending = pending_daily(db, row)
    return {"id": row.id, "kind": row.kind, "target_id": row.target_id, "project_id": row.project_id,
        "title": row.title, "impact": impact, "reason": row.reason, "confirmed_at": row.confirmed_at, "restored_at": row.restored_at,
        "remaining_seconds": max(0, (30000 - row.elapsed_ms + 999) // 1000) if impact["requires_wait"] else 0,
        "pending_daily": [{"id": d.id, "title": d.text, "date": str(d.task_date)} for d in pending]}


def clear_execution(db, row, content):
    plan = db.get(ExecutionPlan, row.user_id)
    if not plan: return
    task_ids, daily_ids = set(content["task"]), set(content["daily"])
    def removed(key):
        kind, raw_id = key.split(":", 1)
        if kind in ("project", "task"): return int(raw_id) in task_ids
        if kind == "daily":
            daily = db.get(DailyTask, int(raw_id))
            return int(raw_id) in daily_ids or bool(daily and daily.user_id == row.user_id and daily.project_task_id in task_ids)
        return False
    plan.queue_json = dumps([key for key in json.loads(plan.queue_json) if not removed(key)])
    paused = db.get(WorkSession, plan.paused_session_id) if plan.paused_session_id else None
    if paused and (paused.project_task_id in task_ids or paused.daily_task_id in daily_ids):
        plan.paused_session_id, plan.remaining_seconds = None, None


def confirm(db, row, reason):
    if row.confirmed_at: return payload(db, row)
    commitments.verify_unchanged(db, row)
    _, _, _, tasks, daily, sessions, affected, wait, running = scope(db, row.user_id, row.kind, row.target_id)
    content = json.loads(row.scope_json)
    if row.kind == "stage":
        has_execution = stage_has_execution(db, row.user_id, tasks, daily, sessions, row.target_id)
        if has_execution and content["task"]:
            raise HTTPException(409, "这个阶段已有执行记录，请重新预览并保留任务与投入")
        if not has_execution:
            wait = False
            running = []
        if content.get("retained_task"):
            affected = []
    if affected: raise HTTPException(409, "还有其他内容依赖这里，请先调整前置条件，再重新预览")
    if running: raise HTTPException(409, "请先结束正在进行的工作计时，保留投入后重新预览")
    if wait and (not reason.strip() or row.elapsed_ms < 30000):
        raise HTTPException(409, "请说明原因并完成后果说明的30秒前台暂停")
    row.confirmed_at, row.reason, row.last_visible_at = datetime.utcnow(), reason.strip() or None, None
    deleted_at = row.confirmed_at.replace(tzinfo=timezone.utc)
    for kind in ("project", "stage", "task"):
        for item in db.query(MODELS[kind]).filter(MODELS[kind].user_id == row.user_id, MODELS[kind].id.in_(content[kind])):
            if not (kind == "stage" and content.get("hard_stage")):
                item.deleted_at = deleted_at
    for task in db.query(ProjectTask).filter(ProjectTask.user_id == row.user_id,
            ProjectTask.id.in_(content.get("retained_task", []))):
        task.stage_id = None
    for daily in db.query(DailyTask).filter(DailyTask.user_id == row.user_id, DailyTask.id.in_(content["daily"])):
        daily.deleted_at = deleted_at
        sync_task_reminder(db, daily, remind_time=None)
    clear_execution(db, row, content)
    if row.kind == "project":
        occurrences = db.query(FeedbackOccurrence).filter_by(user_id=row.user_id, project_id=row.project_id).all()
        ids = [o.id for o in occurrences]
        for occurrence in occurrences: occurrence.reminders_enabled = False
        for delivery in db.query(FeedbackDelivery).filter(FeedbackDelivery.user_id == row.user_id,
                FeedbackDelivery.occurrence_id.in_(ids), FeedbackDelivery.email_status.in_(("pending", "retry"))):
            delivery.email_status = "cancelled"
        # Already presented notifications stay in history, but are no longer outstanding.
        logs = db.query(FeedbackDelivery.log_id).filter(FeedbackDelivery.user_id == row.user_id, FeedbackDelivery.occurrence_id.in_(ids))
        for log in db.query(SelfTalkReminderLog).filter(SelfTalkReminderLog.user_id == row.user_id, SelfTalkReminderLog.id.in_(logs)):
            log.dismissed_at = deleted_at
    if row.kind == "stage" and content.get("hard_stage"):
        stage = db.get(ProjectStage, row.target_id)
        if not stage or stage.user_id != row.user_id:
            raise HTTPException(409, "阶段已经变化，请重新预览")
        for task in db.query(ProjectTask).filter_by(user_id=row.user_id, project_id=row.project_id, stage_id=stage.id):
            task.stage_original_id = stage.id
            task.stage_id = None
        for task in db.query(ProjectTask).filter(ProjectTask.user_id == row.user_id,
                ProjectTask.project_id == row.project_id, ProjectTask.id.in_(content.get("stage_members", []))):
            task.stage_original_id = stage.id
        for model in (StageCommitmentDraft, StageCommitment, CommitmentAdjustment):
            for history in db.query(model).filter_by(user_id=row.user_id, stage_id=stage.id):
                history.stage_original_id = stage.id
                history.stage_title_snapshot = stage.title
                if model is StageCommitmentDraft: history.project_id = stage.project_id
                if model is CommitmentAdjustment and history.confirmed_at is None:
                    history.fingerprint = ""
                history.stage_id = None
        db.flush()
        db.delete(stage)
    record_event(db, row.user_id, row.kind, row.target_id, "content_deleted", before=content, reason=row.reason)
    db.flush()
    if row.kind == "task":
        task = db.get(ProjectTask, row.target_id)
        stage = db.get(ProjectStage, task.stage_id) if task.stage_id else None
        if stage and stage.deleted_at is None and stage.state == "current" and commitments.commitment(db, row.user_id, stage.id):
            commitments.commit_stage(db, row.user_id, stage)
    return payload(db, row)


def restore(db, row, *, with_daily=False, past_date=None, stage_as_next=False, daily_ids=None, daily_dates=None):
    if not row.confirmed_at: raise HTTPException(409, "这条记录尚未执行删除")
    content = json.loads(row.scope_json)
    hard_stage = row.kind == "stage" and content.get("hard_stage")
    target = db.get(ProjectStage, row.target_id) if hard_stage else owned(db, row.user_id, row.kind, row.target_id, deleted=True)
    if hard_stage and target is not None and target.user_id != row.user_id:
        raise HTTPException(404, "内容不存在")
    project = owned(db, row.user_id, "project", row.project_id, deleted=True)
    if (row.kind != "project" and project.deleted_at is not None) or (row.restored_at and target is not None and target.deleted_at is not None):
        raise HTTPException(409, "请先恢复所属项目或再次删除的内容")
    if row.kind == "task" and target.stage_id:
        stage = owned(db, row.user_id, "stage", target.stage_id, deleted=True)
        if stage.deleted_at is not None: raise HTTPException(409, "请先恢复所属阶段")
    if row.kind == "task" and not target.stage_id and target.stage_original_id:
        stage = db.get(ProjectStage, target.stage_original_id)
        if stage is None or stage.user_id != row.user_id or stage.deleted_at is not None:
            raise HTTPException(409, "请先恢复所属阶段")
    if row.restored_at and (not with_daily or not pending_daily(db, row)):
        return payload(db, row) | {"warnings": []}
    daily_rows = pending_daily(db, row) if with_daily else []
    if with_daily and daily_ids is not None:
        if not daily_ids or len(set(daily_ids)) != len(daily_ids) or not set(daily_ids) <= {d.id for d in daily_rows}:
            raise HTTPException(400, "请选择本次删除记录中仍可恢复的日程")
        daily_rows = [d for d in daily_rows if d.id in daily_ids]
    daily_dates = daily_dates or {}
    dates = {d.id: daily_dates.get(d.id, past_date if d.task_date < today() else d.task_date) for d in daily_rows}
    if any(value is None or value < today() for value in dates.values()):
        raise HTTPException(400, "恢复过去的未完成日程，请先选择今天或未来的新日期")
    warnings = []
    if row.restored_at is None:
        if hard_stage and target is None:
            snapshot = content["stage_snapshot"]
            state = snapshot["state"]
            current = commitments.current_stage(db, snapshot["project_id"])
            if state == "current" and current and current.id != snapshot["id"]:
                if not stage_as_next:
                    raise HTTPException(409, "已有其他当前阶段；请明确选择将原阶段恢复为下一阶段")
                state = "next"
                warnings.append("原当前阶段已恢复为下一阶段，未自动开始")
            created_at = datetime.fromisoformat(snapshot["created_at"]) if snapshot.get("created_at") else None
            closed_at = datetime.fromisoformat(snapshot["closed_at"]) if snapshot.get("closed_at") else None
            target = ProjectStage(id=snapshot["id"], user_id=row.user_id, project_id=snapshot["project_id"],
                title=snapshot["title"], position=snapshot["position"], state=state,
                closed_reason=snapshot["closed_reason"], created_at=created_at, closed_at=closed_at)
            db.add(target); db.flush()
            for model in (StageCommitmentDraft, StageCommitment, CommitmentAdjustment):
                for history in db.query(model).filter_by(user_id=row.user_id, stage_original_id=target.id, stage_id=None):
                    history.stage_id = target.id
                    if model is StageCommitmentDraft: history.project_id = target.project_id
            for task in db.query(ProjectTask).filter(ProjectTask.user_id == row.user_id,
                    ProjectTask.project_id == target.project_id, ProjectTask.id.in_(content.get("stage_members", [])),
                    ProjectTask.stage_id.is_(None)):
                task.stage_id, task.stage_original_id = target.id, None
        for stage in db.query(ProjectStage).filter(ProjectStage.user_id == row.user_id, ProjectStage.id.in_(content["stage"])):
            if not marked(stage, row): continue
            current = commitments.current_stage(db, stage.project_id)
            if stage.state == "current" and current and current.id != stage.id:
                if not stage_as_next: raise HTTPException(409, "已有其他当前阶段；请明确选择将原阶段恢复为下一阶段")
                stage.state = "next"
                warnings.append("原当前阶段已恢复为下一阶段，未自动开始")
        for kind in ("project", "stage", "task"):
            for item in db.query(MODELS[kind]).filter(MODELS[kind].user_id == row.user_id, MODELS[kind].id.in_(content[kind])):
                if marked(item, row): item.deleted_at = None
        if row.kind == "stage":
            for task in db.query(ProjectTask).filter(ProjectTask.user_id == row.user_id,
                    ProjectTask.id.in_(content.get("retained_task", []))):
                if task.deleted_at is None and task.stage_id is None:
                    task.stage_id = row.target_id
        row.restored_at = datetime.utcnow()
        db.flush()
        for task in db.query(ProjectTask).filter(ProjectTask.user_id == row.user_id, ProjectTask.id.in_(content["task"]), ProjectTask.deleted_at.is_(None)):
            commitments.record_scope_addition(db, row.user_id, task)
    daily_ids = {d.id for d in daily_rows}
    for daily in daily_rows:
        if daily.project_task_id and not live(db, row.user_id, "task", daily.project_task_id):
            raise HTTPException(409, "关联任务仍被删除，请先恢复任务")
        parent = db.get(DailyTask, daily.parent_id) if daily.parent_id else None
        if parent and (parent.user_id != row.user_id or (parent.deleted_at is not None and parent.id not in daily_ids)):
            raise HTTPException(409, "日程的上级仍被删除，请先恢复上级")
        new_date = dates[daily.id]
        if daily.project_task_id and db.query(DailyTask).filter(DailyTask.user_id == row.user_id,
                DailyTask.id != daily.id, DailyTask.project_task_id == daily.project_task_id,
                DailyTask.task_date == new_date, DailyTask.deleted_at.is_(None)).first():
            raise HTTPException(409, "该任务在所选日期已有日程，请保留原日程或选择其他日期")
        daily.task_date, daily.deleted_at = new_date, None
        todo = sync_task_reminder(db, daily, remind_time=None)
        if todo: todo.todo_date = new_date
        db.flush()  # subsequent rows must see restored identities even with autoflush=False
    record_event(db, row.user_id, row.kind, row.target_id, "content_restored",
                 after={"deletion_id": row.id, "daily": sorted(daily_ids), "warnings": warnings})
    db.flush()
    return payload(db, row) | {"warnings": warnings}
