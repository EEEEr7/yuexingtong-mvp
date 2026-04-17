from __future__ import annotations

import os
import sys
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 让本地 src 包在不安装的情况下也能运行
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from dotenv import load_dotenv

# 允许本地放置 .env 来注入 OPENAI_API_KEY 等配置（真实 key 不应提交到 GitHub）
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=False)

from eink_agent.pipeline import run_agent_flow_safe  # noqa: E402


app = FastAPI(title="ReadStar Eink Agent Flow (Collector -> Refiner -> Publisher)")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    input: str


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ReadStar - Eink MVP</title>
    <style>
      * { box-sizing: border-box; }
      body {
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Noto Sans";
        margin: 0;
        background: #f8f9fa;
        color: #111827;
      }
      .layout {
        display: grid;
        grid-template-columns: 25% 50% 25%;
        min-height: 100vh;
      }
      .panel {
        padding: 28px 24px;
      }
      .side-card, .main-card {
        background: rgba(255,255,255,0.94);
        border: 1px solid rgba(17,24,39,0.08);
        border-radius: 24px;
        box-shadow: 0 10px 28px rgba(15,23,42,0.08);
      }
      .side-card {
        padding: 22px;
      }
      .side-card.full-height {
        height: calc(100vh - 56px);
        display: flex;
        flex-direction: column;
      }
      .side-scroll {
        overflow: auto;
        padding-right: 6px;
      }
      .main-panel {
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .main-card {
        width: 100%;
        min-height: calc(100vh - 56px);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 28px 20px;
      }
      .preview-shell {
        width: 80%;
        max-width: 560px;
        padding: 18px 18px 22px;
        border-radius: 36px;
        background: linear-gradient(180deg, #e5e7eb 0%, #d1d5db 100%);
        box-shadow: 0 28px 60px rgba(15,23,42,0.16);
        border: 1px solid rgba(148,163,184,0.35);
        position: relative;
      }
      .device-topbar {
        width: 100%;
        display: flex;
        justify-content: center;
        margin-bottom: 18px;
      }
      .device-speaker {
        width: 84px;
        height: 8px;
        border-radius: 999px;
        background: rgba(100,116,139,0.25);
        box-shadow: inset 0 1px 2px rgba(15,23,42,0.18);
      }
      .preview-scale {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
        min-height: 720px;
      }
      .screen-stage {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .screen-transform {
        transform-origin: top center;
        will-change: transform;
      }
      .screen-frame {
        width: 100%;
        max-width: 436px;
        padding: 10px;
        border-radius: 26px;
        background: linear-gradient(180deg, #f3f4f6 0%, #e5e7eb 100%);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.55), inset 0 -1px 0 rgba(148,163,184,0.18);
      }
      input, textarea {
        width: 100%;
        padding: 12px 14px;
        border: 1px solid #d1d5db;
        border-radius: 12px;
        background: #fff;
        font: inherit;
        color: inherit;
      }
      textarea {
        min-height: 120px;
        resize: vertical;
      }
      button {
        margin-top: 14px;
        padding: 12px 16px;
        border-radius: 12px;
        border: none;
        background: #111827;
        color: #fff;
        cursor: pointer;
        width: 100%;
        font-weight: 600;
      }
      button:hover { background: #0f172a; }
      pre {
        background: #0b0f19;
        color: #e5e7eb;
        padding: 12px;
        border-radius: 14px;
        overflow: auto;
        max-height: 44vh;
        margin: 12px 0 0;
      }
      iframe {
        border: 0;
        border-radius: 18px;
        background: #f8fafc;
        display: block;
        width: 480px;
        height: 800px;
      }
      .device-buttons {
        margin-top: 18px;
        display: flex;
        justify-content: center;
        gap: 18px;
      }
      .device-btn {
        width: 112px;
        height: 14px;
        border-radius: 999px;
        background: linear-gradient(180deg, #e5e7eb 0%, #cbd5e1 100%);
        border: 1px solid rgba(148,163,184,0.38);
        box-shadow: inset 0 1px 1px rgba(255,255,255,0.65), inset 0 -1px 2px rgba(100,116,139,0.2);
      }
      .muted { color: #6b7280; margin-top: 8px; line-height: 1.6; }
      .err {
        color: #b00020;
        white-space: pre-wrap;
        margin-top: 14px;
        font-size: 14px;
      }
      .section-title {
        margin: 0 0 8px;
        font-size: 20px;
        font-weight: 700;
      }
      .sub-title {
        margin: 0 0 18px;
        font-size: 13px;
        color: #6b7280;
      }
      .guide-card {
        margin-top: 16px;
        padding: 14px 16px;
        border-radius: 16px;
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
      }
      .guide-title {
        font-size: 13px;
        font-weight: 700;
        color: #111827;
        margin: 0 0 6px;
      }
      .guide-text {
        margin: 0;
        font-size: 13px;
        color: #6b7280;
        line-height: 1.6;
      }
      details summary {
        cursor: pointer;
        font-weight: 700;
        list-style: none;
        user-select: none;
      }
      details summary::-webkit-details-marker { display: none; }
      .debug-link {
        display: inline-block;
        margin-top: 8px;
        font-size: 12px;
        color: #64748b;
        text-decoration: underline;
        cursor: pointer;
      }
      .preview-note {
        margin-top: 14px;
        font-size: 13px;
        color: #6b7280;
        text-align: center;
      }
      .debug-status {
        margin: 0 0 14px;
        padding: 10px 12px;
        border-radius: 14px;
        background: #f8fafc;
        border: 1px solid #e5e7eb;
        color: #475569;
        font-size: 13px;
        line-height: 1.5;
      }
      .debug-status strong {
        color: #111827;
      }
      .editor-group {
        margin-top: 16px;
      }
      .editor-label {
        display: block;
        margin-bottom: 8px;
        font-size: 13px;
        font-weight: 700;
        color: #374151;
      }
      .tag-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }
      .tag-chip {
        padding: 8px 10px;
        border-radius: 999px;
        border: 1px solid #d1d5db;
        background: #fff;
        min-width: 72px;
        width: calc(50% - 4px);
      }
      .loading-overlay {
        position: absolute;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        background: rgba(243,244,246,0.84);
        border-radius: 26px;
        z-index: 5;
      }
      .loading-box {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 14px;
        color: #374151;
        font-size: 14px;
        font-weight: 600;
        text-align: center;
      }
      .spinner {
        width: 28px;
        height: 28px;
        border-radius: 999px;
        border: 3px solid rgba(100,116,139,0.2);
        border-top-color: #475569;
        animation: spin 1s linear infinite;
      }
      @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      @media (max-width: 1200px) {
        .layout { grid-template-columns: 1fr; }
        .main-card { min-height: auto; }
        pre { max-height: 40vh; }
        .preview-shell { width: 100%; max-width: 620px; }
        .tag-chip { width: 100%; }
      }
      @media (max-width: 1440px) and (min-width: 1201px) {
        .preview-scale {
          transform: scale(0.92);
          transform-origin: center center;
        }
      }
    </style>
  </head>
  <body>
    <div class="layout">
      <section class="panel">
        <div class="side-card">
          <h2 class="section-title">输入区</h2>
          <div class="sub-title">输入 URL 或纯文本，触发 Collector → Refiner → Publisher 完整链路。</div>

          <input id="urlInput" placeholder="https://example.com/xxx 或直接粘贴文本" />
          <button onclick="run()">运行</button>

          <div class="guide-card">
            <div class="guide-title">操作指南</div>
            <p class="guide-text">输入 URL 即可一键生成卡片；也支持直接粘贴纯文本内容，便于快速演示 480x800 墨屏效果。</p>
          </div>

          <div id="error" class="err" style="display:none;"></div>
        </div>
      </section>

      <section class="panel main-panel">
        <div class="main-card">
          <h2 class="section-title">480x800 核心预览</h2>
          <div class="sub-title">居中放大展示最终卡片，便于直接评估墨屏设备观感。</div>

          <div class="preview-shell">
            <div class="device-topbar">
              <div class="device-speaker"></div>
            </div>
            <div class="preview-scale">
              <div class="screen-frame">
                <div id="loadingOverlay" class="loading-overlay">
                  <div class="loading-box">
                    <div class="spinner"></div>
                    <div>正在通过百炼 Qwen3 提取精华...</div>
                  </div>
                </div>
                <div class="screen-stage">
                  <div id="screenTransform" class="screen-transform">
                    <iframe id="preview" width="480" height="800"></iframe>
                  </div>
                </div>
              </div>
            </div>
            <div class="device-buttons">
              <div class="device-btn"></div>
              <div class="device-btn"></div>
            </div>
          </div>
          <div class="preview-note">当前预览采用浅灰墨水屏设备外观，包含嵌入式屏幕与底部双按键，贴近真实产品展示图。</div>
        </div>
      </section>

      <section class="panel">
        <div class="side-card full-height">
          <h2 class="section-title">内容包</h2>
          <div class="sub-title">右侧支持直接微调核心字段，并实时映射到中间卡片。</div>
          <div id="debugStatus" class="debug-status"><strong>状态：</strong>等待运行。执行后这里会展示结果摘要。</div>
          <div class="side-scroll">
            <div class="editor-group">
              <label class="editor-label" for="titleEditor">Title（标题）</label>
              <input id="titleEditor" placeholder="运行后自动填充标题" oninput="syncPreview()" />
            </div>

            <div class="editor-group">
              <label class="editor-label" for="summaryEditor">Summary（摘要）</label>
              <textarea id="summaryEditor" placeholder="运行后自动填充摘要" oninput="syncPreview()"></textarea>
            </div>

            <div class="editor-group">
              <label class="editor-label">Tags（标签）</label>
              <div class="tag-row">
                <input class="tag-chip" id="tagEditor1" placeholder="标签 1" oninput="syncPreview()" />
                <input class="tag-chip" id="tagEditor2" placeholder="标签 2" oninput="syncPreview()" />
                <input class="tag-chip" id="tagEditor3" placeholder="标签 3" oninput="syncPreview()" />
                <input class="tag-chip" id="tagEditor4" placeholder="标签 4" oninput="syncPreview()" />
              </div>
            </div>

            <details id="debugPanel" style="margin-top: 16px;">
              <summary class="debug-link">查看 Debug JSON</summary>
              <pre id="jsonOut">等待输入...</pre>
            </details>
          </div>
        </div>
      </section>
    </div>

    <script>
      let lastPackage = null;
      let lastIndexHtml = '';

      function fitScreen() {
        const frame = document.querySelector('.screen-frame');
        const t = document.getElementById('screenTransform');
        if (!frame || !t) return;

        // 预留一些 padding，避免贴边裁切
        const availableW = Math.max(0, frame.clientWidth - 20);
        const availableH = Math.max(0, frame.clientHeight - 20);
        const scale = Math.min(1, availableW / 480, availableH / 800);
        t.style.transform = `scale(${scale})`;
      }

      function setLoading(show) {
        document.getElementById('loadingOverlay').style.display = show ? 'flex' : 'none';
      }

      function escapeHtml(str) {
        return String(str ?? '')
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('\"', '&quot;')
          .replaceAll("'", '&#39;');
      }

      function updateEditorsFromPackage(pkg) {
        document.getElementById('titleEditor').value = pkg?.title || '';
        document.getElementById('summaryEditor').value = pkg?.summary || '';
        const tags = pkg?.tags || [];
        const tagIds = ['tagEditor1', 'tagEditor2', 'tagEditor3', 'tagEditor4'];
        tagIds.forEach((id, idx) => {
          document.getElementById(id).value = tags[idx] || '';
        });
      }

      function syncPreview() {
        if (!lastIndexHtml || !lastPackage) return;

        const title = document.getElementById('titleEditor').value.trim() || lastPackage.title || '';
        const summary = document.getElementById('summaryEditor').value.trim() || lastPackage.summary || '';
        const tags = ['tagEditor1', 'tagEditor2', 'tagEditor3', 'tagEditor4']
          .map(id => document.getElementById(id).value.trim())
          .filter(Boolean);

        let patched = lastIndexHtml;
        patched = patched.replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(title)}</title>`);
        patched = patched.replace(
          /(<div class="text-white text-\[18px\] leading-snug font-semibold break-words line-clamp-3">\s*)[\s\S]*?(\s*<\/div>)/,
          `$1${escapeHtml(title)}$2`
        );
        patched = patched.replace(
          /(<div class="mt-2 text-white\/92 text-\[14px\] leading-relaxed break-words line-clamp-8">\s*)[\s\S]*?(\s*<\/div>)/,
          `$1${escapeHtml(summary)}$2`
        );

        const tagHtml = tags.map(tag =>
          `<span class="inline-flex items-center rounded-full border border-white/20 bg-white/5 px-3 py-1 text-[12px] leading-none text-white/90">${escapeHtml(tag)}</span>`
        ).join('');
        patched = patched.replace(
          /(<div class="mt-3 flex flex-wrap gap-2">\s*)[\s\S]*?(\s*<\/div>)/,
          `$1${tagHtml}$2`
        );

        document.getElementById('preview').srcdoc = patched;
      }

      async function run() {
        document.getElementById('error').style.display = 'none';
        document.getElementById('debugStatus').innerHTML = '<strong>状态：</strong>运行中，正在生成内容包与卡片预览...';
        setLoading(true);
        fitScreen();
        const url = document.getElementById('urlInput').value.trim();
        if (!url) {
          document.getElementById('error').innerText = '请输入 URL 或纯文本';
          document.getElementById('error').style.display = 'block';
          document.getElementById('debugStatus').innerHTML = '<strong>状态：</strong>等待运行。';
          setLoading(false);
          return;
        }

        document.getElementById('jsonOut').innerText = '运行中...';
        document.getElementById('preview').srcdoc = '';

        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (!res.ok) {
          document.getElementById('error').innerText = data.error || '运行失败';
          document.getElementById('error').style.display = 'block';
          document.getElementById('debugStatus').innerHTML = '<strong>状态：</strong>运行失败，请查看错误信息或展开 Debug Panel。';
          setLoading(false);
          return;
        }

        lastPackage = data.package || null;
        lastIndexHtml = data.indexHtml || '';
        document.getElementById('jsonOut').innerText = JSON.stringify(data.package, null, 2);
        document.getElementById('preview').srcdoc = data.indexHtml;
        updateEditorsFromPackage(data.package || {});
        setTimeout(fitScreen, 0);
        document.getElementById('debugStatus').innerHTML =
          '<strong>状态：</strong>生成完成。标题：' +
          (data.package?.title || '未命名') +
          '；置信度：' +
          (data.package?.confidence ?? '-') +
          '；来源：' +
          (data.package?.source || '-');
        setLoading(false);
      }

      window.addEventListener('resize', fitScreen);
      window.addEventListener('load', fitScreen);
    </script>
  </body>
</html>"""


@app.post("/api/run")
def run_api(req: RunRequest) -> Any:
    try:
        result = run_agent_flow_safe(req.input, out_dir=os.getenv("OUT_DIR", "output"))
        if not result.get("ok"):
            return JSONResponse(
                {
                    "error": result.get("error"),
                    "trace": result.get("trace"),
                    "cost": result.get("cost"),
                },
                status_code=400,
            )

        return JSONResponse(
            {
                "paths": result.get("paths"),
                "package": result.get("package"),
                "indexHtml": result.get("indexHtml"),
                "trace": result.get("trace"),
                "cost": result.get("cost"),
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

