from __future__ import annotations

import os
import sys
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# 让本地 src 包在不安装的情况下也能运行
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# 自动加载项目根目录 .env（不应提交）
# 以项目 .env 为准，覆盖可能存在的系统/会话环境变量（避免残留代理变量影响演示）
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=True)

from eink_agent.pipeline import run_agent_flow_safe  # noqa: E402


app = FastAPI(title="ReadStar Backend API (Collector -> Refiner -> Publisher)")

# 允许前端跨域调用（本地开发默认放开）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    input: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


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

