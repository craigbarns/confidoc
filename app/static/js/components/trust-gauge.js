// ConfiDoc — Trust Gauge (§3.5.2)
// Custom element <trust-gauge> with 4 concentric rings.
//
// Attributes (all 0..100):
//   data-pii            inner ring  — PII directs
//   data-coherence                   — Cohérence tokens
//   data-reversibility               — Réversibilité
//   data-quasi          outer ring  — Quasi-identifiants
//
// Modifiers:
//   data-size           pixel size of the SVG (default 140)
//   data-mini="true"    hide the center label, render compact

const RINGS = [
  { attr: "pii",           r: 17 },
  { attr: "coherence",     r: 26 },
  { attr: "reversibility", r: 35 },
  { attr: "quasi",         r: 44 },
];

function colorFor(v) {
  if (v >= 90) return "var(--accent)";
  if (v >= 70) return "var(--warning)";
  return "var(--danger)";
}

class TrustGauge extends HTMLElement {
  static get observedAttributes() {
    return RINGS.map(r => `data-${r.attr}`).concat(["data-size", "data-mini"]);
  }
  connectedCallback() { this.render(); }
  attributeChangedCallback() { if (this.isConnected) this.render(); }

  render() {
    const size = parseInt(this.getAttribute("data-size") || "140", 10);
    const showCenter = this.getAttribute("data-mini") !== "true";
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const values = RINGS.map(r => {
      const raw = parseInt(this.getAttribute(`data-${r.attr}`) || "0", 10);
      return Math.max(0, Math.min(100, isNaN(raw) ? 0 : raw));
    });
    const globalScore = Math.min(...values);

    const rings = RINGS.map((ring, i) => {
      const circumference = 2 * Math.PI * ring.r;
      const value = values[i];
      const targetOffset = circumference * (1 - value / 100);
      const startOffset = reduced ? targetOffset : circumference;
      return `
        <circle cx="50" cy="50" r="${ring.r}" fill="none" stroke="var(--border)" stroke-width="4"/>
        <circle data-ring="${ring.attr}" cx="50" cy="50" r="${ring.r}" fill="none"
                stroke="${colorFor(value)}" stroke-width="4" stroke-linecap="round"
                stroke-dasharray="${circumference}"
                stroke-dashoffset="${startOffset}"
                style="transition: stroke-dashoffset var(--t-gauge);"/>
      `;
    }).join("");

    this.innerHTML = `
      <div class="trust-gauge-wrap" style="width:${size}px;height:${size}px">
        <svg viewBox="0 0 100 100" width="${size}" height="${size}" style="transform:rotate(-90deg);display:block">
          ${rings}
        </svg>
        ${showCenter ? `
          <div class="trust-gauge-center">
            <div>
              <div data-role="value" class="tabular" style="font-size:${Math.round(size*0.21)}px;font-weight:800;letter-spacing:-0.025em;color:${colorFor(globalScore)};line-height:1">
                ${globalScore}<span style="font-size:${Math.round(size*0.10)}px;opacity:0.6">%</span>
              </div>
              <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:var(--ink-muted);font-weight:700;margin-top:4px">Trust</div>
            </div>
          </div>` : ""}
      </div>
    `;

    if (!reduced) {
      requestAnimationFrame(() => {
        this.querySelectorAll("[data-ring]").forEach((circleEl, i) => {
          const circumference = 2 * Math.PI * RINGS[i].r;
          circleEl.style.strokeDashoffset = String(circumference * (1 - values[i] / 100));
        });
      });
    }
  }
}

if (!customElements.get("trust-gauge")) {
  customElements.define("trust-gauge", TrustGauge);
}

export function init_trust_gauge() { /* element auto-registers on import */ }
