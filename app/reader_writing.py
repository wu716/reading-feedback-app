"""Separate consented output stream; atomic snapshots and checkpoints."""
import hashlib
import json
from datetime import date, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.feedback_service import TZ, dumps, utc_now
from app.models import LongTermLedgerDay, User
from app.project_models import ReaderBinding, ReaderWritingDay, ReaderWritingState


class Counts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: int = Field(ge=0, le=10000000, strict=True)
    knowledge: int = Field(ge=0, le=10000000, strict=True)
    review: int = Field(ge=0, le=10000000, strict=True)
    material: int = Field(ge=0, le=10000000, strict=True)


class Day(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    revision: int = Field(ge=1, strict=True)
    snapshot_kind: Literal["full_day"]
    words: int = Field(ge=0, le=10000000, strict=True)
    categories: Counts

    @model_validator(mode="after")
    def totals(self):
        if self.words != sum(self.categories.model_dump().values()):
            raise ValueError("输出总字数须等于分类之和")
        return self


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    source_instance_id: str = Field(min_length=1, max_length=100)
    source_account_id: str = Field(min_length=1, max_length=200)
    receiver_account_id: str = Field(min_length=1, max_length=200)
    timezone: Literal["Asia/Shanghai"]
    authorized: bool
    writing_started_at: datetime | None
    days: list[Day] = Field(max_length=100)
    high_watermark: int = Field(ge=0, strict=True)
    next_cursor: str | None = Field(default=None, max_length=8000)
    checkpoint: str | None = Field(default=None, max_length=8000)


def apply_page(db, binding, state, page):
    if (page.source_instance_id, page.source_account_id, page.receiver_account_id) != (
            binding.source_instance_id, binding.source_user_id, binding.receiver_subject):
        raise HTTPException(409, "字数来源身份与已确认账号不符")
    if not page.authorized:
        if page.days or page.next_cursor or page.checkpoint:
            raise HTTPException(502, "未授权的字数响应不应携带数据")
        state.status, state.error = "not_authorized", None
        return set()
    if not page.writing_started_at or page.writing_started_at.tzinfo is None:
        raise HTTPException(502, "缺少真实字数统计启用时刻")
    started = page.writing_started_at.astimezone(TZ).date()
    if state.started_on and state.started_on != started:
        raise HTTPException(409, "字数统计启用日期改变，请核对来源")
    if page.high_watermark < state.high_watermark or (not page.next_cursor and not page.checkpoint):
        raise HTTPException(409, "字数进度倒退或缺少读取检查点")
    if len({d.date for d in page.days}) != len(page.days):
        raise HTTPException(409, "字数日期不能重复")
    changed = set()
    today = datetime.now(TZ).date()
    for day in page.days:
        if day.date < max(binding.authorized_from, started) or day.date > today or day.revision > page.high_watermark:
            raise HTTPException(409, "字数日期或修订超出授权与记录范围")
        categories = dumps(day.categories.model_dump())
        digest = hashlib.sha256(categories.encode()).hexdigest()
        old = db.query(ReaderWritingDay).filter_by(binding_id=binding.id, record_date=day.date).first()
        if old and old.revision == day.revision and old.digest != digest:
            raise HTTPException(409, "同一字数修订包含不同内容")
        if old and day.revision <= old.revision:
            continue
        row = old or ReaderWritingDay(user_id=binding.user_id, binding_id=binding.id, record_date=day.date)
        if old is None or old.digest != digest:
            changed.add(day.date)
            ledger = db.query(LongTermLedgerDay).filter_by(user_id=binding.user_id, record_date=day.date).with_for_update().first()
            if ledger:
                from app.routers.long_term_details import CATEGORIES
                data = json.loads(ledger.payload_json)
                confirmed = data.get("category_confirmed", list(CATEGORIES) if data.get("day_confirmed") else [])
                data["category_confirmed"] = [key for key in confirmed if key != "writing"]
                data["day_confirmed"] = False
                ledger.payload_json = dumps(data)
                ledger.revision += 1
        row.revision, row.words, row.categories_json, row.digest, row.synced_at = day.revision, day.words, categories, digest, utc_now()
        db.add(row)
    state.cursor, state.high_watermark = page.next_cursor or page.checkpoint, page.high_watermark
    state.started_on, state.last_sync_at = started, utc_now()
    state.status, state.error = ("catching_up" if page.next_cursor else "synced"), None
    return changed


def sync_writing(db, binding_id, max_pages=3):
    from app.reader_client import remote, unseal
    changed, complete = set(), False
    try:
        for _ in range(max_pages):
            binding = db.query(ReaderBinding).filter_by(id=binding_id).with_for_update().first()
            if not binding or not binding.active or not db.get(User, binding.user_id).is_active:
                raise HTTPException(409, "关联已停止")
            state = db.get(ReaderWritingState, binding_id)
            if not state:
                state = ReaderWritingState(binding_id=binding_id, high_watermark=0)
                db.add(state)
            params = {"from": str(binding.authorized_from), "limit": 31}
            if state.cursor:
                params["cursor"] = state.cursor
            page = Page.model_validate(remote("GET", "/writing-days", params=params, reading_token=unseal(binding.credential_cipher)))
            changed.update(apply_page(db, binding, state, page))
            db.commit()
            if not page.next_cursor:
                complete = True
                break
    except (HTTPException, ValidationError) as exc:
        db.rollback()
        state = db.get(ReaderWritingState, binding_id)
        if not state:
            state = ReaderWritingState(binding_id=binding_id, high_watermark=0)
            db.add(state)
        state.status = "retry"
        state.error = str(exc.detail)[:300] if isinstance(exc, HTTPException) else "来源字数格式无效，未保存失败页"
        if isinstance(exc, HTTPException) and exc.status_code == 422:
            state.cursor = None
            state.status = "resync_required"
        db.commit()
        complete = False
    return {"changed_dates": changed, "complete": complete}


def source_days(db, user_id, start, end):
    result = {}
    for row in db.query(ReaderWritingDay).filter(ReaderWritingDay.user_id == user_id,
            ReaderWritingDay.record_date >= start, ReaderWritingDay.record_date <= end):
        binding = db.get(ReaderBinding, row.binding_id)
        result.setdefault(row.record_date, []).append({"id": f"output_{row.binding_id}", "reader_output_key": f"output_{row.binding_id}",
            "category": "writing", "title": "知间学习输出", "seconds": 0, "words": row.words,
            "reader_output_source": {"label": "知间", "account_label": binding.source_label,
                "categories": json.loads(row.categories_json), "revision": row.revision, "active_binding": binding.active}})
    return result


def merge(data, incoming, activity_cls):
    incoming = {a["id"]: a for a in incoming}
    existing = set()
    for item in data["activities"]:
        if not item.get("reader_output_key"):
            continue
        existing.add(item["id"])
        source = incoming.get(item["id"])
        item["words"], item["seconds"], item["source_missing"] = source["words"] if source else 0, 0, source is None
        if source:
            item["title"], item["reader_output_source"] = source["title"], source["reader_output_source"]
    for key, source in incoming.items():
        if key not in existing:
            data["activities"].append({**activity_cls.model_validate({k: v for k, v in source.items() if k in activity_cls.model_fields}).model_dump(),
                "reader_output_source": source["reader_output_source"], "source_missing": False})
