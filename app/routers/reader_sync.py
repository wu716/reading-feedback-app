"""Reader 0.1.16 receiver: explicit two-sided confirmation and server-only pull."""
import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator, field_validator
from sqlalchemy.orm import Session
from app.auth import get_current_active_user
from app.database import get_db
from app.models import User, LongTermLedgerDay
from app.project_models import ReaderPairing, ReaderBinding, ReaderReadingDay, ReaderReceiverAccount
from app.feedback_service import utc_now, dumps

router = APIRouter(prefix="/integrations/reader", tags=["知间阅读联动"])


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def pairing_owner(db, user_id, pairing_id):
    row = db.query(ReaderPairing).filter_by(id=pairing_id, user_id=user_id).with_for_update().first()
    if not row:
        raise HTTPException(404, "关联请求不存在")
    if row.claimed_at or row.expires_at <= utc_now() or not row.nonce_cipher:
        raise HTTPException(409, "关联请求已使用或过期，请重新发起")
    return row


class RemoteRequest(BaseModel):
    request_id: uuid.UUID
    code: str = Field(min_length=16, max_length=40)
    receiver_nonce: str = Field(min_length=32, max_length=100)
    expires_at: datetime
    source_instance_id: uuid.UUID


class LinkConfirmation(BaseModel):
    expected_source_instance_id: uuid.UUID
    expected_source_account_id: uuid.UUID


