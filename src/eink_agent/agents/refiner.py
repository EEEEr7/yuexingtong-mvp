from __future__ import annotations
"""
Refiner：语义精炼核心模块。

职责：
- 调用 LLM 生成主标题/副标题/摘要/标签/置信度；
- 对标题与标签做工程化清洗（去噪、去重、去“蠢”）；
- 当标签不足时使用 Embedding + MMR 做补足；
- 在失败场景下回退到本地启发式策略，保证链路可演示。
"""

import json
import os
import re
from typing import Any, Iterable, Optional

import requests

from eink_agent.agents.base import BaseAgent
from eink_agent.cost_tracker import perf_ms, record_embedding_call, record_llm_call
from eink_agent.schemas.content import CollectorResult, RefinerResult, Trace


def extract_json_object(text: str) -> Any:
    """
    Best-effort JSON extractor:
    - 找到第一个 `{` 和最后一个 `}`，截取后尝试解析
    """
    if not text:
        raise ValueError("空响应无法解析 JSON")

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("未找到可解析的 JSON 对象片段")

    candidate = text[start : end + 1]
    return json.loads(candidate)


def _uniq_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


_TAG_STOPWORDS = {
    # 过泛/无信息密度
    "内容",
    "信息",
    "文章",
    "阅读",
    "总结",
    "摘要",
    "分析",
    "解读",
    "分享",
    "观点",
    "思考",
    "学习",
    "教程",
    "指南",
    "方法",
    "技巧",
    "经验",
    "案例",
    "方案",
    "工具",
    "系统",
    "产品",
    "项目",
    "功能",
    "优化",
    "提升",
    # 本项目语境里的“噪声标签”
    "墨屏展示",
    "卡片信息",
    "阅读体验",
    "内容精炼",
}


_TAG_SYNONYMS = {
    # 常见缩写 -> 更可检索的中文表述
    "LLM": "大语言模型",
    "AI": "人工智能",
    "NLP": "自然语言处理",
    "RAG": "检索增强生成",
    "AIGC": "生成式AI",
    "Qwen": "通义千问",
    "Qwen3": "通义千问3",
}


def _clean_tag(tag: str) -> str:
    t = (tag or "").strip()
    t = re.sub(r"[\s\u3000]+", " ", t).strip()
    # 去掉常见包裹符号与尾部标点
    t = t.strip("`'\"“”‘’[]()（）【】<>《》·•、，。,:：;；!?！？|-")
    t = re.sub(r"\s+", " ", t).strip()
    # 同义归一化（缩写优先转成中文），保证“补齐”的候选也会一致
    if t in _TAG_SYNONYMS:
        t = _TAG_SYNONYMS[t]
    return t


def _looks_like_ascii_token(t: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9\-\._]*", t or ""))


def _prune_redundant_tags(tags: list[str]) -> list[str]:
    """
    进一步“去蠢”：
    - 去掉过短英文碎片（Tra / Transforme）
    - 去掉被更长标签包含/前缀包含的短标签（Transformer vs Transforme）
    """
    cleaned = [t for t in tags if t]
    if not cleaned:
        return []

    # 先过滤明显无意义的短英文碎片
    filtered: list[str] = []
    for t in cleaned:
        if _looks_like_ascii_token(t) and len(t) < 4:
            continue
        filtered.append(t)

    # 去掉“被包含”的短标签（大小写不敏感）
    keep: list[str] = []
    for t in sorted(filtered, key=lambda x: (-len(x), x.lower())):
        tl = t.lower()
        redundant = False
        for k in keep:
            kl = k.lower()
            if tl == kl:
                redundant = True
                break
            # 如果短词是长词的子串/前缀（常见于被截断的英文），剔除短词
            if tl in kl and len(tl) <= len(kl) - 1:
                redundant = True
                break
        if not redundant:
            keep.append(t)

    # 恢复原始顺序
    keep_set = {k.lower(): k for k in keep}
    out: list[str] = []
    for t in cleaned:
        key = t.lower()
        if key in keep_set and keep_set[key] not in out:
            out.append(keep_set[key])
    return out


