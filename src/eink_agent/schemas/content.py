from __future__ import annotations
"""
核心数据模型定义（Pydantic）。

用于约束 Agent 之间的数据边界，保证输出结构稳定、可验证、可追踪。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """返回 UTC 当前时间，统一用于 createdAt/trace at 字段。"""
    return datetime.now(timezone.utc)


class TraceEvent(BaseModel):
    """单条 trace 事件：记录某一步的级别、信息、耗时与附加数据。"""
    at: datetime = Field(default_factory=utc_now)
    level: Literal["info", "warning", "error"] = "info"
    message: str
    durationMs: Optional[int] = None
    ok: Optional[bool] = None
    data: Dict[str, Any] = Field(default_factory=dict)


Trace = Dict[str, List[TraceEvent]]


class CollectorResult(BaseModel):
    """Collector 阶段输出：来源 + 抽取文本 + trace 快照。"""
    source: str  # URL
    text: str
    createdAt: datetime = Field(default_factory=utc_now)
    trace: Trace = Field(default_factory=dict)


class RefinerResult(BaseModel):
    """Refiner 阶段输出：结构化内容核心字段。"""
    title: str
    summary: str
    tags: List[str] = Field(min_items=3, max_items=5)
    confidence: float = Field(ge=0, le=1)


class ContentPackage(BaseModel):
    """最终内容包：前端渲染与落盘的统一数据格式。"""
    id: str
    title: str
    summary: str
    tags: List[str] = Field(min_items=3, max_items=5)
    source: str
    confidence: float = Field(ge=0, le=1)
    createdAt: datetime
    trace: Trace

