"""Saved output must survive retries, remain private, and feed the writing ledger."""
import io
import json
import zipfile
from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from test_feedback_workflow import DAY, binding, ctx  # noqa: F401

from app import database, reader_client
from app.models import LongTermLedgerDay, User
from app.project_models import ReaderWritingDay, ReaderWritingState
from app.routers.long_term_details import target_progress
from app.user_export import build_user_export_zip


def writing_source(client, monkeypatch, words=150, revision=1):
    previous = client.reader_source.remote
    payload = {'authorized': True, 'writing_started_at': '2026-10-23T00:00:00+08:00',
        'days': [{'date': str(DAY), 'revision': revision, 'snapshot_kind': 'full_day', 'words': words,
                 'categories': {'note': words, 'knowledge': 0, 'review': 0, 'material': 0}}],
        'high_watermark': revision, 'next_cursor': None, 'checkpoint': f'writing-{revision}'}

    def remote(method, path, **kwargs):
        if path != '/writing-days':
            return previous(method, path, **kwargs)
        grant = client.reader_source.grants[kwargs['reading_token']]
        return {'schema_version': 1, 'timezone': 'Asia/Shanghai',
            'source_instance_id': client.reader_source.instance, 'source_account_id': client.reader_source.account,
            'receiver_account_id': grant['receiver_account_id'], **payload}

    monkeypatch.setattr(reader_client, 'remote', remote)
    return payload


def sync(client, linked):
    return client.post(f"/api/integrations/reader/bindings/{linked['binding_id']}/sync")


def stored_activity(row):
    from app.routers.long_term_details import Activity
    return {key: value for key, value in row.items() if key in Activity.model_fields}


def test_output_revision_reports_reconciliation_and_account_export(ctx, monkeypatch):
    client, sessions, _ = ctx
    linked = binding(client)
    payload = writing_source(client, monkeypatch)
    first = sync(client, linked)
    assert first.status_code == 200, first.text
    assert first.json()['writing_complete'] is True
    day = client.get(f'/api/long-term/details/day?day={DAY}').json()
    assert day['summary']['words'] == 150
    source = stored_activity(next(a for a in day['activities'] if a.get('reader_output_key')))
    manual = {**source, 'id': 'manual_output', 'reader_output_key': None, 'words': 150, 'seconds': 600,
        'reader_output_duplicate_of': source['reader_output_key']}
    saved = client.put(f'/api/long-term/details/day?day={DAY}', json={
        'revision': day['revision'], 'activities': [source, manual], 'day_confirmed': True})
    assert saved.status_code == 200, saved.text
    assert saved.json()['summary']['words'] == 150
    assert saved.json()['summary']['total_seconds']['writing'] == 600
    # Retry is a replacement, not an addition or a reason to invalidate confirmation.
    assert sync(client, linked).json()['changed_dates'] == []
    assert client.get(f'/api/long-term/details/day?day={DAY}').json()['day_confirmed'] is True
    payload['days'][0].update(words=200, revision=2)
    payload['days'][0]['categories']['note'] = 200
    payload.update(high_watermark=2, checkpoint='writing-2')
    assert sync(client, linked).json()['changed_dates'] == [str(DAY)]
    day = client.get(f'/api/long-term/details/day?day={DAY}').json()
    assert day['summary']['words'] == 200
    assert day['day_confirmed'] is False and 'writing' not in day['category_confirmed']
    for period in ('day', 'week', 'month', 'quarter', 'year'):
        response = client.get(f'/api/long-term/details/report?period={period}&anchor={DAY}')
        assert response.status_code == 200, response.text
        assert response.json()['words'] == 200
    assert target_progress({'category': 'writing', 'metric': 'words'}, [day]) == 200
    assert client.get(f'/api/long-term/details/day?day={DAY}', headers={'X-Test-User': '2'}).json()['summary']['words'] == 0
    with sessions() as db:
        assert db.query(ReaderWritingDay).count() == 1
        exported = build_user_export_zip(db, db.get(User, 1))
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            assert json.loads(archive.read('reader_writing_days.json'))[0]['words'] == 200
    # A stale client cannot change the source count, or remove the source activity.
    altered = stored_activity(day['activities'][0]); altered['words'] = 999
    response = client.put(f'/api/long-term/details/day?day={DAY}', json={'revision': day['revision'], 'activities': [altered]})
    assert response.status_code == 200, response.text
    assert response.json()['summary']['words'] == 200


def test_failed_page_does_not_advance_cursor_or_invalidate_reading(ctx, monkeypatch):
    client, sessions, _ = ctx
    linked = binding(client)
    payload = writing_source(client, monkeypatch)
    assert sync(client, linked).status_code == 200
    # Same revision, contradictory content is rejected with no progress changes.
    payload['days'][0].update(words=151)
    payload['days'][0]['categories']['note'] = 151
    response = sync(client, linked)
    assert response.status_code == 200 and response.json()['writing_complete'] is False
    with sessions() as db:
        assert db.query(ReaderWritingDay).one().words == 150
        state = db.get(ReaderWritingState, linked['binding_id'])
        assert state.cursor == 'writing-1' and state.status == 'retry'
    payload['days'] = []
    payload['authorized'] = False
    payload['checkpoint'] = None
    assert sync(client, linked).json()['writing_complete'] is True
    assert client.get('/api/integrations/reader/status').json()['items'][0]['writing_status'] == 'not_authorized'
    assert client.get(f'/api/long-term/details/day?day={DAY}').json()['summary']['words'] == 150
    payload['authorized'] = True
    payload['checkpoint'] = 'invalid-identity'
    # Revocation keeps the already-received daily output.
    assert client.delete(f"/api/integrations/reader/bindings/{linked['binding_id']}").status_code == 200
    assert sync(client, linked).status_code == 409
    assert client.get(f'/api/long-term/details/day?day={DAY}').json()['summary']['words'] == 150


def test_additive_upgrade_preserves_existing_ledger(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    database.Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE reader_writing_days'))
        conn.execute(text('DROP TABLE reader_writing_states'))
        conn.execute(text("INSERT INTO users(id,email,name,password_hash,capture_kind) VALUES(1,'synthetic@test','旧用户','x','moment')"))
        conn.execute(text("INSERT INTO long_term_ledger_days(user_id,record_date,revision,payload_json,updated_at) VALUES(1,'2026-10-23',3,:payload,'2026-10-23')"), {'payload': '{"activities":[],"kept":"原记录"}'})
    monkeypatch.setattr(database, 'engine', engine)
    database.ensure_schema(); database.ensure_schema()
    with Session(engine) as db:
        assert db.query(LongTermLedgerDay).one().revision == 3
        assert json.loads(db.query(LongTermLedgerDay).one().payload_json)['kept'] == '原记录'
        assert db.query(ReaderWritingDay).count() == 0
    engine.dispose()
