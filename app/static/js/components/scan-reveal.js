// ConfiDoc — Scan Reveal (§3.5.4)
// triggerScanReveal(rootEl, { onDone }) runs the one-and-only ceremonial
// animation: an emerald sweep top→bottom in ~600ms, then a bouncy checkmark.
// Returns a Promise that resolves once the ceremony is complete.

export function triggerScanReveal(rootEl, { onDone } = {}) {
  if (!rootEl) return Promise.resolve();
  if (getComputedStyle(rootEl).position === "static") {
    rootEl.style.position = "relative";
  }

  const overlay = document.createElement("div");
  overlay.className = "scan-reveal scan-reveal--running";
  overlay.setAttribute("role", "status");
  overlay.setAttribute("aria-live", "polite");
  overlay.innerHTML = `
    <div class="scan-reveal__halo"></div>
    <div class="scan-reveal__line"></div>
    <div class="scan-reveal__check" aria-hidden="true">✓</div>
  `;
  rootEl.appendChild(overlay);

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const lineDuration = reduced ? 0 : 600;
  const checkDuration = reduced ? 0 : 220;

  return new Promise(resolve => {
    setTimeout(() => {
      overlay.classList.remove("scan-reveal--running");
      overlay.classList.add("scan-reveal--done");
      setTimeout(() => {
        onDone?.();
        setTimeout(() => overlay.remove(), 1200);
        resolve();
      }, checkDuration);
    }, lineDuration);
  });
}

export function init_scan_reveal() {
  // Expose for legacy app.js callers that aren't ES modules
  window.triggerScanReveal = triggerScanReveal;
}
