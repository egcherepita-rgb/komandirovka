from __future__ import annotations

from pydantic import BaseModel, Field


class SlotUpdateForm(BaseModel):
    status: str = Field(..., min_length=1)
    branch: str | None = None
    contact: str | None = None
    visit_goal: str | None = None
    priority: str | None = None
    comment: str | None = None
