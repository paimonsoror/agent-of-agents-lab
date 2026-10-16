/* Play-by-play drawer: click any box on the board to read, in plain English, what that component
 * was asked, what it did, and how it talked to its neighbours during the current trace.
 * Also hosts the static "How it works" guide. Vanilla JS, no deps. Wired by app.js via init(). */

window.MaestroDrawer = (function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const DOMAINS = ["apim", "cache", "messaging"];
  const PLATFORMS = ["prometheus", "valkey", "kafka", "edge-gateway", "grafana", "keycloak", "skills", "portal"];
  const RESULT_CLIP = 600;

  let api = null;
  const st = { open: false, mode: null, nodeId: null, raf: 0 };

  // What each box is for — shown at the top of its play-by-play so a newcomer has context even
  // before the first event arrives.
  const ROLE = {
    "console": "The consumer. Stands in for the ITSM / chat bridge: raising an incident here asks Maestro using the console's own non-human identity (a Keycloak service account).",
    "ide": "The other consumer. An engineer's IDE (Claude Code, Copilot, Cursor) talks to the very same gateway endpoint with the engineer's own identity — same agents, same tools, filtered by the engineer's roles.",
    "maestro": "The orchestrator — the agent of agents. It never remediates: it works out which domains are relevant, asks their agents in parallel (forwarding the caller's own token), and consolidates their findings into one assessment for a human.",
    "gateway": "The fleet gateway (agentgateway). Every hop between Maestro and the domain agents passes through here: it validates the caller's JWT against Keycloak, enforces per-tool RBAC (a caller without the domain role never even sees that agent's tools), passes the token through, and records metrics.",
    "keycloak": "The identity provider. Issues the JWTs every caller presents: client-credentials tokens for services (non-human identities) and user tokens for engineers. Roles ride inside the token as realm_access.roles.",
    "skills": "The cognition. Each agent's expertise is a SKILL.md bundle (agentskills.io format) — what to check, which metrics and dashboards matter, what 'implicated' means. Agents load their skills at request time and can read reference files on demand.",
    "apim-agent": "Domain agent for API management. Verifies the JWT itself, loads the apim-observability skill, inspects the edge gateway's declarative config and change history, probes routes, and reads the shared Prometheus — then returns a Finding.",
    "cache-agent": "Domain agent for the distributed cache. Loads the cache-observability skill, reads Valkey INFO / CONFIG / SLOWLOG natively, checks evictions and hit ratio in Prometheus, and returns a Finding.",
    "messaging-agent": "Domain agent for messaging. Loads the messaging-observability skill, reads consumer-group lag and broker metadata from Kafka, checks produce rate and members in Prometheus, and returns a Finding.",
    "edge-gateway": "The API-management platform: a second agentgateway fronting the member portal. Its routes live in a ConfigMap, so a bad change is inspectable (and annotated with a change id).",
    "valkey": "The distributed-cache platform (Redis-compatible). The member portal caches member lookups here; memory pressure shows up as evictions and a collapsing hit ratio.",
    "kafka": "The messaging platform. The member portal publishes member.events; a consumer group reads them. Lag growth is the signal every messaging SRE watches first.",
    "prometheus": "The shared monitoring every domain already sends to. Each platform exports natively; agents query it with PromQL and cite the results as evidence.",
    "grafana": "Dashboards over the shared Prometheus. Findings deep-link to the exact panel an agent looked at so a responder can open what the agent saw.",
    "portal": "The sample business application whose incident we investigate. It depends on all three domains, which is what makes 'which domain is implicated?' a real question.",
  };

  const GUIDE = [
    { node: "console", title: "1 · A consumer asks", text: "An operator raises a P1 in the console (or an engineer asks from their IDE). The console starts a trace — a correlation id every later event carries." },
    { node: "keycloak", title: "2 · Identity is established", text: "The consumer obtains a JWT from Keycloak: a client-credentials token for the console's service account, or the engineer's own user token. Roles such as domain:cache travel inside the token." },
    { node: "maestro", title: "3 · Maestro receives the question", text: "Maestro verifies the JWT, records who asked, loads its orchestration skill, and decides which domains could be involved." },
    { node: "gateway", title: "4 · The fleet gateway authenticates and authorises", text: "Maestro connects over MCP with the caller's token — never its own. The gateway checks issuer, audience and signature against Keycloak, then lists only the tools the caller's roles allow. A missing role makes an agent invisible, not merely blocked." },
    { node: "apim-agent", title: "5 · Domain agents investigate", text: "Each relevant agent receives assess() with the token passed through, verifies it again, and loads its SKILL.md bundle — the domain's expert knowledge." },
    { node: "prometheus", title: "6 · Platforms and shared monitoring are queried", text: "Agents use platform-native tools (gateway config, Valkey INFO, Kafka lag) and PromQL against the shared Prometheus, citing Grafana panels as evidence." },
    { node: "cache-agent", title: "7 · Findings come back", text: "Every agent returns the same Finding shape: implicated or cleared, a confidence score, evidence with links, and recommended actions. Agents recommend; they never remediate." },
    { node: "console", title: "8 · One assessment, a human decides", text: "Maestro consolidates the findings into a single assessment — implicated, cleared, not consulted and why — and the next step for a responder. The human decides." },
  ];

  // ------------------------------------------------------------------ helpers
  function fmtTime(ts) { return api && api.fmtTime ? api.fmtTime(ts) : ts; }
  function nodeMeta(id) { return (api && api.node(id)) || { id, label: id, sublabel: "" }; }
  function who(c) {
    if (!c) return "unknown caller";
    const name = c.username || c.preferred_username || c.azp || c.sub || "unknown";
    const parts = [];
    if (c.sub) parts.push(`sub ${c.sub}`);
    if (c.azp) parts.push(`azp ${c.azp}`);
    if (Array.isArray(c.roles) && c.roles.length) parts.push(`roles ${c.roles.join(", ")}`);
    return `${name}${parts.length ? ` (${parts.join(" · ")})` : ""}`;
  }
  function code(s) { return `<pre class="pbp-code">${esc(typeof s === "string" ? s : JSON.stringify(s, null, 2))}</pre>`; }
  function quote(s) { return s ? `<blockquote class="pbp-quote">${esc(s)}</blockquote>` : ""; }
  function result(r) {
    if (r == null || r === "") return "";
    const text = typeof r === "string" ? r : JSON.stringify(r, null, 2);
    const long = text.length > RESULT_CLIP;
    return `<div class="pbp-result-wrap"><pre class="pbp-result${long ? " clipped" : ""}">${esc(text)}</pre>${long ? '<button class="pbp-more" type="button">show more</button>' : ""}</div>`;
  }
  function pill(text, cls) { return `<span class="pill ${cls || ""}">${esc(text)}</span>`; }
  function conf(c) { return typeof c === "number" ? c.toFixed(2) : ""; }
  function raw(ev) {
    return `<div class="pbp-rawrow"><button class="pbp-raw-toggle" type="button">raw</button><pre class="pbp-raw" hidden>${esc(JSON.stringify({ ts: ev.ts, trace_id: ev.trace_id, source: ev.source, kind: ev.kind, edge: ev.edge, summary: ev.summary, detail: ev.detail || null }, null, 2))}</pre></div>`;
  }
  const KIND_CLASS = {
    "incident.raised": "c-incident", "question.asked": "c-incident", "error": "c-error", "token.issued": "c-identity",
    "request.sent": "c-request", "request.received": "c-request", "tools.discovered": "c-request", "skills.loaded": "c-skills",
    "evidence.gathered": "c-evidence", "llm.turn": "c-evidence", "finding.returned": "c-finding", "assessment.posted": "c-finding",
    "scenario.applied": "c-scenario", "scenario.cleared": "c-scenario",
  };

  // ------------------------------------------------------------------ relevance
  function domainOfAgent(id) { return id.endsWith("-agent") ? id.slice(0, -6) : null; }

  function relevant(ev, id) {
    const e = ev.edge || {};
    if (ev.source === id || e.from === id || e.to === id) return true;
    if (id === "gateway") {
      return ev.kind === "tools.discovered" || (ev.kind === "request.sent" && ev.source === "maestro") ||
        (ev.kind === "request.received" && ev.source !== "maestro");
    }
    const dom = domainOfAgent(id);
    if (dom && ev.kind === "request.sent" && ev.source === "maestro") {
      const tool = (ev.detail && ev.detail.tool) || "";
      return tool.startsWith(`${dom}_`);
    }
    return false;
  }

  // ------------------------------------------------------------------ per-kind narrative
  function describe(ev, viewId) {
    const d = ev.detail || {};
    const src = ev.source;
    const srcLabel = nodeMeta(src).label || src;
    switch (ev.kind) {
      case "incident.raised": {
        const text = d.question || d.description || "";
        const meta = [d.incident, d.title, d.service ? `service ${d.service}` : ""].filter(Boolean).join(" · ");
        return { h: `Incident raised${d.incident ? ` · ${d.incident}` : ""}`, b: (meta ? `<div class="pbp-meta">${esc(meta)}</div>` : "") + quote(text || ev.summary) };
      }
      case "question.asked":
        return { h: `Question asked from ${src === "ide" ? "the IDE" : "the console"}`, b: quote(d.question || ev.summary) };
      case "token.issued":
        return { h: "Identity established", b: `<div>${esc(d.text || "Identity: client-credentials token for fleet-console issued by Keycloak")}</div>${d.caller ? `<div class="pbp-meta">${esc(who(d.caller))}</div>` : ""}` };
      case "request.sent": {
        if (src === "maestro") {
          const tool = d.tool || "a domain agent";
          const tr = d.transport;
          let transport = "";
          if (tr) {
            const a = tr.auth || {};
            const roles = Array.isArray(a.roles) ? a.roles.join(", ") : "";
            transport = `<div class="pbp-transport">` +
              `<div><b>Transport</b> ${esc(tr.protocol || "MCP tools/call over Streamable HTTP")}${tr.endpoint ? ` → <code>${esc(tr.endpoint)}</code>` : ""}</div>` +
              `<div><b>Authorization</b> ${esc(a.scheme || "Bearer JWT")}${a.sub || a.azp ? ` (${[a.sub ? `sub ${a.sub}` : "", a.azp ? `azp ${a.azp}` : "", roles ? `roles ${roles}` : ""].filter(Boolean).map(esc).join(" · ")})` : ""}</div>` +
              (tr.gateway_rule ? `<div><b>Gateway rule</b> <code>${esc(tr.gateway_rule)}</code></div>` : "") +
              (tr.trace_id ? `<div><b>Trace</b> <code>${esc(tr.trace_id)}</code></div>` : "") + `</div>`;
          } else {
            transport = `<div class="pbp-transport"><div><b>Transport</b> MCP tools/call over Streamable HTTP via the fleet gateway, Authorization: Bearer JWT (the caller's own token, passed through)</div></div>`;
          }
          return { h: `Maestro → ${esc(tool)} via the fleet gateway`, b: quote(d.args && d.args.question) + transport };
        }
        return { h: ev.summary, b: quote(d.question) + (d.transport ? code(d.transport) : "") };
      }
      case "request.received": {
        const w = who(d.caller);
        if (src === "maestro") return { h: `Asked by ${esc((d.caller && (d.caller.username || d.caller.azp)) || "unknown")}`, b: `<div class="pbp-meta">${esc(w)}</div>${quote(d.question)}` };
        return { h: `Received from the gateway · caller ${esc((d.caller && (d.caller.username || d.caller.azp)) || "unknown")}`, b: `<div class="pbp-meta">${esc(w)} · the JWT was verified again by the agent</div>${quote(d.question)}` };
      }
      case "tools.discovered": {
        const tools = d.tools || [];
        const hidden = d.hidden || d.not_visible || [];
        const visible = d.visible || [];
        let b = tools.length ? `<div class="pbp-meta">Tools the gateway exposed to this caller:</div><ul class="pbp-list">${tools.map((t) => `<li><code>${esc(t)}</code></li>`).join("")}</ul>` : "";
        if (visible.length) b += `<div class="pbp-meta">Visible domains: ${visible.map(esc).join(", ")}</div>`;
        for (const h of hidden) b += `<div class="pbp-hidden">${esc(h)}: not visible to this caller (missing role <code>domain:${esc(h)}</code>)</div>`;
        return { h: `Discovered ${visible.length || tools.length} agent tool(s) through the gateway${hidden.length ? ` · ${hidden.length} hidden by RBAC` : ""}`, b };
      }
      case "skills.loaded": {
        if (/^Consulted/i.test(ev.summary || "")) return { h: "Consulted a skill reference on demand", b: `<div>${esc(ev.summary)}</div>` };
        const skills = d.skills || [];
        const items = skills.map((s) => `<li><code>${esc(s.name)}</code>${s.version ? ` v${esc(s.version)}` : ""}${Array.isArray(s.references) && s.references.length ? `<div class="pbp-refs">references: ${s.references.map(esc).join(", ")}</div>` : ""}</li>`).join("");
        return { h: `${esc(srcLabel)} loaded ${skills.length || ""} skill${skills.length === 1 ? "" : "s"} into its reasoning`, b: items ? `<ul class="pbp-list">${items}</ul>` : `<div>${esc(ev.summary)}</div>` };
      }
      case "evidence.gathered": {
        const q = d.query || d.command || "";
        const target = ev.edge && ev.edge.to ? nodeMeta(ev.edge.to).label : "";
        return { h: `${esc(srcLabel)} gathered evidence${target ? ` from ${esc(target)}` : ""}`, b: (q ? code(q) : `<div>${esc(ev.summary)}</div>`) + result(d.result) };
      }
      case "llm.turn": {
        const m = /^(\S+) turn (\d+): stop=(\S+)/.exec(ev.summary || "");
        const u = d.usage || {};
        const tokens = `tokens in ${u.input_tokens ?? "–"} · out ${u.output_tokens ?? "–"} · cache read ${u.cache_read_input_tokens ?? 0} · cache write ${u.cache_creation_input_tokens ?? 0}`;
        return { h: m ? `${esc(m[1])} · turn ${m[2]} · stop=${esc(m[3])}` : esc(ev.summary), b: `<div class="pbp-meta">${esc(tokens)}${d.effort ? ` · effort ${esc(d.effort)}` : ""}</div>` };
      }
      case "finding.returned": {
        const imp = d.implicated === true;
        const ev2 = (d.evidence || []).map((e) => `<li><code>${esc(e.source || "")}</code> ${esc(e.observation || "")}${e.link ? ` <a href="${esc(e.link)}" target="_blank" rel="noopener">open ↗</a>` : ""}</li>`).join("");
        const acts = (d.recommended_actions || []).map((a) => `<li>${esc(a)}</li>`).join("");
        return {
          h: `${esc(srcLabel)} returned its finding: ${imp ? "implicated" : "cleared"}${conf(d.confidence) ? ` · ${conf(d.confidence)}` : ""}`,
          b: `<div class="chips">${pill(imp ? `implicated · ${conf(d.confidence)}` : `cleared · ${conf(d.confidence)}`, imp ? "implicated" : "cleared")}${d.domain ? pill(d.domain) : ""}</div>` +
            (d.headline ? `<div class="pbp-strong">${esc(d.headline)}</div>` : "") + (d.summary ? `<p>${esc(d.summary)}</p>` : "") +
            (ev2 ? `<div class="pbp-meta">Evidence</div><ul class="pbp-list">${ev2}</ul>` : "") +
            (acts ? `<div class="pbp-meta">Recommended actions</div><ul class="pbp-list">${acts}</ul>` : "") +
            (Array.isArray(d.skills_used) && d.skills_used.length ? `<div class="pbp-meta">Skills used: ${d.skills_used.map(esc).join(", ")}</div>` : ""),
        };
      }
      case "assessment.posted": {
        const a = d.assessment && d.assessment.verdict ? d.assessment : d;
        const chips = [];
        for (const x of a.implicated || []) chips.push(pill(`${x.domain} · implicated ${conf(x.confidence)}`, "implicated"));
        for (const x of a.cleared || []) chips.push(pill(`${x.domain} · cleared ${conf(x.confidence)}`, "cleared"));
        for (const x of a.not_consulted || []) chips.push(pill(`${x.domain} · not consulted${x.reason ? ` — ${x.reason}` : ""}`, "skipped"));
        return {
          h: "Maestro posted one consolidated assessment · a human decides the next step",
          b: (a.verdict ? `<div class="pbp-strong">${esc(a.verdict)}</div>` : "") + `<div class="chips">${chips.join("")}</div>` +
            (a.next_step_for_human ? `<div class="next-step"><b>Next step for a human</b>${esc(a.next_step_for_human)}</div>` : "") +
            `<div class="pbp-meta">The full assessment, with every finding, is in the Assessment panel below the board.</div>`,
        };
      }
      case "scenario.applied": return { h: `Fault injected: ${esc(ev.summary)}`, b: d && Object.keys(d).length ? code(d) : "" };
      case "scenario.cleared": return { h: `Fault cleared: ${esc(ev.summary)}`, b: d && Object.keys(d).length ? code(d) : "" };
      case "error": return { h: `Error: ${esc(ev.summary)}`, b: d && Object.keys(d).length ? code(d) : "" };
      default: return { h: esc(ev.summary || ev.kind), b: d && Object.keys(d).length ? code(d) : "" };
    }
  }

  function card(ev, viewId) {
    const { h, b } = describe(ev, viewId);
    const cls = KIND_CLASS[ev.kind] || "c-neutral";
    const arrow = ev.edge && ev.edge.from && ev.edge.to ? `<span class="pbp-edge">${esc(nodeMeta(ev.edge.from).label)} → ${esc(nodeMeta(ev.edge.to).label)}</span>` : "";
    return `<article class="pbp-card ${cls}${ev.kind === "error" ? " is-error" : ""}">` +
      `<div class="pbp-head"><span class="pbp-time">${esc(fmtTime(ev.ts))}</span><span class="tl-kind ${cls}">${esc(ev.kind)}</span><span class="pbp-src">${esc(ev.source)}</span>${arrow}</div>` +
      `<div class="pbp-headline">${h}</div>` + (b ? `<div class="pbp-body">${b}</div>` : "") + raw(ev) + `</article>`;
  }

  // Demo identities an engineer would use from the IDE (served by /api/topology.credentials).
  function identitiesBlock() {
    const c = api.credentials && api.credentials();
    if (!c || !Array.isArray(c.demo_users) || !c.demo_users.length) return "";
    const users = c.demo_users.map((u) => `<li><code>${esc(u.username)}</code> / <code>${esc(u.password)}</code> — roles: ${(u.roles || []).map((r) => `<code>${esc(r)}</code>`).join(" ")}</li>`).join("");
    return `<div class="pbp-ids"><h4>Demo identities for the IDE path</h4><ul class="pbp-list">${users}</ul>` +
      `<div class="pbp-meta">Get a token with <code>make token-engineer</code> or <code>make token-sre-lead</code>, then point your MCP client at the gateway's <code>/maestro/mcp</code> (see docs/ide-setup.md). An identity without <code>domain:messaging</code> never sees the messaging agent.</div></div>`;
  }

  // ------------------------------------------------------------------ views
  function renderNode(id) {
    const meta = nodeMeta(id);
    const all = api.events();
    const evs = all.filter((ev) => relevant(ev, id));
    const trace = api.traceId();
    const I = window.MaestroIcons;
    $("drawer-title").innerHTML = (I ? I.svg(I.NODE_ICON[id] || "agent", 22, "drawer-icon") : "") + `<span>${esc(meta.label || id)}</span>`;
    $("drawer-sub").textContent = [meta.sublabel, trace ? `trace ${trace}` : "no active trace", api.replaying() ? `replay · ${evs.length} of the steps so far` : `${evs.length} step${evs.length === 1 ? "" : "s"}`].filter(Boolean).join(" · ");
    let html = `<p class="pbp-role">${esc(ROLE[id] || "")}</p>`;
    if (id === "ide") html += identitiesBlock();
    if (!trace) {
      html += `<div class="pbp-empty">No trace yet. Raise an incident or ask Maestro a question, then come back to this box to read its play-by-play.</div>`;
    } else if (!evs.length) {
      html += `<div class="pbp-empty">Nothing has touched ${esc(meta.label)} ${api.replaying() ? "up to this point in the replay" : "in this trace"} yet.</div>`;
    } else if (PLATFORMS.includes(id)) {
      // Platforms don't act; they are consulted. Group by who asked.
      const groups = new Map();
      for (const ev of evs) { const k = ev.source; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(ev); }
      for (const [asker, list] of groups) {
        const label = nodeMeta(asker).label || asker;
        html += `<h3 class="pbp-group"><button type="button" class="pbp-link" data-node="${esc(asker)}">${esc(label)}</button> <span class="muted">· ${list.length} interaction${list.length === 1 ? "" : "s"}</span></h3>`;
        html += list.map((ev) => card(ev, id)).join("");
      }
    } else {
      html += evs.map((ev) => card(ev, id)).join("");
    }
    $("drawer-body").innerHTML = html;
  }

  function renderGuide() {
    $("drawer-title").textContent = "How it works";
    $("drawer-sub").textContent = "The eight steps of every request · click a step to open that box's play-by-play";
    $("drawer-body").innerHTML = `<ol class="pbp-guide">` + GUIDE.map((s) => {
      const m = nodeMeta(s.node);
      return `<li><button type="button" class="pbp-step" data-node="${esc(s.node)}"><span class="pbp-step-title">${esc(s.title)}</span><span class="pbp-step-text">${esc(s.text)}</span><span class="pbp-step-node">→ ${esc(m.label)}</span></button></li>`;
    }).join("") + `</ol><p class="pbp-role">Transport today is MCP over the fleet gateway with the caller's JWT propagated on every hop; A2A is the north star and is a routing-policy change on the same gateway. Agents recommend; humans decide.</p>`;
  }

  function show() {
    const el = $("drawer");
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add("open"));
    st.open = true;
  }

  function openNode(id) {
    if (!api || !api.node(id)) return;
    st.mode = "node"; st.nodeId = id;
    api.select(id);
    renderNode(id);
    show();
    $("drawer-body").scrollTop = 0;
  }

  function openGuide() {
    st.mode = "guide"; st.nodeId = null;
    api.select(null);
    renderGuide();
    show();
    $("drawer-body").scrollTop = 0;
  }

  function close() {
    const el = $("drawer");
    el.classList.remove("open");
    st.open = false; st.mode = null; st.nodeId = null;
    api.select(null);
    setTimeout(() => { if (!st.open) el.hidden = true; }, 260);
  }

  // Re-render the open node view when new events arrive or the replay cursor moves (coalesced per frame).
  function refresh() {
    if (!st.open || st.mode !== "node") return;
    if (st.raf) return;
    st.raf = requestAnimationFrame(() => {
      st.raf = 0;
      if (!st.open || st.mode !== "node") return;
      const body = $("drawer-body");
      const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
      renderNode(st.nodeId);
      if (atBottom) body.scrollTop = body.scrollHeight;
    });
  }

  function wire() {
    $("drawer-close").addEventListener("click", close);
    $("how-it-works").addEventListener("click", () => (st.open && st.mode === "guide" ? close() : openGuide()));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && st.open) close(); });
    $("drawer-body").addEventListener("click", (e) => {
      const nodeBtn = e.target.closest("[data-node]");
      if (nodeBtn) { openNode(nodeBtn.dataset.node); return; }
      const rawBtn = e.target.closest(".pbp-raw-toggle");
      if (rawBtn) { const pre = rawBtn.parentElement.querySelector("pre.pbp-raw"); pre.hidden = !pre.hidden; rawBtn.textContent = pre.hidden ? "raw" : "hide raw"; return; }
      const more = e.target.closest(".pbp-more");
      if (more) { const pre = more.previousElementSibling; pre.classList.toggle("clipped"); more.textContent = pre.classList.contains("clipped") ? "show more" : "show less"; }
    });
  }

  function init(a) { api = a; wire(); }

  return { init, openNode, openGuide, close, refresh, isOpen: () => st.open, current: () => st.nodeId };
})();
