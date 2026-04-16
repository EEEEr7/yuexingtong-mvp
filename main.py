from __future__ import annotations

import argparse
import json
import os
import sys

# 让本地 src 包在不安装的情况下也能运行
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from dotenv import load_dotenv

# 允许本地放置 .env，提供开箱即用的环境变量加载（真实 key 不应提交）
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=False)

from eink_agent.pipeline import run_agent_flow_safe  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="ReadStar Eink Agent Flow - Collector -> Refiner -> Publisher")
    parser.add_argument("--url", type=str, required=True, help="输入一个 HTTP/HTTPS 网页 URL")
    parser.add_argument("--out-dir", type=str, default="output", help="输出目录（会生成 index.html + JSON）")
    args = parser.parse_args()

    result = run_agent_flow_safe(args.url, out_dir=args.out_dir)
    if not result.get("ok"):
        print(json.dumps({"error": result.get("error"), "trace": result.get("trace")}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    paths = result.get("paths") or {}
    print(json.dumps(paths, ensure_ascii=False, indent=2))
    print(json.dumps(result.get("package"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

