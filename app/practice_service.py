"""Learning from real plans. Feedback totals are never inserted into the time ledger."""
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, or_

from app.models import DailyTask, User
from app.project_models import (Goal, Project, ProjectTask, TaskPractice, PracticeEvent,
                                WorkSession, TaskChecklistItem, TimeActivityAssessment)

BEIJING = ZoneInfo("Asia/Shanghai")


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))


def today():
    return datetime.now(BEIJING).date()


def lock_user(db, user_id):
    db.query(User).filter(User.id == user_id).with_for_update().first()


def owner(db, user_id, kind, row_id):
    model = {"task": ProjectTask, "daily": DailyTask, "goal": Goal, "project": Project}.get(kind)
    row = db.get(model, row_id) if model else None
    if row is None or row.user_id != user_id or getattr(row, "deleted_at", None) is not None:
        raise HTTPException(404, "记录不存在")
    if kind == "daily" and row.project_task_id:
        return owner(db, user_id, "task", row.project_task_id)
    return kind, row


def event(db, user_id, kind, row_id, event_type, payload, day=None):
    row = PracticeEvent(user_id=user_id, owner_kind=kind, owner_id=row_id, event_type=event_type,
                        record_date=day or today(), payload_json=dumps(payload))
    db.add(row)
    db.flush()
    return row


def events(db, user_id, kind, row_id, event_type=None):
    q = db.query(PracticeEvent).filter_by(user_id=user_id, owner_kind=kind, owner_id=row_id)
    if event_type:
        q = q.filter_by(event_type=event_type)
    return q.order_by(PracticeEvent.id.desc()).all()


def practice(db, user_id, kind, row, create=True):
    state = db.query(TaskPractice).filter_by(user_id=user_id, owner_kind=kind, owner_id=row.id).first()
    if state is None and create:
        legacy_estimate = getattr(row, "original_estimate_minutes", None) if kind == "task" else row.estimated_minutes
        state = TaskPractice(user_id=user_id, owner_kind=kind, owner_id=row.id,
                             original_estimate=legacy_estimate,
                             estimate_origin="legacy_unknown" if legacy_estimate is not None else None)
        db.add(state); db.flush()
    return state


def title(row):
    return getattr(row, "title", None) or row.text


def goal_text(db, row):
    if isinstance(row, ProjectTask):
        p = db.get(Project, row.project_id)
        g = db.get(Goal, p.goal_id) if p and p.goal_id else None
        return g.title if g else (p.outcome or p.title if p else "")
    return ""


def task_sessions(db, user_id, kind, row_id):
    q = db.query(WorkSession).filter(WorkSession.user_id == user_id, WorkSession.kind == "work")
    if kind == "task":
        ids = db.query(DailyTask.id).filter_by(user_id=user_id, project_task_id=row_id)
        q = q.filter(or_(WorkSession.project_task_id == row_id,
                         and_(WorkSession.project_task_id.is_(None), WorkSession.daily_task_id.in_(ids))))
    else:
        q = q.filter(WorkSession.daily_task_id == row_id)
    return q.all()


def recorded_minutes(db, user_id, kind, row_id):
    return round(sum((s.ended_at - s.started_at).total_seconds() for s in task_sessions(db, user_id, kind, row_id)
                     if s.ended_at) / 60, 2)


def settle_daily_completion(db, user_id, row):
    from app.execution_service import settle_expired, execution_plan
    settle_expired(db, user_id)
    for s in task_sessions(db, user_id, "daily", row.id):
        if not s.ended_at:
            s.ended_at = max(datetime.utcnow(), s.started_at + timedelta(microseconds=1))
    plan = execution_plan(db, user_id)
    paused = db.get(WorkSession, plan.paused_session_id) if plan.paused_session_id else None
    if paused and paused.daily_task_id == row.id:
        plan.paused_session_id, plan.remaining_seconds = None, None
    db.flush()


def note_estimate(db, user_id, kind, row, value, reason="", created=False):
    state = practice(db, user_id, kind, row)
    prior_events = events(db, user_id, kind, row.id, "estimate")
    origin = "before_start" if created or not task_sessions(db, user_id, kind, row.id) else "retrospective"
    if state.estimate_origin is None and value is not None:
        state.original_estimate, state.estimate_origin = value, origin
        if isinstance(row, ProjectTask) and row.original_estimate_minutes is None:
            row.original_estimate_minutes = value
    elif created and not prior_events and value is not None:
        state.original_estimate, state.estimate_origin = value, origin
    scope = {"criteria": row.acceptance_criteria, "steps": json.loads(row.steps_json or "[]")}
    if kind == "task":
        from app.commitment_service import commitment
        c = commitment(db, user_id, row.stage_id) if row.stage_id else None
        scope["commitment_id"] = c.id if c else None
    event(db, user_id, kind, row.id, "estimate", {"value": value, "origin": origin,
          "reason": reason, "original": state.original_estimate, "title": title(row), "scope": scope})


