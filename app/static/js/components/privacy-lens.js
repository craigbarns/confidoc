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
    container.replaceChildren();
    return;
  }
  const rawZones = root.getAttribute("data-privacy-zones") || "[]";
  let zones;
  try { zones = JSON.parse(rawZones); } catch { return; }
  if (!Array.isArray(zones)) return;

  const fragment = document.createDocumentFragment();
  zones.forEach(z => {
    const zone = document.createElement("div");
    zone.className = "privacy-lens-zone";
    zone.style.top = safeCssLength(z.top);
    zone.style.left = safeCssLength(z.left);
    zone.style.width = safeCssLength(z.width);
    zone.style.height = safeCssLength(z.height);
    zone.title = String(z.label || "");
    zone.textContent = String(z.label || "");
    fragment.appendChild(zone);
  });
  container.replaceChildren(fragment);
}

function safeCssLength(value) {
  if (typeof value === "number" && Number.isFinite(value)) return `${value}%`;
  const raw = String(value ?? "").trim();
  if (/^-?\d+(\.\d+)?(px|%)$/.test(raw)) return raw;
  return "0%";
}
