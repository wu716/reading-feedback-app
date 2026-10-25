"""Account-owned moments and session linkage; no inferred time gaps."""
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import User, TimeLogNode
from app.project_models import WorkSession, WorkMomentLink
from app.work_link_service import sources

router = APIRouter(prefix="/work-links", tags=["工作与时刻联动"])


def owned(db, model, user, key):
    row = db.get(model, key)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    return row


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NoteInput(Strict):
    note: str = Field(max_length=3000)


class ConfirmInput(Strict):
    node_id: int = Field(gt=0)
    session_id: int | None = Field(default=None, gt=0)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    daily_task_id: int | None = Field(default=None, gt=0)
    category: Literal["reading", "fitness", "friends", "family", "writing", "work", "relaxation"] = "work"


class IntervalInput(Strict):
    started_at: datetime
    ended_at: datetime
    correction_note: str = Field(min_length=1, max_length=2000)


@router.patch("/{session_id}/interval")
def correct_interval(session_id: int, body: IntervalInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.routers.projects import correct_session, SessionCorrectionInput
    owned(db, WorkSession, user, session_id)
    if body.started_at.tzinfo is None or body.ended_at.tzinfo is None:
        raise HTTPException(400, "区间必须包含时区")
    if body.ended_at.astimezone(timezone.utc).replace(tzinfo=None) > datetime.utcnow():
        raise HTTPException(400, "结束时间不能晚于当前时间")
    return correct_session(session_id, SessionCorrectionInput(**body.model_dump()), user=user, db=db)


def metadata(db, user, session):
    row = db.get(WorkMomentLink, session.id)
    if row is None:
        row = WorkMomentLink(session_id=session.id, user_id=user.id, note="", imported=False)
        db.add(row)
    return row


@router.get("")
def list_links(day: date = Query(...), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    all_sources = sources(db, user.id, day, day, historical=True).get(day, [])
    db.commit()
    return {"items": [r for r in all_sources if r["work_source"]["enabled"]],
            "history": [r for r in all_sources if not r["work_source"]["enabled"]]}


@router.put("/{session_id}/note")
def update_note(session_id: int, body: NoteInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    session = owned(db, WorkSession, user, session_id)
    if session.kind != "work":
        raise HTTPException(400, "只能补充工作活动")
    metadata(db, user, session).note = body.note
    db.commit()
    return {"saved": True}


@router.get("/{session_id}")
def get_source(session_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    session = owned(db, WorkSession, user, session_id)
    if session.kind != "work":
        raise HTTPException(404, "工作片不存在")
    return {"started_at": session.started_at.isoformat()+"Z",
            "ended_at": session.ended_at.isoformat()+"Z" if session.ended_at else None,
            "correction_note": session.correction_note or ""}


@router.post("/{session_id}/import")
def import_session(session_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter_by(id=user.id).with_for_update().first()
    session = owned(db, WorkSession, user, session_id)
    if session.kind != "work" or session.ended_at is None:
        raise HTTPException(400, "请先结束工作活动，再核对导入")
    metadata(db, user, session).imported = True
    db.commit()
    return {"saved": True}


@router.post("/confirm")
def confirm_moment(body: ConfirmInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.routers.projects import assert_no_overlap, owned as owned_task
    from app.models import DailyTask
    from app.routers.long_term_details import Activity, read_range, dumps
    from app.models import LongTermLedgerDay
    from app import practice_service

    db.query(User).filter_by(id=user.id).with_for_update().first()
    node = owned(db, TimeLogNode, user, body.node_id)
    if node.deleted_at is not None:
        raise HTTPException(404, "时刻已移除")
    # Retrying confirmation returns the existing source; never duplicates an interval.
    existing = db.query(WorkSession).filter_by(user_id=user.id, time_log_node_id=node.id, kind="work").first()
    if existing:
        if body.session_id and body.session_id != existing.id:
            raise HTTPException(409, "该时刻已关联另一工作片")
        return {"session_id": existing.id}
    if body.session_id:
        session = owned(db, WorkSession, user, body.session_id)
        if session.kind != "work" or session.time_log_node_id not in (None, node.id):
            raise HTTPException(409, "该工作片已经关联其他时刻，请保留原关联")
        session.time_log_node_id = node.id
        metadata(db, user, session).imported = True
        db.commit()
        return {"session_id": session.id}
    if body.started_at is None or body.ended_at is None:
        raise HTTPException(400, "请明确确认实际开始与结束时间")
    if body.started_at.tzinfo is None or body.ended_at.tzinfo is None:
        raise HTTPException(400, "区间必须包含时区")
    start = body.started_at.astimezone(timezone.utc).replace(tzinfo=None)
    end = body.ended_at.astimezone(timezone.utc).replace(tzinfo=None)
    if end > datetime.utcnow():
        raise HTTPException(400, "结束时间不能晚于当前时间")
    from app.execution_service import settle_expired
    settle_expired(db, user.id)
    assert_no_overlap(db, user.id, start, end)
    task = owned_task(db, DailyTask, body.daily_task_id, user.id) if body.daily_task_id else None
    session = WorkSession(user_id=user.id, time_log_node_id=node.id, daily_task_id=task.id if task else None,
        project_task_id=task.project_task_id if task else None, kind="work", source="moment",
        started_at=start, ended_at=end, label=node.label or "确认时刻", correction_note="用户确认实际活动区间")
    if task:
        practice_service.snapshot_session(db, session)
    db.add(session)
    db.flush()
    metadata(db, user, session).imported = True
    # Persist the chosen category for each Beijing slice, using the same ledger as reports.
    day = (start.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Asia/Shanghai'))).date()
    last = (end - timedelta(microseconds=1) + timedelta(hours=8)).date()

    while day <= last:
        data = read_range(db, user.id, day, day)[0]
        for activity in data["activities"]:
            if activity.get("work_session_id") == session.id:
                activity["category"] = body.category
        allowed = {"activities", "expenses", "expense_confirmed", "day_confirmed", "category_confirmed",
                   "attention_items", "attention_confirmed"}
        payload = {k: v for k, v in data.items() if k in allowed}
        payload["activities"] = [Activity.model_validate({k: v for k, v in a.items() if k in Activity.model_fields}).model_dump()
                                 for a in payload["activities"]]
        row = db.query(LongTermLedgerDay).filter_by(user_id=user.id, record_date=day).first()
        if row is None:
            row = LongTermLedgerDay(user_id=user.id, record_date=day, revision=0)
            db.add(row)
        row.payload_json = dumps(payload)
        row.revision += 1
        day += timedelta(days=1)
    db.commit()
    return {"session_id": session.id}
