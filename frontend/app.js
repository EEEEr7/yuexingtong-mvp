/**
 * 前端主控制脚本。
 *
 * 负责：
 * 1) 调用后端 /api/run；
 * 2) 渲染双设备预览（雾灰白/星穹黑）；
 * 3) 支持右侧编辑区实时回写 title/summary/tags；
 * 4) 展示成本统计（接口 cost + trace 兜底）。
 */
// Backend API base (front/back 分离)
const API_BASE = "http://127.0.0.1:8000";

const inputBox = document.getElementById("inputBox");
const runBtn = document.getElementById("runBtn");
const errorBox = document.getElementById("error");
const jsonOut = document.getElementById("jsonOut");
const preview = document.getElementById("preview");
const debugStatus = document.getElementById("debugStatus");
const loadingOverlay = document.getElementById("loadingOverlay");

const titleEditor = document.getElementById("titleEditor");
const summaryEditor = document.getElementById("summaryEditor");
const tagList = document.getElementById("tagList");
const tagInput = document.getElementById("tagInput");
const addTagBtn = document.getElementById("addTagBtn");

let lastPackage = null;
let lastIndexHtmlDark = "";
let lastIndexHtmlLight = "";
let tagsState = [];
let isRunning = false;

function setLoading(show) {
  if (loadingOverlay) {
    loadingOverlay.style.display = show ? "flex" : "none";
  }
}

/** 浅灰设备 = 白底墨字（light）；酷黑设备 = 黑底白字（dark） */
function setPreviewIframes(htmlLight, htmlDark) {
  const l = htmlLight ?? "";
  const d = htmlDark ?? "";
  if (preview) preview.srcdoc = l;
  const b = document.getElementById("previewB");
  if (b) b.srcdoc = d;
}

/**
 * 将右侧编辑区写回 HTML（两套主题分别匹配 Publisher 产出的 class）
 */