def _clean_title_for_card(title: str, *, max_chars: int = 24) -> str:
    """
    标题清洗：
    - 压缩空白、去尾部标点
    - 避免把英文单词截成碎片（Tra/Transforme）
    """
    s = re.sub(r"\s+", " ", (title or "")).strip()
    s = s.strip("`'\"“”‘’[]()（）【】<>《》·•、，。,:：;；!?！？|-")
    if not s:
        return "内容精炼结果"

    # 先清掉结尾的短英文碎片（无论是否需要截断）
    s = re.sub(r"(?:\s+|[，。；;！？!?、,:：\-—])([A-Za-z]{1,3})$", "", s).rstrip()

    if len(s) <= max_chars:
        return s

    # 优先在标点处截断
    cut_candidates = [m.start() for m in re.finditer(r"[，。；;！？!?、,:：]", s[: max_chars + 1])]
    if cut_candidates:
        s = s[: cut_candidates[-1]].strip()
        return s or "内容精炼结果"

    cut = max_chars
    # 如果截断点落在英文单词内部，则回退到该单词开头
    if cut < len(s) and s[cut - 1].isascii() and s[cut].isascii() and s[cut - 1].isalnum() and s[cut].isalnum():
        m = re.search(r"[A-Za-z0-9\-\._]+$", s[:cut])
        if m:
            cut = m.start()

    s = s[:cut].rstrip()
    # 再次去掉尾部残留的短英文碎片
    s = re.sub(r"(?:\s+|[，。；;！？!?、,:：\-—])([A-Za-z]{1,3})$", "", s).rstrip()
    return s or "内容精炼结果"


def _repair_truncated_ascii_suffix(title: str, *, source_text: str) -> str:
    """
    修复标题末尾“被截断的英文单词”：
    - 若标题末尾存在英文 token（>=4），且原文中存在更长的同前缀 token，则替换为更长者
    例：Transforme -> Transformer
    """
    t = re.sub(r"\s+", " ", (title or "")).strip()
    if not t:
        return t

    m = re.search(r"([A-Za-z][A-Za-z0-9\-\._]{3,})$", t)
    if not m:
        return t

    suffix = m.group(1)
    # 在原文中找同前缀的更长 token（优先最长）
    blob = source_text or ""
    cands = re.findall(r"[A-Za-z][A-Za-z0-9\-\._]{3,30}", blob)
    # 若原文中存在“完全相同 token”，说明不是截断，无需修复
    if any(c.lower() == suffix.lower() for c in cands):
        return t
    longer = [c for c in cands if c.lower().startswith(suffix.lower()) and len(c) >= len(suffix) + 1]
    if not longer:
        return t

    best = max(longer, key=len)
    return t[: m.start(1)] + best


