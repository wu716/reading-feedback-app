"""Portable, account-scoped business-data export for every plan."""
import io
import json
import zipfile

from sqlalchemy.orm import Session

from app import models, project_models


# Deliberate allowlist: adding a table to the application must not silently put
# credentials, other accounts, or internal administration data into this ZIP.
USER_TABLES = (
    models.MethodCard, models.MethodUse, models.MethodVisit, models.ProductFeedback,
    models.Ebook, models.EbookProgress, models.EbookNote,
    models.Action, models.PracticeLog, models.HabitProgram, models.HabitEvent,
    models.Subscription, models.PaymentTransaction, models.RefundTransaction, models.GrantEvent,
    models.DailyTodo, models.DailyTask, models.DailySchedule,
    models.FutureAction, models.Idea, models.TimeLogNode,
    models.LongTermDailyRecord, models.LongTermNodeCategory,
    models.LongTermLedgerDay, models.LongTermPreferences, models.ReadingEntry,
    models.SelfTalkPlaybackLog, models.SelfTalk, models.AIAdviceSession,
    models.SelfTalkReminderSetting, models.SelfTalkReminderLog, models.AiCallLog,
    project_models.Goal, project_models.Project, project_models.ProjectStage,
    project_models.ProjectTask, project_models.TaskDependency,
    project_models.TaskChecklistItem, project_models.WorkSession,
    project_models.ExecutionPlan, project_models.TimeActivityAssessment,
    project_models.ProcessTemplate,
    project_models.StartCondition, project_models.ExecutionConditionEvent,
    project_models.TaskPractice, project_models.PracticeEvent, project_models.PlanningCycle,
    project_models.StageCommitment, project_models.CommitmentAdjustment,
)


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def _rows(db: Session, model, user_id: int, *, query=None) -> list[dict]:
    query = query if query is not None else db.query(model).filter(model.user_id == user_id)
    columns = [column.name for column in model.__table__.columns]
    # Server-local storage paths are not portable account data.
    excluded = {"storage_path", "audio_path"}
    if model in (models.PaymentTransaction, models.RefundTransaction, models.GrantEvent):
        excluded |= {"actor_user_id", "idempotency_key", "note"}
    columns = [name for name in columns if name not in excluded]
    return [{name: getattr(row, name) for name in columns} for row in query.all()]


def build_user_export_zip(db: Session, user: models.User) -> bytes:
    """Export this account's stored business rows, including archived history."""
    user_id = user.id
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("profile.json", _json_bytes({
            "id": user.id, "name": user.name, "real_name": user.real_name,
            "email": user.email, "phone": user.phone,
            "plan": user.plan, "plan_expires_at": user.plan_expires_at,
            "created_at": user.created_at,
        }))
        for model in USER_TABLES:
            archive.writestr(
                f"{model.__tablename__}.json",
                _json_bytes(_rows(db, model, user_id)),
            )
        ebook_ids = db.query(models.Ebook.id).filter(models.Ebook.user_id == user_id)
        archive.writestr("ebook_chapters.json", _json_bytes(_rows(
            db, models.EbookChapter, user_id,
            query=db.query(models.EbookChapter).filter(models.EbookChapter.ebook_id.in_(ebook_ids)),
        )))
        session_ids = db.query(models.AIAdviceSession.id).filter(models.AIAdviceSession.user_id == user_id)
        archive.writestr("ai_advice_messages.json", _json_bytes(_rows(
            db, models.AIAdviceMessage, user_id,
            query=db.query(models.AIAdviceMessage).filter(models.AIAdviceMessage.session_id.in_(session_ids)),
        )))
        archive.writestr("README.txt", (
            "书然个人数据导出，含本账户业务表和已删除的历史行；JSON 数值以数据库原单位保存。\n"
            "不含密码、登录验证码、管理员资料或其他账户记录。\n"
            "原始 EPUB 和音频文件不在本包中；其正文、笔记、转写及元数据已导出。\n"
        ).encode("utf-8"))
    return output.getvalue()
