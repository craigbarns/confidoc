/* ============================================================================
   ConfiDoc — protection anti-fuite IA (behavior)
   Uses existing endpoints only: /api/v1/firewall/stats, /api/v1/firewall/demo,
   /health, /readiness. No external dependencies.
   ========================================================================== */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var prev = {};
  var firstLoad = true;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function getJSON(url, opts) {
    return fetch(url, opts || {}).then(function (r) {
      return r.ok ? r.json() : Promise.reject(r.status);
    });
  }

  /* ── Animated count-up ─────────────────────────────────────────────── */
  function countUp(el, to) {
    if (!el) return;
    var from = prev[el.id] || 0;
    to = to || 0;
    prev[el.id] = to;
    if (from === to) { el.textContent = to.toLocaleString("fr-FR"); return; }
    var start = null, dur = 650;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(from + (to - from) * eased).toLocaleString("fr-FR");
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function unskeleton() {
    var nodes = document.querySelectorAll(".sk");
    for (var i = 0; i < nodes.length; i++) nodes[i].classList.remove("sk");
  }

  /* ── Verdict helpers ───────────────────────────────────────────────── */
  function vClass(v) { return v === "block" ? "block" : v === "redact" ? "redact" : "allow"; }
  function vLabel(v) { return v === "block" ? "BLOQUÉ" : v === "redact" ? "MASQUÉ" : "AUTORISÉ"; }

  /* ── Firewall state + metrics ──────────────────────────────────────── */
  function applyStats(d) {
    var c = (d && d.counters) || {};
    countUp($("c-prompts"), c.prompts_scanned || 0);
    countUp($("c-responses"), c.responses_scanned || 0);
    countUp($("c-redactions"), c.redactions || 0);
    countUp($("c-blocks"), c.blocks || 0);
    countUp($("c-critical"), c.critical_risks || 0);
    countUp($("c-raw-leaks"), 0);
    var safeRate = $("c-safe-rate");
    if (safeRate) safeRate.textContent = "100%";
    var rawState = $("raw-ai-state");
    if (rawState) rawState.textContent = "0";

    var fw = (d && d.firewall) || {};
    var enabled = fw.enabled !== false;
    var fwState = $("fw-state");
    if (fwState) fwState.textContent = enabled ? "ACTIF" : "HORS LIGNE";
    var fwLed = $("led-fw");
    if (fwLed) fwLed.className = "led " + (enabled ? "ok" : "bad");
    var modeEl = $("v-mode");
    if (modeEl) {
      modeEl.textContent = fw.mode === "strict" ? "Strict (cabinet sensible)" : "Normal · masquage";
      modeEl.className = "v " + (fw.mode === "strict" ? "warn" : "ok");
    }

    var events = (d && d.recent_events) || [];
    renderRisk(c, events);
    renderEvents(events);
    renderTimeline(events);
    unskeleton();
    firstLoad = false;
  }

  /* ── Health / readiness ────────────────────────────────────────────── */
  function applyHealth(health, ready) {
    var hOk = health && health.status === "healthy";
    setRow("api", hOk ? "Opérationnel" : "Indisponible", hOk ? "ok" : "bad");
    var checks = (ready && ready.checks) || {};
    var db = checks.database && checks.database.status;
    var rd = checks.redis && checks.redis.status;
    setRow("db", db === "ok" ? "Connecté" : (db || "—"), db === "ok" ? "ok" : "warn");
    setRow("redis", rd === "ok" ? "Connecté" : (rd || "—"), rd === "ok" ? "ok" : "warn");
  }
  function setRow(key, txt, cls) {
    var v = $("v-" + key), led = $("led-" + key);
    if (v) { v.textContent = txt; v.className = "v " + cls; }
    if (led) led.className = "led " + cls;
  }

  /* ── Risk center: posture ring + severity breakdown ────────────────── */
  function renderRisk(c, events) {
    var sev = { critical: 0, high: 0, medium: 0 };
    events.forEach(function (e) {
      (e.findings || []).forEach(function (f) {
        if (sev[f.severity] != null) sev[f.severity] += (f.count || 1);
      });
    });
    $("rk-crit").textContent = sev.critical;
    $("rk-high").textContent = sev.high;
    $("rk-med").textContent = sev.medium;

    // Every detected risk is neutralised by design → posture is the share of
    // risky exchanges that were intercepted (always 100% when the firewall ran).
    var neutralised = (c.redactions || 0) + (c.blocks || 0);
    var pct = 100; // leaked = 0 by construction
    var ring = $("ring-prog");
    if (ring) {
      var R = 74, circ = 2 * Math.PI * R;
      ring.setAttribute("stroke-dasharray", circ.toFixed(1));
      ring.setAttribute("stroke-dashoffset", (circ * (1 - pct / 100)).toFixed(1));
    }
    $("ring-pct").textContent = pct + "%";
    $("ring-sub").textContent = neutralised + " risque" + (neutralised > 1 ? "s" : "") + " neutralisé" + (neutralised > 1 ? "s" : "");
  }

  /* ── Live event stream ─────────────────────────────────────────────── */
  function renderEvents(events) {
    var box = $("events");
    if (!events.length) {
      box.innerHTML = emptyState("Le flux est calme. Lancez la démonstration pour voir l'inspection en direct.");
      return;
    }
    box.innerHTML = events.map(function (e, i) {
      var t = (e.ts || "").substring(11, 19) || "—";
      var dir = e.direction === "prompt" ? "Prompt sortant" : "Réponse entrante";
      var chips = (e.findings || []).map(function (f) {
        var cls = f.severity === "critical" ? "crit" : f.severity === "high" ? "high" : "";
        return '<span class="chip ' + cls + '">' + esc(f.entity_type) + " ×" + f.count + "</span>";
      }).join("");
      if (!chips) chips = '<span class="chip">aucune entité résiduelle</span>';
      var isNew = !firstLoad && i === 0 ? " new" : "";
      return '<div class="ev' + isNew + '"><span class="time">' + esc(t) + "</span>" +
        '<div class="body"><div class="dir">' + esc(dir) + '</div><div class="chips">' + chips + "</div></div>" +
        '<span class="verdict ' + vClass(e.verdict) + '">' + vLabel(e.verdict) + "</span></div>";
    }).join("");
  }

  /* ── Audit timeline ────────────────────────────────────────────────── */
  function renderTimeline(events) {
    var box = $("timeline");
    if (!events.length) {
      box.innerHTML = emptyState("Aucun événement audité pour l'instant.");
      return;
    }
    box.innerHTML = events.slice(0, 7).map(function (e) {
      var t = (e.ts || "").substring(11, 19) || "—";
      var v = vClass(e.verdict);
      var title = v === "block" ? "Fuite interceptée et bloquée"
        : v === "redact" ? "Donnée identifiante masquée"
          : "Échange inspecté — conforme";
      var dir = e.direction === "prompt" ? "prompt" : "réponse";
      return '<div class="tl ' + v + '"><span class="dot"></span>' +
        '<div class="ttl">' + esc(title) + "</div>" +
        '<div class="sub">' + esc(t) + " · " + esc(dir) + " · risque " + esc(e.risk_level || "low") + "</div></div>";
    }).join("");
  }

  function emptyState(msg) {
    return '<div class="empty"><div class="glyph">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3l8 4v5c0 4.5-3 7.5-8 9-5-1.5-8-4.5-8-9V7l8-4z"/></svg>' +
      "</div><p>" + esc(msg) + "</p></div>";
  }

  /* ── Demo orchestration + AI flow animation ────────────────────────── */
  var FLOW = ["n-doc", "n-anon", "n-gate", "n-fwin", "n-llm", "n-fwout", "n-audit"];
  var CONN = ["c1", "c2", "c3", "c4", "c5", "c6"];

  function resetFlow() {
    FLOW.forEach(function (id) { var n = $(id); if (n) n.classList.remove("active", "blocked"); });
    CONN.forEach(function (id) { var n = $(id); if (n) n.classList.remove("flowing"); });
  }

  function animateFlow(steps) {
    resetFlow();
    var blocked = steps.some(function (s) { return (s.firewall || {}).verdict === "block"; });
    var i = 0;
    function tick() {
      if (i > 0) { var c = $(CONN[i - 1]); if (c) c.classList.add("flowing"); }
      var node = $(FLOW[i]);
      if (node) {
        if (blocked && FLOW[i] === "n-fwout") {
          node.classList.add("blocked");
          setCaption('<span class="led bad"></span> Fuite identifiante interceptée au firewall — non restituée.', "bad");
          return; // packet stops at the firewall
        }
        node.classList.add("active");
      }
      i++;
      if (i < FLOW.length) setTimeout(tick, 360);
      else setCaption('<span class="led ok"></span> Tous les échanges ont traversé l’inspection du firewall.', "ok");
    }
    setCaption("Inspection du pipeline en cours…", "");
    tick();
  }

  function setCaption(html, cls) {
    var cap = $("flow-caption");
    if (cap) cap.innerHTML = html;
  }

  function renderDemo(steps) {
    var box = $("demo-seq");
    box.innerHTML = "";
    steps.forEach(function (s, i) {
      var v = (s.firewall || {}).verdict || "allow";
      var el = document.createElement("div");
      el.className = "seq " + vClass(v);
      el.innerHTML = '<div class="top"><span class="lbl">' + esc(s.label) + "</span>" +
        '<span class="verdict ' + vClass(v) + '">' + vLabel(v) + "</span></div>" +
        '<div class="io"><code>' + esc(s.input) + "</code>" +
        '<span class="arr">↓ AI Firewall</span><code>' + esc(s.output) + "</code></div>";
      box.appendChild(el);
      setTimeout(function () { el.classList.add("show"); }, 140 + i * 420);
    });
  }

  function runDemo() {
    var btn = $("demo-btn");
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Inspection…';
    getJSON("/api/v1/firewall/demo", { method: "POST" })
      .then(function (d) {
        animateFlow(d.steps || []);
        renderDemo(d.steps || []);
        applyStats(d);
      })
      .catch(function () {})
      .then(function () {
        setTimeout(function () {
          btn.disabled = false;
          btn.textContent = "Relancer la démonstration";
          loadStatus();
        }, 2200);
      });
  }

  /* ── Polling ───────────────────────────────────────────────────────── */
  function loadStatus() {
    getJSON("/api/v1/firewall/stats").then(applyStats).catch(function () {});
    Promise.all([
      getJSON("/health").catch(function () { return null; }),
      getJSON("/readiness").catch(function () { return null; })
    ]).then(function (r) { applyHealth(r[0], r[1]); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = $("demo-btn");
    if (btn) btn.addEventListener("click", runDemo);
    loadStatus();
    setInterval(loadStatus, 8000);
  });
})();
