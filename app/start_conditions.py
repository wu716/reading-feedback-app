"""One account-scoped readiness check for every live execution entry point."""
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import and_, or_

from app.models import DailyTask
from app.project_models import (
    ExecutionConditionEvent, Project, ProjectStage, ProjectTask, StartCondition, TaskDependency,
)

OWNER_MODELS = {"project": Project, "task": ProjectTask, "daily": DailyTask}


def resolve_owner(db, user_id, kind, row_id):
    model = OWNER_MODELS.get(kind)
    row = db.get(model, row_id) if model else None
    if row is None or row.user_id != user_id or row.deleted_at is not None:
        raise HTTPException(404, "记录不存在")
    if kind == "daily" and row.project_task_id:
        return resolve_owner(db, user_id, "task", row.project_task_id)
    return kind, row


def condition_snapshot(row):
    return {c.name: getattr(row, c.name) for c in StartCondition.__table__.columns}


def record_event(db, user_id, kind, owner_id, action, before=None, after=None, reason=None, condition_id=None):
    db.add(ExecutionConditionEvent(
        user_id=user_id, owner_kind=kind, owner_id=owner_id, action=action,
        condition_id=condition_id, reason=reason,
        before_json=json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
        after_json=json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
    ))


def active_conditions(db, user_id, kind, owner_id):
    owner_filter = and_(StartCondition.owner_kind == kind, StartCondition.owner_id == owner_id)
    if kind == "task":
        # Promoting a daily task keeps its original condition identity and history.
        daily_ids = db.query(DailyTask.id).filter(DailyTask.user_id == user_id, DailyTask.project_task_id == owner_id)
        owner_filter = or_(owner_filter, and_(StartCondition.owner_kind == "daily", StartCondition.owner_id.in_(daily_ids)))
    return db.query(StartCondition).filter(
        StartCondition.user_id == user_id, owner_filter, StartCondition.removed_at.is_(None),
    ).order_by(StartCondition.id).all()


def evaluate_condition(db, condition, now=None):
    now = now or datetime.utcnow()
    satisfied, detail = False, "尚未确认"
    if condition.kind in ("task", "project"):
        model = OWNER_MODELS[condition.target_kind]
        target = db.get(model, condition.target_id)
        if target is None or target.user_id != condition.user_id or target.deleted_at is not None:
            detail = "前置对象已移除，需重新处理条件"
        elif condition.target_kind == "task":
            satisfied = target.state == "completed"
            detail = f"前置任务《{target.title}》" + ("已完成" if satisfied else "尚未完成")
        else:
            satisfied = target.execution_state == "accepted" or (
                condition.required_state == "delivered" and target.execution_state == "delivered")
            # A reopened or newly added task invalidates the claimed delivery.
            if satisfied:
                satisfied = not db.query(ProjectTask.id).filter(ProjectTask.user_id == condition.user_id,
                    ProjectTask.project_id == target.id, ProjectTask.deleted_at.is_(None), ProjectTask.state.notin_(["completed", "cancelled"])).first()
            detail = f"前置项目《{target.title}》" + (
                "已达到要求" if satisfied else ("尚未验收" if condition.required_state == "accepted" else "尚未交付"))
    elif condition.kind == "time" and condition.not_before is not None:
        satisfied = now >= condition.not_before
        detail = "已到允许开始时间" if satisfied else f"尚未到允许开始时间 {condition.not_before.isoformat()}Z"
    else:
        satisfied = condition.confirmation == "met" or (
            condition.confirmation == "not_applicable" and bool((condition.evidence or "").strip()))
        detail = {"unknown": "尚未确认", "unmet": "尚未满足", "met": "已确认满足",
                  "not_applicable": "已说明不适用"}.get(condition.confirmation, "尚未确认")
    result = condition_snapshot(condition)
    result.update(satisfied=satisfied, detail=detail)
    return result


