const $ = (id) => document.getElementById(id);
const pct = (v) => (v == null ? "—" : (v * 100).toFixed(1) + "%");
const cls = (v) => (v >= 0 ? "up" : "down");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Ticker facts for prose annotation, scoped server-side to what's on screen.
let FACTS = {};
async function loadFacts() {
  try { FACTS = await getJSON("/api/tickers"); } catch (e) { FACTS = {}; }
}

async function getJSON(url) { const r = await fetch(url); return r.json(); }

function rows(items, render) {
  return items.length ? items.map(render).join("") : '<div class="note">None</div>';
}

// Ticker stays the anchor; identity sits beneath it in muted type.
function sub(name, sector) {
  const t = [name, sector].filter(Boolean).join(" · ");
  return t ? `<div class="sub">${esc(t)}</div>` : "";
}

// `ticker` (raw, unescaped) is optional; when a row's own name/sector are
// absent, fall back to the module-level FACTS map (already loaded from
// /api/tickers before any panel renders). Covers rows sourced from artifacts
// written before the `name` field existed (e.g. old data/signals-*.json).
function cell(main, name, sector, ticker) {
  const f = (ticker && FACTS[ticker]) || {};
  return `<div class="cell"><span>${main}</span>${sub(name || f.name, sector || f.sector)}</div>`;
}

// Mirrors vantage/tickers.py: same symbol shape, same price-cue rule. The
// stoplist verdict arrives per-ticker as `common_word` so there is only one
// list, maintained in Python.
const TK_RE = /\b[A-Z][A-Z0-9]{0,4}(?:-[A-Z])?\b/g;
const CUE_RE = /^\s*(?:is\s+|at\s+)?[+\-]?\$?\d/;

// `facts` defaults to the module-level FACTS (overview, chat) but callers
// scoped to a specific, non-latest brief (openBrief) pass their own map.
function annotate(text, facts = FACTS) {
  const s = String(text == null ? "" : text);
  const frag = document.createDocumentFragment();
  let last = 0, m;
  TK_RE.lastIndex = 0;
  while ((m = TK_RE.exec(s)) !== null) {
    const f = facts[m[0]];
    if (!f) continue;
    const end = m.index + m[0].length;
    if (f.common_word && !CUE_RE.test(s.slice(end, end + 12))) continue;
    const tip = [f.name, f.sector].filter(Boolean).join(" · ");
    if (!tip) continue;
    frag.appendChild(document.createTextNode(s.slice(last, m.index)));
    const span = document.createElement("span");
    span.className = "tk";
    span.textContent = m[0];          // text node, never innerHTML
    span.setAttribute("data-tip", tip);
    // CSS ::after content isn't reliably announced by screen readers, so
    // the identity is repeated in an aria-label for assistive tech.
    span.setAttribute("aria-label", m[0] + ", " + tip);
    span.setAttribute("tabindex", "0");
    frag.appendChild(span);
    last = end;
  }
  frag.appendChild(document.createTextNode(s.slice(last)));
  return frag;
}

// A <p> whose text is annotated. Used wherever prose is rendered.
function proseP(className, text, facts = FACTS) {
  const p = document.createElement("p");
  p.className = className;
  p.appendChild(annotate(text, facts));
  return p;
}

