from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Optional

from eink_agent.agents.base import BaseAgent
from eink_agent.schemas.content import ContentPackage, Trace


class Publisher(BaseAgent):
    def __init__(self, *, logger: Optional[object] = None) -> None:
        super().__init__(agent_key="publisher", logger=logger)

    def _run(self, input_data: object, trace: Trace) -> str:
        if isinstance(input_data, ContentPackage):
            pkg = input_data
        elif isinstance(input_data, dict):
            pkg = ContentPackage.model_validate(input_data)
        else:
            raise ValueError("Publisher 输入必须为 ContentPackage 或 dict")

        self._push_event(
            trace,
            level="info",
            message="render_index_html",
            data={"id": pkg.id, "titleLen": len(pkg.title), "tagsCount": len(pkg.tags)},
        )

        # Eink/黑白友好的“类宝玉信息图”风格：
        # - 深色渐变底
        # - 大分区卡片
        # - 标签胶囊
        # - 少阴影、少细线、清晰层级
        title = html.escape(pkg.title)
        source = html.escape(pkg.source)
        summary = html.escape(pkg.summary)
        tags = [html.escape(t) for t in pkg.tags]
        confidence = float(pkg.confidence)

        created_at = pkg.createdAt
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat(timespec="seconds")
        else:
            created_at_str = str(created_at)

        tag_html = "\n".join(
            [f'<span class="inline-flex items-center rounded-full border border-white/20 bg-white/5 px-3 py-1 text-[12px] leading-none text-white/90">{t}</span>' for t in tags]
        )

        # 只做单页：严格 480x800
        return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=480,initial-scale=1,maximum-scale=1" />
    <script src="https://cdn.tailwindcss.com"></script>
    <title>{title}</title>
    <style>
      body {{
        margin: 0;
        background: #000;
        color: #fff;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Noto Sans", "Liberation Sans", sans-serif;
      }}
      .bgInk {{
        background:
          radial-gradient(1200px 600px at 10% 0%, rgba(255,255,255,0.10), rgba(255,255,255,0) 55%),
          radial-gradient(800px 500px at 90% 20%, rgba(255,255,255,0.08), rgba(255,255,255,0) 60%),
          linear-gradient(180deg, #0b0b0b 0%, #141414 50%, #0a0a0a 100%);
        color: #fff;
      }}
      /* 细腻但不依赖彩色的“信息图纹理” */
      .inkPattern {{
        background-image:
          linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.00) 40%),
          repeating-linear-gradient(90deg, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, rgba(255,255,255,0) 1px, rgba(255,255,255,0) 12px);
      }}
    </style>
  </head>
  <body>
    <div class="bgInk inkPattern w-[480px] h-[800px] overflow-hidden mx-auto relative">
      <div class="absolute inset-0 opacity-60 pointer-events-none"></div>

      <!-- 顶部：标题与来源 -->
      <div class="px-6 pt-8">
        <div class="rounded-3xl border border-white/15 bg-white/5 backdrop-blur-sm p-5">
          <div class="flex items-start gap-3">
            <div class="w-10 h-10 rounded-2xl border border-white/20 bg-white/5 flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 2L2 7l10 5 10-5-10-5Z" stroke="rgba(255,255,255,0.85)" stroke-width="1.6" />
                <path d="M2 17l10 5 10-5" stroke="rgba(255,255,255,0.85)" stroke-width="1.6" stroke-linecap="round"/>
                <path d="M2 12l10 5 10-5" stroke="rgba(255,255,255,0.85)" stroke-width="1.6" stroke-linecap="round"/>
              </svg>
            </div>

            <div class="min-w-0 flex-1">
              <div class="text-white text-[18px] leading-snug font-semibold break-words line-clamp-3">
                {title}
              </div>
              <div class="mt-2 text-white/70 text-[12px] leading-tight break-words">
                来源：{source}
              </div>
            </div>
          </div>
        </div>

        <!-- 视觉占位图：标题与摘要之间的“视觉锚点” -->
        <div class="mt-4 rounded-3xl border border-white/15 bg-white/5 p-4">
          <div
            class="w-full flex items-center justify-center rounded-2xl border border-white/10 bg-white/5"
            style="aspect-ratio: 16 / 5;"
          >
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M4 7.5C4 6.119 5.119 5 6.5 5H17.5C18.881 5 20 6.119 20 7.5V16.5C20 17.881 18.881 19 17.5 19H6.5C5.119 19 4 17.881 4 16.5V7.5Z"
                stroke="rgba(255,255,255,0.75)"
                stroke-width="1.6"
              />
              <path
                d="M8 11.5L10.2 9.3C10.6 8.9 11.3 8.9 11.7 9.3L20 17.6"
                stroke="rgba(255,255,255,0.75)"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M9 15C9.9 15.6 10.8 15.9 11.9 15.9C13.9 15.9 15.6 14.3 15.6 12.3C15.6 10.3 13.9 8.7 11.9 8.7"
                stroke="rgba(255,255,255,0.35)"
                stroke-width="1.6"
                stroke-linecap="round"
              />
            </svg>
            <div class="sr-only">placeholder-image</div>
          </div>
        </div>

        <!-- 信息层级：摘要卡 -->
        <div class="mt-4 rounded-3xl border border-white/15 bg-white/5 p-5">
          <div class="text-white text-[13px] tracking-wide uppercase font-semibold text-white/85">
            摘要
          </div>
          <div class="mt-2 text-white/92 text-[14px] leading-relaxed break-words line-clamp-8">
            {summary}
          </div>
        </div>
      </div>

      <!-- 中部：要点与置信度 -->
      <div class="px-6 mt-5">
        <div class="grid grid-cols-2 gap-3">
          <div class="rounded-3xl border border-white/15 bg-white/5 p-4">
            <div class="text-white/70 text-[12px] font-semibold">置信度</div>
            <div class="mt-2 flex items-end gap-2">
              <div class="text-white text-[28px] font-bold">{confidence:.2f}</div>
              <div class="text-white/70 text-[12px] pb-1">/1.00</div>
            </div>
            <div class="mt-2 text-white/60 text-[12px] leading-tight">
              用于控制展示质量与可信度。
            </div>
          </div>
          <div class="rounded-3xl border border-white/15 bg-white/5 p-4">
            <div class="text-white/70 text-[12px] font-semibold">时间</div>
            <div class="mt-2 text-white text-[14px] leading-snug">{html.escape(created_at_str)}</div>
            <div class="mt-2 text-white/60 text-[12px] leading-tight">
              生成于一次完整 Agent Flow。
            </div>
          </div>
        </div>
      </div>

      <!-- 底部：标签胶囊 + trace 简版 -->
      <div class="absolute left-6 right-6 bottom-6">
        <div class="rounded-3xl border border-white/15 bg-white/5 p-5">
          <div class="text-white/70 text-[12px] font-semibold">标签</div>
          <div class="mt-3 flex flex-wrap gap-2">
            {tag_html if tag_html else ""}
          </div>

          <div class="mt-4 pt-4 border-t border-white/10">
            <div class="flex items-center justify-between">
              <div class="text-white/70 text-[12px] font-semibold">trace</div>
              <div class="text-white/60 text-[12px]">{len(pkg.trace.keys())} 段</div>
            </div>
            <div class="mt-2 text-white/60 text-[12px] leading-snug break-words">
              {html.escape(", ".join(sorted(pkg.trace.keys())))}
            </div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""

