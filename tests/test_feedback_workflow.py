"""End-to-end contracts: dated delivery, reader identity, privacy and report revisions.

All business rows live in memory; evidence files use an isolated D: test directory.
"""
import io
import json
import shutil
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import project_models as pm, feedback_service as svc
from app.auth import get_current_active_user, get_current_user
from app.database import Base, get_db
from app.models import User, SelfTalkReminderSetting, SelfTalkReminderLog, LongTermLedgerDay
from app.routers import projects, long_term_details, project_feedback, reader_sync, self_talk_reminders
from app.self_talk.reminder_service import ReminderService
from fake_reader_source import ReaderSource
from app.reader_client import remote as reader_http_request

DAY = date(2026, 10, 23)


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as db:
        db.add_all([User(id=1, name="测试甲", email="a@example.test", password_hash="unused", plan="monthly", plan_expires_at=date(2099, 1, 1), created_at=datetime(2026, 1, 1)),
                    User(id=2, name="测试乙", email="b@example.test", password_hash="unused")]); db.commit()
    app = FastAPI()
    for router in (projects.router, long_term_details.router, project_feedback.router, reader_sync.router):
        app.include_router(router, prefix="/api")
    app.include_router(self_talk_reminders.router)
    def session():
        with factory() as db:
            yield db
    def identity(request: Request):
        with factory() as db:
            return db.get(User, int(request.headers.get("X-Test-User", "1")))
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_active_user] = identity
    app.dependency_overrides[get_current_user] = identity
    monkeypatch.setenv("READER_API_URL", "https://reader.example.test")
    monkeypatch.setenv("READER_CLIENT_ID", "shuran-test")
    monkeypatch.setenv("READER_CLIENT_SECRET", "synthetic-server-secret-at-least-32-characters")
    from app import reader_client
    source = ReaderSource()
    monkeypatch.setattr(reader_client, "remote", source.remote)
    files = Path("D:/UserData/ProjectArtifacts/reading-feedback-app") / ("feedback-test-" + uuid.uuid4().hex)
    files.mkdir(parents=True)
    monkeypatch.setenv("FEEDBACK_STORAGE_DIR", str(files))
    monkeypatch.setenv("TEMP", str(files)); monkeypatch.setenv("TMP", str(files))
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(files))
    monkeypatch.setattr(long_term_details, "beijing_today", lambda: DAY)
    with TestClient(app) as client:
        client.reader_source = source
        yield client, factory, files
    assert files.resolve().parent == Path("D:/UserData/ProjectArtifacts/reading-feedback-app").resolve()
    shutil.rmtree(files)
    engine.dispose()


