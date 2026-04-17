from __future__ import annotations
"""
Agent 抽象基类。

统一提供：
- 生命周期埋点（start/success/failed）；
- trace 事件写入；
- 可选 logger 输出；
- 子类只需关注业务逻辑 _run。
"""

import abc
import time
from typing import Any, Dict, Optional

from eink_agent.schemas.content import Trace, TraceEvent, utc_now


class BaseAgent(abc.ABC):
    """
    Base class for all agents.

    Requirement:
    - Every agent must write execution logs into `trace` field.
    """

    def __init__(self, agent_key: str, logger: Optional[Any] = None) -> None:
        """初始化 agent 身份标识与可选日志器。"""
        self.agent_key = agent_key
        self.logger = logger

    def _push_event(
        self,
        trace: Trace,
        *,
        level: str,
        message: str,
        ok: Optional[bool] = None,
        duration_ms: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """向 trace 追加单条事件，并尽量同步写入 logger（失败不抛异常）。"""
        if self.agent_key not in trace:
            trace[self.agent_key] = []

        trace[self.agent_key].append(
            TraceEvent(
                level=level,  # type: ignore[arg-type]
                message=message,
                ok=ok,
                durationMs=duration_ms,
                data=data or {},
            )
        )

        if self.logger is not None:
            try:
                self.logger.info(f"[{self.agent_key}] {message}")
            except Exception:
                pass

    def execute(self, input_data: Any, trace: Trace) -> Any:
        """
        统一执行入口。

        约束：
        - 自动写入 start/success/failed；
        - 自动记录耗时；
        - 业务异常继续上抛，由上层 pipeline 决定如何处理。
        """
        start = time.perf_counter()
        self._push_event(trace, level="info", message="start", data={"inputType": type(input_data).__name__})
        try:
            output = self._run(input_data, trace)
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._push_event(trace, level="info", message="success", ok=True, duration_ms=duration_ms)
            return output
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._push_event(
                trace,
                level="error",
                message="failed",
                ok=False,
                duration_ms=duration_ms,
                data={"error": str(e)},
            )
            raise

    @abc.abstractmethod
    def _run(self, input_data: Any, trace: Trace) -> Any:
        """子类必须实现：纯业务逻辑，不关心埋点模板。"""
        raise NotImplementedError