def readiness(db, user_id, kind, row_id, *, purpose="start", now=None):
    if kind == "daily":
        daily = db.get(DailyTask, row_id)
        from app.stage_schedule_models import day_plan
        if daily and daily.user_id == user_id and not daily.project_task_id and day_plan(db, user_id, daily.id):
            return {"owner_kind": "daily", "owner_id": row_id, "can_start": False, "configured": False,
                    "blockers": ["关联项目任务已移除，请处理原关联"], "reminders": [], "conditions": [],
                    "summary": "关联项目任务已移除，请处理原关联"}
        if daily and daily.user_id == user_id and daily.deleted_at is None and daily.project_task_id:
            linked = db.get(ProjectTask, daily.project_task_id)
            if linked is None or linked.user_id != user_id or linked.deleted_at is not None:
                return {"owner_kind": "daily", "owner_id": row_id, "can_start": False, "configured": False,
                        "blockers": ["关联项目任务已移除，请处理原关联"], "reminders": [], "conditions": [],
                        "summary": "关联项目任务已移除，请处理原关联"}
    kind, owner = resolve_owner(db, user_id, kind, row_id)
    conditions = [evaluate_condition(db, c, now) for c in active_conditions(db, user_id, kind, owner.id)]
    blockers, reminders = [], []
    if kind == "task":
        project = db.get(Project, owner.project_id)
        if project is None or project.deleted_at is not None:
            blockers.append("所属项目已移除")
        elif owner.execution_role != "preparation":
            if project.execution_state in ("preparation", "delivered", "accepted"):
                blockers.append("所属项目尚未正式开始" if project.execution_state == "preparation" else "所属项目已交付，请先说明原因并重新开始")
            conditions += [dict(evaluate_condition(db, c, now), inherited=True, source_title=project.title)
                           for c in active_conditions(db, user_id, "project", project.id)]
            stage = db.get(ProjectStage, owner.stage_id) if owner.stage_id else None
            if purpose == "start" and stage and stage.state != "current":
                blockers.append("任务属于下一阶段或历史阶段，请先完成阶段交接")
        for dep in db.query(TaskDependency).filter(TaskDependency.user_id == user_id, TaskDependency.task_id == owner.id):
            prior = db.get(ProjectTask, dep.prerequisite_id)
            if prior is None or prior.user_id != user_id or prior.deleted_at is not None or prior.state != "completed":
                blockers.append(f"前置任务《{prior.title if prior and prior.user_id == user_id else '已移除'}》尚未完成或已移除")
        if purpose == "start" and owner.state == "completed": blockers.append("任务已完成")
        if purpose == "start" and owner.state == "cancelled": blockers.append("任务已取消，原投入与结果保留")
    elif kind == "daily" and purpose == "start" and owner.completed:
        blockers.append("日程任务已完成")
    for condition in conditions:
        applicable = condition["check_at"] in ("start", "throughout") if purpose == "start" else True
        if not applicable:
            continue
        message = f"{condition.get('source_title', '本项')} · {condition['title']}：{condition['detail']}"
        if condition["strength"] == "required" and not condition["satisfied"]:
            blockers.append(message)
        elif condition["strength"] == "reminder":
            reminders.append(message)
    return {"owner_kind": kind, "owner_id": owner.id, "can_start": not blockers,
            "configured": bool(conditions), "blockers": blockers, "reminders": reminders,
            "conditions": conditions,
            "summary": "；".join(blockers) if blockers else ("可以开始" if conditions else "未配置启动条件")}


def require_ready(db, user_id, kind, row_id, *, purpose="start"):
    result = readiness(db, user_id, kind, row_id, purpose=purpose)
    if result["blockers"]:
        raise HTTPException(409, "；".join(result["blockers"]) + "。请在“开始条件与约束”中处理。")
    return result


def validate_dependency_graph(db, user_id):
    """Separate start/result nodes include project inheritance and delivery rules."""
    graph = {}

    def edge(source, target):
        graph.setdefault(source, set()).add(target)

    tasks = db.query(ProjectTask).filter(ProjectTask.user_id == user_id).all()
    for task in tasks:
        edge(("task_result", task.id), ("task", task.id))
        if task.execution_role != "preparation":
            edge(("task", task.id), ("project", task.project_id))
        if task.deleted_at is None:
            edge(("project_result", task.project_id), ("task_result", task.id))
    for project in db.query(Project).filter(Project.user_id == user_id):
        edge(("project_result", project.id), ("project", project.id))
    for dep in db.query(TaskDependency).filter(TaskDependency.user_id == user_id):
        edge(("task", dep.task_id), ("task_result", dep.prerequisite_id))
    for c in db.query(StartCondition).filter(StartCondition.user_id == user_id, StartCondition.removed_at.is_(None),
                                           StartCondition.strength == "required", StartCondition.target_id.isnot(None)):
        row = db.get(OWNER_MODELS[c.owner_kind], c.owner_id)
        if row is None or row.deleted_at is not None:
            continue
        if c.owner_kind == "daily" and row.project_task_id:
            linked = db.get(ProjectTask, row.project_task_id)
            if linked is None or linked.deleted_at is not None:
                continue
        owner_kind, owner = resolve_owner(db, user_id, c.owner_kind, c.owner_id)
        source_kind = owner_kind + "_result" if c.check_at == "delivery" else owner_kind
        edge((source_kind, owner.id), (c.target_kind + "_result", c.target_id))
    visiting, visited = set(), set()

    def visit(node):
        if node in visiting:
            raise HTTPException(400, "依赖不能形成环（包括项目启动、交付与任务继承关系）")
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, ()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in list(graph):
        visit(node)