def normalize_tags(*, raw_tags: Any, title: str, text: str) -> list[str]:
    """
    目标：产出 3-5 个“可用标签”
    - 去重、去噪、长度约束
    - 不够则优先用 DashScope embedding + MMR 从原文候选短语中补足
    - embedding 失败则回退到启发式补足（原有正则/词频逻辑）
    """
    tags: list[str] = []
    if isinstance(raw_tags, list):
        tags = [_clean_tag(str(x)) for x in raw_tags]
    elif isinstance(raw_tags, str):
        # 兼容模型输出成 "a, b, c" 的情况
        split = re.split(r"[,\n/，、;；|]+", raw_tags)
        tags = [_clean_tag(x) for x in split]

    def is_good(t: str) -> bool:
        if not t:
            return False
        if t in _TAG_STOPWORDS:
            return False
        # 太短：单字信息量太低；太长：不像标签
        if len(t) < 2:
            return False
        if len(t) > 14:
            return False
        # 过滤“Tra/AI”这类英文碎片（AI 会被同义归一化为中文，这里主要防止被截断的英文词根）
        if _looks_like_ascii_token(t) and len(t) < 4:
            return False
        # 禁止纯数字/纯符号
        if re.fullmatch(r"[\d\W_]+", t or ""):
            return False
        return True

    tags = [t for t in tags if is_good(t)]
    tags = _uniq_keep_order(tags)
    tags = _prune_redundant_tags(tags)
    tags = tags[:5]

    if len(tags) >= 3:
        return tags

    def _fallback_supplements() -> list[str]:
        # 旧逻辑：从 title/text 里抽取候选词（不引入 jieba，做轻量启发式）
        blob = f"{title}\n{text}"
        blob = re.sub(r"\s+", " ", blob).strip()

        # 1) 英文/数字组合词（如 Qwen3 / OpenAI / FastAPI / e-ink）
        en_tokens = re.findall(r"[A-Za-z][A-Za-z0-9\\-\\._]{1,19}", blob)
        # 2) 中文候选（2-6 字）
        zh_tokens = re.findall(r"[\\u4e00-\\u9fff]{2,6}", blob)

        cand = []
        cand.extend(en_tokens)
        cand.extend(zh_tokens)
        cand = [_clean_tag(c) for c in cand]

        # 简单词频
        freq: dict[str, int] = {}
        for c in cand:
            if not is_good(c):
                continue
            freq[c] = freq.get(c, 0) + 1

        # 优先从 title 里出现的词补足（更贴主题）
        title_blob = re.sub(r"\\s+", " ", title).strip()
        title_zh = re.findall(r"[\\u4e00-\\u9fff]{2,6}", title_blob)
        title_en = re.findall(r"[A-Za-z][A-Za-z0-9\\-\\._]{1,19}", title_blob)
        title_cand = [_clean_tag(x) for x in (title_en + title_zh)]

        supplements: list[str] = []
        for t in title_cand:
            if is_good(t):
                supplements.append(t)

        # 再按全局词频补
        by_freq = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
        supplements.extend([w for w, _ in by_freq])

        # 最后的兜底“通用但不至于太泛”的标签
        supplements.extend(["生成式AI", "关键信息抽取", "结构化提炼", "要点摘要"])
        return supplements

    def _cosine(a: list[float], b: list[float]) -> float:
        # 纯 Python 余弦相似度，避免引入 sklearn 依赖
        dot = 0.0
        na = 0.0
        nb = 0.0
        for x, y in zip(a, b):
            dot += x * y
            na += x * x
            nb += y * y
        if na <= 0.0 or nb <= 0.0:
            return 0.0
        return dot / ((na**0.5) * (nb**0.5))

    def _mmr_select(
        *,
        candidates: list[str],
        doc_vec: list[float],
        cand_vecs: list[list[float]],
        k: int,
        lambda_mult: float = 0.75,
    ) -> list[str]:
        # 轻量 MMR：相关性高 + 与已选多样性
        rel = [_cosine(v, doc_vec) for v in cand_vecs]
        selected: list[int] = []
        remaining = set(range(len(candidates)))

        for _ in range(min(k, len(candidates))):
            best_i = None
            best_score = -1e9
            for i in list(remaining):
                redundancy = 0.0
                if selected:
                    redundancy = max(_cosine(cand_vecs[i], cand_vecs[j]) for j in selected)
                score = lambda_mult * rel[i] - (1.0 - lambda_mult) * redundancy
                if score > best_score:
                    best_score = score
                    best_i = i
            if best_i is None:
                break
            selected.append(best_i)
            remaining.remove(best_i)

        return [candidates[i] for i in selected]

    def _try_embedding_supplements() -> list[str]:
        # 只用原文里的 2-6 字中文短语做候选池（可再混入英文专名，但按需求先聚焦中文）
        blob = f"{title}\n{text}"
        blob = re.sub(r"\s+", " ", blob).strip()
        zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,6}", blob)
        # 统一清洗/同义词归一
        candidates = [_clean_tag(x) for x in zh_tokens]
        candidates = [c for c in candidates if is_good(c)]
        candidates = _uniq_keep_order(candidates)

        # 候选太少就没必要 embedding
        if len(candidates) < 6:
            return []

        try:
            import os as _os

            import dashscope  # type: ignore
            from dashscope import TextEmbedding  # type: ignore

            # 兼容：优先使用环境变量；未单独配置 embedding key 时复用 OPENAI_API_KEY（同一百炼 key）
            if not getattr(dashscope, "api_key", None):
                dashscope.api_key = _os.getenv("DASHSCOPE_API_KEY") or _os.getenv("OPENAI_API_KEY")

            if not getattr(dashscope, "api_key", None):
                return []

            # 为降低成本：只取前 N 个候选做 embedding
            max_cands = 80
            candidates = candidates[:max_cands]

            # 文档向量：取标题 + 正文头部（足够表达主题，且控制 token）
            doc_text = blob[:2000]
            inputs: list[str] = [doc_text] + candidates
            t0 = perf_ms()
            resp = TextEmbedding.call(model="text-embedding-v3", input=inputs, text_type="document")
            wall = perf_ms() - t0
            usage = getattr(resp, "usage", None)
            if usage is None and isinstance(resp, dict):
                usage = resp.get("usage")
            record_embedding_call(wall_ms=wall, usage=usage)
            if getattr(resp, "status_code", None) != 200:
                return []

            embs = resp.output.embeddings  # type: ignore[attr-defined]
            if not embs or len(embs) != len(inputs):
                return []

            doc_vec = embs[0].embedding
            cand_vecs = [e.embedding for e in embs[1:]]

            # 先按与主题相似度预筛一轮（TopM），再做 MMR
            rel = [(_cosine(v, doc_vec), i) for i, v in enumerate(cand_vecs)]
            rel.sort(key=lambda x: x[0], reverse=True)
            top_m = 40
            keep_idx = [i for _, i in rel[:top_m] if _ > 0.0]
            if len(keep_idx) < 6:
                return []

            cand2 = [candidates[i] for i in keep_idx]
            vec2 = [cand_vecs[i] for i in keep_idx]

            # 选择数量：补足到至少 3 个，最多 5 个
            need = max(3 - len(tags), 0)
            want = min(max(need, 3), 5)  # 至少挑 3 个候选再去重合并
            picked = _mmr_select(candidates=cand2, doc_vec=doc_vec, cand_vecs=vec2, k=want, lambda_mult=0.78)
            return picked
        except Exception:
            return []

    supplements = _try_embedding_supplements()
    if not supplements:
        supplements = _fallback_supplements()

    out = tags[:]
    for s in supplements:
        s = _clean_tag(s)
        if not is_good(s):
            continue
        if s in out:
            continue
        out.append(s)
        if len(out) >= 3:
            break

    out = _prune_redundant_tags(out)
    return out[:5]