@router.post("/pairing")
def create_pairing(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.reader_client import remote, seal
    db.query(User).filter_by(id=user.id).with_for_update().first()
    identity = db.query(ReaderReceiverAccount).filter_by(user_id=user.id).first()
    if identity is None:
        identity = ReaderReceiverAccount(user_id=user.id, subject=str(uuid.uuid4()))
        db.add(identity); db.flush()
    try:
        result = RemoteRequest.model_validate(remote("POST", "/link-requests", body={
            "receiver_account_id": identity.subject, "receiver_account_label": user.name or "书然账号"}))
    except ValidationError:
        raise HTTPException(502, "来源关联响应不符合协议，请联系管理员核对") from None
    if result.expires_at.tzinfo is None:
        raise HTTPException(502, "来源关联请求缺少明确有效期")
    db.query(ReaderPairing).filter_by(user_id=user.id, claimed_at=None).update({"expires_at": utc_now(), "nonce_cipher": None})
    row = ReaderPairing(user_id=user.id, code_hash=digest(result.code),
        expires_at=result.expires_at.astimezone(timezone.utc).replace(tzinfo=None),
        remote_request_id=str(result.request_id), receiver_subject=identity.subject,
        nonce_cipher=seal(result.receiver_nonce), source_instance_id=str(result.source_instance_id))
    db.add(row); db.commit()
    return {"pairing_id": row.id, "code": result.code, "expires_at": row.expires_at.isoformat() + "Z",
        "receiver_account_label": user.name, "scope": "逐日逐书阅读时长；知间确认后还需在书然核对两个账号"}


@router.get("/pairings/{pairing_id}")
def pairing_status(pairing_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.reader_client import remote, unseal
    row = pairing_owner(db, user.id, pairing_id)
    result = remote("POST", f"/link-requests/{row.remote_request_id}/status", body={
        "receiver_account_id": row.receiver_subject, "receiver_nonce": unseal(row.nonce_cipher)})
    if result.get("source_instance_id") != row.source_instance_id:
        raise HTTPException(409, "来源实例发生变化，请重新发起关联")
    public = {k: result.get(k) for k in ("source_confirmed", "source_account_label", "source_account_id",
        "source_instance_id", "authorized_from", "private_titles", "expires_at")}
    row.preview_json = dumps(public); db.commit()
    return {**public, "pairing_id": row.id, "receiver_account_label": user.name}


@router.post("/pairings/{pairing_id}/confirm")
def confirm_pairing(pairing_id: int, body: LinkConfirmation,
                    user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.reader_client import remote, unseal, seal
    db.query(User).filter_by(id=user.id).with_for_update().first()
    row = pairing_owner(db, user.id, pairing_id)
    preview = json.loads(row.preview_json or "{}")
    expected = (str(body.expected_source_instance_id), str(body.expected_source_account_id))
    if not preview.get("source_confirmed") or expected != (preview.get("source_instance_id"), preview.get("source_account_id")):
        raise HTTPException(409, "请先读取并核对知间已确认的账号")
    existing = db.query(ReaderBinding).filter_by(source_instance_id=expected[0], source_user_id=expected[1]).with_for_update().first()
    if existing and existing.user_id != user.id:
        raise HTTPException(409, "该知间账号已关联其他书然账号，请先明确核对原账号归属")
    other = db.query(ReaderBinding).filter_by(user_id=user.id, active=True).first()
    if other and (not existing or other.id != existing.id):
        raise HTTPException(409, "请先解除书然中的另一个知间账号")
    result = remote("POST", f"/link-requests/{row.remote_request_id}/confirm", body={
        "receiver_account_id": row.receiver_subject, "receiver_nonce": unseal(row.nonce_cipher),
        "expected_source_instance_id": expected[0], "expected_source_account_id": expected[1]})
    if ((result.get("source_instance_id"), result.get("source_account_id"), result.get("receiver_account_id")) != (*expected, row.receiver_subject)
            or result.get("authorized_from") != preview.get("authorized_from")):
        raise HTTPException(409, "最终授权的账号与已核对账号不符，请重新关联")
    reading_token = result.get("reading_token", "")
    if not isinstance(reading_token, str) or not 32 <= len(reading_token) <= 1000 or result.get("scope") != "reading-days:read":
        raise HTTPException(502, "来源没有返回有效的受限阅读授权，请重新关联")
    binding = existing or ReaderBinding(user_id=user.id, source_instance_id=expected[0], source_user_id=expected[1])
    binding.token_hash, binding.credential_cipher = digest(reading_token), seal(reading_token)
    binding.source_label = str(preview.get("source_account_label") or "知间账号")[:200]
    binding.active, binding.remote_grant_id, binding.receiver_subject = True, result["grant_id"], row.receiver_subject
    binding.authorized_from = date.fromisoformat(result["authorized_from"])
    binding.cursor, binding.sync_status, binding.sync_error, binding.next_retry_at = None, "pending", None, None
    db.add(binding); row.claimed_at, row.nonce_cipher = utc_now(), None; db.commit()
    return {"binding_id": binding.id, "linked": True, "source_label": binding.source_label, "sync_status": "pending"}


class Book(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_book_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    active_seconds: int = Field(ge=0, le=86400, strict=True)
    document_deleted: bool = False


class HistoricalBook(Book):
    active_seconds: int = Field(ge=0, le=100000000000, strict=True)


class ReadingDay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    revision: int = Field(ge=1, strict=True)
    snapshot_kind: Literal["full_day"]
    active_seconds: int = Field(ge=0, le=86400, strict=True)
    coverage: Literal["recorded_not_day_confirmed", "no_records_not_confirmed_zero"] = "recorded_not_day_confirmed"
    books: list[Book] = Field(max_length=1000)
    removed_book_ids: list[str] = Field(default_factory=list, max_length=1000)
    deleted: bool = False

    @model_validator(mode="after")
    def totals(self):
        if len({b.source_book_id for b in self.books}) != len(self.books):
            raise ValueError("逐书身份不能重复")
        if sum(b.active_seconds for b in self.books) != self.active_seconds:
            raise ValueError("每日总量应等于逐书活跃阅读时长之和")
        if self.deleted and (self.books or self.active_seconds):
            raise ValueError("删除日快照必须为空")
        return self


class SourcePage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    source_instance_id: str = Field(min_length=1, max_length=100)
    source_account_id: str = Field(min_length=1, max_length=200)
    receiver_account_id: str = Field(min_length=1, max_length=200)
    timezone: Literal["Asia/Shanghai"]
    reading_detail_started_at: date
    days: list[ReadingDay] = Field(max_length=100)
    historical_baseline: list[HistoricalBook] = Field(default_factory=list, max_length=2000)
    high_watermark: int = Field(ge=0, strict=True)
    next_cursor: str | None = Field(default=None, max_length=8000)
    checkpoint: str | None = Field(default=None, max_length=8000)
    coverage: Literal["recorded_not_day_confirmed"] = "recorded_not_day_confirmed"
    pending_tail: Literal["client_memory_not_observable"] = "client_memory_not_observable"

    @field_validator("reading_detail_started_at", mode="before")
    @classmethod
    def start_date(cls, value):
        if isinstance(value, str) and "T" in value:
            from app.feedback_service import TZ
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("明细起始时刻需要包含时区")
            return dt.astimezone(TZ).date()
        return value


def apply_snapshot(db, binding, body):
    """Apply only a validated, identity-checked server page; caller commits cursor too."""
    from app.feedback_service import TZ
    from app.routers.long_term_details import CATEGORIES
    if len({d.date for d in body.days}) != len(body.days):
        raise HTTPException(409, "来源同一批次日期重复")
    today = datetime.now(TZ).date()
    if any(d.date < body.reading_detail_started_at or d.date > today for d in body.days):
        raise HTTPException(409, "来源日明细超出真实记录日期范围")
    if binding.detail_started_on and binding.detail_started_on != body.reading_detail_started_at:
        raise HTTPException(409, "来源明细起始日期变化，请核对迁移后重新关联")
    acknowledgements, changed = [], []
    for day in body.days:
        books = [b.model_dump() for b in sorted(day.books, key=lambda b: b.source_book_id)]
        text = dumps(books); checksum = digest(text)
        old = db.query(ReaderReadingDay).filter_by(binding_id=binding.id, record_date=day.date).first()
        if old and old.revision == day.revision and old.digest != checksum:
            raise HTTPException(409, "同一日期同一修订号内容不同，失败页未保存")
        if not old or day.revision > old.revision:
            content_changed = old is None or old.digest != checksum
            row = old or ReaderReadingDay(user_id=binding.user_id, binding_id=binding.id, record_date=day.date)
            row.revision, row.books_json, row.digest, row.synced_at = day.revision, text, checksum, utc_now()
            db.add(row)
            if content_changed:
                changed.append(day.date)
                ledger = db.query(LongTermLedgerDay).filter_by(user_id=binding.user_id, record_date=day.date).with_for_update().first()
                if ledger:
                    payload = json.loads(ledger.payload_json)
                    confirmed = payload.get("category_confirmed", list(CATEGORIES) if payload.get("day_confirmed") else [])
                    payload["category_confirmed"] = [k for k in confirmed if k != "reading"]
                    payload["day_confirmed"] = False
                    ledger.payload_json = dumps(payload); ledger.revision += 1
        acknowledgements.append({"date": str(day.date), "revision": max(old.revision if old else 0, day.revision)})
    binding.detail_started_on = body.reading_detail_started_at
    if body.historical_baseline:
        binding.baseline_json = dumps([b.model_dump() for b in body.historical_baseline])
    return {"acknowledged": acknowledgements, "changed_dates": changed}


@router.post("/bindings/{binding_id}/sync")
def sync(binding_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.reader_client import sync_binding
    return sync_binding(db, binding_id, user.id)


@router.get("/status")
def status(user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    from app.reader_client import configured
    return {"configured": configured(), "items": [{
        "id": r.id, "source_label": r.source_label, "source_instance_id": r.source_instance_id,
        "active": r.active, "detail_started_on": r.detail_started_on, "last_sync_at": r.last_sync_at,
        "sync_status": r.sync_status, "sync_error": r.sync_error,
        "historical_baseline": json.loads(r.baseline_json or "[]")}
        for r in db.query(ReaderBinding).filter_by(user_id=user.id)]}


@router.delete("/bindings/{binding_id}")
def revoke(binding_id: int, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    row = db.query(ReaderBinding).filter_by(id=binding_id, user_id=user.id).with_for_update().first()
    if not row:
        raise HTTPException(404, "关联不存在")
    row.active, row.credential_cipher, row.cursor = False, None, None
    row.sync_status = "stopped"; db.commit()
    return {"revoked": True, "history_retained": True}