def project(c, **kw):
    r = c.post("/api/projects", json={"title": "自学研究", "outcome": "形成可用的学习方法", **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def cycle(c, p, **kw):
    r = c.post(f"/api/projects/practice/projects/{p}/cycles", json={
        "start_date": str(DAY), "end_date": str(DAY + timedelta(days=10)), "horizon": "custom", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def node(c, p):
    cycle(c, p, feedback={"frequency": "dates", "dates": [str(DAY)], "deliverable": "一次研究报告或实践成果", "reminders": True})
    return c.get(f"/api/feedback/occurrences?start={DAY}&end={DAY}").json()["items"][0]


def binding(c):
    pair = c.post("/api/integrations/reader/pairing").json()
    path = f'/api/integrations/reader/pairings/{pair["pairing_id"]}'
    assert c.get(path).json()["source_confirmed"] is False
    c.reader_source.approve(pair["code"])
    preview = c.get(path).json()
    body = {"expected_source_instance_id": preview["source_instance_id"], "expected_source_account_id": preview["source_account_id"]}
    r = c.post(path + "/confirm", json=body)
    assert r.status_code == 200, r.text
    assert "reading_token" not in r.json() and "receiver_nonce" not in pair
    assert c.post(path + "/confirm", json=body).status_code == 409
    return r.json()


def snapshot(c, b, revision=1, seconds=1800, books=None):
    c.reader_source.highest = max(revision, c.reader_source.highest)
    c.reader_source.page = {"reading_detail_started_at": "2026-10-23T00:00:00+08:00", "high_watermark": c.reader_source.highest,
        "days": [{"date": str(DAY), "revision": revision, "snapshot_kind": "full_day", "active_seconds": seconds,
                  "books": books if books is not None else [{"source_book_id": "book-a", "title": "同名书", "active_seconds": seconds}]}],
        "historical_baseline": [{"source_book_id": "book-old", "title": "历史累计", "active_seconds": 500000}]}
    return c.post(f'/api/integrations/reader/bindings/{b["binding_id"]}/sync')


def test_project_and_plan_visible_task_composition_is_atomic_and_optional(ctx):
    c, factory, _ = ctx
    p = project(c, tasks=[{"title": "查找证据", "stage_title": "探索", "importance": "important", "difficulty": "difficult", "estimated_minutes": 30}])
    overview = c.get("/api/projects/overview").json()["projects"][0]
    t = overview["tasks"][0]
    assert t["practice"]["importance"] == "important"
    assert next(s for s in overview["stages"] if s["id"] == t["stage_id"])["title"] == "探索"
    plain = project(c)
    plan = cycle(c, plain)
    assert plan["plan"]["scope"] == "project" and plan["plan"]["tasks"] == []
    assert plan["expected_result"] == "形成可用的学习方法"
    plan2 = cycle(c, p, task_ids=[t["id"]], new_tasks=[{"title": "试写", "stage_id": t["stage_id"]}])
    assert len(plan2["plan"]["tasks"]) == 2
    before = len(c.get("/api/projects/overview").json()["projects"][1]["tasks"])
    invalid = c.post(f"/api/projects/practice/projects/{p}/cycles", json={"start_date": str(DAY), "end_date": str(DAY),
        "new_tasks": [{"title": "不能半保存", "stage_id": 9999}]})
    assert invalid.status_code == 400
    with factory() as db:
        assert not db.query(pm.ProjectTask).filter_by(title="不能半保存").first()
    assert c.post(f"/api/projects/practice/projects/{p}/cycles", headers={"X-Test-User": "2"}, json={"start_date": str(DAY), "end_date": str(DAY)}).status_code == 404


def test_calendar_materializes_real_dates_with_additions_and_skips(ctx):
    c, factory, _ = ctx
    p = project(c)
    plan = cycle(c, p, feedback={"frequency": "weekly", "weekdays": [0, 2, 4], "add_dates": ["2026-10-24"],
        "skip_dates": ["2026-10-26"], "deliverable": "图片与练习说明", "formats": ["image", "other"]})
    items = c.get("/api/feedback/occurrences?start=2026-10-23&end=2026-11-02").json()["items"]
    assert [n["due_date"] for n in items] == ["2026-10-23", "2026-10-24", "2026-10-28", "2026-10-30", "2026-11-02"]
    assert all(n["requirement"]["min_words"] is None for n in items)
    r = c.post(f"/api/projects/practice/projects/{p}/cycles", json={"start_date": str(DAY), "end_date": str(DAY),
        "feedback": {"frequency": "dates", "dates": ["2026-11-01"], "deliverable": "录音"}})
    assert r.status_code == 400
    with factory() as db:
        assert db.query(pm.PlanningCycle).count() == 1


def test_submission_versions_idempotency_private_evidence_review_and_skip(ctx):
    c, factory, files = ctx
    n = node(c, project(c))
    upload = c.post("/api/feedback/attachments", files={"file": ("../练习图.png", b"synthetic image", "image/png")})
    assert upload.status_code == 200, upload.text
    f = upload.json()
    assert f["filename"] == "练习图.png" and len(list(files.iterdir())) == 1
    assert c.get(f'/api/feedback/attachments/{f["id"]}', headers={"X-Test-User": "2"}).status_code == 404
    assert c.get(f'/api/feedback/attachments/{f["id"]}').content == b"synthetic image"
    path = f'/api/feedback/occurrences/{n["id"]}/submissions'
    body = {"client_id": "same-request-1", "links": ["https://example.test/report"], "attachment_ids": [f["id"]]}
    one = c.post(path, json=body); assert one.status_code == 200, one.text
    assert one.json()["latest"]["version"] == 1
    assert c.post(path, json=body).json()["latest"]["version"] == 1
    assert c.post(path, json={**body, "client_id": "new-request-2", "text": "补充成果"}).json()["latest"]["version"] == 2
    first_id = one.json()["latest"]["id"]
    assert c.post(f"/api/feedback/submissions/{first_id}/review", json={"status": "accepted", "note": "旧版"}).status_code == 409
    current = c.get(f'/api/feedback/occurrences/{n["id"]}').json()
    r = c.post(f'/api/feedback/submissions/{current["latest"]["id"]}/review', json={"status": "accepted", "note": "已逐项核对练习与说明"})
    assert r.json()["status"] == "accepted" and len(r.json()["versions"]) == 2
    assert c.get(f'/api/feedback/occurrences/{n["id"]}', headers={"X-Test-User": "2"}).status_code == 404
    assert c.post(path, json={"client_id": "invalid-link", "links": ["javascript:alert(1)"]}).status_code == 422
    with factory() as db:
        assert db.query(pm.FeedbackSubmission).count() == 2


def test_reader_pairing_revision_replacement_tombstone_and_manual_notes(ctx):
    c, factory, _ = ctx
    b = binding(c)
    first = snapshot(c, b); assert first.status_code == 200, first.text
    assert snapshot(c, b).json()["changed_dates"] == []
    assert snapshot(c, b, seconds=1900).status_code == 409
    day = c.get(f"/api/long-term/details/day?day={DAY}").json()
    a = day["activities"][0]
    assert day["summary"]["total_seconds"]["reading"] == 1800 and not day["day_confirmed"]
    source = {k: v for k, v in a.items() if k not in ("source_missing", "reader_source")}
    source.update(note="我的收获", primary_topic="education", seconds=86400, title="篡改源标题")
    manual = {"id": "paper-book", "category": "reading", "title": "纸书", "seconds": 600}
    saved = c.put(f"/api/long-term/details/day?day={DAY}", json={"revision": day["revision"], "activities": [source, manual]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["summary"]["total_seconds"]["reading"] == 2400
    assert snapshot(c, b, revision=2, seconds=2400).status_code == 200
    after = c.get(f"/api/long-term/details/day?day={DAY}").json()
    assert after["summary"]["total_seconds"]["reading"] == 3000
    assert next(x for x in after["activities"] if x.get("reader_book_key"))["note"] == "我的收获"
    assert snapshot(c, b, revision=1).json()["changed_dates"] == []
    assert snapshot(c, b, revision=3, seconds=0, books=[]).status_code == 200
    removed = c.get(f"/api/long-term/details/day?day={DAY}").json()
    assert removed["summary"]["total_seconds"]["reading"] == 600
    assert any(x.get("source_missing") and x["note"] == "我的收获" for x in removed["activities"])
    assert c.get('/api/integrations/reader/status', headers={"X-Test-User": "2"}).json()["items"] == []
    assert c.delete(f'/api/integrations/reader/bindings/{b["binding_id"]}').status_code == 200
    assert snapshot(c, b, revision=4).status_code == 409
    with factory() as db:
        assert db.query(pm.ReaderReadingDay).count() == 1


def test_same_title_different_books_keep_identity_and_baseline_out_of_charts(ctx):
    c, _, _ = ctx
    b = binding(c)
    books = [{"source_book_id": "a", "title": "同名书", "active_seconds": 900}, {"source_book_id": "b", "title": "同名书", "active_seconds": 900}]
    assert snapshot(c, b, books=books).status_code == 200
    r = c.get(f"/api/long-term/details/report?period=day&anchor={DAY}").json()
    assert len(r["books"]) == 2 and sum(b["seconds"] for b in r["books"]) == 1800
    assert c.get('/api/integrations/reader/status').json()["items"][0]["historical_baseline"][0]["active_seconds"] == 500000


def test_manual_reading_can_reference_same_source_without_double_counting(ctx):
    c, factory, _ = ctx
    b = binding(c); assert snapshot(c, b).status_code == 200
    day = c.get(f"/api/long-term/details/day?day={DAY}").json()
    source = {k: v for k, v in day["activities"][0].items() if k not in ("source_missing", "reader_source")}
    manual = {"id": "earlier-manual", "category": "reading", "title": "先前已补记的同一段", "seconds": 1800,
        "reader_duplicate_of": source["reader_book_key"], "note": "已核对为同一段"}
    r = c.put(f"/api/long-term/details/day?day={DAY}", json={"revision": 0, "activities": [source, manual]})
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["total_seconds"]["reading"] == 1800
    assert r.json()["summary"]["source_duplicate_count"] == 1
    assert len(r.json()["activities"]) == 2
    with factory() as db:
        assert db.query(pm.PracticeEvent).filter_by(event_type="reader_reconciliation").count() == 1
    manual["reader_duplicate_of"] = "reader_other_user_book"
    assert c.put(f"/api/long-term/details/day?day={DAY}", json={"revision": 1, "activities": [source, manual]}).status_code == 400


def test_late_supplement_does_not_rewrite_first_on_time_submission(ctx):
    c, factory, _ = ctx
    n = node(c, project(c))
    path = f'/api/feedback/occurrences/{n["id"]}/submissions'
    c.post(path, json={"client_id": "first-on-time", "note": "首次成果"})
    with factory() as db:
        row = db.query(pm.FeedbackSubmission).one()
        row.submitted_at = datetime(2026, 10, 23, 12, 0)  # 20:00 Beijing, before 21:00 deadline.
        db.commit()
    c.post(path, json={"client_id": "later-supplement", "note": "补充成果"})
    with factory() as db:
        row = db.query(pm.FeedbackSubmission).order_by(pm.FeedbackSubmission.version.desc()).first()
        row.submitted_at = datetime(2026, 10, 24, 12, 0); db.commit()
    current = c.get(f'/api/feedback/occurrences/{n["id"]}').json()
    assert current["late"] is False and current["latest"]["version"] == 2


def test_closed_report_generation_recovers_once_after_scheduler_wakes(ctx, monkeypatch):
    c, factory, _ = ctx
    project(c)
    with factory() as db:
        db.get(User, 1).created_at = datetime(2024, 1, 1); db.commit()
        svc.generate_closed_reports(db)
        first = db.query(pm.FeedbackReport).count()
        assert first == 5
        svc.generate_closed_reports(db)
        assert db.query(pm.FeedbackReport).count() == first
        assert db.query(pm.FeedbackDelivery).count() == 5


def test_reminders_are_idempotent_stop_on_submission_and_retry_email(ctx):
    c, factory, _ = ctx
    n = node(c, project(c))
    now = datetime(2026, 10, 23, 20, 30, tzinfo=svc.TZ)
    with factory() as db:
        svc.check_feedback_reminders(db, 1, now)
        svc.check_feedback_reminders(db, 1, now)
        assert db.query(pm.FeedbackDelivery).count() == 1
        with patch.object(ReminderService, "send_email_notification", return_value=False):
            svc.deliver_email_outbox(db, 1)
        out = db.query(pm.FeedbackDelivery).one()
        assert out.email_status == "retry" and out.attempts == 1
        out.next_attempt_at = None; db.commit()
        with patch.object(ReminderService, "send_email_notification", return_value=True):
            svc.deliver_email_outbox(db, 1)
        db.refresh(out); assert out.email_status == "sent" and out.attempts == 2
    assert c.post(f'/api/feedback/occurrences/{n["id"]}/submissions', json={"client_id": "submit-stops-reminder", "note": "练习已完成"}).status_code == 200
    with factory() as db:
        svc.check_feedback_reminders(db, 1, now + timedelta(days=1))
        assert db.query(pm.FeedbackDelivery).filter_by(occurrence_id=n["id"]).count() == 1
        assert db.query(SelfTalkReminderLog).filter_by(reminder_type="project_feedback").one().action_taken


def test_reports_have_project_progress_revisions_equal_comparison_and_gates(ctx):
    c, factory, _ = ctx
    p = project(c, tasks=[{"title": "实际工作"}])
    n = node(c, p)
    with factory() as db:
        task = db.query(pm.ProjectTask).filter_by(project_id=p).one()
        # Twenty minutes crosses Beijing midnight; only ten belong to DAY.
        db.add(pm.WorkSession(user_id=1, project_task_id=task.id, kind="work", source="manual",
            started_at=datetime(2026, 10, 22, 15, 50), ended_at=datetime(2026, 10, 22, 16, 10)))
        db.add(pm.WorkSession(user_id=1, project_task_id=task.id, kind="work", source="timer", started_at=datetime(2026, 10, 23, 1)))
        db.commit()
    first = c.get(f"/api/long-term/details/report?period=day&anchor={DAY}").json()
    assert first["projects"][0]["actual_seconds"] == 600
    assert first["total_seconds"]["work"] == 0  # References do not become duplicate ledger rows.
    repeat = c.get(f"/api/long-term/details/report?period=day&anchor={DAY}").json()
    assert repeat["snapshot"]["revision"] == first["snapshot"]["revision"]
    saved = c.put(f"/api/long-term/details/day?day={DAY}", json={"revision": 0, "day_confirmed": True,
        "activities": [{"id": "run", "category": "fitness", "title": "散步", "seconds": 1200}]})
    assert saved.status_code == 200, saved.text
    for period in ("day", "week", "month", "quarter", "year"):
        r = c.get(f"/api/long-term/details/report?period={period}&anchor={DAY}")
        assert r.status_code == 200, r.text
        payload = r.json()
        assert len(payload["evolution"]["history"]) == 6 and payload["effective_end"] == str(DAY)
        assert len(payload["evolution"]["current"]["total_seconds"]) == 8
    later = c.get(f"/api/long-term/details/report?period=day&anchor={DAY}").json()
    assert later["snapshot"]["revision"] > first["snapshot"]["revision"]
    assert c.get(f'/api/feedback/reports/{later["snapshot"]["id"]}', headers={"X-Test-User": "2"}).status_code == 404
    assert c.get(f"/api/long-term/details/report?period=month&anchor={DAY}", headers={"X-Test-User": "2"}).status_code == 403
    with factory() as db:
        assert db.query(SelfTalkReminderLog).filter_by(reminder_type="feedback_report").count() == 1


def test_additive_migration_is_repeatable_and_preserves_legacy_data(ctx, monkeypatch):
    c, factory, _ = ctx
    p = project(c)
    from app import database
    with factory() as db:
        engine = db.get_bind()
    monkeypatch.setattr(database, "engine", engine)
    database.ensure_schema(); database.ensure_schema()
    assert c.get('/api/projects/overview').json()["projects"][0]["id"] == p


def test_direction_zero_missing_and_late_sync_confirmation_are_distinct(ctx):
    c, _, _ = ctx
    r = c.put(f"/api/long-term/details/day?day={DAY}", json={"revision": 0, "category_confirmed": ["fitness"]})
    assert r.status_code == 200, r.text
    assert not r.json()["day_confirmed"]
    report = c.get(f"/api/long-term/details/report?period=day&anchor={DAY}").json()
    assert report["evolution"]["current"]["category_confirmed_days"]["fitness"] == 1
    assert report["evolution"]["current"]["category_confirmed_days"]["reading"] == 0
    assert c.put(f"/api/long-term/details/day?day={DAY}", json={"revision": 1, "day_confirmed": True}).status_code == 200
    b = binding(c)
    assert snapshot(c, b).status_code == 200
    changed = c.get(f"/api/long-term/details/day?day={DAY}").json()
    assert changed["revision"] == 3 and not changed["day_confirmed"]
    assert "reading" not in changed["category_confirmed"] and "fitness" in changed["category_confirmed"]
    assert c.put(f"/api/long-term/details/day?day={DAY}", json={"revision": 2, "day_confirmed": True}).status_code == 409


def test_backlog_retains_unsubmitted_old_nodes_and_hides_completed(ctx):
    c, factory, _ = ctx
    n = node(c, project(c))
    with factory() as db:
        row = db.get(pm.FeedbackOccurrence, n["id"]); row.due_date = DAY - timedelta(days=60); db.commit()
    r = c.get(f"/api/feedback/backlog?before={DAY}")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    c.post(f'/api/feedback/occurrences/{n["id"]}/submissions', json={"client_id": "old-node-submission", "note": "补交旧成果"})
    assert c.get(f"/api/feedback/backlog?before={DAY}").json()["total"] == 0
    assert c.get(f"/api/feedback/backlog?before={DAY}", headers={"X-Test-User": "2"}).json()["total"] == 0


@pytest.mark.parametrize("port,implicit", [(465, True), (587, False)])
def test_email_transport_uses_correct_tls_and_safe_return_link(ctx, monkeypatch, port, implicit):
    c, factory, _ = ctx
    from app.config import settings
    from app.self_talk import reminder_service
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(settings, "SMTP_PORT", port)
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(settings, "SMTP_FROM_EMAIL", "noreply@example.test")
    with patch.object(reminder_service.smtplib, "SMTP_SSL") as ssl, patch.object(reminder_service.smtplib, "SMTP") as smtp:
        with factory() as db:
            assert ReminderService.send_email_notification(db, 1, "反馈", '<script>unsafe</script>\nhttps://example.test/path?a=1&b=2')
        chosen = ssl if implicit else smtp
        chosen.assert_called_once_with("smtp.example.test", port, timeout=30)
        server = chosen.return_value.__enter__.return_value
        assert server.starttls.call_count == (0 if implicit else 1)
        message = server.send_message.call_args.args[0]
        html = message.get_payload()[0].get_payload(decode=True).decode()
        assert '&lt;script&gt;' in html and 'href="https://example.test/path?a=1&amp;b=2"' in html


def test_reader_credentials_are_encrypted_and_confirmation_is_account_scoped(ctx):
    c, factory, _ = ctx
    pair = c.post('/api/integrations/reader/pairing').json()
    path = f'/api/integrations/reader/pairings/{pair["pairing_id"]}'
    assert c.get(path, headers={"X-Test-User": "2"}).status_code == 404
    c.reader_source.approve(pair["code"])
    preview = c.get(path).json()
    wrong = {"expected_source_instance_id": preview["source_instance_id"], "expected_source_account_id": str(uuid.uuid4())}
    assert c.post(path+'/confirm', json=wrong).status_code == 409
    right = {**wrong, "expected_source_account_id": preview["source_account_id"]}
    response = c.post(path+'/confirm', json=right)
    assert response.status_code == 200, response.text
    with factory() as db:
        row = db.get(pm.ReaderBinding, response.json()["binding_id"])
        token = next(iter(c.reader_source.grants))
        assert token not in row.credential_cipher and token != row.token_hash
        assert db.get(pm.ReaderPairing, pair["pairing_id"]).nonce_cipher is None
        from app.user_export import build_user_export_zip
        import zipfile
        data = zipfile.ZipFile(io.BytesIO(build_user_export_zip(db, db.get(User, 1))))
        exported = json.loads(data.read('reader_bindings.json'))[0]
        assert 'credential_cipher' not in exported and 'token_hash' not in exported


def test_reader_failed_page_keeps_data_and_cursor_and_recovers_expired_cursor(ctx, monkeypatch):
    c, factory, _ = ctx
    b = binding(c); assert snapshot(c, b).status_code == 200
    path = f'/api/integrations/reader/bindings/{b["binding_id"]}/sync'
    with factory() as db:
        original = db.get(pm.ReaderBinding, b["binding_id"]).cursor
    c.reader_source.page['days'][0]['active_seconds'] = 9999
    assert c.post(path).status_code == 502
    with factory() as db:
        assert db.get(pm.ReaderBinding, b['binding_id']).cursor == original
        assert json.loads(db.query(pm.ReaderReadingDay).one().books_json)[0]['active_seconds'] == 1800
    from app import reader_client
    from fastapi import HTTPException
    def expired(*args, **kwargs):
        raise HTTPException(422, '来源游标失效')
    monkeypatch.setattr(reader_client, 'remote', expired)
    assert c.post(path).status_code == 422
    with factory() as db:
        assert db.get(pm.ReaderBinding, b['binding_id']).cursor is None
        assert db.query(pm.ReaderReadingDay).count() == 1
    monkeypatch.setattr(reader_client, 'remote', c.reader_source.remote)
    assert snapshot(c, b, revision=2, seconds=2700).status_code == 200


def test_source_revocation_stops_pull_without_deleting_received_history(ctx):
    c, factory, _ = ctx
    b = binding(c); assert snapshot(c, b).status_code == 200
    c.reader_source.grants.clear()
    assert c.post(f'/api/integrations/reader/bindings/{b["binding_id"]}/sync').status_code == 403
    with factory() as db:
        row = db.get(pm.ReaderBinding, b['binding_id'])
        assert not row.active and row.credential_cipher is None
        assert db.query(pm.ReaderReadingDay).count() == 1
    assert c.get(f'/api/long-term/details/day?day={DAY}').json()['summary']['total_seconds']['reading'] == 1800


def test_reader_document_deleted_keeps_history_and_long_aliases(ctx):
    c, _, _ = ctx
    b = binding(c)
    title = '私人书名' * 100
    book = {'source_book_id': 'book-a', 'title': title, 'active_seconds': 1800, 'document_deleted': True}
    r = snapshot(c, b, books=[book]); assert r.status_code == 200, r.text
    day = c.get(f'/api/long-term/details/day?day={DAY}').json()
    assert day['summary']['total_seconds']['reading'] == 1800
    assert len(day['activities'][0]['title']) == 200
    assert day['summary']['books'][0]['title'] == title


def test_oversize_evidence_is_rejected_without_an_orphan_file(ctx):
    c, _, files = ctx
    r = c.post('/api/feedback/attachments', files={'file': ('too-large.bin', b'x' * (25 * 1024 * 1024 + 1), 'application/octet-stream')})
    assert r.status_code == 413
    assert not list(files.iterdir())


def test_stored_report_keeps_current_subscription_boundary(ctx):
    c, factory, _ = ctx
    report = c.get(f'/api/long-term/details/report?period=day&anchor={DAY}').json()
    with factory() as db:
        user = db.get(User, 1); user.plan, user.plan_expires_at = 'free', None; db.commit()
    old = c.get(f'/api/feedback/reports/{report["snapshot"]["id"]}').json()['report']
    assert old['premium_locked'] and old['evolution'] is None
    assert old['activities'] == [] and old['comparison'] is None


def test_repeated_reviews_keep_all_reasons_in_node_history(ctx):
    c, _, _ = ctx
    n = node(c, project(c))
    submitted = c.post(f'/api/feedback/occurrences/{n["id"]}/submissions', json={'client_id': 'review-history', 'note': '练习成果'}).json()
    path = f'/api/feedback/submissions/{submitted["latest"]["id"]}/review'
    assert c.post(path, json={'status': 'accepted', 'note': '首轮检查通过'}).status_code == 200
    assert c.post(path, json={'status': 'needs_changes', 'note': '复核发现需要补充证据'}).status_code == 200
    history = c.get(f'/api/feedback/occurrences/{n["id"]}').json()['events']
    assert {e['detail']['note'] for e in history if e['action'] == 'delivery_review'} == {'首轮检查通过', '复核发现需要补充证据'}


def test_reader_http_transport_uses_dual_headers_and_never_follows_redirect(ctx):
    import app.reader_client as module
    with patch.object(module.requests, 'request') as http:
        response = http.return_value.__enter__.return_value
        response.status_code = 200
        response.iter_content.return_value = [b'{"days":[]}']
        assert reader_http_request('GET', '/reading-days', params={'from': str(DAY)}, reading_token='synthetic-grant')['days'] == []
        arguments = http.call_args.kwargs
        assert arguments['headers']['X-Shuran-Client'] == 'shuran-test'
        assert arguments['headers']['X-Reading-Grant'] == 'synthetic-grant'
        assert arguments['headers']['Authorization'].startswith('Bearer ')
        assert arguments['allow_redirects'] is False
        response.status_code = 302
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as error:
            reader_http_request('GET', '/reading-days', reading_token='synthetic-grant')
        assert error.value.status_code == 502
