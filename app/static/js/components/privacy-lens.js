// ConfiDoc — Privacy Lens (§3.5.5)
// Toggle overlay that paints terracotta zones over the Original pane,
// fed by a JSON array on [data-document-detail]: data-privacy-zones.
//
// Shortcut: ⌘L / Ctrl+L
// Also bound to any button with [data-privacy-lens-toggle].

export function init_privacy_lens() {
  document.addEventListener("keydown", e => {
    const key = (e.key || "").toLowerCase();
    if ((e.metaKey || e.ctrlKey) && key === "l") {
      const root = document.querySelector("[data-document-detail]");
      if (!root) return;
      e.preventDefault();
      togglePrivacyLens(root);
    }
  });

  document.addEventListener("click", e => {
    const btn = e.target.closest("[data-privacy-lens-toggle]");
    if (!btn) return;
    const root = btn.closest("[data-document-detail]") || document.querySelector("[data-document-detail]");
    if (root) togglePrivacyLens(root);
  });
}

function togglePrivacyLens(root) {
  const on = root.getAttribute("data-privacy-lens") === "on";
  root.setAttribute("data-privacy-lens", on ? "off" : "on");
  renderZones(root);
}

function renderZones(root) {
  const container = root.querySelector(".privacy-lens-overlay");
  if (!container) return;
  if (root.getAttribute("data-privacy-lens") !== "on") {
    container.innerHTML = "";
    return;
  }
  const rawZones = root.getAttribute("data-privacy-zones") || "[]";
  let zones;
  try { zones = JSON.parse(rawZones); } catch { return; }
  container.innerHTML = zones.map(z =>
    `<div class="privacy-lens-zone" style="top:${z.top};left:${z.left};width:${z.width};height:${z.height}" title="${(z.label || "").replace(/"/g, "&quot;")}">${z.label || ""}</div>`
  ).join("");
}
