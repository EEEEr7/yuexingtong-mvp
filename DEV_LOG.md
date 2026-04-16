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

### [2026-04-17 02:07] Refiner 标题/标签“很蠢”（英文截断、同义重复）修复 + Embedding/MMR 标签增强

- 需求/问题：
  - 用户反馈生成结果“标题/标签很蠢”，典型表现：
    - 标题被截断成英文碎片：`... Tra`、`... Transforme`
    - 标签出现同义/前缀重复：`Transforme` 与 `Transformer` 同时出现；短英文碎片 `Tra` 混入 tags
    - 标签语义不贴切：容易选到泛词或与主题弱相关的短语
- 复现方式（纯文本输入）：
  - 输入包含 `Transformer` 等英文专有名词的中文段落（direct-text）
  - 观察右侧 `Title/Tags`：出现 `Tra/Transforme`，或同一词根的多个版本
- 根因分析：
  - **标题**：LLM 输出的标题本身可能包含被截断的英文词（或以短英文碎片结尾），前端展示看起来像“断词”。
  - **标签**：
    - 原逻辑对英文 token 只做了长度与停用词过滤，缺少“短英文碎片/前缀重复”的专门治理。
    - 标签不足时的补足阶段依赖正则/词频启发式，容易补出“看起来像词但不贴题”的候选。
  - **截断英文修复 bug（调试过程）**：
    - 初版修复逻辑用 `suffix in source_text` 判断“是否需要修复”，但 `Transforme` 是 `Transformer` 的子串，导致误判为“已存在无需修复”。
    - 修复为“按 token 全等判断”，只要原文中没有完全相同 token，且存在更长同前缀 token，就替换为更长者。
- 修改内容：
  - `src/eink_agent/agents/refiner.py`
    - `normalize_tags`：
      - 增加对短英文碎片的过滤（ASCII token 且长度 < 4）。
      - 增加 `_prune_redundant_tags`：剔除“被更长标签包含/前缀包含”的短标签，避免 `Transforme/Transformer` 并存。
      - 标签不足时优先走 DashScope embedding（`text-embedding-v3`）+ 余弦相似度 + 轻量 MMR 从候选短语中补足；失败自动回退到旧的正则/词频补足逻辑。
    - 标题清洗：
      - `_clean_title_for_card`：压缩空白、去尾标点、移除末尾 1-3 字母英文碎片；截断时避免落在英文单词中间。
      - `_repair_truncated_ascii_suffix`：从原文中寻找更长同前缀英文 token 修复标题尾部截断词（例如 `Transforme -> Transformer`）。
  - `requirements.txt`：新增 `dashscope>=1.25.12`（用于 embedding）。
  - `.env.example`：新增 `DASHSCOPE_API_KEY` 说明；同时支持“不填则复用 OPENAI_API_KEY”，实现只维护一个百炼 key。
  - `frontend/index.html`：扩展“示例输入”按钮，加入科普/面试/技术三种纯文本样例，便于快速回归测试。
- 验证结果：
  - 服务重启后（`8000` 后端 + `5173` 前端）页面可正常访问：
    - `http://127.0.0.1:8000/docs` 返回 200
    - `http://127.0.0.1:5173/` 返回 200
  - 对包含 `Transformer` 的输入进行回归：
    - tags 中 `Tra` 等短英文碎片被过滤
    - `Transforme/Transformer` 这类前缀重复标签会被压缩为更合理的单一标签
    - 标题末尾不会残留 `Tra`；若原文存在完整词，会尝试修复 `Transforme -> Transformer`
- 风险与回滚点：
  - embedding 依赖外部 API（配额/网络/超时），已设计为失败自动回退，不影响主链路可用性。
  - 如需回滚：恢复 `src/eink_agent/agents/refiner.py` 中新增的标题/标签后处理与 embedding 补足逻辑；移除 `requirements.txt` 中 `dashscope` 依赖与 `.env.example` 的相关说明即可。

