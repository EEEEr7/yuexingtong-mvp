# 阅星曈 MVP（Collector -> Refiner -> Publisher）

输入：URL（HTTP/HTTPS 网页）  
输出：标准 JSON 内容包（含 `trace`） + 适配 `480x800` 的墨屏卡片式 `index.html`

## 环境准备

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 配置 LLM（OpenAI 兼容接口，例如 DeepSeek / DashScope）
```bash
set OPENAI_API_KEY=你的_api_key
set OPENAI_BASE_URL=https://api.deepseek.com
set OPENAI_MODEL=deepseek-chat
```

说明：
- `Collector`/`Publisher` 不依赖 LLM。
- `Refiner` 依赖 `OPENAI_API_KEY`，并调用 chat.completions 接口。
- `OPENAI_BASE_URL` 和可选的 `OPENAI_CHAT_COMPLETIONS_PATH` 用于适配不同供应商的 endpoint 规则。

如果某些供应商路径规则与默认推断不一致，可以在 `.env` 里设置：
- `OPENAI_CHAT_COMPLETIONS_PATH`（只写 path，可带 query）
  - 例如：`/v1/chat/completions`
  - 或：`/chat/completions`

## 启动命令

### 方式 A：极简 Web（推荐演示）
```bash
uvicorn server:app --reload --port 8000
```
打开：`http://localhost:8000`

### 方式 B：CLI 一键运行
```bash
python main.py --url "https://example.com"
```

运行时会生成：
- `output/{id}.json`
- `output/index.html`（480x800 预览）

## Agent Flow 说明

三段式串联：
1. `Collector`
   - 输入：URL
   - 输出：提取后的纯文本（并写入 `trace`）
2. `Refiner`
   - 输入：Collector 文本
   - 输出：结构化数据（`title/summary/tags/confidence`），并写入 `trace`
   - 通过“严格 JSON 提示 + JSON 解析 + Pydantic schema 校验”保证输出合规
3. `Publisher`
   - 输入：标准内容包 JSON
   - 输出：`480x800` 的单页卡片式 HTML（Tailwind CDN + 墨屏友好配色与卡片分区）

## 输入示例

URL：
`https://www.example.com/`

## 输出示例（标准内容包 Schema）

成功时 Web/CLI 会返回类似如下结构（字段要求与 Schema 一致）：

```json
{
  "id": "b3c4b9f1c0a64ddc9c2e8f5c8a4f0c1a",
  "title": "（LLM 提炼出的标题）",
  "summary": "（1-3 句摘要）",
  "tags": ["标签1", "标签2", "标签3"],
  "source": "https://www.example.com/",
  "confidence": 0.86,
  "createdAt": "2026-04-16T12:34:56+00:00",
  "trace": {
    "collector": [
      {
        "at": "2026-04-16T12:34:55.100000+00:00",
        "level": "info",
        "message": "start",
        "durationMs": null,
        "ok": null,
        "data": { "inputType": "str" }
      }
    ],
    "refiner": [
      { "at": "2026-04-16T12:34:58.200000+00:00", "level": "info", "message": "llm_call", "data": { "attempt": 1 } }
    ],
    "publisher": [
      { "at": "2026-04-16T12:34:59.050000+00:00", "level": "info", "message": "render_index_html", "data": { "id": "..." } }
    ]
  }
}
```

## 异常处理策略（包含失败可追踪）

1. Web 接口：`POST /api/run`
   - 成功：返回 `ok=true` 的结构
   - 失败：返回 `400`，并在响应体携带 `trace`
2. Collector 错误
   - URL 非法、超时、无法提取正文、文本为空等会中断流程
3. Refiner 错误
   - LLM 输出非 JSON 或缺字段：会进行一次“二次提示 + 重试”，仍不通过则失败
4. Publisher 错误
   - 内容包 schema 不满足（Pydantic 校验失败）则失败

## 代码由 AI 生成 & 质量校验方式

本实现中：
- `Refiner` 的严格 JSON 提示词、JSON 提取与重试策略由 AI 辅助生成/调整
- `Publisher` 的 `480x800` 墨屏卡片模板（Tailwind CDN + 黑白高对比信息分区）由 AI 辅助生成
- 运行时质量校验：
  - `RefinerResult` / `ContentPackage` 使用 Pydantic schema 强校验
  - `Refiner` 的 JSON 解析失败会触发重试
  - 输出最终必须包含：`id/title/summary/tags/source/confidence/createdAt/trace`

## 演示视频提纲（3-8 分钟）

1. 30 秒：展示输入 URL，回到页面展示 `JSON + 480x800 index.html`
2. 90 秒：讲清三段式 Agent Flow 与每段输入输出边界
3. 60 秒：讲墨屏适配原则（固定画布、分区、胶囊标签、低细线）
4. 60 秒：讲 trace 与失败可追踪（展示失败时 trace 回传）

