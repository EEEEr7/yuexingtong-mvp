from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

import requests

from eink_agent.agents.base import BaseAgent
from eink_agent.schemas.content import CollectorResult, RefinerResult, Trace


def extract_json_object(text: str) -> Any:
    """
    Best-effort JSON extractor:
    - 找到第一个 `{` 和最后一个 `}`，截取后尝试解析
    """
    if not text:
        raise ValueError("空响应无法解析 JSON")

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("未找到可解析的 JSON 对象片段")

    candidate = text[start : end + 1]
    return json.loads(candidate)


class Refiner(BaseAgent):
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        logger: Optional[object] = None,
        max_text_chars: int = 12000,
        retry_count: int = 2,
    ) -> None:
        super().__init__(agent_key="refiner", logger=logger)

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com"
        self.model = model or os.getenv("OPENAI_MODEL") or "deepseek-chat"
        self.max_text_chars = max_text_chars
        self.retry_count = max(1, retry_count)

        if not self.api_key:
            raise ValueError("缺少 OPENAI_API_KEY（或传入 api_key）")

    def _run(self, input_data: object, trace: Trace) -> RefinerResult:
        if isinstance(input_data, CollectorResult):
            source = input_data.source
            text = input_data.text
        elif isinstance(input_data, dict):
            source = input_data.get("source", "")
            text = input_data.get("text", "")
        else:
            raise ValueError("Refiner 输入必须为 CollectorResult 或 dict")

        if not source:
            raise ValueError("Refiner 缺少 source（来源 URL）")
        if not text or not isinstance(text, str):
            raise ValueError("Refiner 缺少 text（待精炼文本）")

        if len(text) > self.max_text_chars:
            self._push_event(
                trace, level="info", message="truncate_refiner_text", data={"max_text_chars": self.max_text_chars}
            )
            text = text[: self.max_text_chars].strip()

        system_prompt = (
            "你是内容精炼器（Eink Reader Content Refiner）。"
            "你只能输出“严格 JSON 对象”，不能包含 Markdown、代码块、额外解释。"
            "JSON 必须满足以下字段："
            "- title: 字符串，适合作为手机墨屏卡片标题（简短、有信息密度）"
            "- summary: 字符串，1-3 句摘要（清晰、可读、不堆砌）"
            "- tags: 字符串数组，长度 3-5 个，尽量覆盖主题与关键要点"
            "- confidence: 数值 0 到 1，表示你对摘要与结构化的把握度"
        )

        user_prompt = (
            f"来源 URL：{source}\n\n"
            "待精炼文本如下（可能较长）：\n"
            f"{text}\n\n"
            "请直接返回 JSON。"
        )

        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        last_err: Optional[str] = None
        for attempt in range(1, self.retry_count + 1):
            self._push_event(trace, level="info", message="llm_call", data={"attempt": attempt, "url": url})
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            self._push_event(trace, level="info", message="llm_response_received", data={"contentLen": len(content)})

            try:
                obj = extract_json_object(content)
                result = RefinerResult.model_validate(obj)
                return result
            except Exception as e:
                last_err = str(e)
                self._push_event(
                    trace,
                    level="warning",
                    message="json_parse_failed",
                    data={"attempt": attempt, "error": last_err, "rawHead": content[:120]},
                )

                # 二次提示：强制 JSON、禁止包裹
                payload["messages"].append(
                    {
                        "role": "user",
                        "content": "再次强调：只输出严格 JSON 对象，不要任何额外字符或 Markdown。",
                    }
                )

        raise ValueError(f"Refiner 失败：无法解析或校验 LLM 输出为 schema。lastErr={last_err}")

