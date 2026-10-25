"""Dated delivery, private evidence, report revisions and durable reminders."""
import hashlib
import json
import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import or_, func, exists, cast, String, literal
from sqlalchemy.exc import IntegrityError
from app.models import DailyTask, SelfTalkReminderLog, User
from app.project_models import (FeedbackOccurrence, FeedbackSubmission, FeedbackReport,
    FeedbackDelivery, Project, ProjectTask, ProjectStage, WorkSession, PracticeEvent, ExecutionConditionEvent)

TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def latest(db, occurrence_id):
    return db.query(FeedbackSubmission).filter_by(occurrence_id=occurrence_id).order_by(FeedbackSubmission.version.desc()).first()


def occurrence_payload(db, row, now=None, history=False, brief=False):
    now = now or datetime.now(TZ)
    submission = latest(db, row.id)
    due = datetime.combine(row.due_date, time.fromisoformat(row.deadline), TZ)
    first = db.query(FeedbackSubmission.submitted_at).filter_by(occurrence_id=row.id).order_by(FeedbackSubmission.version).first()
    late = bool(first and first[0].replace(tzinfo=timezone.utc) > due)
    status = "skipped" if row.skipped_reason else submission.status if submission else "overdue" if now > due else "pending"
    def version(s):
        return {"id": s.id, "version": s.version, **({} if brief else {"content": json.loads(s.content_json)}), "status": s.status,
            "review_note": s.review_note, "submitted_at": s.submitted_at.isoformat() + "Z",
            "reviewed_at": s.reviewed_at.isoformat() + "Z" if s.reviewed_at else None}
    project = db.get(Project, row.project_id)
    data = {"id": row.id, "project_id": row.project_id, "project_title": project.title, "source_deleted": project.deleted_at is not None,
        "cycle_id": row.cycle_id, "due_date": str(row.due_date), "deadline": row.deadline,
        "requirement": json.loads(row.requirement_json), "status": status, "late": late,
        "skipped_reason": row.skipped_reason, "first_submitted_at": first[0].isoformat()+"Z" if first else None,
        "latest": version(submission) if submission else None}
    if history:
        data["versions"] = [version(s) for s in db.query(FeedbackSubmission).filter_by(occurrence_id=row.id).order_by(FeedbackSubmission.version.desc())]
        data["events"] = [{"action": e.event_type, "at": e.created_at.isoformat() + "Z", "detail": json.loads(e.payload_json)}
            for e in db.query(PracticeEvent).filter_by(user_id=row.user_id, owner_kind="feedback", owner_id=row.id).order_by(PracticeEvent.id.desc())]
    return data


