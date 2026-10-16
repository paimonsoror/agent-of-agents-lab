/* Topology geometry for the Fleet Console board (ADR-0009).
 * Node ids match docs/contracts.md. Positions are in the SVG's 1600x880 viewBox.
 * The server's /api/topology provides labels and URLs; this file provides where things sit
 * and how edges are routed, so adding a domain means adding a row here and a node there. */

window.MaestroTopology = (function () {
  const COLUMNS = {
    consumers:     { x: 40,   w: 290, label: "CONSUMERS" },
    orchestration: { x: 400,  w: 250, label: "ORCHESTRATION" },
    gateway:       { x: 701,  w: 48,  label: "" },
    agents:        { x: 800,  w: 265, label: "DOMAIN AGENTS" },
    platforms:     { x: 1120, w: 225, label: "DOMAIN PLATFORMS" },
    monitoring:    { x: 1392, w: 186, label: "SHARED MONITORING" },
    identity:      { x: 400,  w: 250, label: "" },
  };

  // id -> geometry. Column widths come from COLUMNS unless overridden.
  const GEOMETRY = {
    "console":         { col: "consumers",     y: 170, h: 120 },
    "ide":             { col: "consumers",     y: 430, h: 120 },
    "maestro":         { col: "orchestration", y: 290, h: 200 },
    "keycloak":        { col: "identity",      y: 610, h: 90 },
    "gateway":         { col: "gateway",       y: 110, h: 660 },
    "skills":          { col: "agents",        y: 60,  h: 70 },
    "apim-agent":      { col: "agents",        y: 170, h: 120 },
    "cache-agent":     { col: "agents",        y: 330, h: 120 },
    "messaging-agent": { col: "agents",        y: 490, h: 120 },
    "edge-gateway":    { col: "platforms",     y: 170, h: 120 },
    "valkey":          { col: "platforms",     y: 330, h: 120 },
    "kafka":           { col: "platforms",     y: 490, h: 120 },
    "portal":          { col: "platforms",     y: 660, h: 90 },
    "prometheus":      { col: "monitoring",    y: 190, h: 190 },
    "grafana":         { col: "monitoring",    y: 450, h: 190 },
  };

  // Short sublabels (≤ 22 chars) so nothing overflows a box; the server's longer sublabel stays in the drawer.
  const SHORT_SUB = {
    "console": "incident intake · P1",
    "ide": "Claude Code · Copilot",
    "maestro": "orchestrator",
    "keycloak": "identity · JWT issuer",
    "skills": "SKILL.md bundles",
    "apim-agent": "API management",
    "cache-agent": "distributed cache",
    "messaging-agent": "messaging",
    "edge-gateway": "gateways · routes",
    "valkey": "clusters · keyspace",
    "kafka": "topics · groups · lag",
    "portal": "sample business app",
    "prometheus": "metrics",
    "grafana": "dashboards",
  };

  const BADGES = {
    "console": "P1", "ide": "</>", "maestro": "M", "keycloak": "ID", "skills": "S",
    "apim-agent": "A", "cache-agent": "C", "messaging-agent": "Q",
    "edge-gateway": "GW", "valkey": "V", "kafka": "K", "portal": "P", "prometheus": "Pr", "grafana": "Gr",
  };

  const GROUPS = [
    { x: 1385, y: 150, w: 200, h: 520, label: "SHARED · ALL DOMAINS" },
  ];

  function rect(id) {
    const g = GEOMETRY[id];
    if (!g) return null;
    const c = COLUMNS[g.col];
    return { id, x: g.x != null ? g.x : c.x, y: g.y, w: g.w != null ? g.w : c.w, h: g.h, col: g.col };
  }

  function center(r) { return { x: r.x + r.w / 2, y: r.y + r.h / 2 }; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  // Anchor point on `r` facing `other`.
  function anchor(r, other) {
    const c = center(r), oc = center(other);
    if (r.id === "gateway") {
      const y = clamp(oc.y, r.y + 24, r.y + r.h - 24);
      return oc.x > c.x ? { x: r.x + r.w, y, dir: "h" } : { x: r.x, y, dir: "h" };
    }
    if (oc.x > r.x + r.w) return { x: r.x + r.w, y: clamp(oc.y, r.y + 18, r.y + r.h - 18), dir: "h" };
    if (oc.x + other.w / 2 < r.x) return { x: r.x, y: clamp(oc.y, r.y + 18, r.y + r.h - 18), dir: "h" };
    if (oc.y > c.y) return { x: clamp(oc.x, r.x + 18, r.x + r.w - 18), y: r.y + r.h, dir: "v" };
    return { x: clamp(oc.x, r.x + 18, r.x + r.w - 18), y: r.y, dir: "v" };
  }

  // Cubic bezier between two nodes.
  function path(fromId, toId) {
    const a = rect(fromId), b = rect(toId);
    if (!a || !b) return null;
    const p = anchor(a, b), q = anchor(b, a);
    const dx = q.x - p.x, dy = q.y - p.y;
    let c1, c2;
    if (p.dir === "h" && q.dir === "h") {
      c1 = { x: p.x + dx * 0.5, y: p.y };
      c2 = { x: q.x - dx * 0.5, y: q.y };
    } else if (p.dir === "v" && q.dir === "v") {
      c1 = { x: p.x, y: p.y + dy * 0.5 };
      c2 = { x: q.x, y: q.y - dy * 0.5 };
    } else {
      c1 = p.dir === "h" ? { x: p.x + dx * 0.6, y: p.y } : { x: p.x, y: p.y + dy * 0.6 };
      c2 = q.dir === "h" ? { x: q.x - dx * 0.6, y: q.y } : { x: q.x, y: q.y - dy * 0.6 };
    }
    return `M ${p.x} ${p.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${q.x} ${q.y}`;
  }

  return { COLUMNS, GEOMETRY, BADGES, SHORT_SUB, GROUPS, rect, center, path };
})();
