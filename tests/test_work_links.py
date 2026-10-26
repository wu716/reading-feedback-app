"""Work linkage invariants: source ownership, reconciliation, cross-day accounting."""
from datetime import date, datetime, timedelta, timezone
import json
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import User, TimeLogNode, LongTermLedgerDay
from app.project_models import WorkSession, WorkLinkSetting
from app.routers import long_term_details as ledger
from app.routers import work_links as links
from app.work_link_service import sources
from app.execution_service import settle_expired

DAY = date(2026, 10, 20)


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([User(id=1,name='A',email='a@test.local',password_hash='x'), User(id=2,name='B',email='b@test.local',password_hash='x')])
        db.commit()
        yield db
    engine.dispose()


def session(db, start=None, end=None, **kw):
    start = start or datetime(2026,10,20,1)
    row = WorkSession(user_id=1,kind='work',source='manual',label='方案',started_at=start,
                      ended_at=end or start+timedelta(minutes=30), **kw)
    db.add(row); db.commit()
    return row


def read(db, day=DAY):
    return ledger.read_range(db,1,day,day)[0]


def save(db, data):
    fields = {'revision','activities','expenses','expense_confirmed','day_confirmed','category_confirmed','attention_items','attention_confirmed'}
    value = {k:v for k,v in data.items() if k in fields}
    value['activities']=[{k:v for k,v in a.items() if k in ledger.Activity.model_fields} for a in value['activities']]
    return ledger.save_day(ledger.LedgerInput(**value),day=DAY,user=db.get(User,1),db=db)


def test_cross_midnight_breaks_and_idempotent_projection(db):
    row=session(db,datetime(2026,10,20,15,50),datetime(2026,10,20,16,10))
    rest=WorkSession(user_id=1,kind='break',source='manual',started_at=row.ended_at,ended_at=row.ended_at+timedelta(minutes=5))
    db.add(rest);db.commit()
    days=ledger.read_range(db,1,DAY,DAY+timedelta(days=1))
    assert [ledger.aggregate([d])['total_seconds']['work'] for d in days]==[600,600]
    assert len(read(db)['activities'])==1
    saved=save(db,read(db))
    assert len(saved['activities'])==1
    assert read(db)['activities'][0]['work_session_id']==row.id


def test_override_survives_source_changes_and_restore_exclusion_progress(db):
    row=session(db)
    data=read(db); a=data['activities'][0]
    a.update(work_override_seconds=1500,work_basis_seconds=1800,work_title_override=True,title='改后的说明')
    save(db,data)
    row.ended_at+=timedelta(minutes=10);db.commit()
    data=read(db);a=data['activities'][0]
    assert a['seconds']==1500 and a['source_changed'] and a['title']=='改后的说明'
    a['work_excluded']=True
    save(db,data)
    data=read(db)
    assert ledger.aggregate([data])['total_seconds']['work']==0
    assert ledger.target_progress({'category':'work','metric':'seconds'},[data])==0
    a=data['activities'][0];a.update(work_excluded=False,work_override_seconds=None,work_title_override=False)
    restored=save(db,data)
    assert restored['summary']['total_seconds']['work']==2400
    assert restored['activities'][0]['title']=='方案'


def test_history_requires_import_and_user_ownership(db):
    row=session(db)
    db.get(WorkLinkSetting,1).first_session_id=row.id+1;db.commit()
    assert read(db)['activities']==[]
    with pytest.raises(HTTPException) as err:
        links.import_session(row.id,user=db.get(User,2),db=db)
    assert err.value.status_code==404
    links.import_session(row.id,user=db.get(User,1),db=db)
    assert len(read(db)['activities'])==1


def test_confirm_moment_no_task_retries_and_overlap(db):
    node=TimeLogNode(user_id=1,log_date=DAY,logged_at=datetime(2026,10,20,10),label='资料',duration_seconds=3600)
    db.add(node);db.commit()
    body=links.ConfirmInput(node_id=node.id,started_at='2026-10-20T10:00:00+08:00',ended_at='2026-10-20T10:40:00+08:00',category='writing')
    result=links.confirm_moment(body,user=db.get(User,1),db=db)
    assert links.confirm_moment(body,user=db.get(User,1),db=db)==result
    assert db.query(WorkSession).count()==1
    data=read(db)
    assert ledger.aggregate([data])['total_seconds']['writing']==2400
    node2=TimeLogNode(user_id=1,log_date=DAY,logged_at=node.logged_at,label='重复',duration_seconds=0)
    db.add(node2);db.commit()
    with pytest.raises(HTTPException) as err:
        links.confirm_moment(body.model_copy(update={'node_id':node2.id}),user=db.get(User,1),db=db)
    assert err.value.status_code==409


