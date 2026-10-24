# -*- coding: utf-8 -*-
"""每日逻辑备份：导出关键表为 CSV，保留 7 天；原文件仍需另备份上传卷。"""
import csv
import io
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.accounts import public_email
from app.database import SessionLocal
from app.models import (
    AuditLog,
    DailyTodo,
    DailyTask,
    DailySchedule,
    Idea,
    GrantEvent,
    InviteCode,
    PaymentTransaction,
    RefundTransaction,
    Subscription,
    TimeLogNode,
    LongTermDailyRecord,
    LongTermNodeCategory,
    LongTermLedgerDay,
    LongTermPreferences,
    User,
)
from app.project_models import (
    ExecutionPlan, Goal, Project, ProjectStage, ProjectTask, TaskDependency,
    TaskChecklistItem, WorkSession, TimeActivityAssessment, ProcessTemplate,
    StartCondition, ExecutionConditionEvent,
    TaskPractice, PracticeEvent, PlanningCycle, StageCommitment, StageCommitmentDraft, CommitmentAdjustment,
    FeedbackOccurrence, FeedbackSubmission, FeedbackAttachment, FeedbackReport, FeedbackDelivery,
    ReaderBinding, ReaderPairing, ReaderReadingDay, ReaderReceiverAccount,
)

logger = logging.getLogger(__name__)
BEIJING = ZoneInfo("Asia/Shanghai")
BACKUP_DIR = Path("backups")
KEEP_DAYS = 7


