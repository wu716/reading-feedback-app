"""Reader 0.1.16 contract double. No external HTTP or business database."""
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException


class ReaderSource:
    instance = "f86c8a14-8ca8-48b0-8124-44ce7a681bda"
    account = "f79dbe2a-d06f-4166-bb80-94bb479f82f9"

    def __init__(self):
        self.requests, self.grants = {}, {}
        self.page = {"days": [], "reading_detail_started_at": "2026-10-23T00:00:00+08:00", "high_watermark": 0}
        self.calls = []
        self.highest = 0

    def approve(self, code):
        next(r for r in self.requests.values() if r["code"] == code)["approved"] = True

    def remote(self, method, path, *, body=None, params=None, reading_token=None):
        self.calls.append((method, path, body, params))
        if path == "/link-requests":
            row = {"request_id": str(uuid.uuid4()), "code": secrets.token_hex(10).upper(),
                "receiver_nonce": secrets.token_urlsafe(32), "receiver_account_id": body["receiver_account_id"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), "source_instance_id": self.instance, "approved": False}
            self.requests[row["request_id"]] = row
            return row
        if path.startswith("/link-requests/"):
            request_id, action = path.split("/")[2:4]
            row = self.requests[request_id]
            if row.get("consumed") or body["receiver_account_id"] != row["receiver_account_id"] or body["receiver_nonce"] != row["receiver_nonce"]:
                raise HTTPException(422, "关联请求无效或已使用")
            if action == "status":
                return {"source_confirmed": row["approved"], "source_account_label": "知间测试甲" if row["approved"] else None,
                    "source_instance_id": self.instance, "source_account_id": self.account if row["approved"] else None,
                    "authorized_from": "2026-10-23", "private_titles": False, "expires_at": row["expires_at"]}
            if not row["approved"] or body["expected_source_instance_id"] != self.instance or body["expected_source_account_id"] != self.account:
                raise HTTPException(409, "知间确认账号不符")
            row["consumed"] = True
            token = secrets.token_urlsafe(48)
            grant = {"grant_id": str(uuid.uuid4()), "reading_token": token, "source_instance_id": self.instance,
                "source_account_id": self.account, "receiver_account_id": row["receiver_account_id"],
                "authorized_from": "2026-10-23", "scope": "reading-days:read"}
            self.grants[token] = grant
            return grant
        if path == "/reading-days":
            if reading_token not in self.grants:
                raise HTTPException(403, "来源授权已撤销")
            grant = self.grants[reading_token]
            return {"schema_version": 1, "timezone": "Asia/Shanghai", "source_instance_id": self.instance,
                "source_account_id": self.account, "receiver_account_id": grant["receiver_account_id"],
                "next_cursor": None, "checkpoint": "checkpoint-"+str(self.page["high_watermark"]),
                "coverage": "recorded_not_day_confirmed", "pending_tail": "client_memory_not_observable", **self.page}
        raise AssertionError(path)
