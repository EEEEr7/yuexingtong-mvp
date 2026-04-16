// Backend API base (front/back 分离)
const API_BASE = "http://127.0.0.1:8000";

const inputBox = document.getElementById("inputBox");
const runBtn = document.getElementById("runBtn");
const errorBox = document.getElementById("error");
const jsonOut = document.getElementById("jsonOut");
const preview = document.getElementById("preview");
const debugStatus = document.getElementById("debugStatus");
const loadingOverlay = document.getElementById("loadingOverlay");
const screenTransform = document.getElementById("screenTransform");

const titleEditor = document.getElementById("titleEditor");
const summaryEditor = document.getElementById("summaryEditor");
const tagList = document.getElementById("tagList");
const tagInput = document.getElementById("tagInput");
const addTagBtn = document.getElementById("addTagBtn");

let lastPackage = null;
let lastIndexHtml = "";
let tagsState = [];
let isRunning = false;

function setLoading(show) {
  loadingOverlay.style.display = show ? "flex" : "none";
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function updateEditorsFromPackage(pkg) {
  titleEditor.value = pkg?.title || "";
  summaryEditor.value = pkg?.summary || "";
  tagsState = Array.isArray(pkg?.tags) ? [...pkg.tags] : [];
  renderTags();
}

function renderTags() {
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
  const t = (raw || "").trim();
  if (!t) return;
  if (tagsState.includes(t)) return;
  tagsState.push(t);
  tagInput.value = "";
  renderTags();
  syncPreview();
}

function syncPreview() {
  if (!lastIndexHtml || !lastPackage) return;

  const title = titleEditor.value.trim() || lastPackage.title || "";
  const summary = summaryEditor.value.trim() || lastPackage.summary || "";
  const tags = tagsState.filter(Boolean);

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

  const tagHtml = tags
    .map(
      (tag) =>
        `<span class="inline-flex items-center rounded-full border border-white/20 bg-white/5 px-3 py-1 text-[12px] leading-none text-white/90">${escapeHtml(
          tag
        )}</span>`
    )
    .join("");
  patched = patched.replace(
    /(<div class="mt-3 flex flex-wrap gap-2">\s*)[\s\S]*?(\s*<\/div>)/,
    `$1${tagHtml}$2`
  );

  preview.srcdoc = patched;
}

function fitScreen() {
  const frame = document.querySelector(".screen-frame");
  if (!frame || !screenTransform) return;

  const padding = 20;
  const availableW = Math.max(0, frame.clientWidth - padding);
  const availableH = Math.max(0, frame.clientHeight - padding);
  const scaleW = availableW / 480;
  const scaleH = availableH / 800;
  // 允许适度放大，让 480x800 在中栏更有冲击力
  const maxScale = 1.18;
  const scale = Math.min(maxScale, scaleW, scaleH);
  screenTransform.style.transform = `scale(${scale})`;
}

async function run() {
  if (isRunning) return;
  isRunning = true;
  const prevBtnText = runBtn.innerText;
  runBtn.disabled = true;
  runBtn.innerText = "运行中...";

  errorBox.style.display = "none";
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
  preview.srcdoc = "";
  fitScreen();

  try {
    const res = await fetch(`${API_BASE}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input }),
    });

    const data = await res.json();
    if (!res.ok) {
      errorBox.innerText = data.error || "运行失败";
      errorBox.style.display = "block";
      debugStatus.innerHTML = "<strong>状态：</strong>运行失败，请查看错误信息或展开 Debug JSON。";
      return;
    }

    lastPackage = data.package || null;
    lastIndexHtml = data.indexHtml || "";
    jsonOut.innerText = JSON.stringify(data.package, null, 2);
    preview.srcdoc = data.indexHtml;
    updateEditorsFromPackage(data.package || {});
    debugStatus.innerHTML =
      "<strong>状态：</strong>生成完成。标题：" +
      (data.package?.title || "未命名") +
      "；置信度：" +
      (data.package?.confidence ?? "-") +
      "；来源：" +
      (data.package?.source || "-");

    setTimeout(fitScreen, 0);
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
window.addEventListener("load", fitScreen);

// 左侧示例输入快捷填充
document.querySelectorAll("[data-sample]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const val = btn.getAttribute("data-sample") || "";
    inputBox.value = val;
    inputBox.focus();
  });
});

