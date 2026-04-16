# 开发过程与问题日志（持续追加）

> 目的：统一记录从项目启动到当前的关键 bug、根因分析、修复动作、涉及代码文件与验证结果。  
> 维护规则：后续每次代码改动后，必须追加一条日志（见文末模板）。

---

## 0) 项目阶段总览

- 阶段 A：MVP 架构搭建（Collector -> Refiner -> Publisher）
- 阶段 B：前后端分离（FastAPI + 静态前端）
- 阶段 C：LLM 接入与环境变量治理（.env / .env.example）
- 阶段 D：UI/UX 多轮迭代（输入区、预览区、编辑区、调试面板）
- 阶段 E：URL 抓取稳定性修复（TLS/SSL、代理变量干扰）

---

## 1) 关键问题与修复时间线

### 1.1 `create_project` 初始化 git 失败
- **现象**：MCP `create_project` 报错 `spawn /bin/sh ENOENT`
- **根因**：Windows 环境下命令执行器路径不匹配
- **修复**：改为手工创建目录并执行 `git init`
- **影响文件**：无代码文件改动（环境与流程问题）

### 1.2 安装 skills 失败
- **现象**：`npx skills add https://www.modelscope.cn/skills/` 返回 `No skills found`
- **根因**：URL 不是具体 skill manifest
- **修复**：改用可解析的具体技能来源（后续按仓库方式处理）
- **影响文件**：无

### 1.3 `pipeline.py` JSON 写出代码错误
- **现象**：序列化语句错误（拼接了 `__class__.__name__`）
- **根因**：错误代码片段被写入
- **修复**：改为 `json.dump(pkg.model_dump(mode="json"), ...)`
- **影响文件**：`src/eink_agent/pipeline.py`

### 1.4 依赖安装失败导致 `bs4` 缺失
- **现象**：`python main.py` 报 `ModuleNotFoundError: No module named 'bs4'`
- **根因**：网络/证书问题导致 `pip install` 失败
- **修复**：`Collector` 改为 **URL 分支懒加载 BeautifulSoup**；纯文本路径不依赖 `bs4`
- **影响文件**：`src/eink_agent/agents/collector.py`

### 1.5 Refiner 错误调用默认 DeepSeek 而非 Qwen
- **现象**：请求打到 `https://api.deepseek.com/v1/chat/completions`
- **根因**：运行时 `OPENAI_BASE_URL` 未生效，触发默认值
- **修复**：补齐 `.env` 配置与自动加载机制
- **影响文件**：`.env`、`.env.example`、`main.py`、`backend/app.py`

### 1.6 DashScope 路径拼接错误（双 `/v1`）
- **现象**：请求路径出现 `/compatible-mode/v1/v1/chat/completions`
- **根因**：endpoint 自动拼接规则不兼容不同供应商 base URL 形态
- **修复**：
  - 增强 URL 组合逻辑（识别是否已包含 `/v1` 或完整路径）
  - 新增可选变量 `OPENAI_CHAT_COMPLETIONS_PATH`
- **影响文件**：`src/eink_agent/agents/refiner.py`、`.env.example`、`README.md`

### 1.7 LLM 网络不稳定导致整链路失败
- **现象**：外部模型调用失败时流程中断
- **根因**：环境网络/TLS 不稳定，重试后仍失败
- **修复**：Refiner 增加本地 fallback（启发式 title/summary/tags）保证可演示性
- **影响文件**：`src/eink_agent/agents/refiner.py`

### 1.8 git 历史重写中文提交信息失败并乱码
- **现象**：`git filter-branch` 多次失败，出现编码乱码
- **根因**：Windows + PowerShell + filter 脚本链路编码复杂
- **修复**：放弃该路径，重克隆恢复仓库继续开发
- **影响文件**：仓库元数据恢复；业务代码保留并继续迭代

### 1.9 前端显示被裁切/预览比例异常
- **现象**：iframe 与 JSON 面板显示不完整，预览区域比例不理想
- **根因**：布局与缩放策略未围绕固定 480x800 设计
- **修复**：
  - iframe 固定 `480x800`
  - 外层容器做 transform 缩放（`fitScreen`）
  - 重构三栏布局与可滚动容器
- **影响文件**：`frontend/index.html`、`frontend/styles.css`、`frontend/app.js`