def test_duplicate_manual_record_and_forged_source(db):
    row=session(db)
    data=read(db)
    data['activities'].append(ledger.Activity(id='manual',category='work',title='补录过',seconds=1800,work_duplicate_of=row.id).model_dump())
    result=save(db,data)
    assert result['summary']['total_seconds']['work']==1800
    data=read(db);data['activities'][0]['work_session_id']=999;data['activities'][0]['id']='work_999'
    with pytest.raises(HTTPException):save(db,data)


def test_running_source_and_expired_deadline(db):
    row=WorkSession(user_id=1,kind='work',source='timer',label='进行中',started_at=datetime.utcnow()-timedelta(minutes=1),planned_minutes=20)
    db.add(row);db.commit()
    day=(datetime.utcnow()+timedelta(hours=8)).date()
    incoming=sources(db,1,day,day)[day]
    assert incoming[0]['work_source']['running'] and incoming[0]['seconds']==0
    assert ledger.read_range(db,1,day,day)[0]['activities']==[]
    row.started_at=datetime.utcnow()-timedelta(minutes=30);db.commit()
    data=ledger.read_range(db,1,day,day)[0]
    assert ledger.aggregate([data])['total_seconds']['work']==1200
    assert db.query(WorkSession).filter_by(kind='break').count()==1


def test_no_expired_timer_does_not_lock_user(db, monkeypatch):
    from sqlalchemy.orm import Query

    def unexpected_lock(*args, **kwargs):
        pytest.fail('a normal read must not lock the user row')

    monkeypatch.setattr(Query, 'with_for_update', unexpected_lock)
    settle_expired(db, 1)
    db.add(WorkSession(user_id=1,kind='work',source='timer',label='进行中',
                       started_at=datetime.utcnow(),planned_minutes=20))
    db.commit()
    settle_expired(db, 1)


def test_metadata_export_backup_and_repeatable_schema(db, monkeypatch):
    import io, zipfile
    from app import database
    from app.backup import build_backup_zip
    from app.user_export import build_user_export_zip
    row=session(db)
    links.update_note(row.id, links.NoteInput(note='保留感受'),user=db.get(User,1),db=db)
    monkeypatch.setattr(database,'engine',db.get_bind())
    database.ensure_schema();database.ensure_schema()
    export=zipfile.ZipFile(io.BytesIO(build_user_export_zip(db,db.get(User,1))))
    assert any('work_moment_links' in name for name in export.namelist())
    backup=zipfile.ZipFile(io.BytesIO(build_backup_zip(db)))
    assert 'work_moment_links.csv' in backup.namelist()
    assert '保留感受' in backup.read('work_moment_links.csv').decode('utf-8-sig')


def test_correct_source_keeps_daily_override_and_moves_slices(db):
    row=session(db)
    data=read(db);data['activities'][0].update(work_override_seconds=1200,work_basis_seconds=1800)
    save(db,data)
    links.correct_interval(row.id,links.IntervalInput(started_at='2026-10-20T09:00:00+08:00',
        ended_at='2026-10-20T09:40:00+08:00',correction_note='更正'),user=db.get(User,1),db=db)
    assert read(db)['activities'][0]['seconds']==1200
    assert read(db)['activities'][0]['source_changed']
    links.correct_interval(row.id,links.IntervalInput(started_at='2026-10-21T09:00:00+08:00',
        ended_at='2026-10-21T09:40:00+08:00',correction_note='移到实际日期'),user=db.get(User,1),db=db)
    assert ledger.aggregate([read(db)])['total_seconds']['work']==0
    assert ledger.aggregate([read(db,DAY+timedelta(days=1))])['total_seconds']['work']==2400


def test_manual_moment_deletion_preserves_confirmed_work_and_legacy_reads(db):
    from app.routers.time_log import day_payload
    from app.routers.long_term import daily_payload, reject_legacy_write
    row=session(db)
    node=TimeLogNode(user_id=1,log_date=DAY,logged_at=row.started_at+timedelta(hours=8),label='工作完成',duration_seconds=3600)
    db.add(node);db.commit()
    links.confirm_moment(links.ConfirmInput(node_id=node.id,session_id=row.id),user=db.get(User,1),db=db)
    assert day_payload(db,db.get(User,1),DAY).total_seconds==0
    node.deleted_at=datetime.utcnow();db.commit()
    assert daily_payload(db,1,DAY)['total_seconds']['work']==1800
    assert db.get(WorkSession,row.id) is not None
    with pytest.raises(HTTPException):reject_legacy_write(db,1,DAY)
