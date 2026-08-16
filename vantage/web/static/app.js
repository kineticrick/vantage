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
// `main` is plain text: cell() escapes it, so no call site has to remember to.
function cell(main, name, sector, ticker) {
  const f = (ticker && FACTS[ticker]) || {};
  return `<div class="cell"><span>${esc(main)}</span>${sub(name || f.name, sector || f.sector)}</div>`;
}

// Third row line: the return term structure, description only. The server
// sends the display strings; we never format a percentage here.
//
// Each cell repeats its column label in an aria-label — same reason annotate()
// does it below: the visible header is a separate element with no table
// semantics tying it to this cell, so assistive tech would otherwise hear a
// bare run of numbers. `value === null` is the server's own "absent" marker
// (termstructure.term_structure), so the missing case reads as words rather
// than as "dash dash".
function tsLine(ts) {
  if (!ts || !ts.length) return "";
  return `<div class="ts">${ts.map((e) =>
    `<span class="ts-cell" aria-label="${esc(e.label + ", " +
      (e.value == null ? "not available" : e.display))}">${esc(e.display)}</span>`
  ).join("")}</div>`;
}

// The column legend. Without it the five numbers are unlabelled, and a column
// nothing identifies cannot be scanned across names — which is the whole point
// of the fixed grid. Same grid as tsLine, so the columns stay aligned with the
// data rows beneath. Labels come from the payload, never a copy kept here.
// aria-hidden because every data cell already carries its own aria-label; a
// second, structurally unrelated run of labels would just be noise.
function tsHead(items) {
  const src = (items || []).find((i) => i.term_structure && i.term_structure.length);
  if (!src) return "";
  return `<div class="ts ts-head" aria-hidden="true">${src.term_structure.map((e) =>
    `<span class="ts-cell">${esc(e.label)}</span>`).join("")}</div>`;
}

// Mirrors vantage/tickers.py: same symbol shape, same price-cue rule. The
// stoplist verdict arrives per-ticker as `common_word` so there is only one
// list, maintained in Python. The 1-character rule is a rule, not a list, so
// it lives here too — mirrors tickers._needs_price_cue.
const TK_RE = /\b[A-Z][A-Z0-9]{0,4}(?:-[A-Z])?\b/g;
const CUE_RE = /^\s*(?:is\s+|at\s+)?[+\-]?\$?\d/;
const needsCue = (t, f) => t.length === 1 || !!f.common_word;

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
    if (needsCue(m[0], f) && !CUE_RE.test(s.slice(end, end + 12))) continue;
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
    ${tsHead(o.top_leaders)}
    ${rows(o.top_leaders, (l) => `<div class="row srow">
      ${cell(l.ticker, l.name, l.sector, l.ticker)}
      <span class="${cls(l.value)}">${esc(l.value_display)}</span>
      ${tsLine(l.term_structure)}</div>`)}
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
        ${cell(h.ticker, h.name, h.sector, h.ticker)}
        <span>${pct(h.pct_of_portfolio)}</span></div>`)}`;
}

async function loadSignals() {
  const s = await getJSON("/api/signals");
  $("signals").innerHTML = `<h2>Signals</h2>
    ${tsHead(s.signals)}
    ${rows(s.signals, (sig) => `<div class="row srow">
      ${cell([sig.ticker, sig.signal_type].filter(Boolean).join(" · "),
             sig.name, sig.sector, sig.ticker)}
      <span class="${cls(sig.value)}">${esc(sig.value_display)}</span>
      ${tsLine(sig.term_structure)}</div>`)}`;
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
  if (b.trajectory_read) {
    body.append(label("Trajectory read"), proseP("prose", b.trajectory_read, briefFacts));
  }
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
  const submitBtn = $("chat-form").querySelector('button[type="submit"]');
  const msg = input.value.trim();
  if (!msg) return;
  addMsg("user", msg);
  input.value = "";
  // Guard against concurrent turns on the one shared session: two in-flight
  // streams would interleave appends into the same server-side conversation
  // and both persist over each other. Mirrors the refresh button's guard.
  input.disabled = true;
  submitBtn.disabled = true;
  // A reply interleaves text with tool calls, so it can own several bubbles.
  // Keep every one: `bubble` is only the open (still-appending) one, while
  // `bubbles` accumulates them all for annotation once the stream is done.
  let bubble = null;
  const bubbles = [];
  try {
    await streamPost("/api/chat", { message: msg }, (ev) => {
      if (ev.type === "text") {
        if (!bubble) { bubble = addMsg("analyst", ""); bubbles.push(bubble); }
        bubble.textContent += ev.text;
        $("chat-log").scrollTop = $("chat-log").scrollHeight;
      } else if (ev.type === "tool_use") {
        addMsg("tool", `[looking up via ${ev.name}(${JSON.stringify(ev.input || {})})]`);
        bubble = null;   // next text starts a new bubble; this one is finished
      } else if (ev.type === "error") {
        addMsg("error", `[error: ${ev.message}]`);
      }
    });
    // Annotate only after the stream ends — never mid-stream, or appending
    // text would land inside/after the elements annotate() just built.
    for (const b of bubbles) b.replaceChildren(annotate(b.textContent));
  } catch (e) {
    addMsg("error", "[error: " + e + "]");
  } finally {
    input.disabled = false;
    submitBtn.disabled = false;
    input.focus();
  }
});

// Read-only viewing state: openChat() shows a past conversation without
// changing which session is actually live, so the composer must not look
// like it will continue that conversation — the next message would in fact
// go to whichever session IS active, against context the panel isn't
// showing. setViewingPast(false) is the "back to live" state: composer
// enabled, banner hidden.
function setViewingPast(viewing) {
  $("chat-input").disabled = viewing;
  $("chat-form").querySelector('button[type="submit"]').disabled = viewing;
  $("chat-viewing-banner").hidden = !viewing;
}

$("chat-new").addEventListener("click", async () => {
  await fetch("/api/chat/new", { method: "POST" });
  $("chat-log").innerHTML = "";
  setViewingPast(false);
  loadChatHistory();
});

// --- Chat history: list, open (read-only), and resume past conversations ---
async function loadChatHistory() {
  const list = document.getElementById('chat-history-list');
  list.replaceChildren();
  let rows = [];
  try {
    const r = await fetch('/api/chats');
    if (!r.ok) throw new Error(r.status);
    rows = await r.json();
  } catch (e) {
    const li = document.createElement('li');
    li.textContent = 'Could not load past conversations.';
    list.append(li);
    return;
  }
  if (!rows.length) {
    const li = document.createElement('li');
    li.textContent = 'No saved conversations yet.';
    list.append(li);
    return;
  }
  for (const row of rows) {
    const li = document.createElement('li');

    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'chat-history-open';
    open.textContent = row.title;               // text node, never innerHTML
    open.addEventListener('click', () => openChat(row.id));

    const meta = document.createElement('span');
    meta.className = 'chat-history-meta';
    meta.textContent = `${(row.updated_at || '').slice(0, 10)} · ${row.turns} turns`;

    const cont = document.createElement('button');
    cont.type = 'button';
    cont.className = 'chat-history-continue';
    cont.textContent = 'Continue';
    cont.addEventListener('click', () => resumeChat(row.id));

    li.append(open, meta, cont);
    list.append(li);
  }
}

async function openChat(id) {
  const r = await fetch(`/api/chats/${encodeURIComponent(id)}`);
  if (!r.ok) return;
  const chat = await r.json();
  $("chat-log").replaceChildren();
  const bubbles = [];
  for (const m of chat.messages) {
    if (typeof m.content === "string") {
      bubbles.push(addMsg(m.role === "user" ? "user" : "analyst", m.content));
      continue;
    }
    for (const b of m.content) {
      if (b.type === "text") bubbles.push(addMsg("analyst", b.text));
      else if (b.type === "tool_use") addMsg("tool", `called ${b.name}`);
      // tool_result blocks are not rendered: the JSON payload is provenance
      // for the transcript file, not something to read in the panel.
    }
  }
  // Same treatment a live reply gets once its stream ends (app.js:316), so a
  // reopened conversation shows names and sectors like a fresh one.
  for (const b of bubbles) b.replaceChildren(annotate(b.textContent));
  // Read-only by design: no server state changed, so the composer must not
  // suggest that typing here continues this conversation.
  setViewingPast(true);
}

async function resumeChat(id) {
  const r = await fetch(`/api/chats/${encodeURIComponent(id)}/resume`,
                        { method: "POST" });
  if (!r.ok) return;
  await openChat(id);
  // openChat() just disabled the composer for read-only viewing; resuming
  // makes this conversation the live one again, so re-enable it.
  setViewingPast(false);
}

$("chat-history-toggle").addEventListener("click", () => {
  const list = $("chat-history-list");
  list.hidden = !list.hidden;
  $("chat-history-toggle").textContent = list.hidden ? "Show" : "Hide";
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

// Sessions live server-side, so a page load would otherwise inherit whatever
// conversation the server still held from the last sitting. Opening the
// dashboard always starts a fresh chat.
(async () => {
  await fetch("/api/chat/new", { method: "POST" });
  await loadChatHistory();
})();
loadData();
