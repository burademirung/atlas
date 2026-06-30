import { escapeHtml, renderMarkdown } from "./render.js?v=13";

const $ = (sel) => document.querySelector(sel);
const stagesEl = $("#stages");
const stageWrap = $("#stage");
const reportEl = $("#report");
const sourcesEl = $("#sources");
const subqsEl = $("#subqs");
const srcCountEl = $("#srcCount");
const statusChip = $("#statusChip");
const qecho = $("#qecho");
const runBtn = $("#run");
const qInput = $("#q");
const chipsEl = $("#dataTypes");

let reportBuffer = "";
let running = false;

/* ---------- data-type chips (what was exposed) ---------------------------- */
function selectedDataTypes() {
  if (!chipsEl) return [];
  return Array.from(chipsEl.querySelectorAll(".chip.active")).map((c) => c.dataset.type);
}
if (chipsEl) {
  for (const chip of chipsEl.querySelectorAll(".chip")) {
    chip.addEventListener("click", () => {
      const active = chip.classList.toggle("active");
      chip.setAttribute("aria-pressed", String(active));
    });
  }
}

/* ---------- Turnstile (bot protection, optional) -------------------------- */
let turnstileSitekey = null;
let turnstileWidgetId = null;

async function initTurnstile() {
  try {
    const r = await fetch("/api/config");
    const cfg = await r.json();
    if (!cfg || !cfg.sitekey) return;
    turnstileSitekey = cfg.sitekey;

    const el = $("#turnstile");
    if (el) el.hidden = false;

    window.onTurnstileLoad = () => {
      if (!window.turnstile || !el) return;
      turnstileWidgetId = window.turnstile.render(el, { sitekey: turnstileSitekey });
    };

    const script = document.createElement("script");
    script.src =
      "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onTurnstileLoad&render=explicit";
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
  } catch {
    /* config unavailable — proceed without Turnstile */
  }
}

function getTurnstileToken() {
  if (!turnstileSitekey || !window.turnstile || turnstileWidgetId === null) return "";
  return window.turnstile.getResponse(turnstileWidgetId) || "";
}

function resetTurnstile() {
  if (turnstileSitekey && window.turnstile && turnstileWidgetId !== null) {
    try {
      window.turnstile.reset(turnstileWidgetId);
    } catch {
      /* ignore */
    }
  }
}

/* ---------- safe, minimal markdown rendering -------------------------------
 * escapeHtml / renderMarkdown (and the internal inline()) live in render.js,
 * an ES module imported at the top of this file, so they can be unit-tested. */

/* ---------- pipeline + status UI ------------------------------------------ */
const ORDER = ["planning", "searching", "verifying", "writing"];

function setPhase(phase) {
  const idx = ORDER.indexOf(phase);
  for (const li of stagesEl.querySelectorAll("li")) {
    const p = li.dataset.phase;
    const i = ORDER.indexOf(p);
    li.classList.toggle("active", p === phase);
    li.classList.toggle("done", i < idx);
  }
}

function setStatus(label, kind) {
  statusChip.textContent = label;
  statusChip.className = "status-chip" + (kind ? " " + kind : "");
}

function resetStage(question) {
  reportBuffer = "";
  reportEl.innerHTML = '<span class="cursor"></span>';
  sourcesEl.innerHTML = "";
  subqsEl.innerHTML = "";
  srcCountEl.textContent = "0";
  qecho.textContent = question;
  for (const li of stagesEl.querySelectorAll("li")) li.classList.remove("active", "done");
  stageWrap.hidden = false;
  stageWrap.scrollIntoView({ behavior: "smooth", block: "start" });
}