async function loadOverview() {
  const o = await getJSON("/api/overview");
  $("overview").innerHTML = `<h2>Overview</h2>
    <div class="note">Signals as of ${esc(o.signals_as_of) || "—"}</div>
    <div class="label">Top 12-month leaders</div>
    ${rows(o.top_leaders, (l) => `<div class="row">
      ${cell(esc(l.ticker), l.name, l.sector, l.ticker)}
      <span class="${cls(l.value)}">${pct(l.value)}</span></div>`)}
    <div class="label">Sector momentum</div>
    ${rows(o.sector_momentum_top, (m) => `<div class="row"><span>${esc(m.sector)}</span>
      <span class="${cls(m.value)}">${pct(m.value)}</span></div>`)}
    ${o.latest_brief ? `<div class="label">Latest brief — ${esc(o.latest_brief.as_of)}</div>
      <p class="prose lede">${esc(o.latest_brief.executive_summary)}</p>` : ""}`;
  const lede = $("overview").querySelector(".prose.lede");
  if (lede) lede.replaceChildren(annotate(lede.textContent));
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
      (h) => `<div class="row">
        ${cell(esc(h.ticker), h.name, h.sector, h.ticker)}
        <span>${pct(h.pct_of_portfolio)}</span></div>`)}`;
}

async function loadSignals() {
  const s = await getJSON("/api/signals");
  $("signals").innerHTML = `<h2>Signals</h2>
    ${rows(s.signals, (sig) => `<div class="row">
      ${cell(esc(sig.ticker) + " · " + esc(sig.signal_type), sig.name, sig.sector, sig.ticker)}
      <span class="${cls(sig.value)}">${sig.signal_type === "volume_spike"
        ? sig.value.toFixed(1) + "×" : pct(sig.value)}</span></div>`)}`;
}

async function loadBriefs() {
  const briefs = await getJSON("/api/briefs");
  const panel = $("briefs");
  panel.innerHTML = "<h2>Briefs</h2>";
  if (!briefs.length) {
    const none = document.createElement("div");
    none.className = "note";
    none.textContent = "None";
    panel.appendChild(none);
    return;
  }
  // Build rows via DOM + addEventListener (not an interpolated inline onclick):
  // HTML-escaping is the wrong escaping for a JS-string-in-attribute context.
  for (const b of briefs) {
    const row = document.createElement("div");
    row.className = "row";
    row.style.cursor = "pointer";
    const date = document.createElement("span");
    date.textContent = b.as_of;
    const summary = document.createElement("span");
    summary.className = "note";
    summary.textContent = (b.summary || "").slice(0, 60) + "…";
    row.append(date, summary);
    row.addEventListener("click", () => openBrief(b.as_of));
    panel.appendChild(row);
  }
}

async function openBrief(asOf) {
  if (!/^[0-9-]+$/.test(asOf)) return;  // brief ids are dates; reject anything else
  const data = await getJSON(`/api/briefs/${encodeURIComponent(asOf)}`);
  const b = data.brief;
  if (!b) return;
  // Facts scoped to THIS brief, not just the latest one — otherwise an
  // older brief's tickers fall out of the on-screen candidate set and its
  // prose renders unannotated. Degrades to {} (plain text, no tooltips)
  // rather than throwing if the lookup fails.
  let briefFacts = {};
  try {
    briefFacts = await getJSON(`/api/tickers?as_of=${encodeURIComponent(asOf)}`);
  } catch (e) { briefFacts = {}; }

  const panel = $("brief-detail");
  panel.style.display = "block";
  panel.innerHTML = `<div class="brief-head"><h2>Brief — ${esc(b.as_of)}</h2>
      <button id="brief-close">Close</button></div><div class="brief-body"></div>`;
  const body = panel.querySelector(".brief-body");

  const label = (t) => {
    const d = document.createElement("div");
    d.className = "label";
    d.textContent = t;
    return d;
  };
  const field = (k, v) => {
    const p = document.createElement("p");
    p.className = "brief-field";
    const key = document.createElement("span");
    key.className = "field-k";
    key.textContent = k;
    p.append(key, annotate(v, briefFacts));
    return p;
  };

  body.append(label("Executive summary"), proseP("prose lede", b.executive_summary, briefFacts));
  for (const i of b.items || []) {
    const div = document.createElement("div");
    div.className = "brief-item";
    const h3 = document.createElement("h3");
    h3.className = "brief-item-title";
    h3.appendChild(annotate(i.title, briefFacts));
    div.append(h3, field("Thesis", i.thesis), field("Evidence", i.evidence),
               field("Why it matters", i.why_it_matters),
               field("Portfolio relevance", i.portfolio_relevance));
    if (i.sources && i.sources.length) {
      const src = document.createElement("p");
      src.className = "brief-sources";
      src.textContent = "Sources: " + i.sources.join(", ");
      div.appendChild(src);
    }
    body.appendChild(div);
  }
  body.append(label("Challenge & coaching"), proseP("prose", b.challenge, briefFacts),
              label("What I might be missing"), proseP("prose", b.what_im_missing, briefFacts),
              label("Watchlist"));
  for (const w of b.watchlist || []) body.appendChild(proseP("prose wl", w, briefFacts));
  if (!(b.watchlist || []).length) body.appendChild(proseP("prose", "—", briefFacts));

  $("brief-close").addEventListener("click", () => { panel.style.display = "none"; });
  panel.scrollIntoView({ behavior: "smooth" });
}

async function loadData() {
  await loadFacts();
  loadOverview(); loadPortfolio(); loadSignals(); loadBriefs();
}

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
    if (bubble) bubble.replaceChildren(annotate(bubble.textContent));
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
