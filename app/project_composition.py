"""Shared transactional task entry for project creation and planning."""
from typing import Literal
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.project_models import ProjectStage, ProjectTask, TaskPractice
from app import practice_service
from app.commitment_service import record_scope_addition


class TaskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=500)
    stage_id: int | None = None
    stage_title: str = Field(default="", max_length=200)
    familiarity: Literal["familiar", "unfamiliar"] | None = None
    difficulty: Literal["simple", "difficult"] | None = None
    importance: Literal["unimportant", "ordinary", "important"] | None = None
    estimated_minutes: int | None = Field(default=None, ge=0, le=100000)
    acceptance_criteria: str = Field(default="", max_length=4000)


def add_drafts(db, user_id, project, drafts, initial=False):
    if drafts and project.execution_state in ("delivered", "accepted"):
        raise HTTPException(409, "项目已交付，请先说明原因并重新开始项目")
    stages = db.query(ProjectStage).filter_by(user_id=user_id, project_id=project.id).all()
    rows = []
    for draft in drafts:
        stage = None
        if draft.stage_id is not None:
            stage = next((s for s in stages if s.id == draft.stage_id and s.state != "closed"), None)
            if not stage:
                raise HTTPException(400, "请选择此项目尚未结束的阶段")
        elif draft.stage_title:
            stage = next((s for s in stages if s.title == draft.stage_title and s.state != "closed"), None)
            if stage is None and initial:
                stage = next((s for s in stages if s.title in ("当前阶段", "下一阶段") and
                    not db.query(ProjectTask.id).filter_by(stage_id=s.id).first()), None)
                if stage:
                    stage.title = draft.stage_title
            if stage is None:
                stage = ProjectStage(user_id=user_id, project_id=project.id, title=draft.stage_title,
                    position=max((s.position for s in stages), default=-1) + 1, state="next")
                db.add(stage); db.flush(); stages.append(stage)
        row = ProjectTask(user_id=user_id, project_id=project.id, stage_id=stage.id if stage else None,
            title=draft.title, familiarity=draft.familiarity, estimated_minutes=draft.estimated_minutes,
            original_estimate_minutes=draft.estimated_minutes, acceptance_criteria=draft.acceptance_criteria)
        db.add(row); db.flush()
        practice_service.note_estimate(db, user_id, "task", row, draft.estimated_minutes, created=True)
        practice = db.query(TaskPractice).filter_by(user_id=user_id, owner_kind="task", owner_id=row.id).first()
        if practice is None:
            practice = TaskPractice(user_id=user_id, owner_kind="task", owner_id=row.id)
            db.add(practice)
        practice.difficulty, practice.importance = draft.difficulty, draft.importance
        practice.initial_importance = draft.importance
        if draft.importance is not None:
            practice.initial_marked_at = datetime.utcnow()
        practice.goal_snapshot = practice_service.goal_text(db, row)
        practice_service.event(db, user_id, "task", row.id, "attributes", {
            "title": row.title, "difficulty": draft.difficulty, "importance": draft.importance,
            "goal": practice.goal_snapshot, "source": "project_creation" if initial else "planning"})
        record_scope_addition(db, user_id, row)
        rows.append(row)
    return rows