def snapshot_session(db, session):
    if session.kind != "work":
        return
    kind, row = owner(db, session.user_id, "task" if session.project_task_id else "daily",
                      session.project_task_id or session.daily_task_id)
    if kind == "task" and session.source == "timer" and row.execution_role == "formal" and row.stage_id:
        from app.commitment_service import commitment, commit_stage
        from app.project_models import ProjectStage
        stage = db.get(ProjectStage, row.stage_id)
        if stage and stage.state == "current" and not commitment(db, session.user_id, stage.id):
            commit_stage(db, session.user_id, stage)
    state = practice(db, session.user_id, kind, row, create=False)
    session.practice_snapshot_json = dumps({"kind": kind, "id": row.id, "title": title(row),
        "difficulty": state.difficulty if state else None, "importance": state.importance if state else None,
        "goal": state.goal_snapshot if state else goal_text(db, row),
        "rehearsal": json.loads(state.rehearsal_json or "{}") if state else {},
        "snapshot_basis": "recorded_now" if session.source != "timer" else "at_start"})


def checklist(db, user_id, kind, row):
    if kind == "task":
        return [{"id": c.id, "text": c.text, "done": c.done, "group": getattr(c, "purpose", None) or "delivery",
                 "not_applicable": getattr(c, "not_applicable_reason", None), "position": c.position}
                for c in db.query(TaskChecklistItem).filter_by(task_id=row.id, user_id=user_id)
                .order_by(TaskChecklistItem.position, TaskChecklistItem.id)]
    return [{"id": i, "position": i, "group": "delivery", **item}
            for i, item in enumerate(json.loads(row.checklist_json or "[]"))]


def require_checklist(db, user_id, kind, row, exception=None):
    missing = [c for c in checklist(db, user_id, kind, row) if not c["done"] and not c.get("not_applicable")]
    if missing and not (exception or "").strip():
        raise HTTPException(409, {"message": "还有未核对项，请先补查，或说明本次例外后完成", "checklist": missing})
    if missing:
        event(db, user_id, kind, row.id, "checklist_exception", {"items": missing, "reason": exception.strip()})


def task_payload(db, user_id, kind, row):
    state = practice(db, user_id, kind, row, create=False)
    history = events(db, user_id, kind, row.id)
    feedback = next((json.loads(e.payload_json) | {"id": e.id, "date": str(e.record_date)}
                     for e in history if e.event_type == "feedback"), None)
    recorded = recorded_minutes(db, user_id, kind, row.id)
    original = state.original_estimate if state else getattr(row, "original_estimate_minutes", None)
    return {"kind": kind, "id": row.id, "title": title(row), "completed": row.state == "completed" if kind == "task" else row.completed,
        "has_children": bool(kind == "daily" and db.query(DailyTask.id).filter_by(parent_id=row.id).filter(DailyTask.deleted_at.is_(None)).first()),
        "estimated_minutes": row.estimated_minutes, "original_estimate": original,
        "estimate_origin": state.estimate_origin if state else ("legacy_unknown" if original is not None else None),
        "recorded_minutes": recorded, "difficulty": state.difficulty if state else None,
        "interval_count": sum(s.ended_at is not None for s in task_sessions(db, user_id, kind, row.id)),
        "reduce_prompts": next((json.loads(e.payload_json).get("reduce_prompts", False) for e in history if e.event_type == "progress"), False),
        "importance": state.importance if state else None, "initial_importance": state.initial_importance if state else None,
        "initial_marked_at": state.initial_marked_at if state else None,
        "reviewed_at": state.reviewed_at if state else None, "goal": state.goal_snapshot if state else goal_text(db, row),
        "rehearsal": json.loads(state.rehearsal_json or "{}") if state else {},
        "legacy_rehearsal": getattr(row, "rehearsal_note", None),
        "criteria": row.acceptance_criteria, "checklist": checklist(db, user_id, kind, row), "feedback": feedback,
        "history": [{"id": e.id, "type": e.event_type, "date": e.record_date,
                     "at": e.created_at, "data": json.loads(e.payload_json)} for e in history]}


