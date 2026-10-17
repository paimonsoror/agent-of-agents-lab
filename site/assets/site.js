/* Shared behaviour for the Maestro lab site: navigation, scroll reveal, small helpers. */
(function () {
  "use strict";
  const REPO = "https://github.com/paimonsoror/agent-of-agents-lab";
  const PAGES = [
    ["index.html", "Overview"],
    ["how-it-works.html", "How it works"],
    ["architecture.html", "Architecture"],
    ["identity.html", "Identity"],
    ["cognition.html", "Cognition"],
    ["scenarios.html", "Scenarios"],
    ["console.html", "Fleet Console"],
    ["decisions.html", "Decisions"],
    ["get-started.html", "Get started"],
  ];
  const REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function current() {
    const p = location.pathname.split("/").pop() || "index.html";
    return p === "" ? "index.html" : p;
  }

  function header() {
    const el = document.getElementById("site-header");
    if (!el) return;
    const here = current();
    const icon = window.MaestroIcons ? window.MaestroIcons.svg("maestro", 22) : "";
    el.className = "site-header";
    el.innerHTML = `<div class="wrap">
      <a class="brand" href="index.html">${icon}<span>Maestro</span><span class="tagline">· agent of agents for observability</span></a>
      <button class="nav-toggle" aria-expanded="false" aria-controls="site-nav">Menu</button>
      <nav class="nav" id="site-nav" aria-label="Site">
        ${PAGES.map(([href, label]) => `<a href="${href}" class="${href === here ? "active" : ""}">${label}</a>`).join("")}
        <a class="gh" href="${REPO}" rel="noopener">GitHub ↗</a>
      </nav></div>`;
    const t = el.querySelector(".nav-toggle"), nav = el.querySelector(".nav");
    t.addEventListener("click", () => { const open = nav.classList.toggle("open"); t.setAttribute("aria-expanded", String(open)); });
  }

  function footer() {
    const el = document.getElementById("site-footer");
    if (!el) return;
    el.className = "site-footer";
    el.innerHTML = `<div class="wrap">
      <span>Maestro is a reference architecture and lab. Everything on these pages is running code in the repository.</span>
      <span><a href="${REPO}" rel="noopener">Source on GitHub</a> · <a href="${REPO}/tree/main/docs" rel="noopener">docs/</a> · <a href="${REPO}/tree/main/docs/adr" rel="noopener">ADRs</a></span>
    </div>`;
  }

  function reveal() {
    const els = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window) || REDUCED) { els.forEach(e => e.classList.add("in")); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { rootMargin: "0px 0px -8% 0px", threshold: .08 });
    els.forEach(e => io.observe(e));
  }

  // Replace <i data-icon="grafana" data-size="18"></i> with inline SVG.
  function icons() {
    if (!window.MaestroIcons) return;
    document.querySelectorAll("[data-icon]").forEach(el => {
      const size = el.dataset.size || 18;
      el.outerHTML = window.MaestroIcons.svg(el.dataset.icon, size, el.className);
    });
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, REDUCED ? Math.min(ms, 60) : ms)); }

  document.addEventListener("DOMContentLoaded", () => { header(); footer(); icons(); reveal(); });
  window.MaestroSite = { REPO, REDUCED, sleep };
})();
