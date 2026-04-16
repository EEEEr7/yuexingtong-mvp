from __future__ import annotations

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
        raise NotImplementedError