function applyEditorToHtml(html, { title, summary, tags }, variant) {
  let patched = html;
  patched = patched.replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(title)}</title>`);

  if (variant === "light") {
    patched = patched.replace(
      /(<div class="text-\[2rem\] leading-snug font-extrabold text-stone-900 tracking-tight break-words">\s*)[\s\S]*?(\s*<\/div>)/,
      `$1${escapeHtml(title)}$2`
    );
    patched = patched.replace(
      /(<div class="mt-1 text-\[1\.1rem\] leading-snug font-normal text-stone-600 break-words">\s*)[\s\S]*?(\s*<\/div>)/,
      `$1${escapeHtml(summary)}$2`
    );
    const tagHtml = tags
      .map(
        (tag) =>
          `<span class="inline-flex items-center rounded-full border border-stone-400/70 bg-stone-100 px-3 py-1.5 text-[12px] leading-none text-stone-900 font-medium">${escapeHtml(
            tag
          )}</span>`
      )
      .join("");
    patched = patched.replace(
      /(<div class="mt-3 flex flex-wrap gap-2">\s*)[\s\S]*?(\s*<\/div>)/,
      `$1${tagHtml}$2`
    );
  } else {
    patched = patched.replace(
      /(<div class="text-\[2rem\] leading-snug font-extrabold text-white tracking-tight break-words">\s*)[\s\S]*?(\s*<\/div>)/,
      `$1${escapeHtml(title)}$2`
    );
    patched = patched.replace(
      /(<div class="mt-1 text-\[1\.1rem\] leading-snug font-normal text-\[rgba\(255,255,255,0\.7\)\] break-words">\s*)[\s\S]*?(\s*<\/div>)/,
      `$1${escapeHtml(summary)}$2`
    );
    const tagHtml = tags
      .map(
        (tag) =>
          `<span class="inline-flex items-center rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-[12px] leading-none text-white/95 font-medium">${escapeHtml(
            tag
          )}</span>`
      )
      .join("");
    patched = patched.replace(
      /(<div class="mt-3 flex flex-wrap gap-2">\s*)[\s\S]*?(\s*<\/div>)/,
      `$1${tagHtml}$2`
    );
  }

  return patched;
}

function escapeHtml(str) {
  // 统一做 HTML 转义，避免把用户输入直接拼进 innerHTML 带来 XSS 风险。
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMs(ms) {
  // 统一毫秒显示格式：<1000 用 ms，>=1000 用秒并保留两位小数。
  const n = Number(ms);
  if (!Number.isFinite(n)) return "-";
  if (n < 1000) return `${Math.round(n)} ms`;
  return `${(n / 1000).toFixed(2)} s`;
}

/** 每次渲染重新解析，避免脚本执行时 DOM 未就绪导致永久拿不到 #costBody */
function resolveCostElements() {
  const card = document.getElementById("costCard");
  if (!card) return { card: null, body: null };
  let body = document.getElementById("costBody");
  if (!body) {
    body = card.querySelector(".guide-text");
  }
  return { card, body };
}

/**
 * 当接口未返回 cost 时，从 package.trace 反推可展示数字（耗时、LLM 次数、评分里的近似 token）。
 * 与后端 cost_tracker 的 billing token 不是同一口径，界面会注明。
 */
function inferCostFromPackageTrace(pkg) {
  const trace = pkg?.trace;
  if (!trace || typeof trace !== "object") return null;

  let llmCalls = 0;
  let embCalls = 0;
  let flowMs = 0;
  let refinerMs = 0;
  let approxTokens = null;

  for (const key of Object.keys(trace)) {
    const arr = trace[key];
    if (!Array.isArray(arr)) continue;
    const isRefiner = key === "refiner";
    for (const ev of arr) {
      if (!ev || typeof ev !== "object") continue;
      const msg = ev.message;
      if (msg === "llm_call") llmCalls++;
      if (typeof msg === "string" && msg.toLowerCase().includes("embedding")) embCalls++;
      if (msg === "success" && ev.durationMs != null) {
        const d = Number(ev.durationMs);
        if (Number.isFinite(d)) {
          flowMs += d;
          if (isRefiner) refinerMs += d;
        }
      }
      if (msg === "confidence_scored" && ev.data) {
        const st = ev.data.sourceTokenCount;
        const pt = ev.data.predictedTokenCount;
        if (st != null || pt != null) approxTokens = { source: st, predicted: pt };
      }
    }
  }

  if (llmCalls === 0 && flowMs === 0 && !approxTokens) return null;

  const apiWall = refinerMs > 0 ? refinerMs : flowMs;
  return {
    _fromTrace: true,
    llm: { calls: llmCalls, tokens: null, wallMsTotal: apiWall },
    embedding: { calls: embCalls, tokens: null, wallMsTotal: 0 },
    totalWallMs: apiWall,
    flowWallMs: flowMs,
    tokensTotal: null,
    _approxTokens: approxTokens,
  };
}

function pickCostForDisplay(apiCost, pkg) {
  // 优先使用后端精准 cost；缺失时退化为 trace 推断结果，保证界面始终有可解释信息。
  if (apiCost != null && typeof apiCost === "object") return apiCost;
  return inferCostFromPackageTrace(pkg) ?? null;
}

function renderCost(cost) {
  const { card: costCard, body: costBody } = resolveCostElements();
  if (!costCard || !costBody) return;
  if (!cost) {
    costBody.innerHTML = `
      点击「运行」后将显示具体参数：
      <div>1) Token：LLM / Embedding（若供应商返回 usage；否则显示“未知”）</div>
      <div>2) 调用次数：LLM 次数、Embedding 次数</div>
      <div>3) 耗时：端到端总耗时；外部 API 耗时（LLM + Embedding 累计）</div>
    `.trim();
    costCard.style.display = "block";
    return;
  }

  const llm = cost.llm || {};
  const emb = cost.embedding || {};
  const formatTok = (n) => (n == null ? "未知" : String(n));
  const fromTrace = Boolean(cost._fromTrace);
  const approx = cost._approxTokens;

  const tokensTotal = cost.tokensTotal;
  let tokenSummary;
  let tokenBreakdown;
  if (fromTrace) {
    tokenSummary = "1) Token（供应商 billing）：未知（接口未返回 cost 时无法统计）";
    if (approx && (approx.source != null || approx.predicted != null)) {
      tokenBreakdown = `　trace 评分近似：源词元 ${approx.source ?? "-"} · 预测词元 ${approx.predicted ?? "-"}（非 API usage，仅供对照）`;
    } else {
      tokenBreakdown = "　分项：LLM 未知 · Embedding 未知";
    }
  } else {
    tokenSummary =
      tokensTotal == null
        ? "1) Token：总计 未知（供应商未返回 usage）"
        : `1) Token：总计 ${tokensTotal}`;
    tokenBreakdown = `　分项：LLM ${formatTok(llm.tokens)} · Embedding ${formatTok(emb.tokens)}`;
  }

  const callsLine = `2) 调用次数：LLM ${llm.calls ?? 0} · Embedding ${emb.calls ?? 0}`;

  const flow = formatMs(cost.flowWallMs);
  const llmMs = formatMs(llm.wallMsTotal);
  const embMs = formatMs(emb.wallMsTotal);
  const extTotalMs = Number(cost.totalWallMs);
  const extAgg = Number.isFinite(extTotalMs)
    ? formatMs(extTotalMs)
    : formatMs((Number(llm.wallMsTotal) || 0) + (Number(emb.wallMsTotal) || 0));

  const timeLine = `3) 耗时：端到端 ${flow}；外部 API ${extAgg}（LLM ${llmMs} · Embedding ${embMs}）`;
  const timeNote = fromTrace
    ? "说明：数字由 trace 反推（各阶段 success 的 durationMs 累计等），与后端 cost 字段口径可能不一致；重启/更新 API 后可显示精确 cost。"
    : "口径：端到端为整条流水线墙钟时间；外部 API 为 LLM/Embedding 请求墙钟时间之和（不含纯本地解析等）。";

  costBody.innerHTML = `
    <div>${escapeHtml(tokenSummary)}</div>
    <div>${escapeHtml(tokenBreakdown)}</div>
    <div>${escapeHtml(callsLine)}</div>
    <div>${escapeHtml(timeLine)}</div>
    <div class="guide-muted">${escapeHtml(timeNote)}</div>
  `.trim();

  costCard.style.display = "block";
}

function updateEditorsFromPackage(pkg) {
  // 每次运行后把内容包同步到编辑区，作为“可微调”的初始态。
  titleEditor.value = pkg?.title || "";
  summaryEditor.value = pkg?.summary || "";
  tagsState = Array.isArray(pkg?.tags) ? [...pkg.tags] : [];
  renderTags();
}

function renderTags() {
  // 标签区使用状态数组渲染，删除按钮会回写 state 并刷新双主题预览。
  tagList.innerHTML = "";
  tagsState.forEach((t, idx) => {
    const pill = document.createElement("div");
    pill.className = "tag-pill";
    pill.innerHTML = `<span>${escapeHtml(t)}</span>`;

    const x = document.createElement("button");
    x.type = "button";
    x.className = "tag-x";
    x.innerText = "×";
    x.addEventListener("click", () => {
      tagsState.splice(idx, 1);
      renderTags();
      syncPreview();
    });

    pill.appendChild(x);
    tagList.appendChild(pill);
  });
}

function addTag(raw) {
  // 新标签去空/去重后写入状态，随后触发预览同步。
  const t = (raw || "").trim();
  if (!t) return;
  if (tagsState.includes(t)) return;
  tagsState.push(t);
  tagInput.value = "";
  renderTags();
  syncPreview();
}

function syncPreview() {
  // 使用同一份编辑态，分别回写 dark/light 两套 HTML，保持主题一致性。
  if (!lastIndexHtmlDark || !lastPackage) return;

  const title = titleEditor.value.trim() || lastPackage.title || "";
  const summary = summaryEditor.value.trim() || lastPackage.summary || "";
  const tags = tagsState.filter(Boolean);

  const baseLight = lastIndexHtmlLight || lastIndexHtmlDark;
  const patchedDark = applyEditorToHtml(lastIndexHtmlDark, { title, summary, tags }, "dark");
  const patchedLight = applyEditorToHtml(baseLight, { title, summary, tags }, "light");

  setPreviewIframes(patchedLight, patchedDark);
}

function fitScreen() {
  // 根据容器尺寸动态计算缩放，保证 480x800 在不同屏幕都能完整展示。
  document.querySelectorAll(".carousel-slide .screen-frame").forEach((frame) => {
    const el = frame.querySelector(".screen-transform");
    if (!el) return;
    const padding = 20;
    const availableW = Math.max(0, frame.clientWidth - padding);
    const availableH = Math.max(0, frame.clientHeight - padding);
    const scaleW = availableW / 480;
    const scaleH = availableH / 800;
    const maxScale = 1.18;
    const scale = Math.min(maxScale, scaleW, scaleH);
    el.style.transform = `scale(${scale})`;
  });
}

function initDeviceCarousel() {
  // 简单轮播：通过 translateX 切换设备外壳，同时更新按钮选中态。
  const track = document.getElementById("deviceCarouselTrack");
  const prevBtn = document.getElementById("carouselPrev");
  const nextBtn = document.getElementById("carouselNext");
  const dotsWrap = document.getElementById("carouselDots");
  if (!track || !prevBtn || !nextBtn || !dotsWrap) return;

  const slides = track.querySelectorAll(".carousel-slide");
  const dots = dotsWrap.querySelectorAll(".carousel-dot");
  const n = Math.max(1, slides.length);
  let idx = 0;

  function applySlide(i) {
    idx = (i + n) % n;
    track.style.transform = `translateX(-${(idx / n) * 100}%)`;
    dots.forEach((d, j) => {
      const on = j === idx;
      d.classList.toggle("is-active", on);
      d.setAttribute("aria-selected", on ? "true" : "false");
    });
    fitScreen();
  }

  prevBtn.addEventListener("click", () => applySlide(idx - 1));
  nextBtn.addEventListener("click", () => applySlide(idx + 1));
  dots.forEach((d, j) => {
    d.addEventListener("click", () => applySlide(j));
  });
}

async function run() {
  // 主交互：请求后端、渲染结果、刷新编辑区和成本区，并处理异常提示。
  if (isRunning) return;
  isRunning = true;
  const prevBtnText = runBtn.innerText;
  runBtn.disabled = true;
  runBtn.innerText = "运行中...";

  errorBox.style.display = "none";
  renderCost(null);
  debugStatus.innerHTML = "<strong>状态：</strong>运行中，正在生成内容包与卡片预览...";
  setLoading(true);

  const input = inputBox.value.trim();
  if (!input) {
    errorBox.innerText = "请输入 URL 或纯文本";
    errorBox.style.display = "block";
    debugStatus.innerHTML = "<strong>状态：</strong>等待运行。";
    setLoading(false);
    runBtn.disabled = false;
    runBtn.innerText = prevBtnText;
    isRunning = false;
    return;
  }

  jsonOut.innerText = "运行中...";
  setPreviewIframes("", "");
  fitScreen();

  try {
    const res = await fetch(`${API_BASE}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input }),
    });

    let data;
    try {
      data = await res.json();
    } catch {
      errorBox.innerText = "接口返回的不是合法 JSON（请确认后端地址为 " + API_BASE + " 且服务正常）";
      errorBox.style.display = "block";
      debugStatus.innerHTML = "<strong>状态：</strong>解析响应失败。";
      renderCost(null);
      return;
    }

    if (!res.ok) {
      errorBox.innerText = data.error || "运行失败";
      errorBox.style.display = "block";
      debugStatus.innerHTML = "<strong>状态：</strong>运行失败，请查看错误信息或展开 Debug JSON。";
      const costUi = pickCostForDisplay(data.cost, data.package);
      renderCost(costUi);
      jsonOut.innerText = JSON.stringify(
        {
          package: data.package ?? null,
          cost: data.cost ?? null,
          costDisplay: costUi,
          error: data.error,
          trace: data.trace,
        },
        null,
        2
      );
      return;
    }

    // 先刷新成本区，避免后续步骤抛错导致数字不显示（无 cost 时用 trace 兜底）
    const costUi = pickCostForDisplay(data.cost, data.package);
    renderCost(costUi);

    lastPackage = data.package || null;
    lastIndexHtmlDark = data.indexHtml || "";
    lastIndexHtmlLight = data.indexHtmlLight || data.indexHtml || "";
    jsonOut.innerText = JSON.stringify(
      {
        package: data.package,
        indexHtml: data.indexHtml,
        indexHtmlLight: data.indexHtmlLight ?? null,
        cost: data.cost ?? null,
        costDisplay: costUi,
        costSource: data.cost != null ? "api" : costUi?._fromTrace ? "trace_fallback" : "none",
      },
      null,
      2
    );
    setPreviewIframes(lastIndexHtmlLight, lastIndexHtmlDark);
    updateEditorsFromPackage(data.package || {});
    debugStatus.innerHTML =
      "<strong>状态：</strong>生成完成。标题：" +
      (data.package?.title || "未命名") +
      "；置信度：" +
      (data.package?.confidence ?? "-") +
      "；来源：" +
      (data.package?.source || "-");

    setTimeout(fitScreen, 0);
  } catch (e) {
    errorBox.innerText = e?.message || String(e);
    errorBox.style.display = "block";
    debugStatus.innerHTML = "<strong>状态：</strong>请求异常。";
    renderCost(null);
  } finally {
    setLoading(false);
    runBtn.disabled = false;
    runBtn.innerText = prevBtnText;
    isRunning = false;
  }
}

runBtn.addEventListener("click", run);
titleEditor.addEventListener("input", syncPreview);
summaryEditor.addEventListener("input", syncPreview);
addTagBtn.addEventListener("click", () => addTag(tagInput.value));
tagInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    addTag(tagInput.value);
  }
});
window.addEventListener("resize", fitScreen);
window.addEventListener("load", () => {
  fitScreen();
  renderCost(null);
  initDeviceCarousel();
});

// 左侧示例输入快捷填充
document.querySelectorAll("[data-sample]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const val = btn.getAttribute("data-sample") || "";
    inputBox.value = val;
    inputBox.focus();
  });
});

