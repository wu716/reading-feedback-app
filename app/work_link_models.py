"""Additive linkage metadata. Original sessions and moment text remain intact."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text, event, func, select
from app.database import Base


class WorkLinkSetting(Base):
    __tablename__ = "work_link_settings"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    first_session_id = Column(Integer, nullable=False)
    enabled_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class WorkMomentLink(Base):
    __tablename__ = "work_moment_links"
    session_id = Column(Integer, ForeignKey("work_sessions.id", ondelete="RESTRICT"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    note = Column(Text, nullable=False, default="")
    imported = Column(Boolean, nullable=False, default=False)


def register_session_activation(session_model):
    @event.listens_for(session_model, "before_insert")
    def activate(mapper, connection, target):
        if target.kind != "work":
            return
        table = WorkLinkSetting.__table__
        if connection.execute(select(table.c.user_id).where(table.c.user_id == target.user_id)).first():
            return
        # Existing sessions remain candidates for explicit historical reconciliation.
        maximum = connection.execute(select(func.max(session_model.id))).scalar() or 0
        connection.execute(table.insert().values(user_id=target.user_id, first_session_id=maximum + 1,
                                                enabled_at=datetime.utcnow()))
