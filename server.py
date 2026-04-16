from __future__ import annotations

import os
import sys
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# 让本地 src 包在不安装的情况下也能运行
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from eink_agent.pipeline import run_agent_flow_safe  # noqa: E402


app = FastAPI(title="ReadStar Eink Agent Flow (Collector -> Refiner -> Publisher)")


class RunRequest(BaseModel):
    url: str


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ReadStar - Eink MVP</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Noto Sans"; margin: 24px; }
      input { width: min(760px, 100%); padding: 10px; border: 1px solid #ddd; border-radius: 10px; }
      button { margin-top: 12px; padding: 10px 14px; border-radius: 10px; border: 1px solid #ddd; background: #111; color: #fff; cursor: pointer; }
      .row { display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap; margin-top: 18px; }
      pre { background: #0b0b0b; color: #e8e8e8; padding: 12px; border-radius: 12px; max-width: 820px; overflow: auto; }
      iframe { border: 1px solid #ddd; border-radius: 12px; background: #000; }
      .muted { color: #666; margin-top: 6px; }
      .err { color: #b00020; white-space: pre-wrap; }
    </style>
  </head>
  <body>
    <h2>阅星曈：Collector → Refiner → Publisher</h2>
    <div class="muted">输入 URL 后，生成标准内容包 JSON + 480x800 墨屏卡片（index.html 预览）。</div>

    <input id="urlInput" placeholder="https://example.com/xxx" />
    <div>
      <button onclick="run()">运行</button>
    </div>

    <div id="error" class="err" style="margin-top:16px; display:none;"></div>

    <div class="row">
      <div style="flex: 1 1 520px; min-width: 320px;">
        <h3>内容包 JSON</h3>
        <pre id="jsonOut">等待输入...</pre>
      </div>
      <div style="flex: 0 0 auto;">
        <h3>480x800 预览</h3>
        <iframe id="preview" width="480" height="800"></iframe>
      </div>
    </div>

    <script>
      async function run() {
        document.getElementById('error').style.display = 'none';
        const url = document.getElementById('urlInput').value.trim();
        if (!url) { document.getElementById('error').innerText = '请输入 URL'; document.getElementById('error').style.display = 'block'; return; }

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
          return;
        }

        document.getElementById('jsonOut').innerText = JSON.stringify(data.package, null, 2);
        document.getElementById('preview').srcdoc = data.indexHtml;
      }
    </script>
  </body>
</html>"""


@app.post("/api/run")
def run_api(req: RunRequest) -> Any:
    try:
        result = run_agent_flow_safe(req.url, out_dir=os.getenv("OUT_DIR", "output"))
        if not result.get("ok"):
            return JSONResponse(
                {"error": result.get("error"), "trace": result.get("trace")},
                status_code=400,
            )

        return JSONResponse(
            {
                "paths": result.get("paths"),
                "package": result.get("package"),
                "indexHtml": result.get("indexHtml"),
                "trace": result.get("trace"),
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