let sourceIndex = 0;
function addSource(s) {
  sourceIndex += 1;
  const a = document.createElement("a");
  a.className = "source";
  a.id = "source-" + sourceIndex;
  a.href = s.url;
  a.target = "_blank";
  a.rel = "noreferrer";
  a.innerHTML =
    `<span class="st"><span class="idx">[${sourceIndex}]</span>${escapeHtml(s.title)}</span>` +
    `<span class="sn">${escapeHtml((s.snippet || "").slice(0, 140))}</span>`;
  sourcesEl.appendChild(a);
  srcCountEl.textContent = String(sourceIndex);
}

function renderReport(final) {
  reportEl.innerHTML = renderMarkdown(reportBuffer) + (final ? "" : '<span class="cursor"></span>');
}

/* ---------- SSE client over fetch POST ------------------------------------ */
async function runResearch(question) {
  if (running) return;
  running = true;
  runBtn.disabled = true;
  sourceIndex = 0;
  resetStage(question);
  setStatus("starting", null);

  try {
    const resp = await fetch("/api/research", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        question,
        dataTypes: selectedDataTypes(),
        turnstileToken: getTurnstileToken(),
      }),
    });
    if (!resp.ok || !resp.body) throw new Error("Request failed (" + resp.status + ")");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split("\n\n");
      buf = frames.pop() || "";
      for (const frame of frames) handleFrame(frame);
    }
  } catch (err) {
    setStatus("error", "error");
    reportEl.innerHTML = `<p style="color:#e06c6c">${escapeHtml(String(err))}</p>`;
  } finally {
    running = false;
    runBtn.disabled = false;
    resetTurnstile();
    loadHistory();
  }
}

function handleFrame(frame) {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  let payload;
  try {
    payload = JSON.parse(data);
  } catch {
    return;
  }

  switch (event) {
    case "status":
      setPhase(payload.phase);
      setStatus(payload.label || payload.phase, null);
      break;
    case "plan":
      for (const sq of payload.subQuestions || []) {
        const d = document.createElement("div");
        d.className = "sq";
        d.textContent = sq;
        subqsEl.appendChild(d);
      }
      break;
    case "source":
      addSource(payload);
      break;
    case "token":
      reportBuffer += payload.delta || "";
      renderReport(false);
      break;
    case "done":
      setPhase("writing");
      for (const li of stagesEl.querySelectorAll("li")) li.classList.add("done");
      setStatus("done · " + (payload.sources || 0) + " sources", "done");
      renderReport(true);
      break;
    case "error":
      setStatus("error", "error");
      reportEl.innerHTML = `<p style="color:#e06c6c">${escapeHtml(payload.message || "error")}</p>`;
      break;
  }
}

/* ---------- history ------------------------------------------------------- */
async function loadHistory() {
  try {
    const r = await fetch("/api/runs");
    const { runs } = await r.json();
    const list = $("#historyList");
    list.innerHTML = "";
    for (const run of runs || []) {
      const b = document.createElement("button");
      b.className = "history-item";
      b.innerHTML =
        `${escapeHtml(run.question)}<span class="when">${escapeHtml(run.created_at)} UTC</span>`;
      b.onclick = () => openRun(run.id);
      list.appendChild(b);
    }
  } catch {
    /* ignore */
  }
}

async function openRun(id) {
  const r = await fetch("/api/runs/" + id);
  if (!r.ok) return;
  const { run, sources } = await r.json();
  resetStage(run.question);
  for (const li of stagesEl.querySelectorAll("li")) li.classList.add("done");
  setStatus("archived", "done");
  sourceIndex = 0;
  for (const s of sources || []) addSource(s);
  reportBuffer = run.report || "";
  renderReport(true);
}

/* ---------- wiring -------------------------------------------------------- */
$("#form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = qInput.value.trim();
  if (q) runResearch(q);
});
qInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    $("#form").requestSubmit();
  }
});
for (const btn of document.querySelectorAll("#examples button")) {
  btn.addEventListener("click", () => {
    qInput.value = btn.textContent;
    $("#form").requestSubmit();
  });
}
loadHistory();
initTurnstile();
