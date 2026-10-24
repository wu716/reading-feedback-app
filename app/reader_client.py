"""Trusted reader 0.1.16 client; credentials never pass through a browser."""
import base64
import hashlib
import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit
import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import ValidationError
from app.config import settings
from app.models import User
from app.project_models import ReaderBinding
from app.feedback_service import utc_now, refresh_reports

BASE = "/api/integrations/shuran/v1"


def configured():
    return bool(os.environ.get("READER_API_URL") and os.environ.get("READER_CLIENT_ID")
        and len(os.environ.get("READER_CLIENT_SECRET", "")) >= 32
        and (not settings.is_production or not settings.is_insecure_secret))


def cipher():
    material = ("shuran-reader-v1:" + settings.secret_key).encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def seal(value):
    return cipher().encrypt(value.encode()).decode()


def unseal(value):
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, AttributeError, ValueError):
        raise HTTPException(409, "来源授权凭证不可用，请重新关联知间账号")


def remote(method, path, *, body=None, params=None, reading_token=None):
    if not configured():
        raise HTTPException(503, "知间联动尚未配置；请继续手动记录")
    url = os.environ["READER_API_URL"].rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(503, "服务器的知间来源地址配置无效")
    if settings.is_production and parsed.scheme != "https" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(503, "生产来源需要 HTTPS，或指向受控本机 SSH 通道")
    headers = {"X-Shuran-Client": os.environ["READER_CLIENT_ID"],
        "Authorization": "Bearer " + os.environ["READER_CLIENT_SECRET"]}
    if reading_token:
        headers["X-Reading-Grant"] = reading_token
    try:
        with requests.request(method, url + BASE + path, json=body, params=params, headers=headers,
                timeout=(5, 15), allow_redirects=False, stream=True) as response:
            if response.status_code >= 300:
                raise HTTPException(response.status_code if response.status_code in (401, 403, 409, 422) else 502,
                    f"知间服务返回 {response.status_code}，请核对授权或服务器配置")
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    raise HTTPException(502, "来源单页超过 10 MB，请联系管理员核对数据")
                chunks.append(chunk)
            return json.loads(b"".join(chunks))
    except (requests.RequestException, json.JSONDecodeError):
        raise HTTPException(502, "暂时无法读取知间，已保留接收历史，稍后可以重试")


def sync_binding(db, binding_id, user_id=None, max_pages=3):
    from app.routers.reader_sync import SourcePage, apply_snapshot
    changed, pages, complete = set(), 0, False
    try:
        for _ in range(max_pages):
            q = db.query(ReaderBinding).filter_by(id=binding_id)
            if user_id is not None:
                q = q.filter_by(user_id=user_id)
            binding = q.with_for_update().first()
            if not binding:
                raise HTTPException(404, "关联不存在")
            if not binding.active or not db.get(User, binding.user_id).is_active:
                raise HTTPException(409, "关联已停止，历史记录保留")
            params = {"from": binding.authorized_from.isoformat(), "limit": 31}
            if binding.cursor:
                params["cursor"] = binding.cursor
            data = remote("GET", "/reading-days", params=params, reading_token=unseal(binding.credential_cipher))
            page = SourcePage.model_validate(data)
            if (page.source_instance_id, page.source_account_id, page.receiver_account_id) != (
                    binding.source_instance_id, binding.source_user_id, binding.receiver_subject):
                raise HTTPException(409, "来源身份与已确认账号不符，停止本页处理")
            if any(d.date < binding.authorized_from or d.revision > page.high_watermark for d in page.days):
                raise HTTPException(409, "来源日期或修订超出已确认授权范围")
            if page.high_watermark < binding.high_watermark:
                raise HTTPException(409, "来源高水位倒退，保留原进度，请核对恢复或迁移")
            if not page.next_cursor and not page.checkpoint:
                raise HTTPException(502, "来源缺少完整读取检查点，未推进同步进度")
            result = apply_snapshot(db, binding, page)
            binding.cursor = page.next_cursor or page.checkpoint
            binding.high_watermark = page.high_watermark
            binding.last_sync_at, binding.sync_error = utc_now(), None
            binding.sync_status = "catching_up" if page.next_cursor else "synced"
            binding.next_retry_at = None
            # Source data and cursor commit together; a failed page is always retried.
            db.commit(); pages += 1; changed.update(result["changed_dates"])
            if not page.next_cursor:
                complete = True; break
    except (HTTPException, ValidationError) as error:
        db.rollback()
        row = db.query(ReaderBinding).filter_by(id=binding_id).first()
        if row and (user_id is None or row.user_id == user_id):
            status_code = error.status_code if isinstance(error, HTTPException) else 502
            row.sync_status = "needs_relink" if status_code in (401, 403, 409) else "retry"
            row.sync_error = str(error.detail)[:300] if isinstance(error, HTTPException) else "来源格式不符合协议，未保存失败页"
            row.next_retry_at = utc_now() + timedelta(minutes=15)
            if status_code == 422 and row.cursor:
                row.cursor = None; row.sync_status = "resync_required"
                row.sync_error = "来源游标已失效，将重新完整读取；已有记录按修订号去重"
            if status_code == 403:
                row.active, row.credential_cipher = False, None
            db.commit()
        if isinstance(error, ValidationError):
            raise HTTPException(502, "来源格式不符合协议，失败页和进度均未保存")
        raise
    finally:
        if changed:
            from app.routers.long_term_details import calendar_bounds, report_for_user
            from app.plans import PAID_PLANS, effective_plan_key
            row = db.get(ReaderBinding, binding_id)
            user = db.get(User, row.user_id)
            periods = ("day", "week", "month", "quarter", "year") if effective_plan_key(user) in PAID_PLANS else ("day", "week")
            targets = {(period, calendar_bounds(period, day)[0]) for day in changed for period in periods}
            for period, day in sorted(targets):
                try:
                    report_for_user(db, user, period, day)
                except Exception:
                    db.rollback()  # The acknowledged source page remains safely committed.
    return {"changed_dates": sorted(str(d) for d in changed), "pages": pages, "complete": complete}


def sync_reader_accounts(db):
    if not configured():
        return
    ids = [row.id for row in db.query(ReaderBinding).join(User, User.id == ReaderBinding.user_id).filter(User.is_active == True, ReaderBinding.active == True,
        (ReaderBinding.next_retry_at.is_(None)) | (ReaderBinding.next_retry_at <= utc_now()))]
    for binding_id in ids:
        try:
            sync_binding(db, binding_id)
        except Exception:
            db.rollback()  # One unavailable/revoked source must not stop other users.
