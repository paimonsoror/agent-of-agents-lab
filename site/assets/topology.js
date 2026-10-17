/* Animated topology for the site. Renders the Maestro fleet as SVG and exposes a tiny
 * animation API (flow a packet along an edge, set a node's state). Vanilla JS + SMIL. */
window.MaestroTopology = (function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const W = 1040, H = 430, NW = 118, NH = 52;

  // x/y are node centres. Columns: consumers, orchestration, gateway, agents, platforms, monitoring.
  const NODES = [
    { id: "console", label: "Fleet Console", sub: "incident intake", icon: "console", x: 80, y: 120 },
    { id: "ide", label: "Engineer in IDE", sub: "Claude Code / Copilot", icon: "ide", x: 80, y: 230 },
    { id: "keycloak", label: "Keycloak", sub: "identity · JWT issuer", icon: "keycloak", x: 80, y: 350 },
    { id: "maestro", label: "Maestro", sub: "Claude Opus 5.5", icon: "maestro", x: 265, y: 175, claude: true },
    { id: "skills", label: "skills/", sub: "SKILL.md bundles", icon: "skills", x: 265, y: 320 },
    { id: "gateway", label: "Fleet gateway", sub: "agentgateway · JWT · RBAC", icon: "gateway", x: 450, y: 175 },
    { id: "apim-agent", label: "apim-agent", sub: "Claude Sonnet 5.5", icon: "agent", x: 635, y: 80, claude: true },
    { id: "cache-agent", label: "cache-agent", sub: "Claude Sonnet 5.5", icon: "agent", x: 635, y: 175, claude: true },
    { id: "messaging-agent", label: "messaging-agent", sub: "Claude Sonnet 5.5", icon: "agent", x: 635, y: 270, claude: true },
    { id: "edge", label: "Edge gateway", sub: "APIM · agentgateway", icon: "edge-gateway", x: 820, y: 80 },
    { id: "valkey", label: "Valkey", sub: "distributed cache", icon: "valkey", x: 820, y: 175 },
    { id: "kafka", label: "Kafka", sub: "messaging", icon: "apachekafka", x: 820, y: 270 },
    { id: "prometheus", label: "Prometheus", sub: "shared monitoring", icon: "prometheus", x: 975, y: 175 },
    { id: "grafana", label: "Grafana", sub: "dashboards", icon: "grafana", x: 975, y: 320 },
  ];
  const EDGES = [
    { id: "console-keycloak", from: "console", to: "keycloak", kind: "v", dashed: true },
    { id: "ide-keycloak", from: "ide", to: "keycloak", kind: "v", dashed: true },
    { id: "console-maestro", from: "console", to: "maestro" },
    { id: "ide-gateway", from: "ide", to: "gateway" },
    { id: "maestro-skills", from: "maestro", to: "skills", kind: "v", dashed: true },
    { id: "maestro-gateway", from: "maestro", to: "gateway" },
    { id: "maestro-keycloak", from: "maestro", to: "keycloak", kind: "mk", dashed: true },
    { id: "gateway-keycloak", from: "gateway", to: "keycloak", kind: "gk", dashed: true },
    { id: "gateway-apim", from: "gateway", to: "apim-agent" },
    { id: "gateway-cache", from: "gateway", to: "cache-agent" },
    { id: "gateway-messaging", from: "gateway", to: "messaging-agent" },
    { id: "apim-edge", from: "apim-agent", to: "edge" },
    { id: "cache-valkey", from: "cache-agent", to: "valkey" },
    { id: "messaging-kafka", from: "messaging-agent", to: "kafka" },
    { id: "apim-prom", from: "apim-agent", to: "prometheus", kind: "arc" },
    { id: "cache-prom", from: "cache-agent", to: "prometheus", kind: "arc" },
    { id: "messaging-prom", from: "messaging-agent", to: "prometheus", kind: "arc" },
    { id: "edge-prom", from: "edge", to: "prometheus" , dashed: true },
    { id: "valkey-prom", from: "valkey", to: "prometheus", dashed: true },
    { id: "kafka-prom", from: "kafka", to: "prometheus", dashed: true },
    { id: "grafana-prom", from: "grafana", to: "prometheus", kind: "v", dashed: true },
  ];
  const LANES = [
    ["Consumers", 80], ["Orchestration", 265], ["Fleet gateway", 450], ["Domain agents", 635], ["Domain platforms", 820], ["Shared monitoring", 975],
  ];

  const byId = Object.fromEntries(NODES.map(n => [n.id, n]));

  function pathFor(e) {
    const a = byId[e.from], b = byId[e.to];
    if (e.kind === "v") {
      const up = b.y < a.y;
      const y1 = a.y + (up ? -NH / 2 : NH / 2), y2 = b.y + (up ? NH / 2 : -NH / 2);
      return `M${a.x},${y1} C${a.x},${(y1 + y2) / 2} ${b.x},${(y1 + y2) / 2} ${b.x},${y2}`;
    }
    if (e.kind === "mk") { // maestro left-bottom → keycloak top-right (the token-exchange hop, ADR-0015)
      const x1 = a.x - NW / 2, y1 = a.y + 14, x2 = b.x + NW / 2 - 10, y2 = b.y - NH / 2;
      return `M${x1},${y1} C${x1 - 50},${y1 + 10} ${x2 + 10},${y2 - 60} ${x2},${y2}`;
    }
    if (e.kind === "gk") { // gateway bottom → keycloak right, a wide curve under maestro/skills
      const x1 = a.x, y1 = a.y + NH / 2, x2 = b.x + NW / 2, y2 = b.y;
      return `M${x1},${y1} C${x1},${y2 + 40} ${x2 + 60},${y2 + 50} ${x2},${y2}`;
    }
    if (e.kind === "arc") { // agent right → prometheus left, passing above/below the platform column
      const x1 = a.x + NW / 2, y1 = a.y, x2 = b.x - NW / 2, y2 = b.y;
      const bend = a.y < b.y ? -30 : a.y > b.y ? 30 : 0;
      return `M${x1},${y1} C${x1 + 70},${y1 + bend} ${x2 - 70},${y2 - bend} ${x2},${y2}`;
    }
    const x1 = a.x + NW / 2, y1 = a.y, x2 = b.x - NW / 2, y2 = b.y;
    const mx = (x1 + x2) / 2;
    return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
  }

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  function render(container, opts) {
    opts = opts || {};
    const uid = "t" + Math.random().toString(36).slice(2, 7);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "topo", role: "img", "aria-label": "Maestro fleet topology" }, null);
    const title = el("title", {}, svg); title.textContent = "Maestro fleet topology";
    const gLanes = el("g", {}, svg), gEdges = el("g", {}, svg), gNodes = el("g", {}, svg), gPackets = el("g", {}, svg);

    LANES.forEach(([name, x]) => {
      const t = el("text", { x, y: 22, class: "lane", "text-anchor": "middle" }, gLanes); t.textContent = name;
      el("line", { x1: x, y1: 32, x2: x, y2: H - 10, class: "lane-line" }, gLanes);
    });

    const edges = {};
    EDGES.forEach(e => {
      const p = el("path", { id: `${uid}-${e.id}`, d: pathFor(e), class: "edge" + (e.dashed ? " dashed" : "") }, gEdges);
      edges[e.id] = p;
    });

    const nodes = {};
    NODES.forEach(n => {
      const g = el("g", { class: "node", "data-id": n.id, transform: `translate(${n.x - NW / 2},${n.y - NH / 2})`, tabindex: opts.focusable ? "0" : "-1" }, gNodes);
      el("rect", { width: NW, height: NH, rx: 10 }, g);
      if (window.MaestroIcons) window.MaestroIcons.place(g, n.icon, 9, NH / 2 - 11, 22);
      const t = el("text", { x: 38, y: 22 }, g); t.textContent = n.label;
      const s = el("text", { x: 38, y: 37, class: "sub" }, g); s.textContent = n.sub;
      if (n.claude && window.MaestroIcons) window.MaestroIcons.place(g, "claude", NW - 16, 4, 11);
      const tt = el("title", {}, g); tt.textContent = `${n.label} — ${n.sub}`;
      nodes[n.id] = g;
    });

    container.appendChild(svg);
    const REDUCED = window.MaestroSite && window.MaestroSite.REDUCED;

    function setState(id, state) {
      const g = nodes[id]; if (!g) return;
      g.classList.remove("active", "ok", "bad", "off", "pulse");
      if (state && state !== "idle") state.split(" ").forEach(s => g.classList.add(s));
    }
    function setEdge(id, cls) {
      const p = edges[id]; if (!p) return;
      p.classList.remove("hot", "hot-ok", "hot-bad");
      if (cls) p.classList.add(cls);
    }
    function reset() {
      Object.keys(nodes).forEach(id => setState(id, "idle"));
      Object.keys(edges).forEach(id => setEdge(id, null));
      while (gPackets.firstChild) gPackets.removeChild(gPackets.firstChild);
      clearBadges();
    }
    const badges = [];
    function badge(id, text, cls) {
      const n = byId[id]; if (!n) return;
      const g = el("g", { class: "badge-g" }, gNodes);
      const w = text.length * 6 + 12;
      el("rect", { x: n.x - w / 2, y: n.y + NH / 2 + 4, width: w, height: 15, class: "badge-bg", style: cls ? `fill: var(--${cls})` : "" }, g);
      const t = el("text", { x: n.x, y: n.y + NH / 2 + 15, class: "badge", "text-anchor": "middle" }, g); t.textContent = text;
      badges.push(g);
    }
    function clearBadges() { badges.splice(0).forEach(b => b.remove()); }

    // Animate a packet along an edge. Resolves when it arrives.
    function flow(id, o) {
      o = o || {};
      const p = edges[id]; if (!p) return Promise.resolve();
      const dur = Math.round((o.duration || 900) * (api.speed || 1)), color = o.color || "var(--accent)";
      setEdge(id, o.cls || "hot");
      if (REDUCED) { return new Promise(r => setTimeout(r, 40)); }
      const c = el("circle", { r: o.size || 5, class: "packet", fill: color, style: `color:${color}` }, gPackets);
      const am = el("animateMotion", { dur: `${dur}ms`, begin: "indefinite", fill: "freeze", calcMode: "linear", keyPoints: o.reverse ? "1;0" : "0;1", keyTimes: "0;1" }, c);
      el("mpath", { href: `#${uid}-${id}` }, am);
      return new Promise(resolve => {
        let done = false;
        const finish = () => { if (done) return; done = true; c.remove(); resolve(); };
        am.addEventListener("endEvent", finish);
        setTimeout(finish, dur + 80);
        am.beginElement();
      });
    }
    function flowAll(ids, o) { return Promise.all(ids.map(id => flow(id, o))); }

    const api = { svg, nodes, edges, setState, setEdge, flow, flowAll, reset, badge, clearBadges, NODES, EDGES, speed: 1 };
    return api;
  }

  // The canonical "raise a P1" sequence used by the overview loop and the walkthrough.
  // `caller` is "console" (all roles) or "ide" (engineer: no domain:messaging).
  async function runIncident(t, opts) {
    opts = opts || {};
    const sleep = (window.MaestroSite ? window.MaestroSite.sleep : (ms) => new Promise(r => setTimeout(r, ms)));
    const caller = opts.caller || "console", gold = "var(--warn)", ok = "var(--ok)", bad = "var(--bad)";
    const consulted = caller === "ide" ? ["apim", "cache"] : ["apim", "cache", "messaging"];
    const on = opts.onStep || (() => {});
    t.reset();
    if (caller === "ide") t.setState("messaging-agent", "off");

    on(0); t.setState(caller, "active");
    await t.flow(`${caller}-keycloak`, { color: gold, cls: "hot" });
    await t.flow(`${caller}-keycloak`, { reverse: true, color: gold, cls: "hot" });
    t.badge("keycloak", "JWT issued", "warn");

    on(1); t.setState("maestro", "pulse active");
    if (caller === "ide") { await t.flow("ide-gateway", { color: gold }); await t.flow("maestro-gateway", { reverse: true, color: gold }); }
    else await t.flow("console-maestro", { color: gold });
    await t.flow("maestro-skills"); await t.flow("maestro-skills", { reverse: true });
    t.badge("maestro", "skills loaded");

    on(2); t.setState("gateway", "active");
    await t.flow("maestro-gateway", { color: gold });
    await Promise.all([t.flow("gateway-keycloak", { duration: 700 })]);
    t.badge("gateway", caller === "ide" ? "4 tools visible" : "6 tools visible", "gw");
    await t.flow("maestro-gateway", { reverse: true, duration: 600 });

    on(3);
    // One on-behalf-of token per agent (ADR-0015): Maestro ↔ Keycloak, then the fan-out with those tokens.
    const obo = "var(--accent)";
    await t.flow("maestro-keycloak", { color: gold, duration: 550 });
    t.setState("keycloak", "active");
    await t.flow("maestro-keycloak", { reverse: true, color: obo, duration: 550 });
    t.badge("keycloak", `${consulted.length} on-behalf-of tokens`, "accent");
    await t.flow("maestro-gateway", { color: obo, duration: 600 });
    consulted.forEach(d => t.setState(`${d}-agent`, "pulse active"));
    await t.flowAll(consulted.map(d => `gateway-${d}`), { color: obo });
    t.setState("keycloak", "idle");
    await sleep(200);

    on(4);
    const plat = { apim: "edge", cache: "valkey", messaging: "kafka" };
    await Promise.all(consulted.flatMap(d => [t.flow(`${d}-${plat[d]}`), t.flow(`${d}-prom`, { duration: 1100 })]));
    consulted.forEach(d => t.setState(plat[d], "active")); t.setState("prometheus", "active");
    await Promise.all(consulted.flatMap(d => [t.flow(`${d}-${plat[d]}`, { reverse: true }), t.flow(`${d}-prom`, { reverse: true, duration: 1100 })]));
    await sleep(250);

    on(5);
    const fault = opts.fault || "apim";
    await Promise.all(consulted.map(d => t.flow(`gateway-${d}`, { reverse: true, color: d === fault ? bad : ok, cls: d === fault ? "hot-bad" : "hot-ok" })));
    consulted.forEach(d => { t.setState(`${d}-agent`, d === fault ? "bad" : "ok"); t.setState(plat[d], d === fault ? "bad" : "ok"); });
    t.badge(`${fault}-agent`, "implicated 0.88", "bad");
    await t.flow("maestro-gateway", { reverse: true, color: bad, cls: "hot-bad" });

    on(6); t.setState("maestro", "active");
    if (caller === "ide") { await t.flow("maestro-gateway", { color: ok, cls: "hot-ok" }); await t.flow("ide-gateway", { reverse: true, color: ok, cls: "hot-ok" }); }
    else await t.flow("console-maestro", { reverse: true, color: ok, cls: "hot-ok" });
    t.setState(caller, "ok"); t.setState("gateway", "idle"); t.setState("prometheus", "idle");
    t.badge(caller, "assessment posted", "ok");

    on(7);
    await sleep(opts.holdMs == null ? 2500 : opts.holdMs);
  }

  return { render, runIncident, NODES, EDGES };
})();
