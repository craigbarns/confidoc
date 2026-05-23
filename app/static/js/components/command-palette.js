// ConfiDoc — Command palette ⌘K (§6)

const ACTIONS = [
  { label: "Aller à Accueil",         hint: "Nav · Accueil",    do: () => navTo("home") },
  { label: "Aller à Documents",       hint: "Nav · Documents",  do: () => navTo("documents") },
  { label: "Aller à Dossiers",        hint: "Nav · Dossiers",   do: () => navTo("clients") },
  { label: "Aller à Qualité & RGPD",  hint: "Nav · Qualité",    do: () => navTo("quality") },
  { label: "Aller à Journal d'audit", hint: "Nav · Audit",      do: () => navTo("audit") },
  { label: "Aller à Paramètres",      hint: "Nav · Paramètres", do: () => navTo("settings") },
  { label: "Importer un document",    hint: "Action · Upload",  do: () => document.querySelector('[data-action="open-upload"]')?.click() },
];

function navTo(key) {
  const btn = document.querySelector(`[data-nav="${key}"]`);
  if (btn) btn.click();
}

export function init_command_palette() {
  const palette = ensureDom();
  const input = palette.querySelector(".cmd-palette__input");
  const list = palette.querySelector(".cmd-palette__list");
  let filtered = ACTIONS.slice();
  let selected = 0;

  const render = () => {
    list.innerHTML = filtered.map((a, i) =>
      `<div class="cmd-palette__item" role="option" aria-selected="${i === selected}" data-i="${i}">
         <span>${escapeHtml(a.label)}</span><span class="cmd-palette__hint">${escapeHtml(a.hint)}</span>
       </div>`
    ).join("");
  };
  const close = () => { palette.removeAttribute("open"); input.value = ""; };
  const open = () => {
    filtered = ACTIONS.slice();
    selected = 0;
    render();
    palette.setAttribute("open", "");
    setTimeout(() => input.focus(), 0);
  };
  const run = i => { filtered[i]?.do(); close(); };

  input.addEventListener("input", () => {
    const q = input.value.toLowerCase().trim();
    filtered = q ? ACTIONS.filter(a => a.label.toLowerCase().includes(q) || a.hint.toLowerCase().includes(q)) : ACTIONS.slice();
    selected = 0;
    render();
  });
  list.addEventListener("click", e => {
    const t = e.target.closest("[data-i]");
    if (t) run(parseInt(t.dataset.i, 10));
  });
  palette.addEventListener("click", e => { if (e.target === palette) close(); });

  document.addEventListener("keydown", e => {
    const open_p = palette.hasAttribute("open");
    const key = (e.key || "").toLowerCase();
    if ((e.metaKey || e.ctrlKey) && key === "k") {
      e.preventDefault();
      open_p ? close() : open();
      return;
    }
    if (!open_p) return;
    if (e.key === "Escape") { e.preventDefault(); close(); }
    if (e.key === "ArrowDown") { e.preventDefault(); selected = (selected + 1) % Math.max(filtered.length, 1); render(); }
    if (e.key === "ArrowUp")   { e.preventDefault(); selected = (selected - 1 + filtered.length) % Math.max(filtered.length, 1); render(); }
    if (e.key === "Enter")     { e.preventDefault(); run(selected); }
  });
}

function ensureDom() {
  let palette = document.getElementById("cmd-palette");
  if (palette) return palette;
  palette = document.createElement("div");
  palette.id = "cmd-palette";
  palette.className = "cmd-palette";
  palette.setAttribute("role", "dialog");
  palette.setAttribute("aria-modal", "true");
  palette.innerHTML = `
    <div class="cmd-palette__panel">
      <input class="cmd-palette__input" placeholder="Chercher un document, un client, une action…" aria-label="Recherche globale" />
      <div class="cmd-palette__list" role="listbox"></div>
    </div>
  `;
  document.body.appendChild(palette);
  return palette;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[c]);
}
