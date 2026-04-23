from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Slot(Base):
    __tablename__ = 'slots'
    __table_args__ = (UniqueConstraint('slot_code', name='uq_slot_code'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    week: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(String(50), nullable=False)
    product_direction: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default='Свободно')
    branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    visit_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    slot_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