def project_progress(db, user_id, start, end):
    """References work intervals without adding them to the long-term time ledger."""
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    lo = datetime.combine(start, time(), TZ).astimezone(timezone.utc).replace(tzinfo=None)
    hi = datetime.combine(end + timedelta(days=1), time(), TZ).astimezone(timezone.utc).replace(tzinfo=None)
    tasks = {t.id: t for t in db.query(ProjectTask).filter_by(user_id=user_id)}
    daily = {d.id: d.project_task_id for d in db.query(DailyTask).filter(DailyTask.user_id == user_id, DailyTask.project_task_id.isnot(None))}
    seconds, intervals = {}, {}
    for s in db.query(WorkSession).filter(WorkSession.user_id == user_id, WorkSession.kind == "work",
            WorkSession.started_at < hi, WorkSession.ended_at.isnot(None), WorkSession.ended_at > lo):
        task = tasks.get(s.project_task_id or daily.get(s.daily_task_id))
        if not task:
            continue
        duration = max(0, (min(s.ended_at, hi) - max(s.started_at, lo)).total_seconds())
        seconds[task.project_id] = seconds.get(task.project_id, 0) + duration
        intervals.setdefault(task.project_id, []).append({"session_id": s.id, "task_id": task.id,
            "title": task.title, "seconds": duration, "date": s.started_at.replace(tzinfo=timezone.utc).astimezone(TZ).date().isoformat()})
    occurrences = db.query(FeedbackOccurrence).filter(FeedbackOccurrence.user_id == user_id,
        FeedbackOccurrence.due_date >= start, FeedbackOccurrence.due_date <= end).all()
    grouped = {}
    for occurrence in occurrences:
        grouped.setdefault(occurrence.project_id, []).append(occurrence_payload(db, occurrence, brief=True))
    updates, transitions, seen = {}, {}, set()
    for event in db.query(PracticeEvent).filter(PracticeEvent.user_id == user_id, PracticeEvent.owner_kind == "task",
            PracticeEvent.event_type == "progress", PracticeEvent.record_date.between(start, end)).order_by(PracticeEvent.id.desc()):
        task = tasks.get(event.owner_id)
        identity = (event.owner_id, event.record_date)
        if task and identity not in seen:
            seen.add(identity)
            updates.setdefault(task.project_id, []).append({**json.loads(event.payload_json), "date": str(event.record_date), "task_id": task.id})
    for event in db.query(ExecutionConditionEvent).filter(ExecutionConditionEvent.user_id == user_id,
            ExecutionConditionEvent.owner_kind == "project", ExecutionConditionEvent.action == "project_state_changed",
            ExecutionConditionEvent.created_at >= lo, ExecutionConditionEvent.created_at < hi).order_by(ExecutionConditionEvent.id):
        transitions.setdefault(event.owner_id, []).append({"date": event.created_at.isoformat() + "Z",
            "state": json.loads(event.after_json or "{}").get("state"), "reason": event.reason})
    results = []
    for p in db.query(Project).filter_by(user_id=user_id):
        own = [t for t in tasks.values() if t.project_id == p.id]
        completed = [t for t in own if t.completed_at and lo <= t.completed_at < hi and t.state == "completed"]
        stages = db.query(ProjectStage).filter_by(user_id=user_id, project_id=p.id).all()
        milestones = [{"id": s.id, "title": s.title, "date": s.closed_at.isoformat() + "Z", "reason": s.closed_reason}
            for s in stages if s.closed_at and lo <= s.closed_at < hi]
        nodes = grouped.get(p.id, [])
        if not (nodes or seconds.get(p.id) or completed or milestones or updates.get(p.id) or transitions.get(p.id)):
            continue
        results.append({"id": p.id, "title": p.title, "outcome": p.outcome, "execution_state": p.execution_state,
            "actual_seconds": seconds.get(p.id, 0), "intervals": intervals.get(p.id, []),
            "completed_tasks": [{"id": t.id, "title": t.title, "result": t.outcome_note} for t in completed],
            "current_stages": [s.title for s in stages if s.state == "current"], "milestones": milestones,
            "updates": updates.get(p.id, []), "transitions": transitions.get(p.id, []),
            "occurrences": nodes, "due_count": sum(n["status"] != "skipped" for n in nodes),
            "submitted_count": sum(n["latest"] is not None for n in nodes),
            "accepted_count": sum(n["status"] == "accepted" for n in nodes),
            "late_count": sum(n["late"] for n in nodes),
            "pending_count": sum(n["status"] in ("pending", "overdue", "needs_changes") for n in nodes)})
    return results


def enqueue(db, user_id, key, title, message, action_url, occurrence_id=None, reminder_type="project_feedback"):
    from app.self_talk.reminder_service import ReminderService
    if db.query(FeedbackDelivery.id).filter_by(event_key=key).first():
        return
    setting = ReminderService.get_or_create_setting(db, user_id)
    if not setting.is_enabled:
        return
    channels_enabled = reminder_type != "feedback_report" or bool(setting.record_reminder_enabled)
    log = SelfTalkReminderLog(user_id=user_id, reminder_type=reminder_type,
        detail=dumps({"title": title, "message": message, "action_url": action_url, "occurrence_id": occurrence_id}),
        notification_method="in_app" if not channels_enabled else "both" if setting.email_notification else "browser" if setting.browser_notification else "in_app")
    db.add(log); db.flush()
    db.add(FeedbackDelivery(user_id=user_id, event_key=key, occurrence_id=occurrence_id,
        log_id=log.id, title=title, message=message + "\n" + os.environ.get("PUBLIC_APP_URL", "http://43.161.238.165:8000").rstrip("/") + action_url,
        email_status="pending" if channels_enabled and setting.email_notification else "disabled"))