def training_report(db, user_id, start, end):
    """Intervals are clipped to Beijing dates. Task self reports remain separate."""
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    lo = datetime.combine(start, time(), BEIJING).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    hi = datetime.combine(end + timedelta(days=1), time(), BEIJING).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    sessions = db.query(WorkSession).filter(WorkSession.user_id == user_id, WorkSession.kind == "work",
        WorkSession.started_at < hi, WorkSession.ended_at > lo).all()
    total, difficult, unknown = 0, 0, 0
    work = []
    assessments = {a.work_session_id: a for a in db.query(TimeActivityAssessment).filter_by(user_id=user_id)}
    for s in sessions:
        seconds = max(0, (min(s.ended_at, hi) - max(s.started_at, lo)).total_seconds())
        snap = json.loads(s.practice_snapshot_json or "{}")
        total += seconds
        if snap.get("difficulty") == "difficult": difficult += seconds
        if not snap.get("difficulty"): unknown += seconds
        a = assessments.get(s.id)
        linked_daily = db.get(DailyTask, s.daily_task_id) if s.daily_task_id else None
        project_task_id = s.project_task_id or (linked_daily.project_task_id if linked_daily else None)
        work.append({"session_id": s.id, "title": snap.get("title") or s.label or "历史工作片",
            "kind": "task" if project_task_id else "daily", "task_id": project_task_id or s.daily_task_id,
            "seconds": seconds, "difficulty": snap.get("difficulty"), "planned_importance": snap.get("importance"),
            "planned_goal": snap.get("goal"),
            "actual_importance": a.importance if a else None, "interesting": a.interesting if a else None,
            "goal": a.goal_title_snapshot if a else None})
    all_events = db.query(PracticeEvent).filter_by(user_id=user_id).order_by(PracticeEvent.id.desc()).all()
    # A correction replaces the interpretation, not the underlying time intervals.
    latest = {}
    for e in all_events:
        if e.event_type == "feedback" and e.record_date <= end: latest.setdefault((e.owner_kind, e.owner_id), e)
    feedback = [json.loads(e.payload_json) | {"kind": e.owner_kind, "task_id": e.owner_id, "date": str(e.record_date)}
                for e in latest.values() if start <= e.record_date <= end]
    samples = [f for f in feedback if f["comparable"]]
    awaiting = {(w["kind"], w["task_id"]): w["title"] for w in work if (w["kind"], w["task_id"]) not in latest}
    for daily in db.query(DailyTask).filter(DailyTask.user_id == user_id, DailyTask.task_date >= start,
            DailyTask.task_date <= end, DailyTask.completed.is_(True), DailyTask.deleted_at.is_(None)):
        identity = ("task", daily.project_task_id) if daily.project_task_id else ("daily", daily.id)
        if identity not in latest and not db.query(DailyTask.id).filter(DailyTask.parent_id == daily.id, DailyTask.deleted_at.is_(None)).first():
            awaiting[identity] = daily.text
    reflections = {}
    progress, seen_progress, planning_reviews, seen_reviews, day_plans = [], set(), [], set(), {}
    for e in all_events:
        if not start <= e.record_date <= end: continue
        if e.event_type == "day_reflection": reflections.setdefault(str(e.record_date), json.loads(e.payload_json))
        if e.event_type == "day_plan": day_plans.setdefault(str(e.record_date), json.loads(e.payload_json))
        if e.event_type == "importance_review" and (e.owner_kind, e.owner_id, e.record_date) not in seen_reviews:
            seen_reviews.add((e.owner_kind, e.owner_id, e.record_date))
            planning_reviews.append(json.loads(e.payload_json) | {"date": str(e.record_date)})
        if e.event_type == "progress" and (e.owner_kind, e.owner_id, e.record_date) not in seen_progress:
            seen_progress.add((e.owner_kind, e.owner_id, e.record_date))
            progress.append(json.loads(e.payload_json) | {"date": str(e.record_date)})
    from app.project_models import CommitmentAdjustment, PlanningCycle
    adjustments = [{"id": a.id, "reason": a.reason, "impact": json.loads(a.impact_json),
                    "result": json.loads(a.result_json or "{}"), "at": a.confirmed_at}
                   for a in db.query(CommitmentAdjustment).filter(CommitmentAdjustment.user_id == user_id,
                       CommitmentAdjustment.confirmed_at >= lo, CommitmentAdjustment.confirmed_at < hi)]
    cycles = [{"id": c.id, "expected_result": c.expected_result, "review": json.loads(c.review_json)}
              for c in db.query(PlanningCycle).filter(PlanningCycle.user_id == user_id,
                  PlanningCycle.reviewed_at >= lo, PlanningCycle.reviewed_at < hi)]
    return {"recorded_seconds": total, "interval_count": len(sessions), "difficult_seconds": difficult,
        "unknown_difficulty_seconds": unknown, "work": work, "feedback": feedback, "sample_count": len(samples),
        "awaiting_feedback": [{"kind": k[0], "id": k[1], "title": v} for k,v in awaiting.items()],
        "missing_estimate_count": sum(f["original_estimate"] is None for f in feedback),
        "scope_change_count": sum(f["scope_changed"] for f in feedback),
        "retrospective_count": sum(f["estimate_origin"] != "before_start" for f in feedback),
        "mean_difference_minutes": round(sum(f["difference"] for f in samples) / len(samples), 2) if samples else None,
        "reflections": reflections, "day_plans": day_plans, "progress": progress, "planning_reviews": planning_reviews, "adjustments": adjustments, "cycles": cycles,
        "note": "只统计已记录区间；未记录不代表没有做。自报累计用时用于估时反馈，不追加时间账。样本少时不推断稳定趋势。"}


def day_task_payload(db, user_id, kind, row, day):
    payload = task_payload(db, user_id, kind, row)
    review = next((e for e in events(db, user_id, kind, row.id, "importance_review") if e.record_date == day), None)
    payload["reviewed_at"] = review.created_at if review and (payload["reviewed_at"] or day < today()) else None
    payload["day_review"] = json.loads(review.payload_json) if review else None
    return payload
