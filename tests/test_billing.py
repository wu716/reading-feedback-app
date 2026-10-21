"""Manual receipts and entitlement changes must stay auditable and atomic."""

import io
import zipfile
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import get_current_owner
from app.backup import build_backup_zip
from app.database import Base, get_db
from app.models import GrantEvent, InviteCode, PaymentTransaction, RefundTransaction, User
from app.plans import _today
from app.routers.auth import router as auth_router
from app.routers.owner import router as owner_router


def make_app():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            User(id=1, email="owner@example.test", name="Owner", password_hash="unused"),
            User(id=2, email="customer@example.test", name="Customer", password_hash="unused"),
        ])
        db.commit()
    app = FastAPI()
    app.include_router(owner_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")

    def db_override():
        with Session(engine) as db:
            yield db

    def owner_override(request: Request, db: Session = Depends(get_db)):
        if request.headers.get("X-Test-Owner") != "1":
            raise HTTPException(status_code=403, detail="仅站长可访问")
        return db.get(User, 1)

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_owner] = owner_override
    return engine, TestClient(app)


def payment(**changes):
    body = {
        "user_id": 2,
        "plan": "monthly",
        "amount_cents": 990,
        "channel": "wechat",
        "transaction_reference": "WX-001",
        "idempotency_key": "checkout-001",
        "paid_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "note": "群内已核实收款",
    }
    body.update(changes)
    return body


def post_owner(client, path, body):
    return client.post("/api/owner" + path, json=body, headers={"X-Test-Owner": "1"})


def refund(payment_id, **changes):
    body = {
        "payment_id": payment_id,
        "amount_cents": 300,
        "channel": "wechat",
        "transaction_reference": "RF-001",
        "idempotency_key": "refund-001",
        "refunded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "reason": "依法处理的售后退款",
    }
    body.update(changes)
    return body


def test_payment_renewal_idempotency_and_duplicate_reference():
    engine, client = make_app()
    try:
        body = payment()
        first = post_owner(client, "/payments", body)
        assert first.status_code == 201, first.text
        assert first.json()["new_expires_at"] == (_today() + timedelta(days=30)).isoformat()
        assert first.json()["paid_at"].endswith("+00:00")
        assert first.json()["recorded_at"].endswith("+00:00")

        retry = post_owner(client, "/payments", body)
        assert retry.status_code == 201, retry.text
        assert retry.json()["id"] == first.json()["id"]
        assert retry.json()["new_expires_at"] == first.json()["new_expires_at"]
        altered = post_owner(client, "/payments", payment(amount_cents=1000))
        assert altered.status_code == 409

        renewal = post_owner(client, "/payments", payment(
            plan="semester", amount_cents=3900,
            transaction_reference="WX-002", idempotency_key="checkout-002",
        ))
        assert renewal.status_code == 201, renewal.text
        assert renewal.json()["prior_expires_at"] == first.json()["new_expires_at"]
        assert renewal.json()["new_expires_at"] == (_today() + timedelta(days=150)).isoformat()
        duplicate_ref = post_owner(client, "/payments", payment(idempotency_key="checkout-003"))
        assert duplicate_ref.status_code == 409

        with Session(engine) as db:
            assert db.query(PaymentTransaction).count() == 2
            assert db.get(User, 2).plan_expires_at == _today() + timedelta(days=150)
        listing = client.get("/api/owner/payments?user_id=2", headers={"X-Test-Owner": "1"})
        assert listing.status_code == 200
        assert listing.json()["total"] == 2
        assert len(listing.json()["items"]) == 2
        assert client.get("/api/owner/payments").status_code == 403
        assert post_owner(client, "/payments", payment(amount_cents=0)).status_code == 422
    finally:
        client.close()
        engine.dispose()


def test_payment_record_failure_rolls_back_entitlement():
    engine, client = make_app()
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TRIGGER reject_receipt BEFORE INSERT ON payment_transactions "
                "BEGIN SELECT RAISE(ABORT, 'receipt rejected'); END"
            )
        failed = post_owner(client, "/payments", payment())
        assert failed.status_code == 409, failed.text
        with Session(engine) as db:
            user = db.get(User, 2)
            assert user.plan in (None, "free")
            assert user.plan_expires_at is None
            assert db.query(PaymentTransaction).count() == 0
    finally:
        client.close()
        engine.dispose()


def test_receipts_require_external_reference_and_discount_reason():
    engine, client = make_app()
    try:
        missing_reference = payment()
        missing_reference.pop("transaction_reference")
        assert post_owner(client, "/payments", missing_reference).status_code == 422
        assert post_owner(client, "/payments", payment(transaction_reference="  ")).status_code == 422
        assert post_owner(client, "/payments", payment(amount_cents=1, note=None)).status_code == 400
        discounted = post_owner(client, "/payments", payment(amount_cents=900, note="小规模体验优惠"))
        assert discounted.status_code == 201, discounted.text
        no_refund_reference = refund(discounted.json()["id"])
        no_refund_reference.pop("transaction_reference")
        assert post_owner(client, "/refunds", no_refund_reference).status_code == 422
    finally:
        client.close()
        engine.dispose()


