"""Authenticated foreground-active time pulses from the shared web app."""
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_active_user
from app.database import get_db
from app.models import User
from app.usage_time import record_active_pulse

router = APIRouter(prefix="/usage", tags=["使用时长"])


class UsagePulseIn(BaseModel):
    reset_baseline: bool = False


@router.post("/pulse", status_code=204)
def pulse_usage_time(
    payload: UsagePulseIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    record_active_pulse(db, user.id, reset_baseline=bool(payload and payload.reset_baseline))
    db.commit()
    return Response(status_code=204)
