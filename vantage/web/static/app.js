const $ = (id) => document.getElementById(id);
const pct = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
const cls = (v) => (v >= 0 ? "up" : "down");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function getJSON(url) { const r = await fetch(url); return r.json(); }

function rows(items, render) {
  return items.length ? items.map(render).join("") : '<div class="note">None</div>';
}

async function loadOverview() {
  const o = await getJSON("/api/overview");
  $("overview").innerHTML = `<h2>Overview</h2>
    <div class="note">Signals as of ${esc(o.signals_as_of) || "—"}</div>
    <div class="label">Top 12-month leaders</div>
    ${rows(o.top_leaders, (l) => `<div class="row"><span>${esc(l.ticker)}</span>
      <span class="${cls(l.value)}">${pct(l.value)}</span></div>`)}
    <div class="label">Sector momentum</div>
    ${rows(o.sector_momentum_top, (m) => `<div class="row"><span>${esc(m.sector)}</span>
      <span class="${cls(m.value)}">${pct(m.value)}</span></div>`)}
    ${o.latest_brief ? `<div class="label">Latest brief — ${esc(o.latest_brief.as_of)}</div>
      <div>${esc(o.latest_brief.executive_summary)}</div>` : ""}`;
}

async function loadPortfolio() {
  const p = await getJSON("/api/portfolio");
  if (!p.available) {
    $("portfolio").innerHTML =
      `<h2>Portfolio</h2><div class="note">Unavailable: ${esc(p.note) || "—"}</div>`;
    return;
  }
  $("portfolio").innerHTML = `<h2>Portfolio</h2>
    <div class="label">Top positions</div>
    ${rows(p.holdings.slice().sort((a, b) => (b.pct_of_portfolio || 0) -
        (a.pct_of_portfolio || 0)).slice(0, 8),
      (h) => `<div class="row"><span>${esc(h.ticker)} — ${esc(h.name)}</span>
        <span>${pct(h.pct_of_portfolio)}</span></div>`)}`;
}

async function loadSignals() {
  const s = await getJSON("/api/signals");
  $("signals").innerHTML = `<h2>Signals</h2>
    ${rows(s.signals, (sig) => `<div class="row">
      <span>${esc(sig.ticker)} · ${esc(sig.signal_type)}</span>
      <span class="${cls(sig.value)}">${sig.signal_type === "volume_spike"
        ? sig.value.toFixed(1) + "×" : pct(sig.value)}</span></div>`)}`;
}

async function loadBriefs() {
  const briefs = await getJSON("/api/briefs");
  $("briefs").innerHTML = `<h2>Briefs</h2>
    ${rows(briefs, (b) => `<div class="row"><span>${esc(b.as_of)}</span>
      <span class="note">${esc(b.summary.slice(0, 60))}…</span></div>`)}`;
}

function loadData() { loadOverview(); loadPortfolio(); loadSignals(); loadBriefs(); }

// --- SSE helper: POST a JSON body, invoke onEvent per parsed event dict ---
async function streamPost(url, body, onEvent) {
  const resp = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop();
    for (const f of frames) {
      const line = f.trim();
      if (line.startsWith("data:")) onEvent(JSON.parse(line.slice(5).trim()));
    }
  }
}

// --- Chat ---
function addMsg(kind, text) {
  const el = document.createElement("div");
  el.className = "msg " + kind;
  el.textContent = text;
  $("chat-log").appendChild(el);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return el;
}

$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("chat-input");
  const msg = input.value.trim();
  if (!msg) return;
  addMsg("user", msg);
  input.value = "";
  let bubble = null;
  try {
    await streamPost("/api/chat", { message: msg }, (ev) => {
      if (ev.type === "text") {
        if (!bubble) bubble = addMsg("analyst", "");
        bubble.textContent += ev.text;
        $("chat-log").scrollTop = $("chat-log").scrollHeight;
      } else if (ev.type === "tool_use") {
        addMsg("tool", `[looking up via ${ev.name}(${JSON.stringify(ev.input || {})})]`);
        bubble = null;
      } else if (ev.type === "error") {
        addMsg("error", `[error: ${ev.message}]`);
      }
    });
  } catch (e) {
    addMsg("error", "[error: " + e + "]");
  }
});

$("chat-new").addEventListener("click", async () => {
  await fetch("/api/chat/new", { method: "POST" });
  $("chat-log").innerHTML = "";
});

// --- Refresh ---
$("refresh-btn").addEventListener("click", async () => {
  const btn = $("refresh-btn");
  btn.disabled = true;
  try {
    await streamPost("/api/refresh", {}, (ev) => {
      if (ev.type === "progress") $("refresh-status").textContent = ev.stage + "…";
      else if (ev.type === "error") $("refresh-status").textContent = "error: " + ev.message;
      else if (ev.type === "done") { $("refresh-status").textContent = "updated"; loadData(); }
    });
  } catch (e) {
    $("refresh-status").textContent = "error: " + e;
  } finally {
    btn.disabled = false;
  }
});

loadData();
