"""Exercise the release flow through HTTP, including auth and real database writes."""
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.anonymization import anonymize_user_data_on_deletion
from app.auth import issue_user_token
from app.backup import build_backup_zip
from app.database import Base, get_db
from app.models import Action, Ebook, EbookChapter, EbookNote, MethodCard, MethodUse, MethodVisit, ProductFeedback, User
from app.rate_limit import _hits
from app.routers.methods import router


@pytest.fixture
def release(tmp_path):
    _hits.clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'methods.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        users = [User(email=f"{name}@example.test", name=name, password_hash="not-used") for name in ("owner", "reader", "other")]
        db.add_all(users)
        db.commit()
        tokens = {user.name: {"Authorization": "Bearer " + issue_user_token(user)} for user in users}
        user_ids = {user.name: user.id for user in users}
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def database():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with patch("app.plans.is_owner_user", side_effect=lambda user: user.name == "owner"):
        with TestClient(app) as client:
            yield client, engine, tokens, user_ids
    engine.dispose()
    _hits.clear()


def card(client, headers, **overrides):
    body = {"situation": "坐到图书馆，打开书后开始刷手机", "first_step": "把手机放进包里，只读第一段", **overrides}
    response = client.post("/api/methods", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def begin(client, headers, card_id, key=None):
    response = client.post(f"/api/methods/{card_id}/uses", headers=headers, json={"client_key": str(key or uuid4())})
    assert response.status_code == 201, response.text
    return response.json()


def feedback(client, headers, use_id, outcome, **other):
    response = client.put(f"/api/methods/uses/{use_id}", headers=headers, json={"outcome": outcome, **other})
    assert response.status_code == 200, response.text
    return response.json()


def test_two_required_fields_and_retry_do_not_create_duplicate_cards(release):
    client, engine, headers, _ = release
    key = str(uuid4())
    first = card(client, headers["reader"], client_key=key)
    repeated = card(client, headers["reader"], client_key=key)
    assert first["id"] == repeated["id"]
    assert first["title"] == first["first_step"]
    for field in ("situation", "first_step"):
        invalid = {"situation": "具体情境", "first_step": "第一步", field: "   "}
        assert client.post("/api/methods", headers=headers["reader"], json=invalid).status_code == 422
    with Session(engine) as db:
        assert db.query(MethodCard).count() == 1
        assert db.query(Action).count() == 0


def test_private_cards_and_trials_are_isolated_by_account(release):
    client, _, headers, _ = release
    own = card(client, headers["reader"])
    other = card(client, headers["other"], first_step="另一个人的私有方法")
    items = client.get("/api/methods", headers=headers["reader"]).json()["items"]
    assert [item["id"] for item in items] == [own["id"]]
    for path, operation in [(f"/api/methods/{other['id']}", "delete"), (f"/api/methods/{other['id']}/uses", "post")]:
        result = getattr(client, operation)(path, headers=headers["reader"], **({"json": {}} if operation == "post" else {}))
        assert result.status_code == 404
    other_use = begin(client, headers["other"], other["id"])
    assert client.put(f"/api/methods/uses/{other_use['id']}", headers=headers["reader"], json={"outcome": "helpful"}).status_code == 404
    assert client.get("/api/methods").status_code in (401, 403)
    assert client.post("/api/methods", json={"situation": "情境", "first_step": "动作"}).status_code in (401, 403)


def test_feedback_is_repeatable_not_a_daily_checkin_and_keeps_snapshots(release):
    client, _, headers, _ = release
    owned = card(client, headers["reader"])
    key = uuid4()
    use = begin(client, headers["reader"], owned["id"], key)
    assert begin(client, headers["reader"], owned["id"], key)["id"] == use["id"]
    assert begin(client, headers["reader"], owned["id"])["id"] == use["id"]
    initial = feedback(client, headers["reader"], use["id"], "not_helpful", barrier="too_hard")
    corrected = feedback(client, headers["reader"], use["id"], "helpful", barrier="too_hard")
    assert corrected["barrier"] is None
    assert corrected["finished_at"] == initial["finished_at"]
    changed = {"situation": owned["situation"], "first_step": "只打开一页", "title": "缩小第一步"}
    assert client.put(f"/api/methods/{owned['id']}", headers=headers["reader"], json=changed).status_code == 200
    second = begin(client, headers["reader"], owned["id"])
    assert second["id"] != use["id"]
    assert second["first_step"] == "只打开一页"
    feedback(client, headers["reader"], second["id"], "not_used", barrier="forgot")
    saved = client.get("/api/methods", headers=headers["reader"]).json()["items"][0]
    assert saved["tried_count"] == 1
    assert saved["helpful_count"] == 1
    previous = next(item for item in saved["recent_uses"] if item["id"] == use["id"])
    assert previous["first_step"] == owned["first_step"]


def test_paused_and_removed_cards_cannot_start_new_trials(release):
    client, _, headers, _ = release
    owned = card(client, headers["reader"])
    pending = begin(client, headers["reader"], owned["id"])
    values = {"situation": owned["situation"], "first_step": owned["first_step"], "state": "paused"}
    assert client.put(f"/api/methods/{owned['id']}", headers=headers["reader"], json=values).status_code == 200
    assert client.post(f"/api/methods/{owned['id']}/uses", headers=headers["reader"], json={}).status_code == 409
    assert client.get("/api/methods", headers=headers["reader"]).json()["items"] == []
    assert len(client.get("/api/methods?state=paused", headers=headers["reader"]).json()["items"]) == 1
    feedback(client, headers["reader"], pending["id"], "not_used")
    assert client.delete(f"/api/methods/{owned['id']}", headers=headers["reader"]).status_code == 204
    assert client.get("/api/methods?state=all", headers=headers["reader"]).json()["items"] == []
    assert client.put(f"/api/methods/uses/{pending['id']}", headers=headers["reader"], json={"outcome": "helpful"}).status_code == 404


def test_two_tabs_starting_together_do_not_duplicate_a_pending_attempt(release):
    client, engine, headers, _ = release
    owned = card(client, headers["reader"])
    with ThreadPoolExecutor(max_workers=2) as executor:
        requests = [executor.submit(begin, client, headers["reader"], owned["id"]) for _ in range(2)]
        ids = [request.result()["id"] for request in requests]
    assert ids[0] == ids[1]
    with Session(engine) as db:
        assert db.query(MethodUse).count() == 1


def test_source_import_uses_own_data_without_modifying_old_actions(release):
    client, engine, headers, user_ids = release
    with Session(engine) as db:
        for name in ("reader", "other"):
            db.add(Action(user_id=user_ids[name], book_title=name + "的书", source_excerpt="原文", action_text=name + "的旧行动"))
        book = Ebook(user_id=user_ids["other"], title="私有书籍", original_filename="test.epub", storage_path="unused", file_size=1)
        db.add(book); db.flush()
        chapter = EbookChapter(ebook_id=book.id, chapter_index=0, title="章节", href="1.xhtml", text_content="正文")
        db.add(chapter); db.flush()
        note = EbookNote(user_id=user_ids["other"], ebook_id=book.id, chapter_id=chapter.id, selected_text="原文", note_text="方法")
        db.add(note); db.commit(); note_id = note.id
    sources = client.get("/api/methods/sources", headers=headers["reader"]).json()["items"]
    assert len(sources) == 1 and sources[0]["source_title"] == "reader的书"
    blocked = client.post("/api/methods", headers=headers["reader"], json={"situation": "情境", "first_step": "动作", "source_note_id": note_id})
    assert blocked.status_code == 404
    card(client, headers["reader"], source_title=sources[0]["source_title"], first_step=sources[0]["first_step"])
    with Session(engine) as db:
        assert db.query(Action).count() == 2


def test_search_matches_case_and_literal_wildcards(release):
    client, _, headers, _ = release
    owned = card(client, headers["reader"], source_title="Read 100% Better")
    card(client, headers["reader"], source_title="Read 1000 Better")
    data = client.get("/api/methods?search=read%20100%25", headers=headers["reader"]).json()
    assert data["total"] == 1 and data["items"][0]["id"] == owned["id"]


def test_market_counts_actual_feedback_separately_from_demo_and_start_clicks(release):
    client, engine, headers, _ = release
    session = str(uuid4())
    for name in ("opened", "demo_saved", "demo_started", "demo_feedback"):
        body = {"session_key": session, "event_name": name}
        assert client.post("/api/methods/visits", json=body).status_code == 201
        assert client.post("/api/methods/visits", json=body).json()["recorded"] is False
    assert client.post("/api/methods/product-feedback", json={"session_key": session, "message": "保存后我找不到入口"}).status_code == 201
    owned = card(client, headers["reader"], source_excerpt="绝不能出现在市场页面的私人摘录")
    first = begin(client, headers["reader"], owned["id"])
    before = client.get("/api/methods/market", headers=headers["owner"]).json()
    assert before["visit_sessions"] == 1 and before["started_users"] == 1
    assert before["tried_users"] == 0 and before["helpful_feedback"] == 0
    feedback(client, headers["reader"], first["id"], "helpful")
    second = begin(client, headers["reader"], owned["id"])
    feedback(client, headers["reader"], second["id"], "not_helpful")
    with Session(engine) as db:
        row = db.get(MethodUse, first["id"])
        row.started_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    after_response = client.get("/api/methods/market", headers=headers["owner"])
    after = after_response.json()
    assert after["returning_users"] == 1 and after["helpful_feedback"] == 1 and after["not_helpful_feedback"] == 1
    assert after["demo_sessions"]["demo_feedback"] == 1
    assert after["feedback"][0]["message"] == "保存后我找不到入口"
    assert "私人摘录" not in after_response.text
    assert client.get("/api/methods/market", headers=headers["reader"]).status_code == 403
    assert client.get("/api/methods/market").status_code in (401, 403)


def test_invalid_public_feedback_and_token_are_rejected(release):
    client, _, _, _ = release
    assert client.post("/api/methods/product-feedback", json={"session_key": str(uuid4()), "message": "   "}).status_code == 422
    assert client.post("/api/methods/visits", json={"session_key": "not-a-uuid"}).status_code == 422
    assert client.post("/api/methods/visits", json={"session_key": str(uuid4()), "event_name": "invented"}).status_code == 422
    assert client.post("/api/methods/product-feedback", headers={"Authorization": "Bearer invalid"}, json={"session_key": str(uuid4()), "message": "测试意见内容"}).status_code == 401


def test_new_data_is_backed_up_and_private_snapshots_removed_on_account_deletion(release):
    client, engine, headers, user_ids = release
    owned = card(client, headers["reader"])
    use = begin(client, headers["reader"], owned["id"])
    feedback(client, headers["reader"], use["id"], "helpful")
    session = str(uuid4())
    client.post("/api/methods/visits", headers=headers["reader"], json={"session_key": session})
    client.post("/api/methods/product-feedback", headers=headers["reader"], json={"session_key": session, "message": "我的具体意见"})
    with Session(engine) as db:
        archive = zipfile.ZipFile(io.BytesIO(build_backup_zip(db)))
        assert {"method_cards.csv", "method_uses.csv", "product_feedback.csv"} <= set(archive.namelist())
        assert owned["first_step"] in archive.read("method_uses.csv").decode("utf-8-sig")
        anonymize_user_data_on_deletion(db, user_ids["reader"])
        db.commit()
        assert db.query(MethodCard).count() == 0 and db.query(MethodUse).count() == 0
        assert db.query(ProductFeedback).count() == 0
        assert db.query(MethodVisit).first().user_id is None
