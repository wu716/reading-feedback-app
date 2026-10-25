"""One UTC work interval, Beijing day slices, and editable ledger projections."""
from datetime import datetime, time, timedelta

from sqlalchemy import or_
from app.models import DailyTask
from app.project_models import ProjectTask, WorkSession, WorkLinkSetting, WorkMomentLink
from app.execution_service import budget_seconds, settle_expired


def bounds(day):
    start = datetime.combine(day, time.min) - timedelta(hours=8)
    return start, start + timedelta(days=1)


def sessions(db, user_id, start, end):
    left, _ = bounds(start)
    _, right = bounds(end)
    return db.query(WorkSession).filter(WorkSession.user_id == user_id, WorkSession.kind == "work",
        WorkSession.started_at < right, or_(WorkSession.ended_at.is_(None), WorkSession.ended_at > left)
    ).order_by(WorkSession.started_at, WorkSession.id).all()


def sources(db, user_id, start, end, *, historical=False):
    # Expired timers settle at their deadline, including when the execution page is closed.
    settle_expired(db, user_id)
    setting = db.get(WorkLinkSetting, user_id)
    notes = {r.session_id: r for r in db.query(WorkMomentLink).filter_by(user_id=user_id)}
    rows = sessions(db, user_id, start, end)
    tasks = {r.id: r.title for r in db.query(ProjectTask).filter(ProjectTask.user_id == user_id,
        ProjectTask.id.in_([s.project_task_id for s in rows if s.project_task_id]))}
    daily = {r.id: r.text for r in db.query(DailyTask).filter(DailyTask.user_id == user_id,
        DailyTask.id.in_([s.daily_task_id for s in rows if s.daily_task_id]))}
    result = {}
    for row in rows:
        meta = notes.get(row.id)
        enabled = bool((setting and row.id >= setting.first_session_id) or (meta and meta.imported))
        if not historical and not enabled:
            continue
        title = row.label or tasks.get(row.project_task_id) or daily.get(row.daily_task_id) or "工作片"
        day = start
        while day <= end:
            left, right = bounds(day)
            actual_end = row.ended_at
            if actual_end is None:
                actual_end = min(datetime.utcnow(), row.started_at + timedelta(seconds=budget_seconds(row)))
            a, b = max(left, row.started_at), min(right, actual_end)
            if b > a:
                result.setdefault(day, []).append({"id": f"work_{row.id}", "work_session_id": row.id,
                    "title": title[:200], "seconds": int((b-a).total_seconds()) if row.ended_at else 0,
                    "work_source": {"started_at": a.isoformat()+"Z", "ended_at": b.isoformat()+"Z" if row.ended_at else None,
                        "seconds": int((b-a).total_seconds()), "running": row.ended_at is None,
                        "source": row.source, "note": meta.note if meta else "", "enabled": enabled,
                        "time_log_node_id": row.time_log_node_id}})
            day += timedelta(days=1)
    return result


def merge(data, incoming, activity_cls):
    incoming = {r["work_session_id"]: r for r in incoming if not r["work_source"]["running"]}
    seen = set()
    for item in data["activities"]:
        sid = item.get("work_session_id")
        if not sid:
            continue
        seen.add(sid)
        source = incoming.get(sid)
        item["source_missing"] = source is None
        item["work_source"] = source["work_source"] if source else None
        item["source_changed"] = bool(source and item.get("work_override_seconds") is not None
            and item.get("work_basis_seconds") != source["seconds"])
        if source:
            if not item.get("work_title_override"):
                item["title"] = source["title"]
            item["seconds"] = item.get("work_override_seconds") if item.get("work_override_seconds") is not None else source["seconds"]
        else:
            item["seconds"] = 0
    for sid, source in incoming.items():
        if sid not in seen:
            data["activities"].append({**activity_cls(id=source["id"], category="work", title=source["title"],
                seconds=source["seconds"], work_session_id=sid).model_dump(), "work_source": source["work_source"],
                "source_missing": False, "source_changed": False})
    # A confirmed moment's original gap is never an additional activity interval.
    linked_nodes = {s["work_source"]["time_log_node_id"] for s in incoming.values()} - {None}
    for item in data["activities"]:
        if item.get("source_node_id") in linked_nodes:
            item["work_duplicate_of"] = next(sid for sid, s in incoming.items()
                if s["work_source"]["time_log_node_id"] == item["source_node_id"])


def counted(item):
    return not (item.get("source_missing") or item.get("work_excluded") or item.get("work_duplicate_of")
                or item.get("reader_duplicate_of"))