def _csv_bytes(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _cell(value) -> str:
    if value is None:
        return ""
    return str(value)


def _model_csv(db: Session, model) -> bytes:
    """Archive every row and column, including soft-deleted history."""
    columns = list(model.__table__.columns)
    return _csv_bytes([col.name for col in columns], [
        [_cell(getattr(row, col.name)) for col in columns] for row in db.query(model).all()
    ])


def build_backup_zip(db: Session) -> bytes:
    users = db.query(User).all()
    todos = db.query(DailyTodo).filter(DailyTodo.deleted_at.is_(None)).all()
    ideas = db.query(Idea).filter(Idea.deleted_at.is_(None)).all()
    time_logs = db.query(TimeLogNode).all()
    subs = db.query(Subscription).all()
    invites = db.query(InviteCode).all()
    audits = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(2000).all()

    files = {
        "users.csv": _csv_bytes(
            ["id", "name", "real_name", "phone", "email", "plan", "plan_expires_at", "is_active", "created_at", "deleted_at"],
            [
                [
                    u.id,
                    u.name,
                    u.real_name or "",
                    u.phone or "",
                    public_email(u.email) or "",
                    u.plan,
                    _cell(u.plan_expires_at),
                    u.is_active,
                    _cell(u.created_at),
                    _cell(u.deleted_at),
                ]
                for u in users
            ],
        ),
        "todos.csv": _csv_bytes(
            ["id", "user_id", "todo_date", "text", "completed"],
            [[d.id, d.user_id, _cell(d.todo_date), d.text, d.completed] for d in todos],
        ),
        "ideas.csv": _csv_bytes(
            ["id", "user_id", "text", "created_at", "deleted_at"],
            [[i.id, i.user_id, i.text, _cell(i.created_at), _cell(i.deleted_at)] for i in ideas],
        ),
        "time_log_nodes.csv": _csv_bytes(
            ["id", "user_id", "log_date", "logged_at", "label", "duration_seconds", "task_id", "deleted_at"],
            [
                [
                    n.id,
                    n.user_id,
                    _cell(n.log_date),
                    _cell(n.logged_at),
                    n.label or "",
                    n.duration_seconds or 0,
                    n.task_id,
                    _cell(n.deleted_at),
                ]
                for n in time_logs
            ],
        ),
        "subscriptions.csv": _csv_bytes(
            ["id", "user_id", "plan", "start_date", "end_date", "is_active"],
            [[s.id, s.user_id, s.plan, _cell(s.start_date), _cell(s.end_date), s.is_active] for s in subs],
        ),
        "invite_codes.csv": _csv_bytes(
            ["id", "code", "plan", "note", "used_at", "used_by_user_id"],
            [[i.id, i.code, i.plan, i.note or "", _cell(i.used_at), _cell(i.used_by_user_id)] for i in invites],
        ),
        "audit_logs.csv": _csv_bytes(
            ["id", "action", "actor_user_id", "target_user_id", "ip", "detail", "created_at"],
            [
                [x.id, x.action, _cell(x.actor_user_id), _cell(x.target_user_id), x.ip or "", x.detail or "", _cell(x.created_at)]
                for x in audits
            ],
        ),
    }

    for name, model in {
        "daily_tasks.csv": DailyTask,
        "daily_schedules.csv": DailySchedule,
        "daily_todos_history.csv": DailyTodo,
        "payment_transactions.csv": PaymentTransaction,
        "refund_transactions.csv": RefundTransaction,
        "grant_events.csv": GrantEvent,
        "goals.csv": Goal,
        "projects.csv": Project,
        "start_conditions.csv": StartCondition,
        "execution_condition_events.csv": ExecutionConditionEvent,
        "task_practices.csv": TaskPractice,
        "practice_events.csv": PracticeEvent,
        "planning_cycles.csv": PlanningCycle,
        "stage_commitments.csv": StageCommitment,
        "stage_commitment_drafts.csv": StageCommitmentDraft,
        "commitment_adjustments.csv": CommitmentAdjustment,
        "feedback_occurrences.csv": FeedbackOccurrence,
        "feedback_submissions.csv": FeedbackSubmission,
        "feedback_attachments.csv": FeedbackAttachment,
        "feedback_reports.csv": FeedbackReport,
        "feedback_deliveries.csv": FeedbackDelivery,
        "reader_bindings.csv": ReaderBinding,
        "reader_pairings.csv": ReaderPairing,
        "reader_receiver_accounts.csv": ReaderReceiverAccount,
        "reader_reading_days.csv": ReaderReadingDay,
        "project_stages.csv": ProjectStage,
        "project_tasks.csv": ProjectTask,
        "task_dependencies.csv": TaskDependency,
        "task_checklist_items.csv": TaskChecklistItem,
        "work_sessions.csv": WorkSession,
        "execution_plans.csv": ExecutionPlan,
        "time_activity_assessments.csv": TimeActivityAssessment,
        "process_templates.csv": ProcessTemplate,
        "long_term_daily_records.csv": LongTermDailyRecord,
        "long_term_node_categories.csv": LongTermNodeCategory,
        "long_term_ledger_days.csv": LongTermLedgerDay,
        "long_term_preferences.csv": LongTermPreferences,
    }.items():
        files[name] = _model_csv(db, model)

    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
        zf.writestr("README.txt", "书然 CSV 逻辑备份，不含密码哈希和上传原文件。完整恢复请另用 pg_dump -Fc，并备份 uploads_data 与 feedback_data 两个文件卷。\n")
    return raw.getvalue()


def latest_backup_path() -> Path | None:
    if not BACKUP_DIR.exists():
        return None
    zips = sorted(BACKUP_DIR.glob("shuran-backup-*.zip"), reverse=True)
    return zips[0] if zips else None


def run_daily_backup() -> Path | None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        payload = build_backup_zip(db)
    except Exception as exc:
        logger.error("备份失败: %s", exc)
        return None
    finally:
        db.close()

    stamp = datetime.now(BEIJING).strftime("%Y%m%d-%H%M")
    path = BACKUP_DIR / f"shuran-backup-{stamp}.zip"
    path.write_bytes(payload)
    cutoff = datetime.now(BEIJING) - timedelta(days=KEEP_DAYS)
    for old in BACKUP_DIR.glob("shuran-backup-*.zip"):
        try:
            if old.stat().st_mtime < cutoff.timestamp():
                old.unlink()
        except OSError as exc:
            logger.warning("删除过期备份失败 %s: %s", old, exc)
    logger.info("已写入备份 %s (%s bytes)", path, path.stat().st_size)
    return path