def _tokenize_for_overlap(text: str) -> set[str]:
    blob = re.sub(r"\s+", " ", text or "").strip()
    zh = re.findall(r"[\u4e00-\u9fff]{2,6}", blob)
    en = re.findall(r"[A-Za-z][A-Za-z0-9\-\._]{1,19}", blob)
    return set([_clean_tag(x) for x in zh + en if _clean_tag(x)])


def compute_explainable_confidence(*, title: str, summary: str, tags: list[str], source_text: str) -> dict[str, Any]:
    """
    可解释评分（0-1）：
    - summary_length_score: 摘要长度与可读性
    - tag_count_score: 标签数量是否符合 3-5
    - tag_diversity_score: 标签去重比例
    - keyword_coverage_score: 标题/摘要/标签与原文关键词重合度
    """
    title_ = (title or "").strip()
    summary_ = re.sub(r"\s+", " ", summary or "").strip()
    tags_ = [t for t in tags if t]
    src_tokens = _tokenize_for_overlap(source_text)

    # 1) 摘要长度分：提高门槛，鼓励 80-220 字
    s_len = len(summary_)
    if s_len < 40:
        summary_length_score = 0.15
    elif s_len < 80:
        summary_length_score = 0.45
    elif s_len <= 220:
        summary_length_score = 1.0
    elif s_len <= 360:
        summary_length_score = 0.72
    else:
        summary_length_score = 0.4

    # 2) 标签数量分：3-5 最优
    tag_count = len(tags_)
    if 3 <= tag_count <= 5:
        tag_count_score = 1.0
    elif tag_count == 2:
        tag_count_score = 0.5
    elif tag_count >= 6:
        tag_count_score = 0.7
    else:
        tag_count_score = 0.2

    # 3) 标签多样性：去重后比例
    uniq_count = len(set(tags_))
    tag_diversity_score = 1.0 if tag_count == 0 else round(uniq_count / tag_count, 4)

    # 4) 关键词覆盖：title/summary/tags 与 source 的重合（更严格）
    pred_tokens = _tokenize_for_overlap(" ".join([title_, summary_] + tags_))
    if not pred_tokens or not src_tokens:
        keyword_coverage_score = 0.0
    else:
        hit = len(pred_tokens & src_tokens)
        coverage = hit / max(1, min(18, len(pred_tokens)))
        # 覆盖率不足时不给高分，避免轻易拉满
        if coverage < 0.15:
            keyword_coverage_score = 0.2
        elif coverage < 0.3:
            keyword_coverage_score = 0.45
        elif coverage < 0.5:
            keyword_coverage_score = 0.72
        else:
            keyword_coverage_score = 0.9

    # 5) 摘要压缩率与复述惩罚
    src_len = max(1, len(re.sub(r"\s+", " ", source_text or "").strip()))
    compression_ratio = s_len / src_len
    if compression_ratio > 0.75:
        compression_score = 0.35
    elif compression_ratio > 0.55:
        compression_score = 0.6
    elif compression_ratio >= 0.18:
        compression_score = 1.0
    else:
        compression_score = 0.7

    summary_tokens = _tokenize_for_overlap(summary_)
    if not summary_tokens or not src_tokens:
        copy_overlap = 0.0
    else:
        copy_overlap = len(summary_tokens & src_tokens) / max(1, len(summary_tokens))
    # 复述过高扣分（不是越像原文越好）
    if copy_overlap > 0.92:
        copy_penalty = 0.2
    elif copy_overlap > 0.85:
        copy_penalty = 0.1
    else:
        copy_penalty = 0.0

    weights = {
        "summary_length_score": 0.2,
        "tag_count_score": 0.18,
        "tag_diversity_score": 0.12,
        "keyword_coverage_score": 0.32,
        "compression_score": 0.18,
    }
    score = (
        summary_length_score * weights["summary_length_score"]
        + tag_count_score * weights["tag_count_score"]
        + tag_diversity_score * weights["tag_diversity_score"]
        + keyword_coverage_score * weights["keyword_coverage_score"]
        + compression_score * weights["compression_score"]
    )
    score = max(0.0, min(1.0, score - copy_penalty))

    # 文本很短时不允许高分，避免“看起来都对”导致总是满分
    if src_len < 120:
        score = min(score, 0.78)
    elif src_len < 240:
        score = min(score, 0.88)
    else:
        score = min(score, 0.94)

    score = round(score, 4)

    return {
        "score": score,
        "details": {
            "summaryLength": s_len,
            "sourceLength": src_len,
            "compressionRatio": round(compression_ratio, 4),
            "copyOverlap": round(copy_overlap, 4),
            "copyPenalty": copy_penalty,
            "tagCount": tag_count,
            "uniqueTagCount": uniq_count,
            "sourceTokenCount": len(src_tokens),
            "predictedTokenCount": len(pred_tokens),
            "summary_length_score": round(summary_length_score, 4),
            "tag_count_score": round(tag_count_score, 4),
            "tag_diversity_score": round(tag_diversity_score, 4),
            "keyword_coverage_score": round(keyword_coverage_score, 4),
            "compression_score": round(compression_score, 4),
            "weights": weights,
        },
    }


