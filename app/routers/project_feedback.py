"""Account-scoped project deliveries and authenticated evidence files."""
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, exists
from sqlalchemy.orm import Session
from app.auth import get_current_active_user
from app.database import get_db
from app.models import User
from app.project_models import FeedbackOccurrence, FeedbackSubmission, FeedbackAttachment, FeedbackReport, FeedbackDelivery, Project
from app import feedback_service as svc

router = APIRouter(prefix="/feedback", tags=["项目反馈"])
MAX_FILE = 25 * 1024 * 1024


def storage():
    return Path(os.environ.get("FEEDBACK_STORAGE_DIR", "private-feedback")).resolve()


def owned(db, cls, row_id, user_id, lock=False):
    q = db.query(cls).filter_by(id=row_id, user_id=user_id)
    row = (q.with_for_update() if lock else q).first()
    if row is None:
        raise HTTPException(404, "记录不存在")
    return row


class SubmissionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    text: str = Field(default="", max_length=100000)
    links: list[str] = Field(default_factory=list, max_length=20)
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)
    note: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def evidence(self):
        if not (self.text or self.links or self.attachment_ids or self.note):
            raise ValueError("请填写成果、链接、附件或实践说明")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("附件不能重复")
        for link in self.links:
            parsed = urlsplit(link)
            if len(link) > 2000 or parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username:
                raise ValueError("请填写完整的 http 或 https 链接")
        return self


class ReviewInput(BaseModel):
    status: Literal["accepted", "needs_changes"]
    note: str = Field(min_length=1, max_length=4000)


