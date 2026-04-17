from __future__ import annotations
"""
流水线编排模块。

负责：
- 串联 Collector / Refiner / Publisher；
- 统一构建 ContentPackage；
- 统一收集并返回 trace 与 cost；
- 统一落盘输出（json + dark/light html）。
"""

import json
import os
import time
import uuid
from typing import Dict, Tuple

from eink_agent.agents.collector import Collector
from eink_agent.agents.publisher import Publisher
from eink_agent.agents.refiner import Refiner
from eink_agent.cost_tracker import reset_costs, snapshot_costs
from eink_agent.schemas.content import CollectorResult, ContentPackage, RefinerResult, Trace, utc_now


def build_content_package(*, collected: CollectorResult, refined: RefinerResult, trace: Trace) -> ContentPackage:
    """将采集结果与精炼结果合并为标准内容包（Schema 层最终对象）。"""
    return ContentPackage(
        id=uuid.uuid4().hex,
        title=refined.title,
        summary=refined.summary,
        tags=refined.tags,
        source=collected.source,
        confidence=refined.confidence,
        createdAt=utc_now(),
        trace=trace,
    )


def run_agent_flow_safe(url: str, *, out_dir: str = "output") -> Dict[str, object]:
    """
    Safe version:
    - 成功：返回 package/indexHtml/paths，并返回 trace（也写入 package.trace）
    - 失败：返回 error + trace（便于定位 Collector/Refiner/Publisher 出错点）
    """
    os.makedirs(out_dir, exist_ok=True)

    # trace 在全链路贯穿，用于“成功可解释、失败可定位”。
    trace: Trace = {}
    reset_costs()
    flow_t0 = time.perf_counter()
    try:
        # 1) 采集阶段：URL 抽取正文或直接使用纯文本输入。
        collector = Collector()
        collected: CollectorResult = collector.execute(url, trace=trace)

        # 2) 精炼阶段：产出 title/summary/tags/confidence。
        refiner = Refiner()
        refined = refiner.execute(collected, trace=trace)

        # 3) 组装内容包并渲染双主题 HTML。
        pkg = build_content_package(collected=collected, refined=refined, trace=trace)
        publisher = Publisher()
        index_html, index_html_light = publisher.execute(pkg, trace=trace)

        # 计算链路耗时并汇总 token/call/wall 时长统计。
        flow_wall_ms = (time.perf_counter() - flow_t0) * 1000.0
        cost = snapshot_costs()
        cost["flowWallMs"] = round(flow_wall_ms, 2)
        llm_t = cost["llm"].get("tokens")
        emb_t = cost["embedding"].get("tokens")
        if llm_t is not None or emb_t is not None:
            cost["tokensTotal"] = int((llm_t or 0) + (emb_t or 0))
        else:
            cost["tokensTotal"] = None

        # 落盘：按步骤要求至少生成 index.html（JSON 内附带 cost，便于归档与对照 API 响应）
        json_path = os.path.join(out_dir, f"{pkg.id}.json")
        html_path = os.path.join(out_dir, "index.html")
        html_light_path = os.path.join(out_dir, "index-light.html")
        record = {**pkg.model_dump(mode="json"), "cost": cost}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(index_html)
        with open(html_light_path, "w", encoding="utf-8") as f:
            f.write(index_html_light)

        return {
            "ok": True,
            "package": pkg.model_dump(mode="json"),
            "indexHtml": index_html,
            "indexHtmlLight": index_html_light,
            "paths": {
                "json": json_path,
                "index_html": html_path,
                "index_html_light": html_light_path,
            },
            "trace": {k: [ev.model_dump(mode="json") for ev in v] for k, v in trace.items()},
            "cost": cost,
        }
    except Exception as e:
        flow_wall_ms = (time.perf_counter() - flow_t0) * 1000.0
        cost = snapshot_costs()
        cost["flowWallMs"] = round(flow_wall_ms, 2)
        llm_t = cost["llm"].get("tokens")
        emb_t = cost["embedding"].get("tokens")
        if llm_t is not None or emb_t is not None:
            cost["tokensTotal"] = int((llm_t or 0) + (emb_t or 0))
        else:
            cost["tokensTotal"] = None
        return {
            "ok": False,
            "error": str(e),
            "trace": {k: [ev.model_dump(mode="json") for ev in v] for k, v in trace.items()},
            "cost": cost,
        }


def run_agent_flow(url: str, *, out_dir: str = "output") -> Tuple[ContentPackage, str, Dict[str, str]]:
    """
    Collector -> Refiner -> Publisher

    Returns:
      - content package (validated)
      - html string (index.html)
      - output paths
    """
    # 非 safe 版本：将失败转换为异常，供 CLI 场景直接退出。
    result = run_agent_flow_safe(url, out_dir=out_dir)
    if not result.get("ok"):
        raise RuntimeError(result.get("error"))

    pkg = ContentPackage.model_validate(result["package"])
    return pkg, result["indexHtml"], result["paths"]  # type: ignore[return-value]