def _decorate_title_with_emoji(title: str, *, tags: list[str], source_text: str) -> str:
    """
    根据内容类型为标题加前缀 emoji：
    - 技术类：💻 / ⚡
    - 思考类：🧠 / 💡
    若已有人为添加 emoji，则不重复添加。
    """
    t = (title or "").strip()
    if not t:
        return t
    if any(ch in t for ch in ("💻", "⚡", "🧠", "💡")):
        return t

    blob = " ".join(tags) + " " + source_text
    blob = blob.lower()

    tech_keywords = ["api", "sdk", "部署", "工程", "开发", "调试", "框架", "算法", "模型", "transformer", "rag", "embedding"]
    think_keywords = ["思考", "反思", "认知", "洞察", "感想", "启发", "心得"]

    is_tech = any(k in blob for k in tech_keywords)
    is_think = any(k in blob for k in think_keywords)

    if is_tech and not is_think:
        return f"💻 {t}"
    if is_think and not is_tech:
        return f"🧠 {t}"

    # 若无法明显区分，保持原样，避免误判
    return t


class Refiner(BaseAgent):
    """内容精炼 Agent：对 Collector 输出文本进行结构化生成与质量治理。"""
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        logger: Optional[object] = None,
        max_text_chars: int = 12000,
        retry_count: int = 2,
    ) -> None:
        """初始化模型连接配置与输入长度/重试策略。"""
        super().__init__(agent_key="refiner", logger=logger)

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com"
        self.model = model or os.getenv("OPENAI_MODEL") or "deepseek-chat"
        self.max_text_chars = max_text_chars
        self.retry_count = max(1, retry_count)

        if not self.api_key:
            raise ValueError("缺少 OPENAI_API_KEY（或传入 api_key）")

    def _run(self, input_data: object, trace: Trace) -> RefinerResult:
        """
        主执行逻辑：
        1) 读取并校验 source/text；
        2) 组装 prompt，调用 LLM；
        3) 解析 JSON 并做标题/标签/置信度后处理；
        4) 异常时进入 fallback，保证稳定产出。
        """
        if isinstance(input_data, CollectorResult):
            source = input_data.source
            text = input_data.text
        elif isinstance(input_data, dict):
            source = input_data.get("source", "")
            text = input_data.get("text", "")
        else:
            raise ValueError("Refiner 输入必须为 CollectorResult 或 dict")

        if not source:
            raise ValueError("Refiner 缺少 source（来源 URL）")
        if not text or not isinstance(text, str):
            raise ValueError("Refiner 缺少 text（待精炼文本）")

        if len(text) > self.max_text_chars:
            self._push_event(
                trace, level="info", message="truncate_refiner_text", data={"max_text_chars": self.max_text_chars}
            )
            text = text[: self.max_text_chars].strip()

        system_prompt = (
            "你是内容精炼器（Eink Reader Content Refiner），负责为墨屏卡片生成“宝玉风格”的主副标题 + 摘要 + 标签。"
            "你只能输出“严格 JSON 对象”，不能包含 Markdown、代码块、额外解释。"
            "JSON 必须满足以下字段："
            "- main_title: 字符串，卡片主标题/金句，优先 8-12 个汉字，禁止口水化开头（例如：可以理解为/通常采用/核心目标是/这篇文章主要介绍 等），"
            "  建议使用“对象 + 关键结论/能力”或对比结构（如：从 X 到 Y、让 A 在 B 中发生）。"
            "- sub_title: 字符串，副标题/核心要点，15-20 个汉字，对 main_title 做一行解释或补充价值点。"
            "- summary: 字符串，1-3 句摘要，用完整句子概括背景、要点与边界，可以比副标题更完整。"
            "- tags: 字符串数组，长度 3-5 个，用作检索/聚合的主题标签（必须“可用”）。"
            "  标签规范：每个标签尽量 2-10 个字；避免泛词（如：内容/信息/文章/阅读/总结/分析/方法/技巧/工具/系统/产品/项目）；"
            "  标签要覆盖：①主题 ②对象/领域 ③动作/方法/结论（至少覆盖其中 2 类）；不得重复或同义重复。"
            "- confidence: 数值 0 到 1，表示你对摘要与结构化的把握度。"
            "若调用方未显式要求，请不要生成多余字段。"
        )

        user_prompt = (
            f"来源 URL：{source}\n\n"
            "待精炼文本如下（可能较长）：\n"
            f"{text}\n\n"
            "请直接返回 JSON。"
        )

        base = self.base_url.rstrip("/")

        # 兼容更多供应商的核心：允许显式指定 chat.completions 路径
        # - 如果你遇到某些供应商“路径规则不一致”（例如必须带 query 参数），
        #   直接在 .env 里配置 OPENAI_CHAT_COMPLETIONS_PATH 即可。
        # - 示例：
        #   OPENAI_CHAT_COMPLETIONS_PATH=/v1/chat/completions
        #   OPENAI_CHAT_COMPLETIONS_PATH=/chat/completions
        #   OPENAI_CHAT_COMPLETIONS_PATH=/openai/deployments/<deployment>/chat/completions?api-version=2024-xx-xx
        explicit_path = os.getenv("OPENAI_CHAT_COMPLETIONS_PATH")
        if explicit_path:
            url = base + "/" + explicit_path.lstrip("/")
        else:
            # 自动推断两类最常见约定：
            # - base_url="https://api.xxx.com" -> /v1/chat/completions
            # - base_url="https://dashscope.aliyuncs.com/compatible-mode/v1" -> /chat/completions
            if base.endswith("/chat/completions"):
                url = base
            elif base.endswith("/v1"):
                url = base + "/chat/completions"
            else:
                url = base + "/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        def fallback_refine(text_: str) -> RefinerResult:
            """
            本地兜底：在无法访问 LLM 时仍能产出结构化字段，保证端到端可演示。
            """
            cleaned = re.sub(r"\s+", " ", text_).strip()
            # title：用更“卡片友好”的截断策略，避免英文被截成碎片
            raw_title = _clean_title_for_card(cleaned, max_chars=24)
            raw_title = _repair_truncated_ascii_suffix(raw_title, source_text=cleaned)
            # 副标题：在开头片段中取一行“核心要点”
            sub = cleaned[:80]
            if len(cleaned) > len(sub):
                sub = sub.rstrip("，。,.!?;；:") + "…"

            tags = normalize_tags(raw_tags=[], title=raw_title, text=cleaned)
            title = _decorate_title_with_emoji(raw_title, tags=tags, source_text=cleaned)
            explained = compute_explainable_confidence(
                title=title or "内容精炼结果",
                summary=sub or "（摘要生成失败时的兜底摘要）",
                tags=tags,
                source_text=cleaned,
            )
            self._push_event(
                trace,
                level="info",
                message="confidence_scored",
                data={"mode": "fallback", **explained["details"], "confidence": explained["score"]},
            )

            return RefinerResult(
                title=title or "内容精炼结果",
                summary=sub or "（摘要生成失败时的兜底摘要）",
                tags=tags,
                confidence=explained["score"],
            )

        last_err: Optional[str] = None
        for attempt in range(1, self.retry_count + 1):
            self._push_event(trace, level="info", message="llm_call", data={"attempt": attempt, "url": url})
            try:
                t0 = perf_ms()
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                record_llm_call(wall_ms=perf_ms() - t0, usage=data.get("usage"))

                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                self._push_event(
                    trace,
                    level="info",
                    message="llm_response_received",
                    data={"contentLen": len(content)},
                )

                try:
                    obj = extract_json_object(content)
                    if isinstance(obj, dict):
                        # 兼容多种返回形态：
                        # - 新约定：main_title + sub_title + summary
                        # - 旧约定：title + summary
                        main_title = str(
                            obj.get("main_title")
                            or obj.get("title")
                            or ""
                        )
                        sub_title = str(
                            obj.get("sub_title")
                            or obj.get("subtitle")
                            or ""
                        )
                        long_summary = str(obj.get("summary") or "")

                        # 如果副标题缺失但存在摘要，则用摘要第一句/前若干字兜底
                        if not sub_title and long_summary:
                            first = re.split(r"[。！!？?]", long_summary)[0]
                            if not first:
                                first = long_summary[:60]
                            sub_title = first.strip()[:60]

                        # 将主/副标题映射回现有 Schema：title=主标题（金句，带 emoji 装饰），summary=副标题
                        cleaned_main = _clean_title_for_card(main_title or long_summary, max_chars=24)
                        cleaned_main = _repair_truncated_ascii_suffix(cleaned_main, source_text=text)
                        obj["tags"] = normalize_tags(
                            raw_tags=obj.get("tags"),
                            title=cleaned_main,
                            text=text,
                        )
                        decorated = _decorate_title_with_emoji(cleaned_main, tags=obj["tags"], source_text=text)
                        obj["title"] = decorated
                        obj["summary"] = sub_title or long_summary
                        explained = compute_explainable_confidence(
                            title=str(obj.get("title") or ""),
                            summary=str(obj.get("summary") or ""),
                            tags=obj["tags"],
                            source_text=text,
                        )
                        obj["confidence"] = explained["score"]
                        self._push_event(
                            trace,
                            level="info",
                            message="confidence_scored",
                            data={"mode": "llm", **explained["details"], "confidence": explained["score"]},
                        )
                    result = RefinerResult.model_validate(obj)
                    return result
                except Exception as e:
                    last_err = str(e)
                    self._push_event(
                        trace,
                        level="warning",
                        message="json_parse_failed",
                        data={"attempt": attempt, "error": last_err, "rawHead": content[:120]},
                    )

                    # 二次提示：强制 JSON、禁止包裹
                    payload["messages"].append(
                        {
                            "role": "user",
                            "content": "再次强调：只输出严格 JSON 对象，不要任何额外字符或 Markdown。",
                        }
                    )
            except Exception as e:
                last_err = str(e)
                self._push_event(
                    trace,
                    level="warning",
                    message="llm_call_failed",
                    data={"attempt": attempt, "error": last_err},
                )

        # 连 LLM 都失败了：用本地兜底保证 Publisher 可演示
        self._push_event(
            trace,
            level="warning",
            message="fallback_refiner_used",
            data={"error": last_err},
        )
        return fallback_refine(text)