def test_exceptional_refund_is_bounded_idempotent_and_keeps_entitlement_until_correction():
    engine, client = make_app()
    try:
        receipt = post_owner(client, "/payments", payment()).json()
        original_expiry = receipt["new_expires_at"]
        body = refund(receipt["id"])
        first = post_owner(client, "/refunds", body)
        assert first.status_code == 201, first.text
        retry = post_owner(client, "/refunds", body)
        assert retry.status_code == 201
        assert retry.json()["id"] == first.json()["id"]
        assert post_owner(client, "/refunds", refund(receipt["id"], amount_cents=500)).status_code == 409
        second = post_owner(client, "/refunds", refund(
            receipt["id"], amount_cents=600,
            transaction_reference="RF-002", idempotency_key="refund-002",
        ))
        assert second.status_code == 201, second.text
        over = post_owner(client, "/refunds", refund(
            receipt["id"], amount_cents=100,
            transaction_reference="RF-003", idempotency_key="refund-003",
        ))
        assert over.status_code == 409
        before_payment = post_owner(client, "/refunds", refund(
            receipt["id"], transaction_reference="RF-004", idempotency_key="refund-004",
            refunded_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        ))
        assert before_payment.status_code == 400
        assert post_owner(client, "/refunds", refund(receipt["id"], reason=" ")).status_code == 422
        with Session(engine) as db:
            assert db.query(RefundTransaction).count() == 2
            assert db.get(User, 2).plan_expires_at.isoformat() == original_expiry
            with zipfile.ZipFile(io.BytesIO(build_backup_zip(db))) as archive:
                assert "refund_transactions.csv" in archive.namelist()
                assert "依法处理的售后退款" in archive.read("refund_transactions.csv").decode("utf-8")
        listing = client.get("/api/owner/refunds?payment_id=" + str(receipt["id"]), headers={"X-Test-Owner": "1"})
        assert listing.status_code == 200
        assert listing.json()["total"] == 2
        assert client.get("/api/owner/refunds").status_code == 403
    finally:
        client.close()
        engine.dispose()


def test_gifts_corrections_and_backup_are_separate_from_receipts():
    engine, client = make_app()
    try:
        assert post_owner(client, "/grants", {"user_id": 2, "kind": "gift", "plan": "monthly"}).status_code == 422
        gift = post_owner(client, "/grants", {
            "user_id": 2, "kind": "gift", "plan": "monthly", "reason": "首批体验赠送", "idempotency_key": "gift-001",
        })
        assert gift.status_code == 201, gift.text
        assert gift.json()["new_expires_at"] == (_today() + timedelta(days=30)).isoformat()
        retry = post_owner(client, "/grants", {
            "user_id": 2, "kind": "gift", "plan": "monthly", "reason": "首批体验赠送", "idempotency_key": "gift-001",
        })
        assert retry.status_code == 201
        assert retry.json()["id"] == gift.json()["id"]
        assert post_owner(client, "/grants", {
            "user_id": 2, "kind": "gift", "plan": "monthly", "reason": "其他赠送", "idempotency_key": "gift-001",
        }).status_code == 409
        correction = post_owner(client, "/grants", {
            "user_id": 2, "kind": "correction", "plan": "free", "reason": "用户请求更正",
        })
        assert correction.status_code == 201, correction.text
        assert correction.json()["new_expires_at"] is None
        assert client.patch("/api/owner/users/2", json={"plan": "monthly"}, headers={"X-Test-Owner": "1"}).status_code == 409
        with Session(engine) as db:
            assert db.query(GrantEvent).count() == 2
            assert db.query(PaymentTransaction).count() == 0
            with zipfile.ZipFile(io.BytesIO(build_backup_zip(db))) as archive:
                assert "payment_transactions.csv" in archive.namelist()
                assert "grant_events.csv" in archive.namelist()
                assert "首批体验赠送" in archive.read("grant_events.csv").decode("utf-8")
    finally:
        client.close()
        engine.dispose()


def test_existing_paid_invite_is_tracked_and_new_paid_invites_are_blocked():
    engine, client = make_app()
    try:
        generated = post_owner(client, "/invite-codes", {"plan": "monthly", "count": 1})
        assert generated.status_code == 400
        with Session(engine) as db:
            db.add(InviteCode(code="4826", plan="monthly", expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
            db.commit()
        signup = client.post("/api/auth/register", json={
            "phone": "13900000000", "name": "测试用户", "password": "testing123", "invite_code": "4826",
        })
        assert signup.status_code == 201, signup.text
        with Session(engine) as db:
            event = db.query(GrantEvent).filter(GrantEvent.kind == "legacy_invite").one()
            assert event.user_id == signup.json()["id"]
            assert event.new_expires_at == db.get(User, event.user_id).plan_expires_at
            assert db.query(PaymentTransaction).count() == 0
    finally:
        client.close()
        engine.dispose()