def check_feedback_reminders(db, user_id=None, now=None):
    now = now or datetime.now(TZ)
    from app.models import SelfTalkReminderSetting
    last_id = db.query(func.max(FeedbackSubmission.id)).filter(FeedbackSubmission.occurrence_id == FeedbackOccurrence.id).correlate(FeedbackOccurrence).scalar_subquery()
    last_version = db.query(func.max(FeedbackSubmission.version)).filter(FeedbackSubmission.occurrence_id == FeedbackOccurrence.id).correlate(FeedbackOccurrence).scalar_subquery()
    pending = or_(last_id.is_(None), exists().where(FeedbackSubmission.id == last_id, FeedbackSubmission.status == "needs_changes"))
    event_key = literal("occurrence:") + cast(FeedbackOccurrence.id, String) + literal(":version:") + cast(func.coalesce(last_version, 0), String)
    unclaimed = ~exists().where(FeedbackDelivery.event_key == event_key)
    q = db.query(FeedbackOccurrence).join(Project, Project.id == FeedbackOccurrence.project_id).join(User, User.id == FeedbackOccurrence.user_id).outerjoin(
        SelfTalkReminderSetting, SelfTalkReminderSetting.user_id == User.id).filter(
        FeedbackOccurrence.due_date <= now.date(), FeedbackOccurrence.skipped_reason.is_(None),
        FeedbackOccurrence.reminders_enabled == True, pending, unclaimed, User.is_active == True,
        Project.deleted_at.is_(None), or_(Project.execution_state.is_(None), Project.execution_state.notin_(("accepted", "delivered"))),
        or_(SelfTalkReminderSetting.id.is_(None), SelfTalkReminderSetting.is_enabled == True))
    if user_id is not None:
        q = q.filter(FeedbackOccurrence.user_id == user_id)
    for row in q.order_by(FeedbackOccurrence.due_date, FeedbackOccurrence.id).limit(2000):
        req = json.loads(row.requirement_json)
        p = db.get(Project, row.project_id)
        user = db.get(User, row.user_id)
        if not user or not user.is_active or not req.get("reminders") or p.deleted_at or p.execution_state in ("accepted", "delivered"):
            continue
        s = latest(db, row.id)
        if s and s.status != "needs_changes":
            continue
        if now < datetime.combine(row.due_date, time.fromisoformat(row.remind_at), TZ):
            continue
        # A supplementary request gets a new reminder, but ordinary polling is idempotent.
        key = f"occurrence:{row.id}:version:{s.version if s else 0}"
        enqueue(db, row.user_id, key, "提交项目反馈", f"{p.title} · {row.due_date}：{req['deliverable']}",
            f"/static/index.html?feedback={row.id}&record={row.due_date}#long-term", row.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # Concurrent workers claimed the same notification.


def deliver_email_outbox(db, user_id=None):
    from app.self_talk.reminder_service import ReminderService, record_status
    now = utc_now()
    q = db.query(FeedbackDelivery).filter(FeedbackDelivery.email_status.in_(("pending", "retry")),
        or_(FeedbackDelivery.next_attempt_at.is_(None), FeedbackDelivery.next_attempt_at <= now))
    if user_id is not None:
        q = q.filter_by(user_id=user_id)
    ids = [r.id for r in q.order_by(FeedbackDelivery.id).limit(50)]
    for row_id in ids:
        row = db.query(FeedbackDelivery).filter_by(id=row_id).with_for_update().first()
        if row.email_status not in ("pending", "retry") or row.next_attempt_at and row.next_attempt_at > now:
            continue
        setting = ReminderService.get_or_create_setting(db, row.user_id)
        user = db.get(User, row.user_id)
        log = db.get(SelfTalkReminderLog, row.log_id) if row.log_id else None
        complete = False
        if row.occurrence_id:
            occurrence = db.get(FeedbackOccurrence, row.occurrence_id)
            submission = latest(db, row.occurrence_id)
            project = db.get(Project, occurrence.project_id) if occurrence else None
            complete = not occurrence or not project or project.deleted_at is not None or not occurrence.reminders_enabled or occurrence.skipped_reason is not None or bool(submission and submission.status != "needs_changes")
        if log and log.reminder_type == "daily_record":
            status = record_status(db, row.user_id)
            complete = not setting.record_reminder_enabled or status["record_complete"] or str(status["record_date"]) != log.detail
        if complete or not user or not user.is_active or not setting.is_enabled or not setting.email_notification:
            row.email_status = "cancelled"; db.commit(); continue
        ok = ReminderService.send_email_notification(db, row.user_id, row.title, row.message)
        row.attempts += 1
        row.email_status = "sent" if ok else "failed" if row.attempts >= 5 else "retry"
        row.sent_at = now if ok else None
        row.last_error = None if ok else "邮件未发送成功，请检查邮箱和服务器 SMTP 配置"
        row.next_attempt_at = now + timedelta(minutes=min(60, 2 ** row.attempts)) if not ok else None
        db.commit()


def snapshot_report(db, user, result, notify=False):
    text = dumps(result)
    digest = hashlib.sha256(text.encode()).hexdigest()
    anchor = date.fromisoformat(result["start"])
    previous = db.query(FeedbackReport).filter_by(user_id=user.id, period=result["period"], anchor=anchor).order_by(FeedbackReport.revision.desc()).first()
    if previous and previous.digest == digest:
        row = previous
    else:
        row = FeedbackReport(user_id=user.id, period=result["period"], anchor=anchor,
            revision=previous.revision + 1 if previous else 1, digest=digest, payload_json=text)
        db.add(row); db.flush()
    if notify:
        names = {"day": "日报", "week": "周报", "month": "月报", "quarter": "季度报", "year": "年报"}
        enqueue(db, user.id, f"report:{user.id}:{row.period}:{anchor}", names[row.period] + "已生成",
            f"{result['start']} 至 {result['effective_end'] or result['end']}，可查看项目推进、方向明细和跨期变化。",
            f"/static/index.html?report={row.period}&record={anchor}#long-term", reminder_type="feedback_report")
    db.commit()
    return {"id": row.id, "revision": row.revision, "generated_at": row.generated_at.isoformat() + "Z"}


def refresh_reports(db, user, changed_day, notify=False):
    from app.routers.long_term_details import report_for_user
    from app.plans import PAID_PLANS, effective_plan_key
    periods = ("day", "week", "month", "quarter", "year") if effective_plan_key(user) in PAID_PLANS else ("day", "week")
    for period in periods:
        try:
            report_for_user(db, user, period, changed_day, notify=notify and period == "day")
        except Exception:
            db.rollback()
            logger.exception("记录已保存，报告更新待重试 user=%s period=%s", user.id, period)


def generate_closed_reports(db):
    from app.routers.long_term_details import calendar_bounds, report_for_user
    from app.plans import PAID_PLANS, effective_plan_key
    from app.models import LongTermLedgerDay, LongTermDailyRecord
    from app.project_models import ReaderReadingDay
    today = datetime.now(TZ).date()
    active_ids = db.query(LongTermLedgerDay.user_id).union(db.query(Project.user_id),
        db.query(LongTermDailyRecord.user_id), db.query(ReaderReadingDay.user_id))
    for user in db.query(User).filter(User.is_active == True, User.id.in_(active_ids)):
        periods = ("day", "week", "month", "quarter", "year") if effective_plan_key(user) in PAID_PLANS else ("day", "week")
        for period in periods:
            try:
                anchor = calendar_bounds(period, today)[0] - timedelta(days=1)
                # Do not invent reports from before this account existed.
                if user.created_at and anchor < user.created_at.date():
                    continue
                report_for_user(db, user, period, anchor, notify=True)
            except Exception:
                db.rollback(); logger.exception("周期报告生成失败 user=%s period=%s", user.id, period)
