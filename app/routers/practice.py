"""Structured practice attached to schedule, projects, execution and existing reports."""
import json
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import DailyTask, User
from app.project_models import (ProjectTask, TaskChecklistItem, TaskPractice, PracticeEvent,
                                PlanningCycle, Project, TimeActivityAssessment, WorkSession)
from app import practice_service as svc

router = APIRouter(prefix="/practice")
Importance = Literal["unimportant", "ordinary", "important"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Attributes(Strict):
    difficulty: Literal["simple", "difficult"] | None = None
    importance: Importance | None = None
    goal: str = Field(default="", max_length=4000)


class ReviewItem(Strict):
    kind: Literal["daily", "task"]
    id: int
    importance: Importance | None


class Review(Strict):
    goal: str = Field(min_length=1, max_length=4000)
    items: list[ReviewItem] = Field(max_length=300)
    task_date: date | None = None


class Rehearsal(Strict):
    first_step: str = Field(default="", max_length=2000)
    sequence: str = Field(default="", max_length=4000)
    preparation: str = Field(default="", max_length=4000)
    difficulty: str = Field(default="", max_length=4000)
    response: str = Field(default="", max_length=4000)
    comparison: str = Field(default="", max_length=4000)
    preparation_action: Literal["none", "checklist", "task"] = "none"


class Feedback(Strict):
    result: Literal["completed", "partial", "rework"]
    actual_minutes: float | None = Field(default=None, ge=0, le=1000000)
    basis: Literal["timer_checked", "manual_checked", "self_report", "pending"]
    reason: str = Field(default="", max_length=4000)
    next_estimate: str = Field(default="", max_length=4000)
    outcome: str = Field(default="", max_length=4000)
    scope_changed: bool = False
    checklist_exception: str = Field(default="", max_length=4000)
    feedback_date: date | None = None


class Estimate(Strict):
    minutes: int | None = Field(default=None, ge=0, le=100000)
    reason: str = Field(min_length=1, max_length=4000)
    experience_id: int | None = None


class Progress(Strict):
    date: date
    status: Literal["recorded", "no_work", "missing"]
    advanced: str = Field(default="", max_length=4000)
    solved: str = Field(default="", max_length=4000)
    blocker: str = Field(default="", max_length=4000)
    next_step: str = Field(default="", max_length=4000)
    help_choice: Literal["smaller_step", "conditions", "help", "time", "goal", "none"] = "none"
    reduce_prompts: bool = False


class Reflection(Strict):
    answer: Literal["yes", "no", "uncertain", "later"]
    session_ids: list[int] = Field(default_factory=list, max_length=100)
    activity: str = Field(default="", max_length=4000)
    minutes: int | None = Field(default=None, ge=0, le=1440)
    goal: str = Field(default="", max_length=4000)
    reason: str = Field(default="", max_length=4000)
    next_step: str = Field(default="", max_length=4000)


class DayAllocation(Strict):
    kind: Literal["task", "daily"]
    id: int
    minutes: int = Field(ge=0, le=1440)


class DayPlan(Strict):
    goal: str = Field(default="", max_length=4000)
    available_minutes: int | None = Field(default=None, ge=0, le=1440)
    allocations: list[DayAllocation] = Field(default_factory=list, max_length=300)


class Feasibility(Strict):
    someone_did_it: bool | None = None
    small_gap: bool | None = None
    reference: str = Field(default="", max_length=4000)
    method: str = Field(default="", max_length=4000)
    reference_time: str = Field(default="", max_length=4000)
    starting_point: str = Field(default="", max_length=4000)
    resources: str = Field(default="", max_length=4000)
    gap: str = Field(default="", max_length=4000)
    bridge: str = Field(default="", max_length=4000)
    deadline_check: str = Field(default="", max_length=4000)
    exploration: str = Field(default="", max_length=4000)
    reason: str = Field(min_length=1, max_length=4000)


def task_owner(db, user_id, kind, row_id):
    if kind not in ("daily", "task"):
        raise HTTPException(400, "请选择日程或项目任务")
    return svc.owner(db, user_id, kind, row_id)


@router.get("/tasks/{kind}/{row_id}")
def get_task(kind: str, row_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    kind, row = task_owner(db, user.id, kind, row_id)
    return svc.task_payload(db, user.id, kind, row)


@router.patch("/tasks/{kind}/{row_id}/attributes")
def attributes(kind: str, row_id: int, body: Attributes, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    kind, row = task_owner(db, user.id, kind, row_id)
    state = svc.practice(db, user.id, kind, row)
    state.difficulty = body.difficulty
    if state.importance != body.importance or state.goal_snapshot != body.goal:
        state.reviewed_at = None
    state.importance, state.goal_snapshot = body.importance, body.goal
    if state.initial_marked_at is None and body.importance is not None:
        state.initial_importance, state.initial_marked_at = body.importance, datetime.utcnow()
    svc.event(db, user.id, kind, row.id, "attributes", body.model_dump() | {"title": svc.title(row)})
    db.commit()
    return svc.task_payload(db, user.id, kind, row)


@router.post("/review")
def review(body: Review, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    if not body.goal.strip(): raise HTTPException(400, "请明确本次判断所针对的目标")
    seen = set()
    for item in body.items:
        kind, row = task_owner(db, user.id, item.kind, item.id)
        if (kind, row.id) in seen: continue
        seen.add((kind, row.id))
        state = svc.practice(db, user.id, kind, row)
        if state.initial_marked_at is None and item.importance is not None:
            # A first mark cannot also pretend to be an earlier second review.
            raise HTTPException(409, "请先作首次标记，再审视；未标记可以保留为空")
        svc.event(db, user.id, kind, row.id, "importance_review", {"initial": state.initial_importance,
            "before": state.importance, "reviewed": item.importance, "goal": body.goal, "title": svc.title(row)}, body.task_date)
        state.importance, state.goal_snapshot, state.reviewed_at = item.importance, body.goal, datetime.utcnow()
    db.commit()
    return {"reviewed": len(seen)}


@router.put("/tasks/{kind}/{row_id}/rehearsal")
def rehearsal(kind: str, row_id: int, body: Rehearsal, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    kind, row = task_owner(db, user.id, kind, row_id)
    state = svc.practice(db, user.id, kind, row)
    state.rehearsal_json = svc.dumps(body.model_dump(exclude={"preparation_action"}))
    created = None
    if body.preparation_action != "none":
        if not body.preparation.strip(): raise HTTPException(400, "先写下准备内容")
        if body.preparation_action == "checklist":
            if kind == "task":
                check = TaskChecklistItem(user_id=user.id, task_id=row.id, text=body.preparation[:500],
                    purpose="preparation", position=len(svc.checklist(db, user.id, kind, row)))
                db.add(check); db.flush(); created = {"checklist_id": check.id}
            else:
                checks = json.loads(row.checklist_json or "[]")
                checks.append({"text": body.preparation[:500], "done": False, "group": "preparation"})
                row.checklist_json = svc.dumps(checks)
        else:
            if kind == "task":
                task = ProjectTask(user_id=user.id, project_id=row.project_id, stage_id=row.stage_id,
                                   title=body.preparation[:500], execution_role="preparation")
            else:
                from app.routers.schedule import next_flow_order, next_sort_order
                task = DailyTask(user_id=user.id, task_date=row.task_date, text=body.preparation[:500],
                    sort_order=next_sort_order(db, user.id, row.task_date, None),
                    flow_order=next_flow_order(db, user.id, row.task_date))
            db.add(task); db.flush(); created = {"kind": kind, "id": task.id}
            if kind == "task":
                from app.commitment_service import record_scope_addition
                record_scope_addition(db, user.id, task)
    svc.event(db, user.id, kind, row.id, "rehearsal", body.model_dump() | {"created": created})
    db.commit()
    return svc.task_payload(db, user.id, kind, row)


@router.post("/tasks/{kind}/{row_id}/estimate")
def estimate(kind: str, row_id: int, body: Estimate, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    kind, row = task_owner(db, user.id, kind, row_id)
    if body.experience_id:
        e = db.get(PracticeEvent, body.experience_id)
        if not e or e.user_id != user.id or e.event_type != "feedback": raise HTTPException(404, "经验不存在")
    svc.note_estimate(db, user.id, kind, row, body.minutes, body.reason)
    row.estimated_minutes = body.minutes
    svc.event(db, user.id, kind, row.id, "experience_link", {"experience_id": body.experience_id, "reason": body.reason})
    db.commit()
    return svc.task_payload(db, user.id, kind, row)


@router.get("/experiences")
def experiences(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    seen, result = set(), []
    for e in db.query(PracticeEvent).filter_by(user_id=user.id, event_type="feedback").order_by(PracticeEvent.id.desc()):
        identity = e.owner_kind, e.owner_id
        if identity in seen: continue
        seen.add(identity)
        result.append({"id": e.id, "date": e.record_date, **json.loads(e.payload_json)})
    return {"items": result}


@router.post("/tasks/{kind}/{row_id}/feedback")
def feedback(kind: str, row_id: int, body: Feedback, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    kind, row = task_owner(db, user.id, kind, row_id)
    prior = svc.events(db, user.id, kind, row.id, "feedback")
    feedback_day = body.feedback_date or (prior[0].record_date if prior else svc.today())
    if feedback_day > svc.today(): raise HTTPException(400, "实际结果不能记为未来日期")
    # Use the same delivery checks and settlement as every other completion entry.
    if kind == "task":
        from app.routers.projects import CompletionInput, apply_task_completion
        apply_task_completion(row.id, CompletionInput(result=body.result, outcome_note=body.outcome,
                    variance_reason=body.reason, checklist_exception=body.checklist_exception), user, db)
    else:
        from app.start_conditions import require_ready
        if body.result == "completed":
            if db.query(DailyTask).filter_by(parent_id=row.id).filter(DailyTask.deleted_at.is_(None)).count():
                raise HTTPException(409, "请分别反馈子任务，容器不重复记录完成用时")
            require_ready(db, user.id, kind, row.id, purpose="delivery")
            svc.require_checklist(db, user.id, kind, row, body.checklist_exception)
        row.completed = body.result == "completed"
        from app.schedule_todos import sync_task_reminder
        from app.routers.schedule import refresh_parent_completion
        refresh_parent_completion(db, user.id, row)
        sync_task_reminder(db, row)
        # End a real running interval at completion, before reading its actual total.
        if row.completed:
            svc.settle_daily_completion(db, user.id, row)
    state = svc.practice(db, user.id, kind, row)
    recorded = svc.recorded_minutes(db, user.id, kind, row.id)
    first_estimates = [json.loads(e.payload_json) for e in reversed(svc.events(db, user.id, kind, row.id, "estimate"))
                       if json.loads(e.payload_json).get("value") is not None]
    original_scope = first_estimates[0].get("scope") if first_estimates else None
    inferred_scope_change = bool(original_scope and (original_scope["criteria"] != row.acceptance_criteria
        or original_scope["steps"] != json.loads(row.steps_json or "[]")))
    scope_changed = body.scope_changed or inferred_scope_change
    if body.basis in ("timer_checked", "manual_checked"):
        if not svc.task_sessions(db, user.id, kind, row.id): raise HTTPException(400, "没有区间，请用自报总量或稍后核对")
        if body.actual_minutes is not None and abs(body.actual_minutes - recorded) > .02:
            raise HTTPException(409, "区间核对值应等于已记录投入；请更正区间，或明确选择自报总量")
        actual = recorded
    else: actual = body.actual_minutes
    if body.basis != "pending" and actual is None: raise HTTPException(400, "请填写确认用时，或选择稍后核对")
    original = state.original_estimate
    difference = round(actual - original, 2) if original is not None and actual is not None else None
    data = body.model_dump() | {"title": svc.title(row), "recorded_minutes": recorded, "actual_minutes": actual,
        "scope_changed": scope_changed, "scope_change_recorded": inferred_scope_change,
        "original_estimate": original, "current_estimate": row.estimated_minutes, "estimate_origin": state.estimate_origin,
        "difference": difference, "percent": round(difference / original * 100, 2) if original and difference is not None else None,
        "unallocated_difference": round(actual - recorded, 2) if actual is not None else None,
        "comparable": bool(body.result == "completed" and body.basis != "pending" and actual is not None
                           and original is not None and original > 0 and state.estimate_origin == "before_start" and not scope_changed)}
    svc.event(db, user.id, kind, row.id, "feedback", data | {"feedback_date": str(feedback_day)}, feedback_day)
    db.commit()
    return svc.task_payload(db, user.id, kind, row)


@router.post("/tasks/{kind}/{row_id}/progress")
def progress(kind: str, row_id: int, body: Progress, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    kind, row = task_owner(db, user.id, kind, row_id)
    state = svc.practice(db, user.id, kind, row)
    svc.event(db, user.id, kind, row.id, "progress", body.model_dump() | {"title": svc.title(row), "difficulty": state.difficulty}, body.date)
    db.commit(); return {"saved": True}


@router.get("/day/{day}")
def day_practice(day: date, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.routers.schedule import visible_tasks
    tasks, seen = [], set()
    for daily in visible_tasks(db, user.id, day):
        if daily.project_task_id:
            linked = db.get(ProjectTask, daily.project_task_id)
            if not linked or linked.deleted_at: continue
        kind, row = task_owner(db, user.id, "daily", daily.id)
        if (kind, row.id) in seen: continue
        seen.add((kind, row.id))
        tasks.append(svc.day_task_payload(db, user.id, kind, row, day))
    history = svc.events(db, user.id, "day", day.toordinal(), "day_reflection")
    plans = svc.events(db, user.id, "day", day.toordinal(), "day_plan")
    return {"date": day, "tasks": tasks, "reflection": json.loads(history[0].payload_json) if history else None,
            "plan": json.loads(plans[0].payload_json) if plans else {},
            "report": svc.training_report(db, user.id, day, day)}


@router.post("/day/{day}/plan")
def day_plan(day: date, body: DayPlan, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    from app.routers.schedule import visible_tasks
    visible = set()
    for daily in visible_tasks(db, user.id, day):
        if daily.project_task_id:
            linked = db.get(ProjectTask, daily.project_task_id)
            if not linked or linked.deleted_at: continue
        kind, row = task_owner(db, user.id, "daily", daily.id)
        if kind == "daily" and db.query(DailyTask.id).filter_by(parent_id=row.id).filter(DailyTask.deleted_at.is_(None)).first():
            continue
        visible.add((kind, row.id))
    allocations, seen = [], set()
    for a in body.allocations:
        kind, row = task_owner(db, user.id, a.kind, a.id)
        identity = kind, row.id
        if identity not in visible or identity in seen: raise HTTPException(400, "当天投入只能关联当日日程任务，且不能重复")
        if kind == "daily" and db.query(DailyTask.id).filter_by(parent_id=row.id).filter(DailyTask.deleted_at.is_(None)).first():
            raise HTTPException(400, "请为可执行的子任务分配当天投入，容器不重复分配")
        seen.add(identity)
        allocations.append({"kind": kind, "id": row.id, "minutes": a.minutes, "title": svc.title(row)})
    svc.event(db, user.id, "day", day.toordinal(), "day_plan", body.model_dump(exclude={"allocations"}) | {
        "allocations": allocations, "unallocated_count": len(visible) - len(seen),
        "planned_minutes": sum(a["minutes"] for a in allocations) if allocations else None}, day)
    db.commit(); return {"saved": True}


@router.post("/day/{day}/reflection")
def reflection(day: date, body: Reflection, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    if len(set(body.session_ids)) != len(body.session_ids): raise HTTPException(400, "请勿重复引用活动")
    if body.answer == "yes" and not (body.session_ids or body.activity.strip()): raise HTTPException(400, "请记录或引用具体活动")
    references = []
    for session_id in body.session_ids:
        s = db.get(WorkSession, session_id)
        if s is None or s.user_id != user.id: raise HTTPException(404, "活动不存在")
        if s.ended_at is None: raise HTTPException(409, "请先结束活动再评价")
        if not (s.started_at.replace(tzinfo=ZoneInfoUTC).astimezone(svc.BEIJING).date() <= day <=
                s.ended_at.replace(tzinfo=ZoneInfoUTC).astimezone(svc.BEIJING).date()):
            raise HTTPException(400, "所选活动不属于反馈日期")
        a = db.query(TimeActivityAssessment).filter_by(user_id=user.id, work_session_id=s.id).first()
        references.append({"session_id": s.id, "label": s.label,
            "importance": a.importance if a else None, "interesting": a.interesting if a else None,
            "goal": a.goal_title_snapshot if a else None})
    svc.event(db, user.id, "day", day.toordinal(), "day_reflection", body.model_dump() | {"references": references}, day)
    db.commit(); return {"saved": True}


from datetime import timezone
ZoneInfoUTC = timezone.utc


@router.get("/feasibility/{kind}/{row_id}")
def get_feasibility(kind: str, row_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if kind not in ("goal", "project"): raise HTTPException(400, "请选择目标或项目")
    kind, row = svc.owner(db, user.id, kind, row_id)
    history = svc.events(db, user.id, kind, row.id, "feasibility")
    revisions = svc.events(db, user.id, kind, row.id, "goal_revision") if kind == "goal" else []
    return {"title": svc.title(row), "horizon_end": getattr(row, "horizon_end", None), "status": row.status,
            "revisions": [{"at": e.created_at, "data": json.loads(e.payload_json)} for e in revisions],
            "latest": json.loads(history[0].payload_json) if history else {},
            "history": [{"id": e.id, "at": e.created_at, "data": json.loads(e.payload_json)} for e in history]}


class GoalRevision(Strict):
    title: str = Field(min_length=1, max_length=200)
    horizon_end: date | None = None
    reason: str = Field(min_length=1, max_length=4000)
    status: Literal["active", "stopped"] = "active"


@router.post("/goals/{goal_id}/revise")
def revise_goal(goal_id: int, body: GoalRevision, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    _, row = svc.owner(db, user.id, "goal", goal_id)
    if not body.title.strip() or not body.reason.strip(): raise HTTPException(400, "请填写目标和修订依据")
    before = {"title": row.title, "horizon_end": row.horizon_end, "status": row.status}
    row.title, row.horizon_end = body.title.strip(), body.horizon_end
    row.status = body.status
    svc.event(db, user.id, "goal", row.id, "goal_revision", {"before": before, "after": body.model_dump()})
    db.commit(); return {"saved": True}


@router.post("/feasibility/{kind}/{row_id}")
def save_feasibility(kind: str, row_id: int, body: Feasibility, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    if kind not in ("goal", "project"): raise HTTPException(400, "请选择目标或项目")
    kind, row = svc.owner(db, user.id, kind, row_id)
    svc.event(db, user.id, kind, row.id, "feasibility", body.model_dump() | {"title": svc.title(row),
        "deadline": str(getattr(row, "horizon_end", None) or ""), "outcome": getattr(row, "outcome", None)})
    db.commit(); return get_feasibility(kind, row_id, user, db)


class ChecklistItem(Strict):
    id: int | None = None
    text: str = Field(min_length=1, max_length=500)
    done: bool = False
    group: Literal["preparation", "delivery"] = "delivery"
    not_applicable: str | None = Field(default=None, max_length=4000)


class Checklist(Strict):
    items: list[ChecklistItem] = Field(max_length=100)


@router.put("/tasks/{kind}/{row_id}/checklist")
def checklist(kind: str, row_id: int, body: Checklist, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    kind, row = task_owner(db, user.id, kind, row_id)
    before = svc.checklist(db, user.id, kind, row)
    old_ids = {c["id"] for c in before}
    ids = [i.id for i in body.items if i.id is not None]
    if len(ids) != len(set(ids)) or not set(ids) <= old_ids: raise HTTPException(409, "检查项已变化，请刷新重试")
    if any(not item.text.strip() or (item.not_applicable is not None and not item.not_applicable.strip()) for item in body.items):
        raise HTTPException(400, "内容和不适用说明不能为空")
    if kind == "task":
        # Historical versions remain in the append-only event even when removing an item.
        for c in db.query(TaskChecklistItem).filter_by(user_id=user.id, task_id=row.id).all():
            if c.id not in ids: db.delete(c)
        for position, item in enumerate(body.items):
            c = db.get(TaskChecklistItem, item.id) if item.id is not None else TaskChecklistItem(user_id=user.id, task_id=row.id)
            c.text, c.done, c.position = item.text.strip(), item.done, position
            c.purpose, c.not_applicable_reason = item.group, item.not_applicable
            db.add(c)
    else:
        row.checklist_json = svc.dumps([i.model_dump(exclude={"id"}) for i in body.items])
    svc.event(db, user.id, kind, row.id, "checklist", {"before": before, "after": body.model_dump()["items"]})
    db.commit(); return svc.task_payload(db, user.id, kind, row)


class CycleInput(Strict):
    start_date: date
    end_date: date
    horizon: Literal["week", "fortnight", "month", "quarter", "year", "custom"] = "week"
    expected_result: str = Field(min_length=1, max_length=4000)
    available_minutes: int | None = Field(default=None, ge=0, le=1000000)
    task_ids: list[int] = Field(max_length=300)
    previous_cycle_id: int | None = None


class CycleReview(Strict):
    actual_result: str = Field(min_length=1, max_length=4000)
    unforeseen: str = Field(default="", max_length=4000)
    conditions: str = Field(default="", max_length=4000)
    goal_help: str = Field(default="", max_length=4000)
    next_changes: str = Field(min_length=1, max_length=4000)
    horizon_decision: Literal["keep", "shorten", "extend", "stop"]
    reason: str = Field(min_length=1, max_length=4000)


def cycle_data(db, user_id, cycle):
    plan = json.loads(cycle.plan_json)
    report = svc.training_report(db, user_id, cycle.start_date, cycle.end_date)
    ids = {t["id"] for t in plan["tasks"]}
    from sqlalchemy import or_, and_
    daily_ids = db.query(DailyTask.id).filter(DailyTask.user_id == user_id, DailyTask.project_task_id.in_(ids))
    session_ids = {s.id for s in db.query(WorkSession).filter(WorkSession.user_id == user_id,
        or_(WorkSession.project_task_id.in_(ids), and_(WorkSession.project_task_id.is_(None), WorkSession.daily_task_id.in_(daily_ids))))}
    included = [w for w in report["work"] if w["session_id"] in session_ids]
    seconds = sum(w["seconds"] for w in included)
    current = db.query(ProjectTask).filter(ProjectTask.user_id == user_id, ProjectTask.id.in_(ids)).all()
    total_estimate = sum(t["estimate"] or 0 for t in plan["tasks"])
    evidence = {"planned_task_count": len(ids), "completed_count": sum(t.state == "completed" and not t.deleted_at for t in current),
        "planned_minutes": total_estimate, "missing_estimates": sum(t["estimate"] is None for t in plan["tasks"]),
        "actual_interval_minutes": round(seconds / 60, 2), "interval_count": len(included), "available_minutes": cycle.available_minutes}
    suggestions = ["先核对漏记、实际结果、困难和条件变化，再决定维持、缩短或延长跨度。"]
    if cycle.available_minutes is not None and total_estimate > cycle.available_minutes:
        suggestions.append(f"原估计 {total_estimate} 分钟超过可用 {cycle.available_minutes} 分钟，下轮可减少负荷或增加真实可用时间。")
    if seconds / 60 > total_estimate and not evidence["missing_estimates"]:
        suggestions.append("已记录投入超过原估计，查看漏算步骤、返工和范围变化，再决定余量。")
    if evidence["missing_estimates"]: suggestions.append("有任务未估时，当前数据不足以判断估时偏差。")
    review = json.loads(cycle.review_json) if cycle.review_json else None
    if review and review.get("conditions"):
        suggestions.append("你记录的条件问题是“%s”。下一轮先落实对应条件，再判断是否适合扩大范围和跨度。" % review["conditions"])
    return {"id": cycle.id, "project_id": cycle.project_id, "start_date": cycle.start_date, "end_date": cycle.end_date,
        "horizon": cycle.horizon, "expected_result": cycle.expected_result, "plan": plan, "evidence": evidence,
        "review": review, "suggestions": suggestions,
        "previous_cycle_id": cycle.previous_cycle_id}


@router.get("/projects/{project_id}/cycles")
def get_cycles(project_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.owner(db, user.id, "project", project_id)
    return {"items": [cycle_data(db, user.id, c) for c in db.query(PlanningCycle).filter_by(user_id=user.id, project_id=project_id).order_by(PlanningCycle.id.desc())]}


@router.post("/projects/{project_id}/cycles")
def create_cycle(project_id: int, body: CycleInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    _, project = svc.owner(db, user.id, "project", project_id)
    if body.end_date < body.start_date or (body.end_date - body.start_date).days > 731:
        raise HTTPException(400, "请设置两年以内、先后正确的周期日期")
    if not body.expected_result.strip() or not body.task_ids or len(set(body.task_ids)) != len(body.task_ids):
        raise HTTPException(400, "请明确结果并选择本轮任务")
    if body.previous_cycle_id:
        prior = db.get(PlanningCycle, body.previous_cycle_id)
        if not prior or prior.user_id != user.id or prior.project_id != project_id: raise HTTPException(404, "上一轮不存在")
        if not prior.review_json: raise HTTPException(409, "请先复盘上一轮，再制定下一轮")
        if db.query(PlanningCycle).filter_by(previous_cycle_id=prior.id, user_id=user.id).first():
            raise HTTPException(409, "本轮已有下一轮，请打开已有周期")
    tasks = []
    for task_id in body.task_ids:
        _, t = task_owner(db, user.id, "task", task_id)
        if t.project_id != project_id: raise HTTPException(400, "任务不属于此项目")
        tasks.append({"id": t.id, "title": t.title, "estimate": t.estimated_minutes, "stage_id": t.stage_id,
                      "criteria": t.acceptance_criteria})
    row = PlanningCycle(user_id=user.id, project_id=project_id, **body.model_dump(exclude={"task_ids"}),
        plan_json=svc.dumps({"goal": svc.goal_text(db, t), "project_outcome": project.outcome, "tasks": tasks}))
    db.add(row); db.commit(); return cycle_data(db, user.id, row)


@router.post("/cycles/{cycle_id}/review")
def cycle_review(cycle_id: int, body: CycleReview, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    svc.lock_user(db, user.id)
    c = db.get(PlanningCycle, cycle_id)
    if not c or c.user_id != user.id: raise HTTPException(404, "周期不存在")
    if any(not v.strip() for v in (body.actual_result, body.next_changes, body.reason)): raise HTTPException(400, "请填写结果、下一轮调整与理由")
    data = body.model_dump() | {"evidence": cycle_data(db, user.id, c)["evidence"]}
    svc.event(db, user.id, "cycle", c.id, "cycle_review", data)
    c.review_json, c.reviewed_at = svc.dumps(data), datetime.utcnow()
    db.commit(); return cycle_data(db, user.id, c)