### 1.10 运行按钮 hover 与文本颜色冲突
- **现象**：
  - 运行按钮 hover 样式可读性差
  - 墨水屏卡片摘要在部分场景下显示为黑字
- **根因**：按钮交互样式不足；文本颜色依赖 Tailwind CDN 类名
- **修复**：
  - 优化按钮 hover 与禁用态
  - 在 Publisher 模板中添加 `body` 与容器白色文字兜底
- **影响文件**：`frontend/styles.css`、`frontend/app.js`、`src/eink_agent/agents/publisher.py`

### 1.11 后端启动失败/端口状态异常
- **现象**：用户反馈“启动失败”
- **根因**：服务进程未就绪或端口未监听
- **修复**：重新确认并拉起 `8000`（后端）与 `5173`（前端）
- **影响文件**：无代码改动（运行态问题）

### 1.12 URL 演示失败（本次修复）
- **现象**：URL 抓取失败，报 `SSLEOFError`，后续又报 `ProxyError`
- **根因**：
  1. 本机 TLS/SSL 握手异常
  2. 系统残留代理环境变量导致 `requests` 走不可用代理
  3. `.env` 默认 `override=False` 时，项目配置可能被系统变量覆盖
- **修复**：
  - `Collector` 新增开关：
    - `COLLECTOR_SSL_VERIFY`（是否验证 SSL）
    - `COLLECTOR_TRUST_ENV`（是否信任系统代理环境变量）
  - `backend/app.py`：`load_dotenv(..., override=True)`，以项目 `.env` 为准
  - 更新 `.env` 与 `.env.example` 示例与注释
- **影响文件**：
  - `src/eink_agent/agents/collector.py`
  - `backend/app.py`
  - `.env`
  - `.env.example`
- **结果**：`/api/run` 对 `https://example.com` 可成功返回内容包与 trace

---

## 2) 已完成与未完成（截至当前）

### 已完成（主线）
- 三段式 Agent Flow 串联与边界定义
- 标准 Schema（`id/title/summary/tags/source/confidence/createdAt/trace`）
- Web + CLI 入口
- 480x800 HTML 视觉输出与桌面预览
- trace 可追踪与错误回传
- README / DESIGN 主体文档

### 未完成或待增强
- 本地文件输入（当前主要是 URL + 纯文本）
- 演示视频成片（已具备提纲）
- Skill 在运行时的自动编排接入（当前以设计原则应用为主）
- Docker 一键运行、主题切换、多模板、成本统计等加分项

---

## 3) 后续记录规范（强制执行）

从现在开始，**每次代码变更后**都要在本文件追加日志，格式如下：

```md
### [YYYY-MM-DD HH:mm] 变更标题
- 需求/问题：
- 根因分析：
- 修改内容：
  - `文件路径A`：做了什么
  - `文件路径B`：做了什么
- 验证结果：
- 风险与回滚点：
```

建议按“最新在上”或“最新在下”保持统一（当前采用“最新在下”）。

### [2026-04-17 00:10] 右侧区域与全局 SaaS 风格精修
- 需求/问题：右侧需要“标题/摘要精致卡片 + 可折叠原始数据清单 + 设计说明区块”，并统一三大面板毛玻璃与轻阴影风格。
- 根因分析：现有功能已具备，但视觉语义层级还不够明确，调试入口可读性和“默认隐藏”表达不够强。
- 修改内容：
  - `frontend/index.html`：为三大面板增加统一 `glass-panel` 类；编辑区增加“标题与摘要编辑区”头部；“设计说明”升级为“设计说明（AI 布局决策）”；`details` 改为 `debug-panel` 抽屉样式并更新文案为“默认折叠”。
  - `frontend/styles.css`：强化毛玻璃（`bg-white/80` 语义对应）与 `shadow-sm` 轻阴影视觉；新增 `glass-panel`、`edit-card-title`、`debug-panel` 样式。
- 验证结果：右侧编辑输入仍通过既有 `input` 监听实时联动中间 480x800 预览；原始数据区默认折叠，仅点击“原始数据清单”后展开。
- 风险与回滚点：仅前端样式与文案改动；如需回滚，恢复 `frontend/index.html` 与 `frontend/styles.css` 对应新增类与区块即可。

