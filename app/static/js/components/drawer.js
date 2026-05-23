// ConfiDoc — Drawer (Copilot ⌘J) (§6 + §3.5 omnipresent)
//
// Slides in from the right. Clones the markup in <template id="tmpl-copilot">
// if present, otherwise renders a fallback shell.

export function init_drawer() {
  const { backdrop, drawer, body } = ensureDom();

  const open = () => {
    backdrop.setAttribute("open", "");
    drawer.setAttribute("open", "");
    populate(body);
  };
  const close = () => {
    backdrop.removeAttribute("open");
    drawer.removeAttribute("open");
  };

  document.addEventListener("keydown", e => {
    const key = (e.key || "").toLowerCase();
    if ((e.metaKey || e.ctrlKey) && key === "j") {
      e.preventDefault();
      drawer.hasAttribute("open") ? close() : open();
      return;
    }
    if (e.key === "Escape" && drawer.hasAttribute("open")) close();
  });
  backdrop.addEventListener("click", close);
  drawer.querySelector(".drawer__close").addEventListener("click", close);

  // Expose for explicit triggers (e.g. topbar Copilot button)
  window.__confidocDrawer = { open, close };
}

function populate(body) {
  const tmpl = document.getElementById("tmpl-copilot");
  body.innerHTML = "";
  if (tmpl && tmpl.content) {
    body.appendChild(tmpl.content.cloneNode(true));
  } else {
    body.innerHTML = `
      <p style="margin:0 0 12px;font-size:13px;color:var(--ink-2)">
        Aucun contenu Copilot disponible pour le moment.
      </p>
      <textarea class="input" rows="6" style="width:100%" placeholder="Demande au Copilot…"></textarea>
      <p style="margin-top:10px;font-size:11px;color:var(--ink-dim)">⌘J pour fermer.</p>
    `;
  }

  const docName = document.querySelector("[data-active-document]")?.textContent?.trim();
  if (docName) {
    const ctx = document.createElement("p");
    ctx.style.cssText = "margin:0 0 12px;font-size:12px;color:var(--ink-muted)";
    ctx.innerHTML = `Contexte : <strong>${escapeHtml(docName)}</strong>`;
    body.prepend(ctx);
  }
}

function ensureDom() {
  let drawer = document.getElementById("drawer-copilot");
  if (drawer) {
    return {
      backdrop: document.getElementById("drawer-backdrop"),
      drawer,
      body: drawer.querySelector(".drawer__body"),
    };
  }
  const backdrop = document.createElement("div");
  backdrop.id = "drawer-backdrop";
  backdrop.className = "drawer-backdrop";
  document.body.appendChild(backdrop);

  drawer = document.createElement("aside");
  drawer.id = "drawer-copilot";
  drawer.className = "drawer";
  drawer.setAttribute("role", "complementary");
  drawer.setAttribute("aria-label", "Copilot IA");
  drawer.innerHTML = `
    <div class="drawer__header">
      <div class="drawer__title">Copilot IA</div>
      <button class="drawer__close" aria-label="Fermer">×</button>
    </div>
    <div class="drawer__body"></div>
  `;
  document.body.appendChild(drawer);
  return { backdrop, drawer, body: drawer.querySelector(".drawer__body") };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[c]);
}