class SkipInput(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


@router.get("/occurrences")
def occurrences(start: date, end: date, project_id: int | None = None,
                user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if end < start or (end - start).days > 732:
        raise HTTPException(400, "请选择两年以内的日期范围")
    q = db.query(FeedbackOccurrence).filter(FeedbackOccurrence.user_id == user.id,
        FeedbackOccurrence.due_date >= start, FeedbackOccurrence.due_date <= end)
    if project_id is not None:
        q = q.filter_by(project_id=project_id)
    return {"items": [svc.occurrence_payload(db, r) for r in q.order_by(FeedbackOccurrence.due_date, FeedbackOccurrence.id)]}


@router.get("/progress")
def progress(day: date, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return {"items": svc.project_progress(db, user.id, day, day)}


@router.get("/backlog")
def backlog(before: date, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
            user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    last_id = db.query(func.max(FeedbackSubmission.id)).filter(FeedbackSubmission.occurrence_id == FeedbackOccurrence.id).correlate(FeedbackOccurrence).scalar_subquery()
    needs_changes = exists().where(FeedbackSubmission.id == last_id, FeedbackSubmission.status == "needs_changes")
    q = db.query(FeedbackOccurrence).join(Project, Project.id == FeedbackOccurrence.project_id).filter(Project.deleted_at.is_(None), FeedbackOccurrence.user_id == user.id, FeedbackOccurrence.due_date < before,
        FeedbackOccurrence.skipped_reason.is_(None), or_(last_id.is_(None), needs_changes))
    return {"total": q.count(), "items": [svc.occurrence_payload(db, row) for row in q.order_by(FeedbackOccurrence.due_date, FeedbackOccurrence.id).offset(offset).limit(limit)]}


@router.get("/occurrences/{row_id}")
def occurrence(row_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return svc.occurrence_payload(db, owned(db, FeedbackOccurrence, row_id, user.id), history=True)


@router.post("/occurrences/{row_id}/submissions")
def submit(row_id: int, body: SubmissionInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = owned(db, FeedbackOccurrence, row_id, user.id, lock=True)
    if row.skipped_reason:
        raise HTTPException(409, "该节点已跳过，请先恢复节点")
    previous = db.query(FeedbackSubmission).filter_by(occurrence_id=row.id).all()
    for old in previous:
        if json.loads(old.content_json).get("client_id") == body.client_id:
            return svc.occurrence_payload(db, row, history=True)
    files = []
    for file_id in body.attachment_ids:
        f = owned(db, FeedbackAttachment, file_id, user.id)
        if f.submission_id and not any(s.id == f.submission_id for s in previous):
            raise HTTPException(400, "该附件已用于其他反馈节点")
        files.append(f)
    data = body.model_dump()
    data["attachments"] = [{"id": f.id, "filename": f.filename, "size": f.size, "content_type": f.content_type} for f in files]
    # Chinese characters + Latin words; external files/links cannot be reliably counted here.
    data["text_word_count"] = len(re.findall(r"[\u3400-\u9fff]|[a-zA-Z0-9]+(?:['’-][a-zA-Z0-9]+)*", body.text))
    minimum = json.loads(row.requirement_json).get("min_words")
    data["criteria_check"] = "not_set" if minimum is None else "text_met" if data["text_word_count"] >= minimum else "needs_manual_check"
    submission = FeedbackSubmission(user_id=user.id, occurrence_id=row.id,
        version=max((s.version for s in previous), default=0) + 1, content_json=svc.dumps(data))
    db.add(submission); db.flush()
    for f in files:
        if f.submission_id is None:
            f.submission_id = submission.id
    # A submitted version clears the corresponding outstanding reminder.
    for delivery in db.query(FeedbackDelivery).filter_by(user_id=user.id, occurrence_id=row.id):
        if delivery.log_id:
            from app.models import SelfTalkReminderLog
            log = db.get(SelfTalkReminderLog, delivery.log_id)
            log.action_taken = True
        if delivery.email_status in ("pending", "retry"):
            delivery.email_status = "cancelled"
    db.commit()
    svc.refresh_reports(db, user, row.due_date)
    return svc.occurrence_payload(db, row, history=True)


@router.post("/submissions/{submission_id}/review")
def review(submission_id: int, body: ReviewInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    s = owned(db, FeedbackSubmission, submission_id, user.id)
    row = owned(db, FeedbackOccurrence, s.occurrence_id, user.id, lock=True)
    if svc.latest(db, row.id).id != s.id:
        raise HTTPException(409, "已有新版本，请检查最新提交")
    if not body.note.strip():
        raise HTTPException(400, "请填写检查依据或需要补充的内容")
    from app.practice_service import event
    event(db, user.id, "feedback", row.id, "delivery_review", {"submission_id": s.id,
        "before": s.status, "after": body.status, "note": body.note})
    s.status, s.review_note, s.reviewed_at = body.status, body.note.strip(), svc.utc_now()
    db.commit(); svc.refresh_reports(db, user, row.due_date)
    return svc.occurrence_payload(db, row, history=True)


@router.post("/occurrences/{row_id}/skip")
def skip(row_id: int, body: SkipInput, restore: bool = False,
         user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = owned(db, FeedbackOccurrence, row_id, user.id, lock=True)
    if svc.latest(db, row.id) and not restore:
        raise HTTPException(409, "已有提交的节点保留记录，不再跳过")
    if not body.reason.strip():
        raise HTTPException(400, "请填写调整原因")
    from app.practice_service import event
    event(db, user.id, "feedback", row.id, "restore_node" if restore else "skip_node", {"reason": body.reason})
    row.skipped_reason = None if restore else body.reason.strip()
    db.commit(); svc.refresh_reports(db, user, row.due_date)
    return svc.occurrence_payload(db, row, history=True)


@router.post("/attachments")
async def upload(file: UploadFile = File(...), user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db.query(User).filter(User.id == user.id).with_for_update().first()
    total = db.query(func.coalesce(func.sum(FeedbackAttachment.size), 0)).filter_by(user_id=user.id).scalar()
    if total >= 500 * 1024 * 1024:
        raise HTTPException(413, "成果附件已达 500 MB，请联系管理员调整容量")
    base = storage(); base.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex
    target = base / key
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE or total + size > 500 * 1024 * 1024:
                    raise HTTPException(413, "单个附件最多 25 MB，账号附件总量最多 500 MB")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "不能上传空文件")
        name = re.sub(r"[\x00-\x1f\x7f]", "", (file.filename or "成果附件").replace("\\", "/").split("/")[-1])[:250] or "成果附件"
        row = FeedbackAttachment(user_id=user.id, filename=name, storage_key=key, size=size,
            content_type=(file.content_type or "application/octet-stream")[:120])
        db.add(row); db.commit()
        return {"id": row.id, "filename": row.filename, "size": row.size}
    except Exception:
        db.rollback(); target.unlink(missing_ok=True); raise
    finally:
        await file.close()


@router.get("/attachments/{file_id}")
def download(file_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = owned(db, FeedbackAttachment, file_id, user.id)
    target = storage() / row.storage_key
    if not target.is_file():
        raise HTTPException(404, "附件暂不可用，请联系管理员检查文件存储")
    return FileResponse(target, filename=row.filename, media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/reports")
def report_history(period: Literal["day", "week", "month", "quarter", "year"] = "day", anchor: date = Query(...),
                   user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.routers.long_term_details import calendar_bounds
    rows = db.query(FeedbackReport).filter_by(user_id=user.id, period=period, anchor=calendar_bounds(period, anchor)[0]).order_by(FeedbackReport.revision.desc()).limit(50)
    return {"items": [{"id": r.id, "revision": r.revision, "generated_at": r.generated_at.isoformat() + "Z"} for r in rows]}


@router.get("/reports/{report_id}")
def saved_report(report_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = owned(db, FeedbackReport, report_id, user.id)
    from app.plans import PAID_PLANS, effective_plan_key
    if row.period in ("month", "quarter", "year") and effective_plan_key(user) not in PAID_PLANS:
        raise HTTPException(403, "月报、季报和年报需要有效月卡或学期卡")
    result = json.loads(row.payload_json)
    from app.routers.long_term_details import apply_report_visibility
    apply_report_visibility(result, effective_plan_key(user) in PAID_PLANS)
    return {"report": result, "revision": row.revision, "generated_at": row.generated_at.isoformat() + "Z"}


@router.get("/deliveries")
def deliveries(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    return {"items": [{"id": r.id, "title": r.title, "email_status": r.email_status, "attempts": r.attempts,
        "last_error": r.last_error, "sent_at": r.sent_at, "next_attempt_at": r.next_attempt_at} for r in db.query(FeedbackDelivery).filter_by(user_id=user.id).order_by(FeedbackDelivery.id.desc()).limit(50)]}
