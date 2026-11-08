"""Server-backed drafts for long-form editors; never treated as submitted business data."""
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import ContentEditorDraft, User

router = APIRouter(prefix="/api/editor-drafts", tags=["内容草稿"])
KEY = re.compile(r"^(task-new:\d{4}-\d{2}-\d{2}|task:\d+|condition:(daily|task|project):\d+|(feedback|rehearsal):(daily|task):\d+)$")


class DraftInput(BaseModel):
    content: dict = Field(default_factory=dict)


def check_key(key: str, user: User, db: Session) -> None:
    if not KEY.fullmatch(key):
        raise HTTPException(400, "草稿类型无效")
    parts = key.split(":")
    if parts[0] == "task-new":
        try:
            date.fromisoformat(parts[1])
        except ValueError:
            raise HTTPException(400, "日期无效") from None
    elif parts[0] == "task":
        from app.routers.schedule import get_task_or_404
        get_task_or_404(db, user.id, int(parts[1]))
    elif parts[0] == "condition":
        from app.start_conditions import resolve_owner
        resolve_owner(db, user.id, parts[1], int(parts[2]))
    else:
        from app.routers.practice import task_owner
        task_owner(db, user.id, parts[1], int(parts[2]))


@router.get("/{key}")
def get_draft(key: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    check_key(key, user, db)
    row = db.query(ContentEditorDraft).filter_by(user_id=user.id, draft_key=key).first()
    return {"content": json.loads(row.content_json) if row else {}, "updated_at": row.updated_at if row else None}


@router.put("/{key}")
def save_draft(key: str, body: DraftInput, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    check_key(key, user, db)
    serialized = json.dumps(body.content, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > 262144:
        raise HTTPException(400, "草稿内容过长")
    row = db.query(ContentEditorDraft).filter_by(user_id=user.id, draft_key=key).first()
    if row is None:
        row = ContentEditorDraft(user_id=user.id, draft_key=key)
        db.add(row)
    row.content_json = serialized
    db.commit()
    return {"saved": True}


@router.delete("/{key}")
def delete_draft(key: str, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    check_key(key, user, db)
    db.query(ContentEditorDraft).filter_by(user_id=user.id, draft_key=key).delete()
    db.commit()
    return {"deleted": True}
