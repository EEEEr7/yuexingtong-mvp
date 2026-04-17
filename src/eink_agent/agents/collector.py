from __future__ import annotations
"""
Collector：负责输入采集与文本清洗。

支持两种输入：
- URL：抓取页面并抽取正文文本；
- direct-text：直接使用文本输入（不依赖网络与 bs4）。
"""

import re
import os
from typing import Optional
from urllib.parse import urlparse

import requests

from eink_agent.agents.base import BaseAgent
from eink_agent.schemas.content import CollectorResult, Trace


class Collector(BaseAgent):
    def __init__(self, *, logger: Optional[object] = None, max_chars: int = 12000) -> None:
        """初始化采集器；max_chars 用于控制后续 LLM 输入规模。"""
        super().__init__(agent_key="collector", logger=logger)
        self.max_chars = max_chars

    def _run(self, input_data: object, trace: Trace) -> CollectorResult:
        """
        执行采集逻辑并返回 CollectorResult。

        关键策略：
        - URL 路径：请求页面 -> 解析正文 -> 去噪 -> 截断；
        - 文本路径：标准化空白 -> 截断；
        - 两条路径都将关键事件写入 trace。
        """
        if not isinstance(input_data, str) or not input_data.strip():
            raise ValueError("Collector 输入必须是非空字符串（URL 或纯文本）")

        input_str = input_data.strip()
        is_url = input_str.startswith(("http://", "https://"))

        # URL 输入：抓取网页并抽取纯文本
        if is_url:
            # 仅在 URL 路径需要抓取/解析时才导入 BeautifulSoup，
            # 这样纯文本输入无需该依赖也能运行。
            try:
                from bs4 import BeautifulSoup  # type: ignore
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError(
                    "缺少依赖 `beautifulsoup4`（用于 URL 抓取 HTML）。"
                    "当前仅支持纯文本输入无需此依赖。"
                ) from e

            parsed = urlparse(input_str)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError(f"不支持的 URL 协议: {parsed.scheme}")

            # 1) 抓取页面 HTML
            verify_ssl = os.getenv("COLLECTOR_SSL_VERIFY", "true").lower() not in {"0", "false", "no"}
            trust_env = os.getenv("COLLECTOR_TRUST_ENV", "true").lower() not in {"0", "false", "no"}
            if not verify_ssl:
                self._push_event(
                    trace,
                    level="warning",
                    message="ssl_verify_disabled",
                    data={"reason": "COLLECTOR_SSL_VERIFY=false"},
                )
            if not trust_env:
                self._push_event(
                    trace,
                    level="warning",
                    message="requests_trust_env_disabled",
                    data={"reason": "COLLECTOR_TRUST_ENV=false"},
                )

            self._push_event(trace, level="info", message="fetch_page", data={"url": input_str, "verifySSL": verify_ssl})
            session = requests.Session()
            session.trust_env = trust_env
            resp = session.get(
                input_str,
                timeout=20,
                verify=verify_ssl,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; eink-agent/1.0)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            resp.raise_for_status()
            html = resp.text or ""
            final_url = getattr(resp, "url", None) or input_str

            # 2) 抽取纯文本
            self._push_event(trace, level="info", message="parse_html", data={"htmlChars": len(html)})
            soup = BeautifulSoup(html, "html.parser")

            # 去掉脚本/样式，减少干扰
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()

            if not text:
                raise ValueError("页面未提取到有效正文文本")

            if len(text) > self.max_chars:
                # 保护 token 成本与模型输出长度
                text = text[: self.max_chars].strip()
                self._push_event(trace, level="info", message="truncate_text", data={"max_chars": self.max_chars})

            self._push_event(
                trace, level="info", message="extracted_text", data={"finalUrl": final_url, "textChars": len(text)}
            )
            return CollectorResult(source=final_url, text=text, trace=trace)

        # 纯文本输入：直接走文本精炼（不进行 HTTP 请求）
        text = re.sub(r"\s+", " ", input_str).strip()
        self._push_event(trace, level="info", message="Direct text input", data={"textChars": len(text)})

        if not text:
            raise ValueError("输入文本为空")

        if len(text) > self.max_chars:
            text = text[: self.max_chars].strip()
            self._push_event(trace, level="info", message="truncate_text", data={"max_chars": self.max_chars})

        return CollectorResult(source="direct-text", text=text, trace=trace)

