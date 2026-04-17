from __future__ import annotations
"""
成本统计模块（线程/协程安全）。

记录维度：
- LLM 调用次数、token、耗时；
- Embedding 调用次数、token、耗时；
- 外部 API 总耗时。
"""

import time
from contextvars import ContextVar
from typing import Any, Dict, Optional


def _empty_snapshot() -> Dict[str, Any]:
    """创建一份空白统计快照。"""
    return {
        "llm": {"calls": 0, "tokens": None, "wallMsTotal": 0.0},
        "embedding": {"calls": 0, "tokens": None, "wallMsTotal": 0.0},
        "totalWallMs": 0.0,
    }


_cost_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("eink_cost_ctx", default=None)


def reset_costs() -> None:
    """重置当前上下文中的成本统计。"""
    _cost_ctx.set(_empty_snapshot())


def snapshot_costs() -> Dict[str, Any]:
    """读取当前统计并返回浅拷贝，防止外部误改内部状态。"""
    snap = _cost_ctx.get()
    if snap is None:
        snap = _empty_snapshot()
        _cost_ctx.set(snap)
    # 返回浅拷贝，避免外部误改内部结构
    return {
        "llm": dict(snap["llm"]),
        "embedding": dict(snap["embedding"]),
        "totalWallMs": float(snap["totalWallMs"]),
    }


def _add_tokens(bucket: Dict[str, Any], n: Optional[int]) -> None:
    """将 token 增量安全累加到目标桶（忽略非法值/非正数）。"""
    if n is None:
        return
    try:
        v = int(n)
    except Exception:
        return
    if v <= 0:
        return
    cur = bucket.get("tokens")
    bucket["tokens"] = v if cur is None else int(cur) + v


def _extract_usage_tokens(usage: Any) -> Optional[int]:
    """
    兼容 OpenAI 兼容接口与 DashScope 常见字段。
    """
    if usage is None:
        return None
    if isinstance(usage, dict):
        if usage.get("total_tokens") is not None:
            try:
                return int(usage["total_tokens"])
            except Exception:
                pass
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        if pt is not None or ct is not None:
            try:
                return int(pt or 0) + int(ct or 0)
            except Exception:
                pass
        # DashScope 常见
        it = usage.get("input_tokens")
        ot = usage.get("output_tokens")
        if it is not None or ot is not None:
            try:
                return int(it or 0) + int(ot or 0)
            except Exception:
                pass
        return None

    # 对象形态
    for attr in ("total_tokens",):
        if hasattr(usage, attr):
            try:
                v = getattr(usage, attr)
                if v is not None:
                    return int(v)
            except Exception:
                pass
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    if pt is not None or ct is not None:
        try:
            return int(pt or 0) + int(ct or 0)
        except Exception:
            pass
    it = getattr(usage, "input_tokens", None)
    ot = getattr(usage, "output_tokens", None)
    if it is not None or ot is not None:
        try:
            return int(it or 0) + int(ot or 0)
        except Exception:
            pass
    return None


def record_llm_call(*, wall_ms: float, usage: Any) -> None:
    """记录一次 LLM 调用的耗时与 token。"""
    snap = _cost_ctx.get()
    if snap is None:
        snap = _empty_snapshot()
        _cost_ctx.set(snap)
    snap["llm"]["calls"] = int(snap["llm"]["calls"]) + 1
    snap["llm"]["wallMsTotal"] = float(snap["llm"]["wallMsTotal"]) + float(wall_ms)
    snap["totalWallMs"] = float(snap["totalWallMs"]) + float(wall_ms)
    _add_tokens(snap["llm"], _extract_usage_tokens(usage))


def record_embedding_call(*, wall_ms: float, usage: Any) -> None:
    """记录一次 Embedding 调用的耗时与 token。"""
    snap = _cost_ctx.get()
    if snap is None:
        snap = _empty_snapshot()
        _cost_ctx.set(snap)
    snap["embedding"]["calls"] = int(snap["embedding"]["calls"]) + 1
    snap["embedding"]["wallMsTotal"] = float(snap["embedding"]["wallMsTotal"]) + float(wall_ms)
    snap["totalWallMs"] = float(snap["totalWallMs"]) + float(wall_ms)
    _add_tokens(snap["embedding"], _extract_usage_tokens(usage))


def perf_ms() -> float:
    """统一性能计时基准（毫秒）。"""
    return time.perf_counter() * 1000.0
