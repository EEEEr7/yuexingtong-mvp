from __future__ import annotations

import html
from datetime import datetime
from typing import Literal, Tuple

from eink_agent.agents.base import BaseAgent
from eink_agent.schemas.content import ContentPackage, Trace


class Publisher(BaseAgent):
    def __init__(self, *, logger: object | None = None) -> None:
        super().__init__(agent_key="publisher", logger=logger)

    def _run(self, input_data: object, trace: Trace) -> Tuple[str, str]:
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
            data={"id": pkg.id, "titleLen": len(pkg.title), "tagsCount": len(pkg.tags), "themes": ["dark", "light"]},
        )

        dark = self._build_html(pkg, "dark")
        light = self._build_html(pkg, "light")
        return dark, light

    def _build_html(self, pkg: ContentPackage, theme: Literal["dark", "light"]) -> str:
        """生成单页 480x800；dark=黑底白字，light=白底墨字（反色 / 纸感墨屏）。"""
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

        if theme == "dark":
            tag_html = "\n".join(
                [
                    f'<span class="inline-flex items-center rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-[12px] leading-none text-white/95 font-medium">{t}</span>'
                    for t in tags
                ]
            )
            style_block = """
      body {
        margin: 0;
        background: #000;
        color: #fff;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Noto Sans", "Liberation Sans", sans-serif;
      }
      .bgInk {
        background:
          radial-gradient(1200px 600px at 10% 0%, rgba(255,255,255,0.10), rgba(255,255,255,0) 55%),
          radial-gradient(800px 500px at 90% 20%, rgba(255,255,255,0.08), rgba(255,255,255,0) 60%),
          linear-gradient(180deg, #0b0b0b 0%, #141414 50%, #0a0a0a 100%);
        color: #fff;
      }
      .inkPattern {
        background-image:
          linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.00) 40%),
          repeating-linear-gradient(90deg, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, rgba(255,255,255,0) 1px, rgba(255,255,255,0) 12px);
      }
"""
            page_cls = "bgInk inkPattern w-[480px] h-[800px] overflow-y-auto overflow-x-hidden mx-auto relative"
            card_outer = "rounded-3xl border border-white/15 bg-white/5 backdrop-blur-sm p-5"
            deco_bar = "w-1 h-10 rounded-full bg-gradient-to-b from-amber-300 via-amber-200 to-transparent"
            title_cls = "text-[2rem] leading-snug font-extrabold text-white tracking-tight break-words"
            sub_cls = "mt-1 text-[1.1rem] leading-snug font-normal text-[rgba(255,255,255,0.7)] break-words"
            meta_cls = "mt-2 text-white/70 text-[12px] leading-tight break-words"
            ph_wrap = "mt-4 rounded-3xl border border-white/15 bg-white/5 p-4"
            ph_inner = "w-full flex items-center justify-center rounded-2xl border border-white/10 bg-white/5"
            svg_stroke_main = "rgba(255,255,255,0.75)"
            svg_stroke_sub = "rgba(255,255,255,0.35)"
            sum_card = "mt-4 rounded-3xl border border-white/15 bg-white/5 p-5"
            sum_label = "text-white text-[13px] tracking-wide uppercase font-semibold text-white/85"
            sum_body = "mt-2 text-white/92 text-[14px] leading-relaxed break-words line-clamp-8"
            grid_card = "rounded-3xl border border-white/15 bg-white/5 p-4"
            lbl = "text-white/70 text-[12px] font-semibold"
            conf_big = "text-white text-[28px] font-bold"
            conf_small = "text-white/70 text-[12px] pb-1"
            hint = "mt-2 text-white/60 text-[12px] leading-tight"
            time_val = "mt-2 text-white text-[14px] leading-snug"
            bottom_wrap = "rounded-3xl border border-white/15 bg-white/5 p-5"
            tag_lbl = "text-white/70 text-[12px] font-semibold"
            trace_top = "mt-4 pt-4 border-t border-white/10"
            trace_row = "text-white/70 text-[12px] font-semibold"
            trace_meta = "text-white/60 text-[12px]"
            trace_txt = "mt-2 text-white/60 text-[12px] leading-snug break-words"
        else:
            tag_html = "\n".join(
                [
                    f'<span class="inline-flex items-center rounded-full border border-stone-400/70 bg-stone-100 px-3 py-1.5 text-[12px] leading-none text-stone-900 font-medium">{t}</span>'
                    for t in tags
                ]
            )
            style_block = """
      body {
        margin: 0;
        background: #e7e5e4;
        color: #1c1917;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Noto Sans", "Liberation Sans", sans-serif;
      }
      .bgInkLight {
        background:
          radial-gradient(1000px 500px at 12% 0%, rgba(0,0,0,0.05), rgba(0,0,0,0) 50%),
          linear-gradient(180deg, #ffffff 0%, #fafaf9 45%, #f5f5f4 100%);
        color: #1c1917;
      }
      .inkPatternLight {
        background-image:
          linear-gradient(135deg, rgba(0,0,0,0.04) 0%, rgba(0,0,0,0) 42%),
          repeating-linear-gradient(90deg, rgba(0,0,0,0.06) 0px, rgba(0,0,0,0.06) 1px, rgba(0,0,0,0) 1px, rgba(0,0,0,0) 11px);
      }
"""
            page_cls = "bgInkLight inkPatternLight w-[480px] h-[800px] overflow-y-auto overflow-x-hidden mx-auto relative"
            card_outer = "rounded-3xl border border-stone-300/90 bg-white shadow-sm p-5"
            deco_bar = "w-1 h-10 rounded-full bg-gradient-to-b from-amber-700 via-amber-600 to-amber-200/80"
            title_cls = "text-[2rem] leading-snug font-extrabold text-stone-900 tracking-tight break-words"
            sub_cls = "mt-1 text-[1.1rem] leading-snug font-normal text-stone-600 break-words"
            meta_cls = "mt-2 text-stone-500 text-[12px] leading-tight break-words"
            ph_wrap = "mt-4 rounded-3xl border border-stone-200 bg-stone-50 p-4"
            ph_inner = "w-full flex items-center justify-center rounded-2xl border border-stone-200 bg-white"
            svg_stroke_main = "rgba(28,25,23,0.55)"
            svg_stroke_sub = "rgba(28,25,23,0.28)"
            sum_card = "mt-4 rounded-3xl border border-stone-200 bg-white p-5 shadow-sm"
            sum_label = "text-stone-800 text-[13px] tracking-wide uppercase font-semibold"
            sum_body = "mt-2 text-stone-800 text-[14px] leading-relaxed break-words line-clamp-8"
            grid_card = "rounded-3xl border border-stone-200 bg-white p-4 shadow-sm"
            lbl = "text-stone-500 text-[12px] font-semibold"
            conf_big = "text-stone-900 text-[28px] font-bold"
            conf_small = "text-stone-500 text-[12px] pb-1"
            hint = "mt-2 text-stone-500 text-[12px] leading-tight"
            time_val = "mt-2 text-stone-900 text-[14px] leading-snug"
            bottom_wrap = "rounded-3xl border border-stone-200 bg-white p-5 shadow-sm"
            tag_lbl = "text-stone-500 text-[12px] font-semibold"
            trace_top = "mt-4 pt-4 border-t border-stone-200"
            trace_row = "text-stone-500 text-[12px] font-semibold"
            trace_meta = "text-stone-400 text-[12px]"
            trace_txt = "mt-2 text-stone-500 text-[12px] leading-snug break-words"

        return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=480,initial-scale=1,maximum-scale=1" />
    <script src="https://cdn.tailwindcss.com"></script>
    <title>{title}</title>
    <style>
{style_block}
    </style>
  </head>
  <body>
    <div class="{page_cls}">
      <div class="absolute inset-0 opacity-60 pointer-events-none"></div>

      <div class="px-6 pt-8">
        <div class="{card_outer}">
          <div class="flex items-start gap-4">
            <div class="flex flex-col items-center pt-1">
              <div class="{deco_bar}"></div>
            </div>

            <div class="min-w-0 flex-1">
              <div class="{title_cls}">
                {title}
              </div>
              <div class="{sub_cls}">
                {summary}
              </div>
              <div class="{meta_cls}">
                来源：{source}
              </div>
            </div>
          </div>
        </div>

        <div class="{ph_wrap}">
          <div
            class="{ph_inner}"
            style="aspect-ratio: 16 / 5;"
          >
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M4 7.5C4 6.119 5.119 5 6.5 5H17.5C18.881 5 20 6.119 20 7.5V16.5C20 17.881 18.881 19 17.5 19H6.5C5.119 19 4 17.881 4 16.5V7.5Z"
                stroke="{svg_stroke_main}"
                stroke-width="1.6"
              />
              <path
                d="M8 11.5L10.2 9.3C10.6 8.9 11.3 8.9 11.7 9.3L20 17.6"
                stroke="{svg_stroke_main}"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M9 15C9.9 15.6 10.8 15.9 11.9 15.9C13.9 15.9 15.6 14.3 15.6 12.3C15.6 10.3 13.9 8.7 11.9 8.7"
                stroke="{svg_stroke_sub}"
                stroke-width="1.6"
                stroke-linecap="round"
              />
            </svg>
            <div class="sr-only">placeholder-image</div>
          </div>
        </div>

        <div class="{sum_card}">
          <div class="{sum_label}">
            摘要
          </div>
          <div class="{sum_body}">
            {summary}
          </div>
        </div>
      </div>

      <div class="px-6 mt-5">
        <div class="grid grid-cols-2 gap-3">
          <div class="{grid_card}">
            <div class="{lbl}">置信度</div>
            <div class="mt-2 flex items-end gap-2">
              <div class="{conf_big}">{confidence:.2f}</div>
              <div class="{conf_small}">/1.00</div>
            </div>
            <div class="{hint}">
              用于控制展示质量与可信度。
            </div>
          </div>
          <div class="{grid_card}">
            <div class="{lbl}">时间</div>
            <div class="{time_val}">{html.escape(created_at_str)}</div>
            <div class="{hint}">
              生成于一次完整 Agent Flow。
            </div>
          </div>
        </div>
      </div>

      <div class="px-6 mt-5 mb-6">
        <div class="{bottom_wrap}">
          <div class="{tag_lbl}">标签</div>
          <div class="mt-3 flex flex-wrap gap-2">
            {tag_html if tag_html else ""}
          </div>

          <div class="{trace_top}">
            <div class="flex items-center justify-between">
              <div class="{trace_row}">trace</div>
              <div class="{trace_meta}">{len(pkg.trace.keys())} 段</div>
            </div>
            <div class="{trace_txt}">
              {html.escape(", ".join(sorted(pkg.trace.keys())))}
            </div>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""
