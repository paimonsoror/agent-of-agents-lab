/* Maestro Fleet Console — live board, timeline, assessment and playback. Vanilla JS, no deps. */
(function () {
  "use strict";
  const T = window.MaestroTopology;
  const I = window.MaestroIcons;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);

  // ---------------------------------------------------------------- state
  const state = {
    topology: null,
    nodes: {},            // id -> { el, status, statusEl, data }
    traces: {},           // trace_id -> [events]
    traceOrder: [],
    current: null,        // active trace id
    currentDone: false,
    assessment: null,
    pageLoadedAt: Date.now(),
    queryCounts: {},
    timelineCount: 0,
  };

  const KIND_CLASS = {
    "incident.raised": "c-incident", "question.asked": "c-incident", "error": "c-error",
    "token.issued": "c-identity", "token.exchanged": "c-identity", "token.refused": "c-error",
    "request.sent": "c-request", "request.received": "c-request", "tools.discovered": "c-request",
    "skills.loaded": "c-skills",
    "evidence.gathered": "c-evidence", "llm.turn": "c-evidence",
    "finding.returned": "c-finding", "assessment.posted": "c-finding",
    "scenario.applied": "c-scenario", "scenario.cleared": "c-scenario",
  };
  const kindClass = (k) => KIND_CLASS[k] || "c-neutral";

  // ---------------------------------------------------------------- board
  function svgEl(tag, attrs, parent) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    if (parent) parent.appendChild(el);
    return el;
  }

  function renderBoard(topo) {
    const labels = $("labels"), nodesG = $("nodes"), groups = $("groups"), sedges = $("static-edges");
    labels.innerHTML = nodesG.innerHTML = groups.innerHTML = sedges.innerHTML = "";

    for (const [key, col] of Object.entries(T.COLUMNS)) {
      if (!col.label) continue;
      svgEl("text", { x: col.x + col.w / 2, y: 830, class: "col-label" }, labels).textContent = col.label;
    }
    for (const g of T.GROUPS) {
      svgEl("rect", { x: g.x, y: g.y, width: g.w, height: g.h, rx: 18, class: "group-rect" }, groups);
      svgEl("text", { x: g.x + 14, y: g.y + 22, class: "group-label" }, groups).textContent = g.label;
    }
    for (const e of topo.edges) {
      const d = T.path(e.from, e.to);
      if (d) svgEl("path", { d, class: "sedge", "data-edge": `${e.from}>${e.to}` }, sedges);
    }
    for (const n of topo.nodes) {
      const r = T.rect(n.id);
      if (!r) continue;
      const g = svgEl("g", { class: `node col-${r.col} ${n.id}`, "data-id": n.id, transform: `translate(${r.x},${r.y})`, tabindex: "0", role: "button", "aria-label": `${n.label}: open play-by-play` }, nodesG);
      attachNodeHandlers(g, n.id);
      svgEl("rect", { class: "box", width: r.w, height: r.h, rx: 16 }, g);
      svgEl("title", {}, g).textContent = n.id === "ide"
        ? `${n.label} — the same gateway, the engineer's own identity. Demo users: ${demoUsersLine()}. Click for the play-by-play.`
        : `${n.label} — click for the play-by-play`;
      if (n.id === "gateway") {
        I.place(g, "gateway", r.w / 2 - 12, 14, 24, "var(--accent)");
        const t = svgEl("text", { class: "gw-text", transform: `translate(${r.w / 2 + 5}, ${r.h / 2 + 16}) rotate(-90)`, "text-anchor": "middle" }, g);
        t.textContent = `FLEET GATEWAY · ${(n.sublabel || "").toUpperCase()}`;
        state.nodes[n.id] = { el: g, data: n, statusEl: null, r };
        continue;
      }
      const small = r.h <= 90;
      const iconSize = small ? 26 : 30;
      const iconY = small ? r.h / 2 - iconSize / 2 : 20;
      I.place(g, I.NODE_ICON[n.id] || "agent", 16, iconY, iconSize, iconColor(r.col, n.id));
      const textX = 16 + iconSize + 12;
      const rightPad = I.CLAUDE_NODES.includes(n.id) ? 34 : 14;
      const maxW = r.w - textX - rightPad;
      const title = svgEl("text", { class: "title", x: textX, y: small ? r.h / 2 - 2 : 40 }, g);
      fitText(title, n.label, maxW);
      const sub = svgEl("text", { class: "sub", x: textX, y: small ? r.h / 2 + 18 : 62 }, g);
      fitText(sub, T.SHORT_SUB[n.id] || n.sublabel || "", maxW);
      let statusEl = null;
      if (!small) {
        statusEl = svgEl("text", { class: "status grey", x: 16, y: r.h - 16 }, g);
        statusEl.textContent = "";
      }
      if (I.CLAUDE_NODES.includes(n.id)) {
        const badge = I.place(g, "claude", r.w - 30, 10, 18);
        if (badge) { badge.setAttribute("class", "icon claude-badge"); badge.querySelector("title").textContent = "Powered by Claude"; }
      }
      if (n.url) {
        const a = svgEl("a", { href: n.url, target: "_blank", rel: "noopener" }, g);
        const t = svgEl("text", { class: "link-icon", x: r.w - 12, y: r.h - 14, "text-anchor": "end" }, a);
        t.textContent = "↗";
        svgEl("title", {}, a).textContent = `Open ${n.label}: ${n.url}`;
      }
      state.nodes[n.id] = { el: g, data: n, statusEl, r, statusMaxW: r.w - (n.url ? 44 : 32) };
    }
  }

  // Trim SVG text with an ellipsis so it never escapes its box; the full text stays in a <title>.
  function fitText(el, text, maxW) {
    const full = String(text || "");
    el.textContent = full;
    let t = full;
    try {
      while (t.length > 1 && el.getComputedTextLength() > maxW) {
        t = t.slice(0, -2).trimEnd() + "…";
        el.textContent = t;
      }
    } catch (e) { /* not rendered yet; leave as is */ }
    const old = el.querySelector("title");
    if (old) old.remove();
    if (t !== full) svgEl("title", {}, el).textContent = full;
  }

  function iconColor(col, id) {
    if (id === "skills") return "var(--c-skills)";
    if (id === "console") return "var(--c-incident)";
    if (id === "kafka") return "var(--text)";
    const sp = I.spec(I.NODE_ICON[id] || "");
    if (sp && sp.kind === "fill") return undefined; // keep the brand colour
    return { consumers: "var(--accent-2)", orchestration: "var(--accent)", agents: "var(--accent-2)", platforms: "var(--text-2)", monitoring: "var(--c-evidence)", identity: "var(--c-identity)" }[col] || "var(--text-2)";
  }

  function attachNodeHandlers(g, id) {
    g.addEventListener("click", (e) => {
      if (e.target.closest("a")) return; // the ↗ link opens the platform UI, not the drawer
      window.MaestroDrawer.openNode(id);
    });
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); window.MaestroDrawer.openNode(id); }
    });
  }

  function selectNode(id) {
    for (const [nid, n] of Object.entries(state.nodes)) n.el.classList.toggle("selected", nid === id);
  }

  function demoUsersLine() {
    const c = (state.topology && state.topology.credentials) || {};
    return (c.demo_users || []).map((u) => `${u.username} / ${u.password}`).join(", ") || "see Keycloak";
  }


  function setStatus(id, text, tone, cls) {
    const n = state.nodes[id];
    if (!n) return;
    if (n.statusEl) {
      n.statusEl.setAttribute("class", `status ${tone || "grey"}`);
      fitText(n.statusEl, text || "", n.statusMaxW || 200);
    }
    n.el.classList.remove("implicated", "cleared", "dimmed");
    if (cls) n.el.classList.add(cls);
  }

  function flash(id) {
    const n = state.nodes[id];
    if (!n) return;
    n.el.classList.add("hot");
    setTimeout(() => n.el.classList.remove("hot"), 1500);
    if (n.r) {
      const p = svgEl("rect", { x: n.r.x - 6, y: n.r.y - 6, width: n.r.w + 12, height: n.r.h + 12, rx: 20, class: "pulse", stroke: "var(--accent-2)" }, $("active-edges"));
      p.style.transformOrigin = `${n.r.x + n.r.w / 2}px ${n.r.y + n.r.h / 2}px`;
      setTimeout(() => p.remove(), 1500);
    }
  }

  function animateEdge(from, to, cls, reverse) {
    const d = T.path(from, to);
    if (!d) return;
    const layer = $("active-edges");
    const p = svgEl("path", { d, class: `aedge ${cls}` }, layer);
    const dot = svgEl("circle", { r: 7, class: `adot ${cls}` }, layer);
    const m = svgEl("animateMotion", { dur: "1.1s", path: d, fill: "freeze", begin: "indefinite", keyPoints: reverse ? "1;0" : "0;1", keyTimes: "0;1", calcMode: "linear" }, dot);
    try { m.beginElement(); } catch (e) { /* older engines */ }
    setTimeout(() => dot.remove(), 1200);
    setTimeout(() => p.remove(), 2700);
    flash(to);
  }

  function resetBoard() {
    for (const id of Object.keys(state.nodes)) setStatus(id, "", "grey");
    $("active-edges").innerHTML = "";
    state.queryCounts = {};
    $("timeline").innerHTML = "";
    state.timelineCount = 0;
    $("timeline-count").textContent = "0 events";
    renderAssessment(null);
    window.MaestroDrawer.refresh();
  }

  // ---------------------------------------------------------------- event semantics
  const DOMAIN_NODE = (d) => (d && d.endsWith("-agent")) ? d : `${d}-agent`;
  const fmtConf = (c) => (typeof c === "number" ? c.toFixed(2) : "");

  function applyEvent(ev, animate) {
    const d = ev.detail || {};
    const src = ev.source;
    const cls = kindClass(ev.kind);

    if (animate && ev.edge && ev.edge.from && ev.edge.to) {
      animateEdge(ev.edge.from, ev.edge.to, cls);
    }

    switch (ev.kind) {
      case "incident.raised":
        setStatus("console", `${d.incident || "P1"} raised`, "red");
        setStatus("maestro", "Receiving incident…", "amber");
        break;
      case "question.asked":
        setStatus(src === "ide" ? "ide" : "console", "Question asked", "red");
        setStatus("maestro", "Receiving question…", "amber");
        break;
      case "token.issued":
        if (state.nodes[src]) setStatus(src, "JWT issued · Keycloak", "amber");
        break;
      case "token.exchanged":
        setStatus("maestro", `On-behalf-of badge · ${d.target || "agent"}`, "amber");
        break;
      case "token.refused":
        setStatus("maestro", `Delegation refused · ${d.target || "agent"}`, "red");
        if (d.target && state.nodes[`${d.target}-agent`]) setStatus(`${d.target}-agent`, "delegation refused", "grey", "dimmed");
        break;
      case "request.sent":
        if (src === "maestro") setStatus("maestro", "Federating via gateway…", "amber");
        break;
      case "request.received":
        if (state.nodes[src]) {
          const c = d.caller || {};
          const who = c.username || c.azp ? ` · ${c.delegated ? "for " : ""}${c.username || c.azp}` : "";
          setStatus(src, `Request received${who}`, "amber");
        }
        break;
      case "tools.discovered": {
        const hidden = (d.hidden || d.not_visible || []).map(DOMAIN_NODE);
        const visible = (d.visible || []).map(DOMAIN_NODE);
        for (const id of hidden) setStatus(id, "not visible to caller", "grey", "dimmed");
        for (const id of visible) if (!state.nodes[id].statusEl.textContent) setStatus(id, "available", "grey");
        setStatus("maestro", `${visible.length || (d.tools || []).length} agent tool(s) visible`, "amber");
        break;
      }
      case "skills.loaded":
        if (state.nodes[src]) setStatus(src, `Skills loaded${d.skills ? " · " + d.skills.length : ""}`, "amber");
        if (animate) flash("skills");
        break;
      case "evidence.gathered":
        if (state.nodes[src]) setStatus(src, "Gathering evidence…", "blue");
        if (ev.edge && ev.edge.to) {
          const t = ev.edge.to;
          state.queryCounts[t] = (state.queryCounts[t] || 0) + 1;
          if (state.nodes[t] && state.nodes[t].statusEl) setStatus(t, `${state.queryCounts[t]} quer${state.queryCounts[t] === 1 ? "y" : "ies"}`, "blue");
        }
        break;
      case "llm.turn":
        break;
      case "finding.returned": {
        const imp = d.implicated === true;
        const conf = fmtConf(d.confidence);
        if (state.nodes[src]) setStatus(src, `${imp ? "Implicated" : "Not implicated"}${conf ? " · " + conf : ""}`, imp ? "red" : "green", imp ? "implicated" : "cleared");
        setStatus("maestro", "Consolidating findings…", "amber");
        break;
      }
      case "assessment.posted":
        setStatus("maestro", "Assessment posted ✓", "green");
        setStatus("console", "Assessment received", "green");
        break;
      case "scenario.applied":
        if (ev.edge && state.nodes[ev.edge.to]) setStatus(ev.edge.to, "FAULT INJECTED", "red", "implicated");
        break;
      case "scenario.cleared":
        if (ev.edge && state.nodes[ev.edge.to]) setStatus(ev.edge.to, "fault cleared", "green");
        break;
      case "error":
        if (state.nodes[src]) setStatus(src, "Error", "red");
        break;
      default:
        break;
    }
    appendTimeline(ev, animate);
    window.MaestroDrawer.refresh();
  }

  // ---------------------------------------------------------------- timeline
  function fmtTime(ts) {
    const dt = new Date(ts);
    if (isNaN(dt)) return ts || "";
    return dt.toLocaleTimeString([], { hour12: false }) + "." + String(dt.getMilliseconds()).padStart(3, "0");
  }

  function appendTimeline(ev, fresh) {
    const tl = $("timeline");
    const row = document.createElement("div");
    row.className = "tl-row" + (fresh ? " fresh" : "");
    row.innerHTML = `<span class="tl-time">${fmtTime(ev.ts)}</span>` +
      `<span class="tl-src" title="${esc(ev.source)}">${esc(ev.source)}</span>` +
      `<span class="tl-kind ${kindClass(ev.kind)}">${esc(ev.kind)}</span>` +
      `<span class="tl-sum">${esc(ev.summary)}</span>`;
    row.addEventListener("click", () => {
      const open = row.querySelector(".tl-detail");
      if (open) { open.remove(); return; }
      const pre = document.createElement("pre");
      pre.className = "tl-detail";
      pre.textContent = JSON.stringify({ trace_id: ev.trace_id, edge: ev.edge, detail: ev.detail || null }, null, 2);
      row.appendChild(pre);
    });
    tl.appendChild(row);
    state.timelineCount++;
    $("timeline-count").textContent = `${state.timelineCount} event${state.timelineCount === 1 ? "" : "s"}`;
    tl.scrollTop = tl.scrollHeight;
  }

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  // ---------------------------------------------------------------- assessment
  function renderAssessment(a) {
    const box = $("assessment");
    const meta = $("assessment-meta");
    if (!a) {
      box.className = "assessment empty";
      box.textContent = "Maestro's consolidated assessment will appear here.";
      meta.textContent = "";
      return;
    }
    box.className = "assessment";
    meta.textContent = [a.model, a.duration_ms ? `${(a.duration_ms / 1000).toFixed(1)}s` : "", a.trace_id].filter(Boolean).join(" · ");
    const chips = [];
    for (const x of a.implicated || []) chips.push(`<span class="pill implicated">${esc(x.domain)} · implicated ${fmtConf(x.confidence)}</span>`);
    for (const x of a.cleared || []) chips.push(`<span class="pill cleared">${esc(x.domain)} · cleared ${fmtConf(x.confidence)}</span>`);
    for (const x of a.not_consulted || []) chips.push(`<span class="pill skipped" title="${esc(x.reason)}">${esc(x.domain)} · not consulted</span>`);
    const findings = (a.findings || []).map((f) => {
      const ev = (f.evidence || []).map((e) => {
        const link = e.link ? `<a class="ev-link" href="${esc(e.link)}" target="_blank" rel="noopener">${/grafana/i.test(e.link) ? "Open in Grafana ↗" : "Open ↗"}</a>` : "";
        return `<li><code>${esc(e.source || "")}${e.query ? ": " + esc(e.query) : ""}</code> — ${esc(e.observation || "")}${link}</li>`;
      }).join("");
      const actions = (f.recommended_actions || []).map((x) => `<li>${esc(x)}</li>`).join("");
      return `<div class="finding ${f.implicated ? "implicated" : "cleared"}">` +
        `<h3><span>${esc(f.domain)} — ${esc(f.headline || "")}</span><span class="conf">${f.implicated ? "implicated" : "cleared"} · ${fmtConf(f.confidence)}</span></h3>` +
        `<p>${esc(f.summary || "")}</p>` +
        (ev ? `<ul>${ev}</ul>` : "") +
        (actions ? `<div class="actions"><b>Recommended</b><ul>${actions}</ul></div>` : "") +
        `</div>`;
    }).join("");
    box.innerHTML = `<div class="verdict">${esc(a.verdict || "")}</div>` +
      `<div class="chips">${chips.join("")}</div>` +
      (a.next_step_for_human ? `<div class="next-step"><b>Next step for a human</b>${esc(a.next_step_for_human)}</div>` : "") +
      findings;
  }

  async function fetchAssessment(traceId, attempt) {
    attempt = attempt || 0;
    try {
      const r = await fetch(`/api/assessment/${encodeURIComponent(traceId)}`);
      if (r.ok) {
        const a = await r.json();
        if (traceId === state.current) { state.assessment = a; renderAssessment(a); }
        return;
      }
    } catch (e) { /* retry */ }
    if (attempt < 10) setTimeout(() => fetchAssessment(traceId, attempt + 1), 1500);
  }

  // ---------------------------------------------------------------- traces & chip
  function startTrace(id) {
    if (player.active) player.stop();
    state.current = id;
    state.currentDone = false;
    state.assessment = null;
    resetBoard();
    updateChip();
    updatePlaybackUi();
  }

  function finishTrace() {
    state.currentDone = true;
    updateChip();
    player.load(state.current);
    updatePlaybackUi();
  }

  function updateChip() {
    const chip = $("trace-chip");
    chip.classList.remove("live", "done", "replay");
    if (!state.current) { $("trace-state").textContent = "IDLE"; $("trace-id").textContent = "no active trace"; $("trace-elapsed").textContent = ""; return; }
    $("trace-id").textContent = state.current;
    if (player.active) { chip.classList.add("replay"); $("trace-state").textContent = "REPLAY"; }
    else if (state.currentDone) { chip.classList.add("done"); $("trace-state").textContent = "COMPLETE"; }
    else { chip.classList.add("live"); $("trace-state").textContent = "LIVE"; }
  }

  function tickElapsed() {
    if (!state.current) return;
    const evs = state.traces[state.current] || [];
    if (!evs.length) return;
    const first = new Date(evs[0].ts).getTime();
    const end = state.currentDone ? new Date(evs[evs.length - 1].ts).getTime() : Date.now();
    const s = Math.max(0, Math.round((end - first) / 1000));
    $("trace-elapsed").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }
  setInterval(tickElapsed, 1000);

  function onEvent(ev) {
    const live = new Date(ev.ts).getTime() >= state.pageLoadedAt - 2000;
    if (ev.trace_id) {
      if (!state.traces[ev.trace_id]) { state.traces[ev.trace_id] = []; state.traceOrder.push(ev.trace_id); }
      state.traces[ev.trace_id].push(ev);
    }
    const starts = ev.kind === "incident.raised" || ev.kind === "question.asked";
    if (starts && ev.trace_id && ev.trace_id !== state.current) startTrace(ev.trace_id);
    if (!state.current && ev.trace_id) startTrace(ev.trace_id);

    const belongs = !ev.trace_id || ev.trace_id === state.current;
    if (!belongs) return;
    if (player.active) return; // replay owns the board; live events are still stored

    applyEvent(ev, live);
    if (ev.kind === "assessment.posted" && ev.trace_id === state.current) {
      const d = ev.detail || {};
      const a = d.assessment && d.assessment.verdict ? d.assessment : (d.verdict ? d : null);
      if (a) { state.assessment = a; renderAssessment(a); }
      fetchAssessment(ev.trace_id);
      finishTrace();
    }
    if (ev.kind === "error" && ev.trace_id === state.current && (ev.source === "console" || ev.source === "maestro")) {
      finishTrace();
    }
    updateChip();
  }

  // ---------------------------------------------------------------- playback
  const player = {
    active: false, playing: false, events: [], index: 0, timer: null, cadence: 1400,
    load(traceId) { this.events = (state.traces[traceId] || []).slice(); this.index = this.events.length; this.active = false; this.playing = false; },
    stop() { clearTimeout(this.timer); this.timer = null; this.playing = false; this.active = false; updateChip(); updatePlaybackUi(); },
    rebuildTo(n) {
      resetBoard();
      for (let i = 0; i < n; i++) applyEvent(this.events[i], false);
      this.index = n;
      if (n >= this.events.length) { renderAssessment(state.assessment); }
    },
    restart() { if (!this.events.length) return; this.active = true; clearTimeout(this.timer); this.playing = false; this.rebuildTo(0); updateChip(); updatePlaybackUi(); },
    step(dir) {
      if (!this.events.length) return;
      this.active = true;
      clearTimeout(this.timer); this.playing = false;
      if (dir > 0 && this.index < this.events.length) { applyEvent(this.events[this.index], true); this.index++; if (this.index >= this.events.length) renderAssessment(state.assessment); }
      else if (dir < 0 && this.index > 0) { this.rebuildTo(this.index - 1); }
      updateChip(); updatePlaybackUi();
    },
    toggle() {
      if (!this.events.length) return;
      if (this.playing) { clearTimeout(this.timer); this.playing = false; updatePlaybackUi(); return; }
      this.active = true;
      if (this.index >= this.events.length) this.rebuildTo(0);
      this.playing = true; updateChip(); updatePlaybackUi();
      const next = () => {
        if (!this.playing) return;
        if (this.index >= this.events.length) { this.playing = false; renderAssessment(state.assessment); updatePlaybackUi(); return; }
        applyEvent(this.events[this.index], true); this.index++; updatePlaybackUi();
        this.timer = setTimeout(next, this.cadence);
      };
      next();
    },
  };

  function updatePlaybackUi() {
    const n = player.events.length;
    const ready = n > 0;
    for (const id of ["pb-restart", "pb-back", "pb-play", "pb-fwd"]) $(id).disabled = !ready;
    $("pb-play").textContent = player.playing ? "❚❚" : "▶";
    $("pb-counter").textContent = `${Math.min(player.index, n)}/${n}`;
    const dots = $("pb-dots");
    dots.innerHTML = "";
    const show = Math.min(n, 40);
    for (let i = 0; i < show; i++) {
      const dot = document.createElement("i");
      const realIdx = Math.round(i * (n - 1) / Math.max(1, show - 1));
      if (realIdx < player.index) dot.className = "done";
      if (realIdx === player.index - 1) dot.className = "cur";
      dots.appendChild(dot);
    }
    const cap = $("pb-caption");
    if (player.active && player.index > 0 && player.index <= n) {
      const ev = player.events[player.index - 1];
      cap.textContent = `${ev.source}: ${ev.summary}`;
    } else if (state.current && !state.currentDone) {
      cap.textContent = "Live — Maestro is working. Watch the request flow through the gateway to the domain agents.";
    } else if (ready) {
      cap.textContent = "Trace complete. Use the controls to replay it step by step for the room.";
    } else {
      cap.textContent = "Raise an incident or ask a question to watch the fleet work. Completed traces can be replayed here.";
    }
  }

  // ---------------------------------------------------------------- scenarios
  async function loadScenarios() {
    try {
      const r = await fetch("/api/scenarios");
      const list = await r.json();
      const box = $("scenarios");
      box.innerHTML = "";
      for (const s of list) {
        const row = document.createElement("div");
        row.className = "scn" + (s.active ? " active" : "") + (s.active == null ? " unavailable" : "");
        row.title = s.error ? s.error : s.description;
        row.innerHTML = `<div><div class="scn-title">${esc(s.title)}</div><div class="scn-sub">${esc(s.name)} · ${esc(s.domain)}${s.active == null ? " · unavailable" : ""}</div></div>` +
          `<button class="toggle${s.active ? " on" : ""}" ${s.active == null ? "disabled" : ""} aria-label="toggle ${esc(s.name)}"></button>`;
        row.querySelector(".toggle").addEventListener("click", async (e) => {
          const btn = e.currentTarget; btn.disabled = true;
          try {
            const res = await fetch(`/api/scenarios/${encodeURIComponent(s.name)}`, { method: s.active ? "DELETE" : "POST" });
            if (!res.ok) { const j = await res.json().catch(() => ({})); alertBanner(j.detail || `Scenario call failed (${res.status})`); }
          } finally { loadScenarios(); }
        });
        box.appendChild(row);
      }
    } catch (e) { /* console offline */ }
  }

  function alertBanner(msg) {
    const cap = $("pb-caption");
    cap.textContent = `⚠ ${msg}`;
  }

  // ---------------------------------------------------------------- intake
  // Delegation mode for this request (ADR-0015); "" lets Maestro use its configured default.
  function authMode() { const el = $("auth-mode"); return el ? el.value : ""; }

  async function tryIdentity(user, domain) {
    const r = await fetch("/api/identity/try", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user, domain }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || `identity sandbox failed (${r.status})`);
    return j;
  }

  async function raiseIncident() {
    const btn = $("raise-incident"); btn.disabled = true;
    try {
      const r = await fetch("/api/incident", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: $("inc-title").value, service: $("inc-service").value, description: $("inc-desc").value, auth_mode: authMode() }) });
      const j = await r.json();
      if (j.trace_id) startTrace(j.trace_id);
    } catch (e) { alertBanner("Could not reach the console API"); }
    finally { setTimeout(() => { btn.disabled = false; }, 2000); }
  }

  async function askQuestion() {
    const q = $("ask-text").value.trim();
    if (!q) return;
    const btn = $("ask-btn"); btn.disabled = true;
    try {
      const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, auth_mode: authMode() }) });
      const j = await r.json();
      if (j.trace_id) startTrace(j.trace_id);
    } catch (e) { alertBanner("Could not reach the console API"); }
    finally { setTimeout(() => { btn.disabled = false; }, 2000); }
  }

  // ---------------------------------------------------------------- SSE
  function connect() {
    const es = new EventSource("/api/stream");
    es.addEventListener("fleet", (m) => { try { onEvent(JSON.parse(m.data)); } catch (e) { /* ignore */ } });
    es.onerror = () => { es.close(); setTimeout(connect, 2000); };
  }

  // ---------------------------------------------------------------- header links + credential cards
  function copyButton(value) {
    return `<button type="button" class="copy" data-copy="${esc(value)}" title="Copy">⧉</button>`;
  }

  function credCard(key, label, href, creds) {
    const c = (creds && creds[key]) || {};
    let rows = `<div class="cred-row"><span class="cred-k">URL</span><code>${esc(href)}</code>${copyButton(href)}</div>`;
    if (c.username) rows += `<div class="cred-row"><span class="cred-k">user</span><code>${esc(c.username)}</code>${copyButton(c.username)}</div>`;
    if (c.password) rows += `<div class="cred-row"><span class="cred-k">password</span><code>${esc(c.password)}</code>${copyButton(c.password)}</div>`;
    if (c.note) rows += `<div class="cred-note">${esc(c.note)}</div>`;
    if (key === "keycloak" && creds) {
      const users = (creds.demo_users || []).map((u) => `<li><code>${esc(u.username)}</code> / <code>${esc(u.password)}</code>${copyButton(u.password)}<div class="cred-roles">${(u.roles || []).map(esc).join(" · ")}</div></li>`).join("");
      if (users) rows += `<div class="cred-k cred-head">Demo users</div><ul class="cred-users">${users}</ul>`;
      const sa = (creds.service_accounts || []).map((s) => `<li><code>${esc(s.client_id)}</code> · secret <code>${esc(s.secret)}</code>${copyButton(s.secret)}${s.note ? `<div class="cred-roles">${esc(s.note)}</div>` : ""}</li>`).join("");
      if (sa) rows += `<div class="cred-k cred-head">Service accounts</div><ul class="cred-users">${sa}</ul>`;
      rows += `<div class="cred-note">Fetch a token: <code>make token-engineer</code>${copyButton("make token-engineer")} · <code>make token-sre-lead</code></div>`;
    }
    return `<div class="cred-card" role="tooltip"><div class="cred-title">${esc(label)}</div>${rows}</div>`;
  }

  function renderTopLinks(topo) {
    const links = $("toplinks");
    links.innerHTML = "";
    const u = topo.urls || {};
    const creds = topo.credentials || null;
    const items = [["grafana", "Grafana", u.grafana], ["prometheus", "Prometheus", u.prometheus], ["keycloak", "Keycloak", u.keycloak], ["gateway", "Gateway UI", u.gateway_ui], ["edge", "Member portal API", u.edge]];
    for (const [key, label, href] of items) {
      if (!href) continue;
      const wrap = document.createElement("span");
      wrap.className = "toplink";
      wrap.innerHTML = `<a href="${esc(href)}" target="_blank" rel="noopener" aria-describedby="cred-${key}">${I.svg(I.LINK_ICON[key], 15)}<span>${esc(label)} ↗</span></a>` + credCard(key, label, href, creds);
      wrap.querySelector(".cred-card").id = `cred-${key}`;
      links.appendChild(wrap);
    }
    links.addEventListener("click", async (e) => {
      const b = e.target.closest(".copy");
      if (!b) return;
      e.preventDefault();
      const v = b.dataset.copy;
      try { await navigator.clipboard.writeText(v); } catch (err) {
        const ta = document.createElement("textarea"); ta.value = v; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e2) { /* ignore */ } ta.remove();
      }
      const old = b.textContent; b.textContent = "✓"; setTimeout(() => { b.textContent = old; }, 900);
    });
  }

  // ---------------------------------------------------------------- init
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    $("theme-toggle").textContent = t === "dark" ? "☀" : "☾";
    try { localStorage.setItem("maestro-theme", t); } catch (e) { /* private mode */ }
  }

  async function init() {
    let theme = "dark";
    try { theme = localStorage.getItem("maestro-theme") || "dark"; } catch (e) { /* ignore */ }
    applyTheme(theme);
    $("theme-toggle").addEventListener("click", () => applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"));

    const topo = await (await fetch("/api/topology")).json();
    state.topology = topo;
    renderBoard(topo);
    renderTopLinks(topo);
    window.MaestroDrawer.init({
      events: () => (player.active ? player.events.slice(0, player.index) : (state.traces[state.current] || [])),
      traceId: () => state.current,
      replaying: () => player.active,
      node: (id) => ((state.topology && state.topology.nodes) || []).find((n) => n.id === id) || null,
      credentials: () => (state.topology && state.topology.credentials) || null,
      identity: () => (state.topology && state.topology.identity) || null,
      tryIdentity,
      fmtTime,
      select: selectNode,
    });

    $("raise-incident").addEventListener("click", raiseIncident);
    $("ask-btn").addEventListener("click", askQuestion);
    $("clear-scenarios").addEventListener("click", async () => {
      for (const n of ["apim-bad-route", "cache-pressure", "messaging-lag"]) await fetch(`/api/scenarios/${n}`, { method: "DELETE" }).catch(() => {});
      loadScenarios();
    });
    $("pb-restart").addEventListener("click", () => player.restart());
    $("pb-back").addEventListener("click", () => player.step(-1));
    $("pb-fwd").addEventListener("click", () => player.step(1));
    $("pb-play").addEventListener("click", () => player.toggle());
    updatePlaybackUi();
    loadScenarios();
    setInterval(loadScenarios, 10000);
    connect();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
