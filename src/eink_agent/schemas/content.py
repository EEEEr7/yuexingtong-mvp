from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TraceEvent(BaseModel):
    at: datetime = Field(default_factory=utc_now)
    level: Literal["info", "warning", "error"] = "info"
    message: str
    durationMs: Optional[int] = None
    ok: Optional[bool] = None
    data: Dict[str, Any] = Field(default_factory=dict)


Trace = Dict[str, List[TraceEvent]]


class CollectorResult(BaseModel):
    source: str  # URL
    text: str
    createdAt: datetime = Field(default_factory=utc_now)
    trace: Trace = Field(default_factory=dict)


class RefinerResult(BaseModel):
    title: str
    summary: str
    tags: List[str] = Field(min_items=3, max_items=5)
    confidence: float = Field(ge=0, le=1)


class ContentPackage(BaseModel):
    id: str
    title: str
    summary: str
    tags: List[str] = Field(min_items=3, max_items=5)
    source: str
    confidence: float = Field(ge=0, le=1)
    createdAt: datetime
    trace: Trace

