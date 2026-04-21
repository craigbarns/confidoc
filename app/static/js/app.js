/* ConfiDoc — Pipeline 3 étapes : Upload → Anonymisation → Discussion IA */

const API = "/api/v1";
let token = sessionStorage.getItem("confidoc_token") || "";
let refreshToken = sessionStorage.getItem("confidoc_refresh_token") || "";
let refreshTimer = null;
let currentDocId = null;
let currentDocName = "";
let currentDocStatus = "";
let currentDocSize = 0;
let currentProvider = "—";
let latestAssistantText = "";
let reportMode = false;
let copilotMode = false;
let selectedCabinetDocType = "generique";
let lastDocsList = [];

const CABINET_DOC_TYPE_PREFIX = {
  generique: "",
  bilan: "[Contexte cabinet — document de type bilan / comptes annuels.] ",
  liasse: "[Contexte cabinet — document de type liasse fiscale.] ",
  urssaf: "[Contexte cabinet — document URSSAF ou social.] ",
  banque: "[Contexte cabinet — relevé ou document bancaire.] ",
  paie: "[Contexte cabinet — paie, bulletin ou DSN.] ",
};

function applyCabinetDocTypePrefix(text) {
  const p = CABINET_DOC_TYPE_PREFIX[selectedCabinetDocType] || "";
  return p + (text || "");
}
let currentClientFilter = "";
let currentIncludeDeleted = false;
let currentSearchFilter = "";
let currentStatusFilter = "";
let activeStream = null; // AbortController pour le streaming SSE
let currentRiskLevel = null; // RGPD risk level from last anonymization
let originalTextCache = {};
let bgPollers = {};
let uploadQueue = [];
let isUploadProcessing = false;
let batchMode = false;
let selectedDocIds = new Set();

const $ = id => document.getElementById(id);
const FILTERS_STORAGE_KEY = "confidoc_filters_v1";
const CHAT_STORAGE_PREFIX = "confidoc_chat_";
const ONBOARDING_KEY = "confidoc_onboarding_done";

function saveFilterState() {
  const payload = {
    client: currentClientFilter,
    search: currentSearchFilter,
    status: currentStatusFilter,
    includeDeleted: currentIncludeDeleted,
  };
  localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(payload));
}

function restoreFilterState() {
  try {
    const raw = localStorage.getItem(FILTERS_STORAGE_KEY);
    if (!raw) return;
    const payload = JSON.parse(raw);
    currentClientFilter = payload.client || "";
    currentSearchFilter = payload.search || "";
    currentStatusFilter = payload.status || "";
    currentIncludeDeleted = !!payload.includeDeleted;
    if ($("filter-client")) $("filter-client").value = currentClientFilter;
    if ($("filter-search")) $("filter-search").value = currentSearchFilter;
    if ($("filter-status")) $("filter-status").value = currentStatusFilter;
    if ($("filter-include-deleted")) $("filter-include-deleted").checked = currentIncludeDeleted;
  } catch (_e) {
    // noop
  }
}


// ── Theme toggle ───────────────────────────────────────────────────────

function initTheme() {
  const saved = localStorage.getItem("confidoc_theme");
  if (saved === "light") document.documentElement.classList.add("theme-light");
  else if (saved === "dark") document.documentElement.classList.remove("theme-light");
  else if (window.matchMedia("(prefers-color-scheme: light)").matches) {
    document.documentElement.classList.add("theme-light");
  }
  updateThemeBtn();
}

function toggleTheme() {
  const isLight = document.documentElement.classList.toggle("theme-light");
  localStorage.setItem("confidoc_theme", isLight ? "light" : "dark");
  updateThemeBtn();
  // Update meta theme-color for mobile browsers
  const metaTheme = document.querySelector('meta[name="theme-color"]');
  if (metaTheme) metaTheme.content = isLight ? "#f4f6fb" : "#0f1117";
}

function updateThemeBtn() {
  const btn = $("btn-theme");
  if (!btn) return;
  const isLight = document.documentElement.classList.contains("theme-light");
  btn.classList.toggle("is-light", isLight);
  btn.title = isLight ? "Mode sombre" : "Mode clair";
  btn.setAttribute("role", "switch");
  btn.setAttribute("aria-checked", isLight ? "true" : "false");
}

// ── API helpers ────────────────────────────────────────────────────────

async function apiRequest(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(opts.body instanceof FormData) && opts.body) {
    headers["Content-Type"] = "application/json";
  }
  let resp = await fetch(API + path, { ...opts, headers });

  // Auto-refresh on 401 if we have a refresh token
  if (resp.status === 401 && refreshToken) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      // Retry the original request with the new token
      const retryHeaders = { ...(opts.headers || {}) };
      retryHeaders["Authorization"] = `Bearer ${token}`;
      if (!(opts.body instanceof FormData) && opts.body) {
        retryHeaders["Content-Type"] = "application/json";
      }
      resp = await fetch(API + path, { ...opts, headers: retryHeaders });
    }
  }

  if (!resp.ok) {
    // If still 401 after refresh attempt, force re-login
    if (resp.status === 401) {
      logout();
      throw new Error("Session expirée. Veuillez vous reconnecter.");
    }
    let msg = `Erreur HTTP ${resp.status}`;
    try {
      const j = await resp.json();
      msg = j.detail || j.message || msg;
    } catch (_e) {
      try {
        const txt = await resp.text();
        if (txt && txt.trim()) msg = txt.trim().slice(0, 220);
      } catch (_e2) {
        // noop
      }
    }
    throw new Error(msg);
  }
  return resp;
}

async function tryRefreshToken() {
  if (!refreshToken) return false;
  try {
    const resp = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!resp.ok) {
      console.warn("Token refresh failed:", resp.status);
      return false;
    }
    const data = await resp.json();
    token = data.access_token;
    refreshToken = data.refresh_token || refreshToken;
    sessionStorage.setItem("confidoc_token", token);
    sessionStorage.setItem("confidoc_refresh_token", refreshToken);
    scheduleTokenRefresh();
    console.log("Token refreshed successfully");
    return true;
  } catch (e) {
    console.error("Token refresh error:", e);
    return false;
  }
}

function scheduleTokenRefresh() {
  if (refreshTimer) clearTimeout(refreshTimer);
  if (!token) return;
  // Decode JWT to find expiry (simple base64 decode of payload)
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const expiresAt = payload.exp * 1000; // ms
    const now = Date.now();
    // Refresh 2 minutes before expiry (or immediately if < 2 min left)
    const refreshIn = Math.max((expiresAt - now) - 120_000, 5_000);
    refreshTimer = setTimeout(async () => {
      console.log("Proactive token refresh...");
      await tryRefreshToken();
    }, refreshIn);
  } catch (_e) {
    // If we can't decode, refresh in 10 minutes
    refreshTimer = setTimeout(() => tryRefreshToken(), 600_000);
  }
}

async function apiFetch(path, opts = {}) {
  const resp = await apiRequest(path, opts);
  return resp.json();
}


// ── Mobile drawer ──────────────────────────────────────────────────────

function toggleSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = $("sidebar-backdrop");
  if (!sidebar) return;
  // On mobile: toggle drawer
  if (window.innerWidth <= 1024) {
    const open = sidebar.classList.toggle("open");
    if (backdrop) backdrop.classList.toggle("visible", open);
  } else {
    // On desktop/tablet: toggle collapse
    sidebar.classList.toggle("collapsed");
    // Update collapse button icon
    const collapseBtn = $("btn-sidebar-collapse");
    if (collapseBtn) {
      collapseBtn.textContent = sidebar.classList.contains("collapsed") ? "▶" : "◀";
      collapseBtn.setAttribute("aria-label", sidebar.classList.contains("collapsed") ? "Agrandir la sidebar" : "Réduire la sidebar");
    }
  }
}

function closeSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = $("sidebar-backdrop");
  if (sidebar) sidebar.classList.remove("open");
  if (backdrop) backdrop.classList.remove("visible");
}

function toggleSidebarCollapse() {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar) return;
  sidebar.classList.toggle("collapsed");
  const collapsed = sidebar.classList.contains("collapsed");
  const collapseBtn = $("btn-sidebar-collapse");
  if (collapseBtn) {
    collapseBtn.textContent = collapsed ? "▶" : "◀";
    collapseBtn.setAttribute("aria-label", collapsed ? "Agrandir la sidebar" : "Réduire la sidebar");
    localStorage.setItem("confidoc_sidebar_collapsed", collapsed ? "1" : "0");
  }
  // Show/hide the external expand button
  const expandBtn = $("btn-sidebar-expand");
  if (expandBtn) expandBtn.style.display = collapsed ? "" : "none";
}

// ── Toast ──────────────────────────────────────────────────────────────

function toast(msg, type = "info") {
  const container = $("toast-container");
  if (!container) return;
  const el = document.createElement("div");
  el.className = `toast${type === "success" ? " success" : type === "error" ? " error" : type === "warning" ? " warning" : ""}`;
  el.textContent = String(msg || "");
  container.prepend(el);
  while (container.children.length > 5) container.removeChild(container.lastElementChild);
  setTimeout(() => {
    el.classList.add("hide");
    setTimeout(() => el.remove(), 250);
  }, 4000);
}

// ── Confirm dialog ─────────────────────────────────────────────────────

function confirm(message, title = "Confirmer", okLabel = "Confirmer") {
  return new Promise(resolve => {
    if ($("confirm-title")) $("confirm-title").textContent = title;
    if ($("btn-confirm-ok")) $("btn-confirm-ok").textContent = okLabel;
    $("confirm-msg").textContent = message;
    $("confirm-overlay").style.display = "";

    // Focus trap: store previously focused element
    const previouslyFocused = document.activeElement;
    // Focus the OK button by default
    setTimeout(() => $("btn-confirm-ok")?.focus(), 50);

    // Trap focus within dialog
    function handleTab(e) {
      if (e.key !== "Tab") return;
      const focusable = [
        $("btn-confirm-ok"),
        $("btn-confirm-cancel"),
      ].filter(Boolean);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    // Close on Escape
    function handleEscape(e) {
      if (e.key === "Escape") {
        $("confirm-overlay").style.display = "none";
        document.removeEventListener("keydown", handleTab);
        document.removeEventListener("keydown", handleEscape);
        if (previouslyFocused && previouslyFocused !== document.body) previouslyFocused.focus();
        resolve(false);
      }
    }

    const onOk = () => {
      $("confirm-overlay").style.display = "none";
      document.removeEventListener("keydown", handleTab);
      document.removeEventListener("keydown", handleEscape);
      cleanup();
      // Restore focus
      if (previouslyFocused && previouslyFocused !== document.body) previouslyFocused.focus();
      resolve(true);
    };
    const onCancel = () => {
      $("confirm-overlay").style.display = "none";
      document.removeEventListener("keydown", handleTab);
      document.removeEventListener("keydown", handleEscape);
      cleanup();
      // Restore focus
      if (previouslyFocused && previouslyFocused !== document.body) previouslyFocused.focus();
      resolve(false);
    };
    const cleanup = () => {
      $("btn-confirm-ok").removeEventListener("click", onOk);
      $("btn-confirm-cancel").removeEventListener("click", onCancel);
    };
    $("btn-confirm-ok").addEventListener("click", onOk);
    $("btn-confirm-cancel").addEventListener("click", onCancel);
    document.addEventListener("keydown", handleTab);
    document.addEventListener("keydown", handleEscape);
  });
}

// ── Pipeline step / panel navigation ──────────────────────────────────

function setStep(n) {
  [1, 2, 3].forEach(i => {
    const s = $(`step-${i}`);
    if (!s) return;
    s.className = "step" + (i === n ? " active" : i < n ? " done" : "");
  });
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const panels = { 1: "panel-upload", 2: "panel-anon", 3: "panel-ai" };
  const el = $(panels[n]);
  if (el) el.classList.add("active");
  const titles = { 1: "Upload", 2: "Anonymisation", 3: "Discussion IA" };
  setPageTitle(titles[n] || "");
}

function goHome() {
  showDashboard();
}

// ── Auth ───────────────────────────────────────────────────────────────

async function login(email, password) {
  const resp = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const j = await resp.json().catch(() => ({}));
    throw new Error(j.detail || "Identifiants incorrects");
  }
  return resp.json();
}

function logout() {
  token = "";
  refreshToken = "";
  if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null; }
  currentDocId = null;
  currentDocName = "";
  currentDocStatus = "";
  currentDocSize = 0;
  currentProvider = "—";
  latestAssistantText = "";
  originalTextCache = {};
  Object.values(bgPollers).forEach(id => clearInterval(id));
  bgPollers = {};
  sessionStorage.removeItem("confidoc_token");
  sessionStorage.removeItem("confidoc_refresh_token");
  if (activeStream) { activeStream.abort(); activeStream = null; }
  // Ferme la modale de confirmation si elle était ouverte (ex: token expiré pendant un delete)
  if ($("confirm-overlay")) $("confirm-overlay").style.display = "none";
  $("screen-auth").style.display = "";
  $("screen-app").style.display = "none";
  $("btn-logout").style.display = "none";
  $("user-info").textContent = "";
  updateHeaderContext();
}

async function initApp(email) {
  $("screen-auth").style.display = "none";
  $("screen-app").style.display = "";
  $("btn-logout").style.display = "";
  if ($("btn-security")) $("btn-security").style.display = "";
  if ($("btn-dashboard")) $("btn-dashboard").style.display = "";

  // Afficher l'email : si non fourni, le charger depuis l'API
  if (email) {
    $("user-info").textContent = email;
  } else {
    try {
      const me = await apiFetch("/users/me");
      $("user-info").textContent = me.email || "";
    } catch (e) {
      console.warn("Impossible de charger le profil utilisateur:", e);
    }
  }

  await loadProviderInfo();
  updateHeaderContext();
  showDashboard();
  restoreFilterState();
  await loadClientSuggestions();
  await loadDocList();

  if (!localStorage.getItem(ONBOARDING_KEY)) {
    setTimeout(() => showOnboarding(), 500);
  }
}

function updateHeaderContext() {
  const docPill = $("header-doc-pill");
  const providerPill = $("header-provider-pill");
  if (currentDocId && currentDocName) {
    const labelMap = { uploaded: "Uploadé", processing: "Traitement", ready: "Prêt IA", failed: "Erreur" };
    docPill.textContent = `📄 ${currentDocName} · ${labelMap[currentDocStatus] || currentDocStatus || "—"}`;
    docPill.style.display = "";
  } else {
    docPill.style.display = "none";
  }
  providerPill.textContent = `🤖 Provider IA: ${currentProvider || "—"}`;
  providerPill.style.display = "";
}

// ── Dynamic page title ───────────────────────────────────────────────

function setPageTitle(section) {
  const titleEl = $("page-title");
  if (!titleEl) return;
  const titles = {
    "": "ConfiDoc — Documents confidentiels anonymisés",
    "Dashboard": "ConfiDoc — Dashboard",
    "Upload": "ConfiDoc — Uploader un document",
    "Anonymisation": "ConfiDoc — Anonymisation",
    "Discussion IA": "ConfiDoc — Discussion IA",
  };
  titleEl.textContent = titles[section] || titles[""];
  if (currentDocName && section) {
    titleEl.textContent = `${currentDocName} — ${titles[section] || "ConfiDoc"}`;
  }
}

async function loadProviderInfo() {
  try {
    const data = await apiFetch("/ai/providers");
    currentProvider = (data.selected_provider || "mistral").toUpperCase();
  } catch (_e) {
    currentProvider = "MISTRAL";
  }
}

function renderAIDocInsights(payload = {}) {
  $("kpi-doc-status").textContent = payload.status || "—";
  $("kpi-ocr-length").textContent = payload.ocrLength ?? "—";
  $("kpi-detections").textContent = payload.detections ?? "—";
  $("kpi-next-action").textContent = payload.nextAction || "—";
}

async function refreshAIDocInsights(docId) {
  if (!docId) {
    renderAIDocInsights({});
    return;
  }
  try {
    const st = await apiFetch(`/documents/${docId}/status`);
    const next = Array.isArray(st.next_steps) && st.next_steps.length ? st.next_steps.join(" → ") : "Discussion IA";
    updatePipelineTimeline({
      status: st.status || currentDocStatus,
      extractDone: !!st?.extraction?.done,
      anonymDone: !!st?.anonymization?.done,
    });
    renderAIDocInsights({
      status: st.status || "—",
      ocrLength: st?.extraction?.text_length ?? 0,
      detections: st?.anonymization?.detections_count ?? 0,
      nextAction: next,
    });
  } catch (_e) {
    updatePipelineTimeline({ status: currentDocStatus, extractDone: currentDocStatus !== "uploaded", anonymDone: currentDocStatus === "ready" });
    renderAIDocInsights({
      status: currentDocStatus || "—",
      ocrLength: "—",
      detections: "—",
      nextAction: "Vérifier document",
    });
  }
}

function updatePipelineTimeline(payload = {}) {
  const tl = $("pipeline-timeline");
  if (!tl) return;
  if (!currentDocId) {
    tl.style.display = "none";
    return;
  }
  tl.style.display = "";
  const extractDone = !!payload.extractDone;
  const anonymDone = !!payload.anonymDone;
  const st = (payload.status || currentDocStatus || "").toLowerCase();
  let currentStep = "extract";
  if (!extractDone) currentStep = "extract";
  else if (!anonymDone) currentStep = "anonymize";
  else if (st === "ready") currentStep = "ai";
  else currentStep = "anonymize";
  tl.querySelectorAll(".pipe-step").forEach((el) => {
    const key = el.dataset.step;
    el.classList.remove("done", "current");
    if (key === "upload") el.classList.add("done");
    if (key === "extract" && extractDone) el.classList.add("done");
    if (key === "anonymize" && anonymDone) el.classList.add("done");
    if (key === "ai" && st === "ready") el.classList.add("done");
    if (key === currentStep) el.classList.add("current");
  });
}

// ── Document list ──────────────────────────────────────────────────────

async function loadDocList() {
  renderDocListSkeleton();
  try {
    const params = new URLSearchParams();
    if (currentClientFilter) params.set("client_name", currentClientFilter);
    if (currentIncludeDeleted) params.set("include_deleted", "true");
    if (currentSearchFilter) params.set("q", currentSearchFilter);
    if (currentStatusFilter) params.set("status_filter", currentStatusFilter);
    const qp = params.toString() ? `?${params.toString()}` : "";
    const docs = await apiFetch(`/documents/${qp}`);
    renderDocList(docs);
    startBgPollers(docs);
  } catch (e) {
    console.warn("loadDocList failed:", e.message);
    const list = $("doc-list");
    const count = $("doc-count");
    if (count) count.textContent = "";
    if (list) {
      list.innerHTML =
        '<div class="empty-state">Impossible de charger les documents.<br>Vérifiez la session ou rechargez la page.</div>';
    }
  }
}

function renderSidebarStats(docs = []) {
  const el = $("sidebar-stats");
  if (!el) return;
  if (!Array.isArray(docs) || !docs.length) {
    el.style.display = "none";
    el.innerHTML = "";
    return;
  }
  const total = docs.length;
  const ready = docs.filter((d) => d.status === "ready").length;
  const processing = docs.filter((d) => d.status === "processing").length;
  const trashed = docs.filter((d) => !!d.is_deleted).length;
  el.innerHTML = [
    `<span class="stat-chip">Total: ${total}</span>`,
    `<span class="stat-chip">Prêt IA: ${ready}</span>`,
    `<span class="stat-chip">Traitement: ${processing}</span>`,
    `<span class="stat-chip">Corbeille: ${trashed}</span>`,
  ].join("");
  el.style.display = "";
}

async function loadClientSuggestions() {
  const el = $("clients-suggestions");
  if (!el) return;
  try {
    const qp = currentIncludeDeleted ? "?include_deleted=true" : "";
    const clients = await apiFetch(`/documents/clients${qp}`);
    el.innerHTML = (clients || [])
      .map((name) => `<option value="${escapeHtml(name)}"></option>`)
      .join("");
  } catch (_e) {
    el.innerHTML = "";
  }
}

function renderDocListSkeleton() {
  const list = $("doc-list");
  if (!list) return;
  list.innerHTML = `
    <div class="skeleton-wrap">
      <div class="skeleton-line w90"></div>
      <div class="skeleton-line w75"></div>
      <div class="skeleton-line w60"></div>
    </div>
  `;
}

function formatBytes(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatDate(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
}

function renderDocList(docs) {
  lastDocsList = Array.isArray(docs) ? docs : [];
  const list = $("doc-list");
  const count = $("doc-count");
  renderSidebarStats(docs);

  if (!docs.length) {
    list.innerHTML = '<div class="empty-state">Aucun document.<br>Uploadez-en un.</div>';
    if (count) count.textContent = "";
    return;
  }

  if (count) count.textContent = docs.length;

  const statusLabel = {
    uploaded: "Uploadé",
    processing: "En cours",
    ready: "Prêt",
    failed: "Erreur",
  };

  list.innerHTML = docs.map(d => {
    const rawName = escapeHtml(d.original_filename || "");
    const name = rawName.length > 26 ? rawName.slice(0, 24) + "…" : rawName;
    const label = escapeHtml(statusLabel[d.status] || d.status || "");
    const selected = d.id === currentDocId ? " selected" : "";
    const size = formatBytes(d.size_bytes);
    const date = formatDate(d.created_at);
    const meta = [date, size].filter(Boolean).join(" · ");
    const clientTag = Array.isArray(d.tags) && d.tags.length
      ? `<span class="doc-client-tag">${escapeHtml(d.tags[0])}</span>`
      : "";
    const isDeleted = !!d.is_deleted;
    const deletedBadge = isDeleted ? `<span class="doc-item-status">Corbeille</span>` : "";
    // Risk dot
    const riskDotClass = {
      ready: "risk-dot-green",
      processing: "risk-dot-blue",
      uploaded: "risk-dot-orange",
      failed: "risk-dot-red",
    }[d.status] || "risk-dot-orange";
    const riskDotTitle = {
      ready: "Anonymisé — prêt pour l'IA",
      processing: "Anonymisation en cours…",
      uploaded: "Non anonymisé — risque RGPD",
      failed: "Erreur de traitement",
    }[d.status] || "";
    const riskDot = isDeleted ? "" : `<span class="risk-dot ${riskDotClass}" title="${riskDotTitle}"></span>`;
    const cardClass = isDeleted ? " trashed" : "";
    const batchCheck = batchMode && !isDeleted
      ? `<input type="checkbox" class="doc-item-check" data-id="${escapeHtml(d.id)}" ${selectedDocIds.has(d.id) ? "checked" : ""} />`
      : "";
    const batchSelectedClass = selectedDocIds.has(d.id) ? " batch-selected" : "";
    const batchModeClass = batchMode ? " batch-mode" : "";
    const deleteBtn = isDeleted || batchMode
      ? ""
      : `<button class="doc-item-del" data-id="${escapeHtml(d.id)}" data-name="${rawName}" title="Supprimer">✕</button>`;
    const trashActions = isDeleted
      ? `<div class="doc-item-actions">
          <button class="btn-tiny doc-item-restore" data-id="${escapeHtml(d.id)}" data-name="${rawName}">Restaurer</button>
          <button class="btn-tiny doc-item-delete-perm" data-id="${escapeHtml(d.id)}" data-name="${rawName}">Suppr. définitive</button>
        </div>`
      : "";

    return `<div class="doc-item${selected}${cardClass}${batchModeClass}${batchSelectedClass}" data-id="${escapeHtml(d.id)}" data-status="${escapeHtml(d.status)}" data-name="${rawName}" data-size="${d.size_bytes || 0}" data-deleted="${isDeleted ? "1" : "0"}">
      <div class="doc-item-name" style="display:flex;align-items:center;gap:6px">${batchCheck}${riskDot}${name}</div>
      <div class="doc-item-meta">
        <span class="doc-item-status status-${escapeHtml(d.status)}">${label}</span>
        ${deletedBadge}
        ${clientTag}
        ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
      </div>
      ${deleteBtn}
      ${trashActions}
    </div>`;
  }).join("");

  list.querySelectorAll(".doc-item").forEach(el => {
    if (el.dataset.deleted === "1") return;
    el.addEventListener("click", (e) => {
      if (batchMode) {
        if (e.target.classList.contains("doc-item-check")) return; // handled by checkbox
        const id = el.dataset.id;
        if (selectedDocIds.has(id)) selectedDocIds.delete(id);
        else selectedDocIds.add(id);
        renderDocList(lastDocsList);
        updateBatchBar();
        return;
      }
      selectDoc(
        el.dataset.id,
        el.dataset.status,
        el.dataset.name,
        parseInt(el.dataset.size, 10) || 0
      );
    });
  });

  list.querySelectorAll(".doc-item-check").forEach(cb => {
    cb.addEventListener("change", (e) => {
      e.stopPropagation();
      const id = cb.dataset.id;
      if (cb.checked) selectedDocIds.add(id);
      else selectedDocIds.delete(id);
      const item = cb.closest(".doc-item");
      if (item) item.classList.toggle("batch-selected", cb.checked);
      updateBatchBar();
    });
  });

  list.querySelectorAll(".doc-item-del").forEach(btn => {
    btn.addEventListener("click", async e => {
      e.stopPropagation();
      await deleteDoc(btn.dataset.id, btn.dataset.name);
    });
  });
  list.querySelectorAll(".doc-item-restore").forEach(btn => {
    btn.addEventListener("click", async e => {
      e.stopPropagation();
      await restoreDoc(btn.dataset.id, btn.dataset.name);
    });
  });
  list.querySelectorAll(".doc-item-delete-perm").forEach(btn => {
    btn.addEventListener("click", async e => {
      e.stopPropagation();
      await permanentDeleteDoc(btn.dataset.id, btn.dataset.name);
    });
  });
  refreshCompareDocSelect();
}

// ── Batch mode ──────────────────────────────────────────────────────────

function updateBatchBar() {
  const bar = $("batch-bar");
  const countEl = $("batch-count");
  if (!bar) return;
  const n = selectedDocIds.size;
  if (batchMode && n > 0) {
    bar.classList.add("visible");
    if (countEl) countEl.textContent = `${n} sélectionné${n > 1 ? "s" : ""}`;
  } else {
    bar.classList.remove("visible");
  }
}

function toggleBatchMode() {
  batchMode = !batchMode;
  selectedDocIds.clear();
  const btn = $("btn-batch-toggle");
  if (btn) btn.classList.toggle("active", batchMode);
  updateBatchBar();
  renderDocList(lastDocsList);
}

async function batchDeleteSelected() {
  const ids = [...selectedDocIds];
  if (!ids.length) return;
  const names = ids.map(id => {
    const d = lastDocsList.find(x => x.id === id);
    return d ? d.original_filename : id;
  });
  const ok = await confirm(
    `${ids.length} document(s) seront déplacés dans la corbeille.`,
    `Supprimer ${ids.length} document(s) ?`,
    "Supprimer"
  );
  if (!ok) return;
  let succeeded = 0;
  for (const id of ids) {
    try {
      await apiRequest(`/documents/${id}`, { method: "DELETE" });
      succeeded++;
    } catch (_e) { /* continue */ }
  }
  toast(`${succeeded} / ${ids.length} document(s) supprimé(s)`, "success");
  selectedDocIds.clear();
  batchMode = false;
  const btn = $("btn-batch-toggle");
  if (btn) btn.classList.remove("active");
  updateBatchBar();
  await loadClientSuggestions();
  await loadDocList();
}

async function batchAnonymizeSelected() {
  const ids = [...selectedDocIds].filter(id => {
    const d = lastDocsList.find(x => x.id === id);
    return d && (d.status === "uploaded" || d.status === "failed");
  });
  if (!ids.length) {
    toast("Aucun document éligible (seuls les docs non anonymisés sont traités)", "error");
    return;
  }
  const ok = await confirm(
    `${ids.length} document(s) vont être anonymisés.`,
    `Anonymiser ${ids.length} document(s) ?`,
    "Lancer"
  );
  if (!ok) return;
  let launched = 0;
  for (const id of ids) {
    try {
      await apiFetch(`/documents/${id}/anonymize`, { method: "POST", body: JSON.stringify({ profile: "moderate", document_type: "auto" }) });
      launched++;
    } catch (_e) { /* continue */ }
  }
  toast(`${launched} anonymisation(s) lancée(s)`, "success");
  selectedDocIds.clear();
  batchMode = false;
  const btn = $("btn-batch-toggle");
  if (btn) btn.classList.remove("active");
  updateBatchBar();
  await loadDocList();
}

// ── Delete document ─────────────────────────────────────────────────────

async function deleteDoc(id, name) {
  const ok = await confirm(`"${name}" sera déplacé dans la corbeille.`, "Supprimer ce document ?", "Supprimer");
  if (!ok) return;
  try {
    await apiRequest(`/documents/${id}`, { method: "DELETE" });
    toast(`"${name}" supprimé`, "success");
    if (currentDocId === id) {
      currentDocId = null;
      currentDocName = "";
      currentDocStatus = "";
      setStep(1);
    }
    await loadClientSuggestions();
    await loadDocList();
  } catch (e) {
    console.error("deleteDoc error:", e);
    toast(`Erreur suppression: ${e.message}`, "error");
  }
}

async function restoreDoc(id, name) {
  try {
    await apiFetch(`/documents/${id}/restore`, { method: "POST" });
    toast(`"${name}" restauré`, "success");
    await loadClientSuggestions();
    await loadDocList();
  } catch (e) {
    console.error("restoreDoc error:", e);
    toast(`Erreur restauration: ${e.message}`, "error");
  }
}

async function permanentDeleteDoc(id, name) {
  const ok = await confirm(`Suppression définitive de "${name}" ? Cette action est irréversible.`, "Suppression définitive", "Supprimer définitivement");
  if (!ok) return;
  try {
    await apiRequest(`/documents/${id}/permanent`, { method: "DELETE" });
    toast(`"${name}" supprimé définitivement`, "success");
    if (currentDocId === id) {
      currentDocId = null;
      currentDocName = "";
      currentDocStatus = "";
      setStep(1);
    }
    await loadClientSuggestions();
    await loadDocList();
  } catch (e) {
    console.error("permanentDeleteDoc error:", e);
    toast(`Erreur suppression définitive: ${e.message}`, "error");
  }
}

// ── Select document ─────────────────────────────────────────────────────

async function selectDoc(id, status, name, sizeBytes) {
  currentDocId = id;
  currentDocName = name || "";
  currentDocStatus = status;
  currentDocSize = sizeBytes || 0;
  delete originalTextCache[id]; // invalide le cache si on recharge
  updateHeaderContext();

  document.querySelectorAll(".doc-item").forEach(el =>
    el.classList.toggle("selected", el.dataset.id === id)
  );

  // Si le document est prêt, aller directement à l'étape 3 (Discussion IA)
  // pour un flux naturel. Sinon, étape 2 (Anonymisation).
  const targetStep = status === "ready" ? 3 : 2;
  setStep(targetStep);

  if (targetStep === 2) {
    resetAnonPanel();
    updateAnonDocBar(name, sizeBytes);
    updatePipelineTimeline({ status, extractDone: status !== "uploaded", anonymDone: status === "ready" });
    await refreshAIDocInsights(id);

    if (status === "processing") {
      showAnonLoading("Traitement en cours…");
      pollDocStatus(id);
    } else if (status === "uploaded") {
      $("anon-empty").style.display = "";
      $("anon-empty").querySelector("p").innerHTML =
        "Document uploadé.<br>Cliquez sur <strong>Anonymiser</strong> pour démarrer.";
    } else if (status === "failed") {
      $("anon-empty").style.display = "";
      $("anon-empty").querySelector(".hint-icon").textContent = "⚠️";
      $("anon-empty").querySelector("p").innerHTML =
        "Le traitement a échoué.<br>Cliquez sur <strong>Anonymiser</strong> pour réessayer.";
    }
  } else {
    // targetStep === 3 (ready doc)
    updateAIDocBar(name, sizeBytes);
    updatePipelineTimeline({ status, extractDone: true, anonymDone: true });
    await refreshAIDocInsights(id);
    // Pre-fill quick insights if possible, but don't block on preview
    try {
      const preview = await apiFetch(`/documents/${id}/preview`);
      showAnonResults(preview.preview_text, preview.detections_count, preview.entity_summary || {});
    } catch (e) {
      console.error("preview load error:", e);
    }
  }
  refreshCompareDocSelect();
}

function updateAnonDocBar(name, sizeBytes) {
  if (!name) { $("anon-doc-bar").style.display = "none"; return; }
  $("anon-doc-name").textContent = name;
  $("anon-doc-size").textContent = formatBytes(sizeBytes);
  const st = $("anon-doc-status");
  const status = currentDocStatus || "uploaded";
  const map = { uploaded: "Uploadé", processing: "Traitement", ready: "Prêt IA", failed: "Erreur" };
  st.textContent = map[status] || status;
  st.className = `doc-stage-badge ${status}`;
  $("anon-doc-bar").style.display = "";
}

function updateAIDocBar(name, sizeBytes) {
  if (!name) { $("ai-doc-bar").style.display = "none"; return; }
  $("ai-doc-name").textContent = name;
  $("ai-doc-size").textContent = formatBytes(sizeBytes);
  const st = $("ai-doc-status");
  const status = currentDocStatus || "uploaded";
  const map = { uploaded: "Uploadé", processing: "Traitement", ready: "Prêt IA", failed: "Erreur" };
  st.textContent = map[status] || status;
  st.className = `doc-stage-badge ${status}`;
  $("ai-doc-bar").style.display = "";
}


function uploadWithProgress(formData, path, fillEl, statusEl) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        fillEl.style.width = pct + "%";
        statusEl.textContent = `Envoi… ${pct}%`;
      }
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        fillEl.style.width = "100%";
        statusEl.textContent = "Upload réussi !";
        try { resolve(JSON.parse(xhr.responseText)); }
        catch (_e) { resolve({}); }
      } else {
        let msg = `HTTP ${xhr.status}`;
        try { const j = JSON.parse(xhr.responseText); msg = j.detail || msg; } catch(_e) {}
        reject(new Error(msg));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Erreur réseau")));
    xhr.addEventListener("abort", () => reject(new Error("Upload annulé")));
    xhr.open("POST", API + path);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.send(formData);
  });
}

// ── Upload ─────────────────────────────────────────────────────────────

function renderUploadQueue() {
  const el = $("upload-queue");
  if (!el) return;
  if (!uploadQueue.length && !isUploadProcessing) {
    el.style.display = "none";
    el.innerHTML = "";
    return;
  }
  el.style.display = "";
  el.innerHTML = uploadQueue.map((item, idx) => {
    return `<div class="upload-queue-item ${item.status}">
      <span>${idx + 1}. ${escapeHtml(item.file.name)}</span>
      <strong>${item.status_label}</strong>
    </div>`;
  }).join("");
}

function enqueueUpload(files) {
  files.forEach((file) => {
    uploadQueue.push({ file, status: "queued", status_label: "En attente" });
  });
  renderUploadQueue();
  processUploadQueue();
}

async function processUploadQueue() {
  if (isUploadProcessing) return;
  isUploadProcessing = true;
  while (uploadQueue.length) {
    const item = uploadQueue[0];
    item.status = "uploading";
    item.status_label = "Envoi...";
    renderUploadQueue();
    try {
      await uploadFile(item.file);
      item.status = "done";
      item.status_label = "Terminé";
    } catch (e) {
      item.status = "error";
      item.status_label = "Échec";
    }
    renderUploadQueue();
    await new Promise((r) => setTimeout(r, 250));
    uploadQueue.shift();
  }
  isUploadProcessing = false;
  renderUploadQueue();
}

async function uploadFile(file) {
  const zone = $("upload-zone");
  const progress = $("upload-progress");
  const statusEl = $("upload-status");
  const fill = $("progress-fill");

  zone.style.display = "none";
  progress.style.display = "";
  statusEl.textContent = "Envoi en cours…";
  fill.style.width = "30%";

  const fd = new FormData();
  fd.append("file", file);
  const clientName = ($("upload-client-name")?.value || "").trim();
  if (!clientName) {
    zone.style.display = "";
    progress.style.display = "none";
    fill.style.width = "0";
    toast("Le nom client est obligatoire à l'upload.", "error");
    $("upload-client-name")?.focus();
    throw new Error("client_name_required");
  }

  try {
    const clientQp = clientName ? `&client_name=${encodeURIComponent(clientName)}` : "";
    const autoAnon = $("upload-auto-anonymize")?.checked ?? true;
    const data = await uploadWithProgress(fd, `/uploads?auto_anonymize=${autoAnon}${clientQp}`, fill, statusEl);
    currentDocId = data.document_id;
    currentDocName = file.name;
    currentDocStatus = "uploaded";
    currentDocSize = file.size || 0;
    updateHeaderContext();
    await loadClientSuggestions();
    await loadDocList();

    setTimeout(() => {
      zone.style.display = "";
      progress.style.display = "none";
      fill.style.width = "0";
      setStep(2);
      resetAnonPanel();
      updateAnonDocBar(file.name, file.size);
      refreshAIDocInsights(currentDocId);
      $("anon-empty").style.display = "";
      $("anon-empty").querySelector(".hint-icon").textContent = "📄";
      if (autoAnon) {
        $("anon-empty").querySelector("p").innerHTML =
          `<strong>${file.name}</strong> uploadé.<br>Anonymisation en cours en arrière-plan…`;
        showAnonLoading("Anonymisation en cours…");
        pollDocStatus(currentDocId);
      } else {
        $("anon-empty").querySelector("p").innerHTML =
          `<strong>${file.name}</strong> uploadé.<br>Cliquez sur <strong>Anonymiser</strong> pour démarrer.`;
      }
    }, 600);

    toast(`${file.name} uploadé`, "success");
  } catch (e) {
    console.error("uploadFile error:", e);
    zone.style.display = "";
    progress.style.display = "none";
    fill.style.width = "0";
    if (e.message !== "client_name_required") {
      toast(`Erreur upload: ${e.message}`, "error");
      // Rafraîchir la liste même en cas d'erreur : le doc peut être en DB
      loadDocList().catch(() => {});
    }
    throw e;
  }
}

async function createDemoDocument() {
  try {
    const res = await apiFetch("/demo", { method: "POST" });
    currentDocId = res.document_id;
    currentDocName = res.original_filename;
    currentDocStatus = "processing";
    currentDocSize = 0;
    updateHeaderContext();
    await loadDocList();

    setStep(2);
    resetAnonPanel();
    updateAnonDocBar(res.original_filename, 0);
    refreshAIDocInsights(currentDocId);
    $("anon-empty").style.display = "";
    $("anon-empty").querySelector(".hint-icon").textContent = "🚀";
    $("anon-empty").querySelector("p").innerHTML =
      `<strong>${res.original_filename}</strong> créé.<br>Anonymisation en cours en arrière-plan…`;
    showAnonLoading("Anonymisation en cours…");
    pollDocStatus(currentDocId);

    toast("Document de démo créé — anonymisation lancée", "success");
  } catch (e) {
    console.error("demo error:", e);
    toast(`Erreur démo: ${e.message}`, "error");
  }
}

// ── Anonymisation ──────────────────────────────────────────────────────

function resetAnonPanel() {
  hideAnonLoading();
  $("anon-results").style.display = "none";
  $("anon-empty").style.display = "none";
  $("anon-empty").querySelector(".hint-icon").textContent = "👈";
  $("anon-empty").querySelector("p").innerHTML =
    "Sélectionnez un document dans la liste<br>ou uploadez-en un nouveau.";
  $("btn-anonymize").disabled = false;
  // Reset vue split
  $("preview-original-text").textContent = "";
  $("original-loading").style.display = "none";
  $("preview-diff-text").innerHTML = "";
  updatePipelineTimeline({});
}

function showAnonLoading(msg) {
  $("anon-loading").style.display = "";
  $("anon-loading-msg").textContent = msg || "Anonymisation en cours…";
  $("anon-results").style.display = "none";
  $("anon-empty").style.display = "none";
  $("btn-anonymize").disabled = true;
}

function hideAnonLoading() {
  $("anon-loading").style.display = "none";
  $("btn-anonymize").disabled = false;
}

function showAnonResults(previewText, count, summary = {}, risk = null, mode = "pseudonymization") {
  hideAnonLoading();
  $("anon-results").style.display = "";
  $("stat-count").textContent = count ?? 0;
  $("preview-anon-text").innerHTML = highlightTags(previewText || "(Aucun texte extrait)");

  // Render summary chips
  const chips = $("anon-summary-chips");
  if (chips) {
    const sorted = Object.entries(summary).sort((a, b) => b[1] - a[1]);
    chips.innerHTML = sorted.map(([type, cnt]) =>
      `<span class="stat-chip" style="background: var(--bg-hover); border-color: var(--accent);">${type}: ${cnt}</span>`
    ).join("");
  }
  renderEntityLegend(summary);

  // Store risk level globally for export gating
  currentRiskLevel = risk ? risk.level : null;

  // Risk indicator (RGPD)
  const riskEl = $("risk-indicator");
  if (riskEl && risk) {
    riskEl.style.display = "";
    const scoreEl = $("risk-score");
    const levelEl = $("risk-level");
    const recoEl = $("risk-recommendation");
    const badgeEl = $("risk-badge");
    if (scoreEl) scoreEl.textContent = `${Math.round(risk.score * 100)}%`;
    if (levelEl) {
      const labels = { low: "Faible", medium: "Moyen", high: "Élevé", critical: "Critique" };
      levelEl.textContent = labels[risk.level] || risk.level;
      levelEl.className = "risk-level risk-" + risk.level;
    }
    if (badgeEl) badgeEl.className = "risk-score-badge risk-bg-" + risk.level;
    if (recoEl) recoEl.textContent = risk.recommendation || "";
  } else if (riskEl) {
    riskEl.style.display = "none";
  }
  const score = risk?.score ?? null;
  renderRiskMeter(score);
  if (currentDocId) {
    loadOriginalText(currentDocId).then(() => loadDiffView());
  }
}

function highlightTags(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\[([A-Z][A-Z0-9_]*)\]/g, (match, tag) => {
      let colorClass = "";
      if (tag.includes("PERSONNE") || tag.includes("ASSOCIE")) colorClass = "tag-person";
      else if (tag.includes("SOCIETE") || tag.includes("CABINET")) colorClass = "tag-org";
      else if (tag.includes("ADRESSE") || tag.includes("VILLE") || tag.includes("NAISSANCE")) colorClass = "tag-geo";
      else if (tag.includes("IBAN") || tag.includes("BANQUE") || tag.includes("MONTANT") || tag.includes("EMPRUNT") || tag.includes("REF")) colorClass = "tag-bank";
      else if (tag.includes("DATE")) colorClass = "tag-date";
      else if (tag.includes("EMAIL")) colorClass = "tag-email";
      else if (tag.includes("TELEPHONE")) colorClass = "tag-phone";
      else if (tag.includes("NSS") || tag.includes("SIRET") || tag.includes("SIREN") || tag.includes("TVA") || tag.includes("CADASTRE")) colorClass = "tag-id";
      return `<mark class="anon-tag ${colorClass}">${match}</mark>`;
    });
}

async function anonymize() {
  if (!currentDocId) { toast("Aucun document sélectionné", "error"); return; }
  const profile = $("anon-profile").value;
  const mode = $("anon-mode") ? $("anon-mode").value : "pseudonymization";
  showAnonLoading(mode === "anonymization" ? "Anonymisation forte en cours…" : "Pseudonymisation en cours…");

  try {
    const res = await fetch(
      `/api/v1/documents/${currentDocId}/anonymize?profile=${profile}&mode=${mode}`,
      { method: "POST", headers: { "Authorization": `Bearer ${token}` } }
    );

    if (res.status === 202) {
      toast("Anonymisation lancée… (peut prendre 30-60 s)", "info");
      showAnonLoading("Traitement en arrière-plan…");
      await loadDocList();
      pollDocStatus(currentDocId);
      updatePipelineTimeline({ status: "processing", extractDone: true, anonymDone: false });
    } else if (res.ok) {
      const data = await res.json();
      showAnonResults(data.preview_text, data.detections_count, data.entity_summary || {}, data.risk || null, data.mode || mode);
      toast(`${data.detections_count ?? 0} entité(s) anonymisée(s) (${mode === "anonymization" ? "anonymisation forte" : "pseudonymisation"})`, "success");
      currentDocStatus = "ready";
      updateHeaderContext();
      updatePipelineTimeline({ status: "ready", extractDone: true, anonymDone: true });
      await loadDocList();
    } else {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
  } catch (e) {
    console.error("anonymize error:", e);
    hideAnonLoading();
    toast(`Erreur: ${e.message}`, "error");
  }
}

function pollDocStatus(docId) {
  let tries = 0;
  const maxTries = 240;  // 240 × 2s = 8 minutes for Railway cold-start + model load
  const interval = setInterval(async () => {
    tries++;
    if (tries > maxTries) {
      clearInterval(interval);
      hideAnonLoading();
      toast("Délai dépassé. Veuillez réessayer.", "error");
      await loadDocList().catch(e => console.warn(e));
      return;
    }
    try {
      const doc = await apiFetch(`/documents/${docId}`);
      if (doc.status === "ready") {
        clearInterval(interval);
        try {
          const preview = await apiFetch(`/documents/${docId}/preview`);
          showAnonResults(preview.preview_text, preview.detections_count, preview.entity_summary || {});
          toast(`${preview.detections_count ?? 0} entité(s) anonymisée(s)`, "success");
        } catch (e) {
          console.warn("preview load after poll:", e);
          hideAnonLoading();
          toast("Anonymisation terminée.", "success");
        }
        currentDocStatus = "ready";
        updateHeaderContext();
        updatePipelineTimeline({ status: "ready", extractDone: true, anonymDone: true });
        await loadDocList();
      } else if (doc.status === "failed") {
        clearInterval(interval);
        hideAnonLoading();
        toast("L'anonymisation a échoué. Veuillez réessayer.", "error");
        updatePipelineTimeline({ status: "failed", extractDone: true, anonymDone: false });
        await loadDocList();
      }
      // sinon: toujours "processing", on continue à poller
    } catch (e) {
      console.error("pollDocStatus error:", e);
      clearInterval(interval);
      hideAnonLoading();
      toast("Erreur de connexion pendant l'anonymisation.", "error");
      await loadDocList().catch(err => console.warn(err));
    }
  }, 2000);
}

// ── Original text ──────────────────────────────────────────────────────

async function loadOriginalText(docId) {
  if (originalTextCache[docId]) {
    $("preview-original-text").textContent = originalTextCache[docId];
    return;
  }
  $("original-loading").style.display = "";
  $("preview-original-text").textContent = "";
  try {
    const data = await apiFetch(`/documents/${docId}/extracted-text`);
    const text = data.text || "(Aucun texte extrait)";
    originalTextCache[docId] = text;
    $("preview-original-text").textContent = text;
  } catch (e) {
    console.warn("loadOriginalText error:", e);
    $("preview-original-text").textContent = "(Texte original non disponible — lancez l'anonymisation d'abord)";
  } finally {
    $("original-loading").style.display = "none";
  }
}

function renderEntityLegend(summary = {}) {
  const el = $("entity-legend");
  if (!el) return;
  const entries = Object.entries(summary || {});
  if (!entries.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = entries
    .sort((a, b) => b[1] - a[1])
    .map(([type, cnt]) => `<span class="entity-pill">${escapeHtml(type)} (${cnt})</span>`)
    .join("");
}

function renderRiskMeter(score) {
  const container = $("risk-indicator");
  if (!container || typeof score !== "number") return;
  let meter = $("doc-risk-meter");
  if (!meter) {
    meter = document.createElement("div");
    meter.id = "doc-risk-meter";
    meter.className = "doc-risk-meter";
    container.appendChild(meter);
  }
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  meter.innerHTML = `<span>Sensibilité</span><div class="doc-risk-meter-bar"><div style="width:${pct}%"></div></div><strong>${pct}%</strong>`;
}


// ── Background pollers (notifications) ─────────────────────────────────

function startBgPollers(docs) {
  Object.values(bgPollers).forEach(id => clearInterval(id));
  bgPollers = {};
  const processing = (docs || []).filter(d => d.status === "processing" && !d.is_deleted);
  processing.forEach(d => {
    bgPollers[d.id] = setInterval(async () => {
      try {
        const doc = await apiFetch(`/documents/${d.id}`);
        if (doc.status === "ready") {
          clearInterval(bgPollers[d.id]);
          delete bgPollers[d.id];
          notifyDocReady(d.original_filename, d.id);
          await loadDocList();
          if (currentDocId === d.id) {
            try {
              const preview = await apiFetch(`/documents/${d.id}/preview`);
              showAnonResults(preview.preview_text, preview.detections_count, preview.entity_summary || {});
            } catch (_e) {}
            currentDocStatus = "ready";
            updateHeaderContext();
            updatePipelineTimeline({ status: "ready", extractDone: true, anonymDone: true });
          }
        } else if (doc.status === "failed") {
          clearInterval(bgPollers[d.id]);
          delete bgPollers[d.id];
          toast(`"${d.original_filename}" a echoue`, "error");
          await loadDocList();
        }
      } catch (_e) {
        clearInterval(bgPollers[d.id]);
        delete bgPollers[d.id];
      }
    }, 3000);
  });
}

function notifyDocReady(filename, docId) {
  toast(`"${filename}" est pret !`, "success");
  const el = document.querySelector(`.doc-item[data-id="${docId}"]`);
  if (el) {
    el.classList.add("doc-item-flash");
    setTimeout(() => el.classList.remove("doc-item-flash"), 2000);
  }
  if ("Notification" in window && Notification.permission === "granted") {
    try { new Notification("ConfiDoc", { body: `${filename} est pret pour la discussion IA` }); } catch(_e){}
  }
}

// ── Diff view ──────────────────────────────────────────────────────────

function buildDiffView(original, anonymized) {
  if (!original || !anonymized) return "<p style='color:var(--text-muted)'>Chargez d'abord le texte original et anonymise.</p>";
  const origLines = original.split("\n");
  const anonLines = anonymized.split("\n");
  const maxLen = Math.max(origLines.length, anonLines.length);
  let html = '<div class="diff-container">';
  for (let i = 0; i < maxLen; i++) {
    const oLine = origLines[i] || "";
    const aLine = anonLines[i] || "";
    const changed = oLine !== aLine;
    const cls = changed ? "diff-changed" : "diff-same";
    html += `<div class="diff-row ${cls}">`;
    html += `<div class="diff-num">${i + 1}</div>`;
    html += `<div class="diff-left">${escapeHtml(oLine)}</div>`;
    html += `<div class="diff-sep">${changed ? "\u2192" : ""}</div>`;
    html += `<div class="diff-right">${changed ? highlightTags(aLine) : escapeHtml(aLine)}</div>`;
    html += `</div>`;
  }
  html += "</div>";
  return html;
}

async function loadDiffView() {
  const diffEl = $("preview-diff-text");
  if (!diffEl) return;
  diffEl.innerHTML = '<div class="loading-state"><div class="spinner spinner-sm"></div><p>Chargement...</p></div>';
  const anonText = $("preview-anon-text")?.textContent || "";
  if (!anonText) { diffEl.innerHTML = "<p>Texte anonymise non disponible.</p>"; return; }
  if (!currentDocId) return;
  if (!originalTextCache[currentDocId]) {
    try {
      const data = await apiFetch(`/documents/${currentDocId}/extracted-text`);
      originalTextCache[currentDocId] = data.text || "";
    } catch (_e) {
      diffEl.innerHTML = "<p>Texte original non disponible.</p>";
      return;
    }
  }
  diffEl.innerHTML = buildDiffView(originalTextCache[currentDocId], anonText);
}

// ── Chat history (localStorage) ────────────────────────────────────────

function saveChatHistory(docId) {
  if (!docId) return;
  const msgs = $("chat-messages");
  if (!msgs) return;
  const messages = [];
  msgs.querySelectorAll(".msg").forEach(el => {
    const isUser = el.classList.contains("msg-user");
    const body = isUser ? el.textContent : (el.querySelector(".msg-body")?.textContent || "");
    if (body.trim()) messages.push({ role: isUser ? "user" : "assistant", content: body });
  });
  if (messages.length) {
    try { localStorage.setItem(CHAT_STORAGE_PREFIX + docId, JSON.stringify(messages)); } catch (_e) {}
  }
}

function loadChatHistory(docId) {
  if (!docId) return;
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_PREFIX + docId);
    if (!raw) return;
    const messages = JSON.parse(raw);
    if (!Array.isArray(messages) || !messages.length) return;
    const msgs = $("chat-messages");
    const intro = msgs.querySelector(".chat-intro");
    if (intro) intro.remove();
    messages.forEach(m => {
      if (m.role === "user") {
        const div = document.createElement("div");
        div.className = "msg msg-user";
        div.textContent = m.content;
        msgs.appendChild(div);
      } else {
        const div = document.createElement("div");
        div.className = "msg msg-ai";
        div.innerHTML = '<div class="msg-label">IA</div><span class="msg-body">' + escapeHtml(m.content) + '</span>';
        msgs.appendChild(div);
        latestAssistantText = m.content;
      }
    });
    msgs.scrollTop = msgs.scrollHeight;
    $("btn-copy-answer").disabled = !latestAssistantText.trim();
  } catch (_e) {}
}

// ── Onboarding ─────────────────────────────────────────────────────────

function showOnboarding() {
  const steps = [
    { target: ".upload-zone", title: "📄 Uploadez un document", text: "Glissez un PDF, PNG ou JPEG — contrat, bilan, relevé bancaire. Saisissez le nom du client. Max 50 MB." },
    { target: "#btn-anonymize", title: "🔒 Anonymisation RGPD", text: "L'IA détecte noms, IBAN, SIREN, adresses… et les remplace par des balises. Mode modéré ou strict selon votre besoin." },
    { target: ".quick-actions", title: "💬 Discussion IA sécurisée", text: "Posez vos questions métier. L'IA ne voit que le texte masqué — vos données confidentielles ne sortent jamais." },
    { target: "#btn-export-txt", title: "⬇ Export & Audit", text: "Téléchargez le texte anonymisé, le PDF rédacté, ou le rapport d'audit RGPD complet pour vos dossiers." },
  ];
  let current = 0;
  const overlay = document.createElement("div");
  overlay.className = "onboarding-overlay";
  overlay.id = "onboarding-overlay";

  function renderStep() {
    const step = steps[current];
    const targetEl = document.querySelector(step.target);
    const dots = steps.map((_, i) =>
      `<div class="onboarding-dot${i === current ? " active" : ""}"></div>`
    ).join("");
    overlay.innerHTML = '<div class="onboarding-backdrop"></div>' +
      '<div class="onboarding-card">' +
      '<div class="onboarding-dots">' + dots + '</div>' +
      '<h3>' + step.title + '</h3>' +
      '<p>' + step.text + '</p>' +
      '<div class="onboarding-actions">' +
      '<button class="btn btn-ghost btn-sm" id="onboarding-skip">Ignorer</button>' +
      (current > 0 ? '<button class="btn btn-ghost btn-sm" id="onboarding-prev">← Précédent</button>' : '') +
      '<button class="btn btn-primary btn-sm" id="onboarding-next">' + (current < steps.length-1 ? 'Suivant →' : '🚀 Commencer !') + '</button>' +
      '</div></div>';
    document.body.appendChild(overlay);
    const card = overlay.querySelector(".onboarding-card");
    if (targetEl) {
      const rect = targetEl.getBoundingClientRect();
      let top = rect.bottom + 12;
      let left = rect.left;
      if (top + 200 > window.innerHeight) top = rect.top - 200;
      if (left + 320 > window.innerWidth) left = window.innerWidth - 336;
      if (left < 16) left = 16;
      card.style.top = Math.max(16, top) + "px";
      card.style.left = left + "px";
      targetEl.classList.add("onboarding-highlight");
    } else {
      card.style.top = "50%";
      card.style.left = "50%";
      card.style.transform = "translate(-50%, -50%)";
    }
    overlay.querySelector("#onboarding-next").addEventListener("click", () => {
      if (targetEl) targetEl.classList.remove("onboarding-highlight");
      current++;
      if (current >= steps.length) { finishOnboarding(); }
      else { overlay.remove(); renderStep(); }
    });
    const prevBtn = overlay.querySelector("#onboarding-prev");
    if (prevBtn) prevBtn.addEventListener("click", () => {
      if (targetEl) targetEl.classList.remove("onboarding-highlight");
      current--;
      overlay.remove(); renderStep();
    });
    overlay.querySelector("#onboarding-skip").addEventListener("click", () => {
      document.querySelectorAll(".onboarding-highlight").forEach(el => el.classList.remove("onboarding-highlight"));
      finishOnboarding();
    });
  }

  function finishOnboarding() {
    overlay.remove();
    document.querySelectorAll(".onboarding-highlight").forEach(el => el.classList.remove("onboarding-highlight"));
    localStorage.setItem(ONBOARDING_KEY, "true");
    toast("Bienvenue sur ConfiDoc ! Uploadez votre premier document.", "success");
    setStep(1);
  }

  renderStep();
}

// ── Validate ───────────────────────────────────────────────────────────

async function validate() {
  if (!currentDocId) return;
  const btn = $("btn-validate");
  btn.disabled = true;
  btn.textContent = "Validation…";
  try {
    await apiFetch(`/documents/${currentDocId}/validate`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setStep(3);
    updateAIDocBar(currentDocName, currentDocSize);
    refreshAIDocInsights(currentDocId);
    resetChat();
    loadChatHistory(currentDocId);
    await loadDocList();
    toast("Document validé — posez vos questions !", "success");
  } catch (e) {
    console.error("validate error:", e);
    toast(`Erreur validation: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Valider et continuer →";
  }
}

function goToChat() {
  if (!currentDocId) return;
  setStep(3);
  updateAIDocBar(currentDocName, currentDocSize);
  refreshAIDocInsights(currentDocId);
  resetChat();
  loadChatHistory(currentDocId);
  refreshCompareDocSelect();
}

// ── AI Chat ────────────────────────────────────────────────────────────

function resetChat() {
  latestAssistantText = "";
  $("btn-copy-answer").disabled = true;
  $("chat-messages").innerHTML =
    '<div class="chat-intro"><div class="chat-intro-icon">🔒</div>' +
    "<p>Document anonymisé. Posez vos questions en toute sécurité.</p></div>";
}

function appendUserMsg(text) {
  const msgs = $("chat-messages");
  const intro = msgs.querySelector(".chat-intro");
  if (intro) intro.remove();
  const div = document.createElement("div");
  div.className = "msg msg-user";
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function appendAssistantMsg() {
  const msgs = $("chat-messages");
  const div = document.createElement("div");
  div.className = "msg msg-ai";
  div.innerHTML = '<div class="msg-label">IA</div><span class="msg-body"></span>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div.querySelector(".msg-body");
}

function escapeHtml(text) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderStructuredAnswer(bodyEl, text) {
  const lines = String(text || "").split(/\r?\n/);
  const sections = [];
  let current = { title: "Réponse", items: [] };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    // Detect headings: ## Title, **Title**, Title :, 1) Title, 1. Title
    const heading =
      line.match(/^#{1,3}\s+(.+)$/) ||
      line.match(/^\*\*([^*]+)\*\*\s*:?\s*$/) ||
      line.match(/^([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 ''\-\/]+)\s*:\s*$/) ||
      line.match(/^\d+[.)\-]\s+\*\*([^*]+)\*\*/) ||
      line.match(/^\d+[.)\-]\s+([A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9 ''\-\/]{3,})\s*:?\s*$/);
    if (heading) {
      if (current.items.length) sections.push(current);
      current = { title: heading[1].replace(/\*\*/g, "").trim(), items: [] };
      continue;
    }
    // Strip list markers: - • * 1. 1) a)
    const cleaned = line.replace(/^(?:[\-•*]|\d+[.)\-]|[a-z][.)\-])\s+/, "").replace(/\*\*(.+?)\*\*/g, "$1");
    current.items.push(cleaned);
  }
  if (current.items.length) sections.push(current);
  if (!sections.length) return;

  // Map section titles to icons
  const sectionIcons = {
    résumé: "📋", resume: "📋", synthèse: "📋", synthese: "📋", executif: "📋",
    points: "🔑", clés: "🔑", cles: "🔑", clef: "🔑",
    risques: "⚠️", alertes: "⚠️", anomalies: "⚠️", vigilance: "⚠️",
    actions: "✅", recommandations: "✅", prochaines: "✅", recommandées: "✅",
    chiffres: "📊", montants: "📊", données: "📊", donnees: "📊",
  };
  function getIcon(title) {
    const lower = title.toLowerCase();
    for (const [kw, icon] of Object.entries(sectionIcons)) {
      if (lower.includes(kw)) return icon;
    }
    return "📌";
  }
  function getSectionClass(title) {
    const lower = title.toLowerCase();
    if (/risque|alerte|anomalie|vigilance/.test(lower)) return "ai-section-risk";
    if (/action|recommand|prochaine/.test(lower)) return "ai-section-action";
    if (/chiffre|montant|donn[ée]e/.test(lower)) return "ai-section-data";
    return "";
  }

  bodyEl.classList.add("structured");
  bodyEl.innerHTML = sections
    .map((s) => {
      const icon = getIcon(s.title);
      const cls = getSectionClass(s.title);
      return `<div class="ai-section ${cls}"><div class="ai-section-title">${icon} ${escapeHtml(s.title)}</div><ul>${s.items.map((it) => `<li>${escapeHtml(it)}</li>`).join("")}</ul></div>`;
    })
    .join("");

  // Show export button if report mode
  if (reportMode && $("btn-export-rapport")) $("btn-export-rapport").style.display = "";
}

async function sendMessage() {
  const input = $("chat-input");
  const question = input.value.trim();
  if (!question || !currentDocId) return;
  if (copilotMode) {
    await sendCopilotMessage(question, input);
    return;
  }
  if (activeStream) return;

  input.value = "";
  appendUserMsg(question);
  const bodyEl = appendAssistantMsg();
  bodyEl.classList.add("streaming");
  latestAssistantText = "";
  $("btn-copy-answer").disabled = true;

  $("btn-send").style.display = "none";
  $("btn-stop-stream").style.display = "";

  const controller = new AbortController();
  activeStream = controller;

  try {
    const baseQ = reportMode
      ? `${question}\n\nRéponds en format rapport structuré avec sections: Résumé, Points clés, Risques, Actions recommandées.`
      : question;
    const effectiveQuestion = applyCabinetDocTypePrefix(baseQ);
    const resp = await fetch(
      `${API}/ai/stream/${currentDocId}?question=${encodeURIComponent(effectiveQuestion)}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      }
    );
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const j = await resp.json();
        detail = j.detail || j.message || detail;
      } catch (_e) {
        // noop
      }
      throw new Error(detail);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (raw === "[DONE]") break;
        try {
          const parsed = JSON.parse(raw);
          if (parsed.chunk) {
            bodyEl.textContent += parsed.chunk;
            latestAssistantText = bodyEl.textContent;
            $("btn-copy-answer").disabled = latestAssistantText.trim().length === 0;
            $("chat-messages").scrollTop = $("chat-messages").scrollHeight;
          } else if (parsed.error) {
            bodyEl.textContent += `\n[Erreur: ${parsed.error}]`;
            latestAssistantText = bodyEl.textContent;
            $("btn-copy-answer").disabled = latestAssistantText.trim().length === 0;
            bodyEl.classList.remove("streaming");
          }
        } catch (e) {
          console.warn("SSE parse error:", e);
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      console.error("sendMessage stream error:", e);
      bodyEl.textContent += `\n[Erreur: ${e.message}]`;
      latestAssistantText = bodyEl.textContent;
    } else {
      bodyEl.textContent += "\n[Réponse interrompue]";
      latestAssistantText = bodyEl.textContent;
    }
    $("btn-copy-answer").disabled = latestAssistantText.trim().length === 0;
  } finally {
    bodyEl.classList.remove("streaming");
    if (reportMode && latestAssistantText.trim()) {
      renderStructuredAnswer(bodyEl, latestAssistantText);
    }
    activeStream = null;
    $("btn-send").style.display = "";
    $("btn-stop-stream").style.display = "none";
    saveChatHistory(currentDocId);
  }
}

async function sendCopilotMessage(question, inputEl) {
  if (!question || !currentDocId) return;
  inputEl.value = "";
  appendUserMsg(question);
  const bodyEl = appendAssistantMsg();
  bodyEl.classList.add("streaming");
  latestAssistantText = "";
  $("btn-copy-answer").disabled = true;
  // Show loading state for copilot (no streaming but still needs visual feedback)
  $("btn-send").style.display = "none";
  $("btn-stop-stream").style.display = "";
  try {
    const baseQ = reportMode
      ? `${question}\n\nRéponds en format rapport structuré avec sections: ## Résumé, ## Points clés, ## Risques, ## Actions recommandées. Utilise des tirets pour les listes.`
      : question;
    const resp = await apiFetch(`/copilot/${currentDocId}/ask`, {
      method: "POST",
      body: JSON.stringify({ question: applyCabinetDocTypePrefix(baseQ), mode: "expert" }),
    });
    latestAssistantText = resp.answer || "";
    bodyEl.textContent = latestAssistantText || "Aucune réponse.";
    $("btn-copy-answer").disabled = !latestAssistantText.trim();
    renderCopilotInsights(resp);
  } catch (e) {
    bodyEl.textContent = `[Erreur: ${e.message}]`;
    toast(`Copilot indisponible: ${e.message}`, "error");
  } finally {
    bodyEl.classList.remove("streaming");
    if (reportMode && latestAssistantText.trim()) {
      renderStructuredAnswer(bodyEl, latestAssistantText);
    }
    $("btn-send").style.display = "";
    $("btn-stop-stream").style.display = "none";
    saveChatHistory(currentDocId);
  }
}

function renderCopilotInsights(resp = {}) {
  const panel = $("copilot-insights");
  if (!panel) return;
  panel.style.display = "";
  const conf = (resp.confidence || "—").toUpperCase();
  $("copilot-confidence").textContent = conf;
  const warns = $("copilot-warnings");
  if (warns) {
    warns.innerHTML = (resp.warnings || []).map((w) => `<span class="stat-chip">${escapeHtml(w)}</span>`).join("");
  }
  const cites = $("copilot-citations");
  if (cites) {
    const list = resp.citations || [];
    cites.innerHTML = list.map((c, idx) => `
      <div class="dash-entity-row">
        <span class="dash-entity-type">Source ${idx + 1}</span>
        <div class="dash-entity-bar-bg"><div class="dash-entity-bar-fill" style="width:${Math.round((c.score || 0) * 100)}%"></div></div>
        <span class="dash-entity-count">${Math.round((c.score || 0) * 100)}%</span>
      </div>
      <div class="chat-intro" style="padding:8px 0 12px; text-align:left;"><p>${escapeHtml(c.snippet || "")}</p></div>
    `).join("");
  }
}

function refreshCompareDocSelect() {
  const sel = $("compare-doc-select");
  if (!sel) return;
  sel.innerHTML = '<option value="">Deuxième document…</option>';
  if (!currentDocId || !lastDocsList.length) return;
  const current = lastDocsList.find((d) => d.id === currentDocId);
  const clientTag = current && Array.isArray(current.tags) && current.tags.length ? current.tags[0] : "";
  let pool = lastDocsList.filter((d) => d.id !== currentDocId);
  if (clientTag) {
    const same = pool.filter((d) => (d.tags && d.tags[0]) === clientTag);
    if (same.length) pool = same;
  }
  pool.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d.id;
    const name = d.original_filename || d.id;
    opt.textContent = name.length > 44 ? `${name.slice(0, 42)}…` : name;
    sel.appendChild(opt);
  });
}

async function runCopilotCompare() {
  const otherId = ($("compare-doc-select") && $("compare-doc-select").value) || "";
  if (!currentDocId) {
    toast("Sélectionnez un document dans la liste.", "error");
    return;
  }
  if (!otherId) {
    toast("Choisissez un second document (de préférence le même client).", "error");
    return;
  }
  const customQ = ($("chat-input") && $("chat-input").value.trim()) || "";
  const payload = { other_document_id: otherId };
  if (customQ) payload.question = applyCabinetDocTypePrefix(customQ);

  const inputEl = $("chat-input");
  if (inputEl) inputEl.value = "";
  appendUserMsg(customQ || "Comparaison de deux documents anonymisés (N / N-1)");
  const bodyEl = appendAssistantMsg();
  bodyEl.classList.add("streaming");
  latestAssistantText = "";
  $("btn-copy-answer").disabled = true;
  try {
    const resp = await apiFetch(`/copilot/${currentDocId}/compare`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    latestAssistantText = resp.answer || "";
    bodyEl.textContent = latestAssistantText || "Aucune réponse.";
    $("btn-copy-answer").disabled = !latestAssistantText.trim();
    renderCopilotInsights(resp);
    toast("Comparaison terminée — à valider humainement.", "info");
  } catch (e) {
    bodyEl.textContent = `[Erreur: ${e.message}]`;
    toast(`Comparaison impossible: ${e.message}`, "error");
  } finally {
    bodyEl.classList.remove("streaming");
    saveChatHistory(currentDocId);
  }
}

async function copyLatestAnswer() {
  const text = (latestAssistantText || "").trim();
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    toast("Réponse IA copiée", "success");
  } catch (_e) {
    toast("Impossible de copier automatiquement", "error");
  }
}

function stopStream() {
  if (activeStream) { activeStream.abort(); activeStream = null; }
  $("btn-send").style.display = "";
  $("btn-stop-stream").style.display = "none";
}

// ── Export ─────────────────────────────────────────────────────────────

async function exportText() {
  if (!currentDocId) return;
  try {
    const resp = await apiRequest(`/documents/${currentDocId}/export`);
    const blob = new Blob([await resp.text()], { type: "text/plain;charset=utf-8" });
    triggerDownload(blob, `confidoc_${currentDocId.slice(0, 8)}.txt`);
    toast("Export texte terminé", "success");
  } catch (e) {
    console.error("exportText error:", e);
    if (e.message && e.message.includes("bloqu")) {
      toast(e.message, "error");
      if (e.message.includes("validation humaine")) {
        showApproveExportPrompt();
      }
    } else {
      toast(`Erreur export texte: ${e.message}`, "error");
    }
  }
}

async function exportPdf() {
  if (!currentDocId) return;
  try {
    const resp = await apiRequest(`/documents/${currentDocId}/export-pdf`);
    const blob = await resp.blob();
    triggerDownload(blob, `confidoc_${currentDocId.slice(0, 8)}.pdf`);
    toast("Export PDF terminé", "success");
  } catch (e) {
    console.error("exportPdf error:", e);
    if (e.message && e.message.includes("bloqu")) {
      toast(e.message, "error");
      if (e.message.includes("validation humaine")) {
        showApproveExportPrompt();
      }
    } else {
      toast(`Erreur export PDF: ${e.message}`, "error");
    }
  }
}


async function showApproveExportPrompt() {
  if (!currentDocId) return;
  const ok = await confirm(
    "Risque de réidentification élevé détecté. Confirmez-vous avoir vérifié manuellement que l'anonymisation est suffisante pour un export externe ? Cette action sera journalisée.",
    "Validation humaine requise",
    "Confirmer l'export"
  );
  if (!ok) return;
  try {
    await apiFetch(`/documents/${currentDocId}/approve-export`, { method: "POST" });
    toast("Export approuvé — vous pouvez maintenant exporter.", "success");
  } catch (e) {
    toast(`Erreur approbation: ${e.message}`, "error");
  }
}

async function downloadAuditReport() {
  if (!currentDocId) return;
  try {
    const resp = await apiRequest(`/documents/${currentDocId}/audit-report-pdf`);
    const blob = await resp.blob();
    triggerDownload(blob, `audit_rgpd_${currentDocId.slice(0, 8)}.pdf`);
    toast("Rapport d'audit PDF telecharge", "success");
  } catch (e) {
    toast(`Erreur rapport: ${e.message}`, "error");
  }
}

async function downloadComplianceReport() {
  if (!currentDocId) return;
  try {
    const data = await apiFetch(`/documents/${currentDocId}/compliance-report`);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    triggerDownload(blob, `conformite_rgpd_${currentDocId.slice(0, 8)}.json`);
    toast("Rapport de conformite telecharge", "success");
  } catch (e) {
    toast(`Erreur conformite: ${e.message}`, "error");
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

// ── Dashboard ──────────────────────────────────────────────────────────

let dashboardLoaded = false;

function emptyDashboardData() {
  return {
    total_documents: 0,
    total_entities_masked: 0,
    trashed_documents: 0,
    status_counts: {},
    gdpr_score: {
      score: 0,
      color: "warning",
      grade: "-",
      status: "Indisponible",
      recommendations: ["Les statistiques completes n'ont pas pu etre chargees."],
      breakdown: {},
    },
    risk_distribution: {},
    entity_distribution: {},
    recent_activity: [],
  };
}

function dashboardErrorMessage(err) {
  const msg = String(err?.message || err || "");
  if (!msg) return "Statistiques indisponibles.";
  return msg.replace(/https?:\/\/\S+/g, "").slice(0, 220);
}

function showDashboard() {
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const dash = $("panel-dashboard");
  if (dash) dash.classList.add("active");
  [1, 2, 3].forEach(i => {
    const s = $(`step-${i}`);
    if (s) s.className = "step";
  });
  setPageTitle("Dashboard");
  if (!dashboardLoaded) loadDashboard();
}

async function loadDashboard() {
  const loading = $("dash-loading");
  const content = $("dash-content");
  if (loading) loading.style.display = "";
  if (content) content.style.display = "none";

  try {
    const [statsResult, summaryResult] = await Promise.allSettled([
      apiFetch("/documents/stats/dashboard"),
      apiFetch("/documents/status-summary?days=30"),
    ]);

    if (statsResult.status === "rejected" && summaryResult.status === "rejected") {
      throw new Error(
        `${dashboardErrorMessage(statsResult.reason)} ${dashboardErrorMessage(summaryResult.reason)}`.trim()
      );
    }

    const data = statsResult.status === "fulfilled" ? statsResult.value : emptyDashboardData();
    const summary = summaryResult.status === "fulfilled" ? summaryResult.value : {};

    dashboardLoaded = statsResult.status === "fulfilled" && summaryResult.status === "fulfilled";
    renderDashboard(data, summary);

    if (!dashboardLoaded) {
      const failed = statsResult.status === "rejected" ? statsResult.reason : summaryResult.reason;
      console.warn("loadDashboard partial:", failed);
      toast(`Dashboard partiel: ${dashboardErrorMessage(failed)}`, "warning");
    }
  } catch (e) {
    console.warn("loadDashboard failed:", e);
    if (content) {
      content.style.display = "";
      content.innerHTML = `<div class="empty-state">Impossible de charger les statistiques. ${escapeHtml(dashboardErrorMessage(e))}</div>`;
    }
  } finally {
    if (loading) loading.style.display = "none";
  }
}

function renderDashboard(data, summary = {}) {
  const content = $("dash-content");
  if (!content) return;
  content.style.display = "";

  // KPIs
  const sc = data.status_counts || {};
  animateNumber($("dash-total-docs"), data.total_documents || 0);
  animateNumber($("dash-total-entities"), data.total_entities_masked || 0);
  animateNumber($("dash-ready-count"), sc.ready || 0);
  animateNumber($("dash-trashed"), data.trashed_documents || 0);
  animateNumber($("dash-bucket-ready"), summary.ready ?? sc.ready ?? 0);
  animateNumber($("dash-bucket-processing"), summary.processing ?? sc.processing ?? 0);
  animateNumber($("dash-bucket-uploaded"), summary.uploaded ?? sc.uploaded ?? 0);
  animateNumber($("dash-bucket-failed"), summary.failed ?? sc.failed ?? 0);
  animateNumber($("dash-uploads-24h"), summary.recent_uploads_24h ?? summary.uploads_24h ?? 0);
  const total = Math.max(0, summary.total ?? data.total_documents ?? 0);
  const ready = Math.max(0, summary.ready ?? sc.ready ?? 0);
  if ($("dash-ready-ratio")) $("dash-ready-ratio").textContent = `${ready} / ${total}`;
  if ($("dash-ready-fill")) $("dash-ready-fill").style.width = total ? `${Math.round((ready / total) * 100)}%` : "0%";

  // GDPR Score
  const gdpr = data.gdpr_score || {};
  const gdprScoreVal = gdpr.score ?? 0;
  const gdprColor = gdpr.color || "success";
  const gdprGrade = gdpr.grade || "-";
  const gdprStatus = gdpr.status || "En attente";
  const gdprRecos = gdpr.recommendations || [];
  const gdprBreak = gdpr.breakdown || {};

  if ($("dash-gdpr-score")) {
    animateNumber($("dash-gdpr-score"), gdprScoreVal);
  }
  const ring = $("dash-gdpr-ring-fill");
  if (ring) {
    ring.setAttribute("stroke-dasharray", `${gdprScoreVal}, 100`);
    ring.className = `dash-gdpr-ring-fill color-${gdprColor}`;
  }
  const gradeEl = $("dash-gdpr-grade");
  if (gradeEl) {
    gradeEl.textContent = `Note ${gdprGrade}`;
    gradeEl.className = `dash-gdpr-grade color-${gdprColor}`;
  }
  const statusElG = $("dash-gdpr-status");
  if (statusElG) {
    statusElG.textContent = gdprStatus;
    statusElG.className = `dash-gdpr-status color-${gdprColor}`;
  }
  const breakEl = $("dash-gdpr-breakdown");
  if (breakEl) {
    const b = gdprBreak;
    const parts = [];
    if (b.success_rate != null) parts.push(`Succès ${Math.round(b.success_rate)}%`);
    if (b.risk_score != null) parts.push(`Risque ${Math.round(b.risk_score)}%`);
    if (b.failure_resilience != null) parts.push(`Resilience ${Math.round(b.failure_resilience)}%`);
    if (b.activity_momentum != null) parts.push(`Activité ${Math.round(b.activity_momentum)}%`);
    breakEl.innerHTML = parts.map(p => `<span>${p}</span>`).join("");
  }
  const recosEl = $("dash-gdpr-recos");
  if (recosEl) {
    if (gdprRecos.length) {
      recosEl.innerHTML = `<h4>Recommandations conformité</h4><ul>` +
        gdprRecos.map(r => `<li class="${r.toLowerCase().includes('bonne') || r.toLowerCase().includes('continuez') ? 'good' : ''}">${escapeHtml(r)}</li>`).join("") +
        `</ul>`;
      recosEl.style.display = "";
    } else {
      recosEl.style.display = "none";
    }
  }

  // Risk distribution
  const riskEl = $("dash-risk-chart");
  if (riskEl) {
    const rd = data.risk_distribution || {};
    const maxRisk = Math.max(1, ...Object.values(rd));
    const levels = ["low", "medium", "high", "critical"];
    const labels = { low: "Faible", medium: "Moyen", high: "Eleve", critical: "Critique" };
    riskEl.innerHTML = levels.map(lvl => {
      const count = rd[lvl] || 0;
      const pct = (count / maxRisk) * 100;
      return `<div class="dash-risk-row">
        <span class="dash-risk-label risk-label-${lvl}">${labels[lvl]}</span>
        <div class="dash-risk-bar-bg">
          <div class="dash-risk-bar-fill dash-risk-bar-${lvl}" style="width:0%" data-target="${pct}" data-count="${count}"></div>
        </div>
      </div>`;
    }).join("");
    setTimeout(() => {
      riskEl.querySelectorAll(".dash-risk-bar-fill").forEach(bar => {
        bar.style.width = bar.dataset.target + "%";
      });
    }, 100);
  }

  // Entity distribution
  const entityEl = $("dash-entity-chart");
  if (entityEl) {
    const ed = data.entity_distribution || {};
    const sorted = Object.entries(ed).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const maxEnt = Math.max(1, ...sorted.map(x => x[1]));
    if (!sorted.length) {
      entityEl.innerHTML = '<div class="empty-state" style="padding:16px">Aucune entite detectee</div>';
    } else {
      entityEl.innerHTML = sorted.map(([type, count]) => {
        const pct = (count / maxEnt) * 100;
        return `<div class="dash-entity-row">
          <span class="dash-entity-type">${type}</span>
          <div class="dash-entity-bar-bg">
            <div class="dash-entity-bar-fill" style="width:0%" data-target="${pct}"></div>
          </div>
          <span class="dash-entity-count">${count}</span>
        </div>`;
      }).join("");
      setTimeout(() => {
        entityEl.querySelectorAll(".dash-entity-bar-fill").forEach(bar => {
          bar.style.width = bar.dataset.target + "%";
        });
      }, 200);
    }
  }

  // Status distribution
  const statusEl = $("dash-status-chart");
  if (statusEl) {
    const statuses = [
      { key: "ready", label: "Pret IA", dot: "ready" },
      { key: "processing", label: "Traitement", dot: "processing" },
      { key: "uploaded", label: "Uploade", dot: "uploaded" },
      { key: "failed", label: "Erreur", dot: "failed" },
    ];
    statusEl.innerHTML = statuses.map(s => {
      const count = sc[s.key] || 0;
      return `<div class="dash-status-pill">
        <div class="dash-status-dot ${s.dot}"></div>
        <span class="dash-status-name">${s.label}</span>
        <span class="dash-status-num">${count}</span>
      </div>`;
    }).join("");
  }

  // Activity chart
  const actSection = $("dash-activity-section");
  const actEl = $("dash-activity-chart");
  if (actEl && data.recent_activity && data.recent_activity.length) {
    if (actSection) actSection.style.display = "";
    const maxAct = Math.max(1, ...data.recent_activity.map(a => a.count));
    actEl.innerHTML = data.recent_activity.map(a => {
      const h = Math.max(2, (a.count / maxAct) * 80);
      const day = a.date ? new Date(a.date).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }) : "";
      return `<div class="dash-activity-col">
        <div class="dash-activity-bar" style="height:${h}px"></div>
        <span class="dash-activity-label">${day}</span>
      </div>`;
    }).join("");
  } else {
    if (actSection) actSection.style.display = "none";
    if (actEl) actEl.innerHTML = "";
  }
  const trendEl = $("dash-trend-7d");
  const trendData = summary.created_last_7_days || [];
  if (trendEl) {
    const max = Math.max(1, ...trendData.map((d) => d.count || 0));
    trendEl.innerHTML = trendData.map((d) => {
      const h = Math.max(2, ((d.count || 0) / max) * 80);
      const day = d.date ? new Date(d.date).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }) : "";
      return `<div class="dash-activity-col"><div class="dash-activity-bar" style="height:${h}px"></div><span class="dash-activity-label">${day}</span></div>`;
    }).join("");
  }
}

function animateNumber(el, target) {
  if (!el) return;
  const duration = 800;
  const start = performance.now();
  const from = 0;
  function step(now) {
    const progress = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(from + (target - from) * ease);
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}


// ── Review Agent (LangGraph) ────────────────────────────────────────────

let reviewRunning = false;
let reviewResult = null;

const REVIEW_STEPS = [
  { id: "classify", icon: "1", label: "Classification du document" },
  { id: "extract", icon: "2", label: "Extraction des données clés" },
  { id: "analyze", icon: "3", label: "Analyse métier" },
  { id: "findings", icon: "4", label: "Identification des constats" },
  { id: "filter", icon: "5", label: "Contrôle qualité" },
  { id: "synthesize", icon: "6", label: "Note de revue" },
];

function renderReviewSteps(activeStep, completedSteps) {
  const el = $("review-steps");
  if (!el) return;
  el.innerHTML = REVIEW_STEPS.map(s => {
    let cls = "";
    let iconContent = s.icon;
    if (completedSteps.includes(s.id)) {
      cls = "done";
      iconContent = "\u2713";
    } else if (s.id === activeStep) {
      cls = "running";
    }
    const timeEl = completedSteps.includes(s.id)
      ? '<span class="review-step-time">\u2713</span>'
      : s.id === activeStep
        ? '<span class="review-step-time"><div class="spinner spinner-sm"></div></span>'
        : '';
    return `<div class="review-step ${cls}">
      <div class="review-step-icon">${iconContent}</div>
      <span class="review-step-label">${s.label}</span>
      ${timeEl}
    </div>`;
  }).join("");
}

function renderReviewResult(data) {
  const el = $("review-result");
  if (!el) return;
  el.style.display = "";

  let html = "";

  const verdict = data.verdict || "";
  const confidence = data.confidence || 0;
  const reviewNote = data.review_note || "";
  const findings = data.findings || {};
  const demandes = data.demandes_formelles || [];
  const pieces = data.pieces_a_verifier || [];
  const nextActions = data.prochaines_actions || [];
  const complement = data.review_complement || {};
  const docType = data.doc_type || "";

  const block = (num, title, bodyHtml) => `
    <div class="review-section review-cabinet-block">
      <div class="review-section-title"><span class="review-block-num">${num}</span> ${title}</div>
      <div class="review-section-body">${bodyHtml}</div>
    </div>`;

  const listOrEmpty = (arr, emptyMsg) =>
    arr.length
      ? `<ul class="review-cabinet-list">${arr.map(x => `<li>${escapeHtml(x)}</li>`).join("")}</ul>`
      : `<p class="review-cabinet-empty">${emptyMsg}</p>`;

  if (verdict) {
    const verdictIcons = { favorable: "\u2705", reserve: "\u26A0\uFE0F", defavorable: "\u274C" };
    const verdictLabels = { favorable: "Favorable", reserve: "Reserve", defavorable: "Defavorable" };
    html += `<div class="review-verdict ${verdict}">${verdictIcons[verdict] || ""} ${verdictLabels[verdict] || verdict} (confiance: ${Math.round(confidence * 100)}%)${docType ? ` — <span class="review-doc-type">${escapeHtml(docType)}</span>` : ""}</div>`;
  }

  html += block("1", "Résumé exécutif", reviewNote ? escapeHtml(reviewNote) : "Aucun resume disponible.");

  const tiers = [
    { key: "anomalies_confirmees", icon: "\u274C", label: "Anomalies confirmees", cls: "tier-confirmed" },
    { key: "points_attention", icon: "\u26A0\uFE0F", label: "Points d'attention", cls: "tier-attention" },
    { key: "informations_manquantes", icon: "\uD83D\uDCC4", label: "Informations manquantes", cls: "tier-missing" },
    { key: "verifications_recommandees", icon: "\uD83D\uDD0D", label: "Verifications recommandees", cls: "tier-verify" },
  ];
  const totalFindings = tiers.reduce((s, t) => s + (findings[t.key]?.length || 0), 0);
  let vigilHtml = "";
  if (totalFindings > 0) {
    tiers.forEach(tier => {
      const items = findings[tier.key] || [];
      if (!items.length) return;
      vigilHtml += `<div class="review-tier ${tier.cls}"><div class="review-tier-header">${tier.icon} ${tier.label} (${items.length})</div>`;
      items.forEach(item => {
        vigilHtml += `<div class="review-finding"><div class="review-finding-desc">${escapeHtml(item.description || "")}</div>${item.detail ? `<div class="review-finding-detail">${escapeHtml(item.detail)}</div>` : ""}</div>`;
      });
      vigilHtml += `</div>`;
    });
  } else {
    vigilHtml = `<p class="review-cabinet-empty">Aucun point structure en vigilance (document ou analyse limitee).</p>`;
  }
  html += block("2", "Points de vigilance", vigilHtml);

  html += block("3", "Demandes formelles", listOrEmpty(demandes, "Aucune demande formelle explicite identifiee."));

  html += block("4", "Pièces et vérifications à obtenir", listOrEmpty(pieces, "Aucune piece ou verification listee."));

  html += block("5", "Prochaines actions", listOrEmpty(nextActions, "Aucune action listee."));

  const id = complement.identification || "";
  const ch = complement.chiffres_cles || "";
  if (id || ch) {
    html += `<div class="review-section review-cabinet-block review-complement"><div class="review-section-title">Detail complementaire</div>`;
    if (id) html += `<p class="review-complement-line"><strong>Identification</strong><br/>${escapeHtml(id)}</p>`;
    if (ch) html += `<p class="review-complement-line"><strong>Chiffres / postes cles</strong><br/>${escapeHtml(ch)}</p>`;
    html += `</div>`;
  }

  el.innerHTML = html;
  $("review-actions").style.display = "";
}

function formatReviewError(message) {
  const raw = String(message || "").trim();
  if (!raw) return "Analyse indisponible. Relancez dans quelques instants.";
  const lower = raw.toLowerCase();
  if (raw.includes("429") || lower.includes("too many requests") || lower.includes("rate limit")) {
    return "Mistral limite temporairement les analyses. Le document reste pret; relancez dans quelques minutes.";
  }
  return raw.replace(/https?:\/\/\S+/g, "").slice(0, 260);
}

function renderReviewError(message, detail = {}) {
  const el = $("review-result");
  if (!el) return;
  const retry = detail?.retry_after_seconds
    ? `<p class="review-cabinet-empty">Nouvel essai conseille dans ${escapeHtml(String(detail.retry_after_seconds))} secondes.</p>`
    : "";
  el.style.display = "";
  el.innerHTML = `<div class="review-section review-cabinet-block">
    <div class="review-section-title">Analyse indisponible</div>
    <div class="review-section-body">
      <p>${escapeHtml(formatReviewError(message))}</p>
      ${retry}
    </div>
  </div>`;
  const actions = $("review-actions");
  if (actions) actions.style.display = "none";
}

async function startReview() {
  if (!currentDocId || reviewRunning) return;
  reviewRunning = true;
  reviewResult = null;

  const panel = $("review-panel");
  panel.style.display = "";
  $("review-result").style.display = "none";
  $("review-result").innerHTML = "";
  $("review-actions").style.display = "none";

  const completedSteps = [];
  let currentStep = "classify";
  renderReviewSteps(currentStep, completedSteps);

  let allData = {};

  try {
    const resp = await fetch(
      `${API}/ai/review/${currentDocId}`,
      { method: "POST", headers: { "Authorization": `Bearer ${token}` } }
    );

    if (!resp.ok) {
      let msg = `HTTP ${resp.status}`;
      try { const j = await resp.json(); msg = j.detail || msg; } catch(_e){}
      throw new Error(msg);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        const cleanLine = line.replace(/\r/g, "");
        if (!cleanLine.startsWith("data:")) continue;
        const raw = cleanLine.slice(5).trim();
        if (raw === "[DONE]") break;

        try {
          const event = JSON.parse(raw);
          const step = event.step;
          const status = event.status;

          if (status === "done" && step !== "complete") {
            if (!completedSteps.includes(step)) completedSteps.push(step);
            if (event.data) {
              Object.assign(allData, event.data);
              if (event.data.findings) allData.findings = event.data.findings;
              if (event.data.demandes_formelles) allData.demandes_formelles = event.data.demandes_formelles;
              if (event.data.pieces_a_verifier) allData.pieces_a_verifier = event.data.pieces_a_verifier;
              if (event.data.review_complement) allData.review_complement = event.data.review_complement;
            }
            renderReviewSteps(null, completedSteps);
          } else if (status === "running") {
            currentStep = step;
            renderReviewSteps(step, completedSteps);
          } else if (status === "complete") {
            renderReviewSteps(null, completedSteps);
            reviewResult = allData;
            renderReviewResult(allData);
            toast(allData.degraded ? "Analyse limitee disponible" : "Synthese cabinet terminee", allData.degraded ? "warning" : "success");
          } else if (status === "error") {
            renderReviewSteps(null, completedSteps);
            const msg = event.data?.message || event.data?.error || "Analyse indisponible.";
            renderReviewError(msg, event.data || {});
            toast(`Analyse interrompue: ${formatReviewError(msg)}`, "error");
          }
        } catch (e) {
          console.warn("Review SSE parse error:", e);
        }
      }
    }
  } catch (e) {
    console.error("startReview error:", e);
    const msg = formatReviewError(e.message);
    renderReviewError(msg);
    toast(`Erreur analyse: ${msg}`, "error");
  } finally {
    reviewRunning = false;
  }
}

function closeReview() {
  const panel = $("review-panel");
  if (panel) panel.style.display = "none";
}

function copyReviewResult() {
  if (!reviewResult) return;
  const note = reviewResult.review_note || "";
  const findings = reviewResult.findings || {};
  const demandes = reviewResult.demandes_formelles || [];
  const pieces = reviewResult.pieces_a_verifier || [];
  const complement = reviewResult.review_complement || {};
  let text = "=== SYNTHESE CABINET ===\n\n";
  if (reviewResult.doc_type) text += `Type detecte: ${reviewResult.doc_type}\n`;
  if (reviewResult.verdict) text += `Verdict: ${reviewResult.verdict}\n`;
  text += "\n--- 1. RESUME EXECUTIF ---\n" + note + "\n\n";

  const tierLabels = {
    anomalies_confirmees: "ANOMALIES CONFIRMEES",
    points_attention: "POINTS D'ATTENTION",
    informations_manquantes: "INFORMATIONS MANQUANTES",
    verifications_recommandees: "VERIFICATIONS RECOMMANDEES",
  };
  text += "--- 2. POINTS DE VIGILANCE ---\n";
  let vig = false;
  for (const [tier, label] of Object.entries(tierLabels)) {
    const items = findings[tier] || [];
    if (!items.length) continue;
    vig = true;
    text += `${label}:\n`;
    items.forEach(item => {
      text += `- ${item.description}\n`;
      if (item.detail) text += `  ${item.detail}\n`;
    });
  }
  if (!vig) text += "(aucun)\n";
  text += "\n--- 3. DEMANDES FORMELLES ---\n";
  demandes.forEach((d, i) => { text += `${i + 1}. ${d}\n`; });
  if (!demandes.length) text += "(aucune)\n";
  text += "\n--- 4. PIECES / VERIFICATIONS ---\n";
  pieces.forEach((x, i) => { text += `${i + 1}. ${x}\n`; });
  if (!pieces.length) text += "(aucune)\n";
  text += "\n--- 5. PROCHAINES ACTIONS ---\n";
  (reviewResult.prochaines_actions || []).forEach((a, i) => { text += `${i + 1}. ${a}\n`; });
  if (complement.identification || complement.chiffres_cles) {
    text += "\n--- DETAIL COMPLEMENTAIRE ---\n";
    if (complement.identification) text += `Identification: ${complement.identification}\n`;
    if (complement.chiffres_cles) text += `Chiffres cles: ${complement.chiffres_cles}\n`;
  }
  navigator.clipboard.writeText(text).then(
    () => toast("Synthese copiee", "success"),
    () => toast("Impossible de copier", "error")
  );
}

function exportReviewResult() {
  if (!reviewResult) return;
  const blob = new Blob([JSON.stringify(reviewResult, null, 2)], { type: "application/json" });
  triggerDownload(blob, `review_${currentDocId?.slice(0, 8) || "doc"}.json`);
  toast("Analyse exportee", "success");
}


// ── Event listeners ────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {

  // Garantir l'état initial : overlay fermé, forgot/reset-section cachés
  if ($("confirm-overlay")) $("confirm-overlay").style.display = "none";
  if ($("forgot-section")) $("forgot-section").style.display = "none";
  if ($("reset-section")) $("reset-section").style.display = "none";

  // Fermer la modal confirm avec Echap
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("confirm-overlay") && $("confirm-overlay").style.display !== "none") {
      $("confirm-overlay").style.display = "none";
    }
  });

  // Password visibility toggle
  if ($("btn-toggle-password")) {
    $("btn-toggle-password").addEventListener("click", () => {
      const inp = $("password");
      const btn = $("btn-toggle-password");
      if (inp.type === "password") {
        inp.type = "text";
        btn.textContent = "🙈️";
        btn.title = "Masquer le mot de passe";
        btn.setAttribute("aria-pressed", "true");
      } else {
        inp.type = "password";
        btn.textContent = "👁️";
        btn.title = "Afficher le mot de passe";
        btn.setAttribute("aria-pressed", "false");
      }
    });
  }

  // Forgot password flow
  if ($("link-forgot-password")) {
    $("link-forgot-password").addEventListener("click", e => {
      e.preventDefault();
      $("form-login").style.display = "none";
      $("forgot-section").style.display = "";
      const emailVal = $("email").value.trim();
      if (emailVal && $("forgot-email")) $("forgot-email").value = emailVal;
      const msgEl = $("forgot-msg");
      if (msgEl) msgEl.style.display = "none";
    });
  }
  if ($("link-back-login")) {
    $("link-back-login").addEventListener("click", e => {
      e.preventDefault();
      $("forgot-section").style.display = "none";
      $("form-login").style.display = "";
    });
  }
  if ($("btn-forgot-submit")) {
    $("btn-forgot-submit").addEventListener("click", async () => {
      const email = ($("forgot-email").value || "").trim();
      const msgEl = $("forgot-msg");
      const btn = $("btn-forgot-submit");
      if (!email) {
        msgEl.textContent = "Entrez votre adresse email.";
        msgEl.style.color = "";
        msgEl.style.background = "";
        msgEl.style.borderColor = "";
        msgEl.style.display = "";
        return;
      }
      btn.disabled = true;
      btn.textContent = "Envoi en cours…";
      msgEl.style.display = "none";
      try {
        await fetch(`${API}/auth/forgot-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        });
        msgEl.textContent = "Si cet email est enregistré, un lien de réinitialisation vous a été envoyé.";
        msgEl.style.color = "var(--success)";
        msgEl.style.background = "rgba(16,185,129,0.08)";
        msgEl.style.borderColor = "rgba(16,185,129,0.2)";
        msgEl.style.display = "";
      } catch (_e) {
        msgEl.textContent = "Erreur réseau. Veuillez réessayer.";
        msgEl.style.color = "";
        msgEl.style.background = "";
        msgEl.style.borderColor = "";
        msgEl.style.display = "";
      } finally {
        btn.disabled = false;
        btn.textContent = "Envoyer le lien";
      }
    });
  }

  // Reset password flow (from ?reset_token=... URL)
  const urlParams = new URLSearchParams(window.location.search);
  const resetToken = urlParams.get("reset_token");
  if (resetToken && $("reset-section") && $("form-login")) {
    $("form-login").style.display = "none";
    $("forgot-section").style.display = "none";
    $("reset-section").style.display = "";
  }
  if ($("btn-toggle-reset-password")) {
    $("btn-toggle-reset-password").addEventListener("click", () => {
      const inp = $("reset-password-new");
      const btn = $("btn-toggle-reset-password");
      if (inp.type === "password") {
        inp.type = "text";
        btn.textContent = "🙈️";
        btn.title = "Masquer le mot de passe";
        btn.setAttribute("aria-pressed", "true");
      } else {
        inp.type = "password";
        btn.textContent = "👁️";
        btn.title = "Afficher le mot de passe";
        btn.setAttribute("aria-pressed", "false");
      }
    });
  }
  if ($("btn-reset-submit")) {
    $("btn-reset-submit").addEventListener("click", async () => {
      const token = resetToken || "";
      const newPassword = ($("reset-password-new").value || "").trim();
      const msgEl = $("reset-msg");
      const btn = $("btn-reset-submit");
      if (!newPassword || newPassword.length < 8) {
        msgEl.textContent = "Le mot de passe doit contenir au moins 8 caractères.";
        msgEl.style.display = "";
        return;
      }
      btn.disabled = true;
      btn.textContent = "Enregistrement…";
      msgEl.style.display = "none";
      try {
        const resp = await fetch(`${API}/auth/reset-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, new_password: newPassword }),
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data.detail || "Token invalide ou expiré.");
        }
        msgEl.textContent = "Mot de passe mis à jour. Redirection…";
        msgEl.style.color = "var(--success)";
        msgEl.style.background = "rgba(16,185,129,0.08)";
        msgEl.style.borderColor = "rgba(16,185,129,0.2)";
        msgEl.style.display = "";
        setTimeout(() => {
          window.location.href = "/ui";
        }, 1500);
      } catch (e) {
        msgEl.textContent = e.message || "Erreur. Veuillez réessayer.";
        msgEl.style.color = "";
        msgEl.style.background = "";
        msgEl.style.borderColor = "";
        msgEl.style.display = "";
      } finally {
        btn.disabled = false;
        btn.textContent = "Enregistrer le mot de passe";
      }
    });
  }

  // Login form
  $("form-login").addEventListener("submit", async e => {
    e.preventDefault();
    const btn = $("btn-login");
    const errEl = $("auth-error");
    btn.disabled = true;
    $("btn-login-text").textContent = "Connexion…";
    errEl.style.display = "none";
    try {
      const email = $("email").value;
      const data = await login(email, $("password").value);
      token = data.access_token;
      refreshToken = data.refresh_token || "";
      sessionStorage.setItem("confidoc_token", token);
      sessionStorage.setItem("confidoc_refresh_token", refreshToken);
      scheduleTokenRefresh();
      await initApp(data.email || email);
    } catch (err) {
      console.error("login error:", err);
      errEl.textContent = err.message;
      errEl.style.display = "";
    } finally {
      btn.disabled = false;
      $("btn-login-text").textContent = "Se connecter";
    }
  });

  $("btn-logout").addEventListener("click", logout);

  // Dashboard
  if ($("btn-dashboard")) $("btn-dashboard").addEventListener("click", showDashboard);
  if ($("btn-home")) $("btn-home").addEventListener("click", goHome);
  if ($("btn-dash-upload")) $("btn-dash-upload").addEventListener("click", () => setStep(1));
  if ($("btn-dash-list")) {
    $("btn-dash-list").addEventListener("click", () => {
      const sidebar = document.querySelector(".sidebar");
      if (!sidebar) return;
      const isMobile = window.innerWidth <= 768;
      if (isMobile) {
        // Ouvrir le drawer sur mobile/tablette avec backdrop
        sidebar.classList.add("open");
        const backdrop = $("sidebar-backdrop");
        if (backdrop) backdrop.classList.add("visible");
      } else {
        // Sur desktop, scroll + highlight temporaire pour guider l'utilisateur
        sidebar.scrollIntoView({ behavior: "smooth", inline: "start" });
        sidebar.animate([
          { boxShadow: "inset 0 0 0 0 rgba(124,116,255,0)" },
          { boxShadow: "inset 4px 0 0 0 rgba(124,116,255,0.6)" },
          { boxShadow: "inset 0 0 0 0 rgba(124,116,255,0)" }
        ], { duration: 700, iterations: 2 });
      }
    });
  }
  if ($("btn-dash-refresh")) $("btn-dash-refresh").addEventListener("click", () => {
    dashboardLoaded = false;
    loadDashboard();
  });
  [1, 2, 3].forEach((n) => {
    const stepBtn = $(`step-${n}`);
    if (stepBtn) stepBtn.addEventListener("click", () => setStep(n));
  });

  // Batch mode
  if ($("btn-batch-toggle")) $("btn-batch-toggle").addEventListener("click", toggleBatchMode);
  if ($("btn-batch-cancel")) $("btn-batch-cancel").addEventListener("click", () => {
    batchMode = false;
    selectedDocIds.clear();
    const btn = $("btn-batch-toggle");
    if (btn) btn.classList.remove("active");
    updateBatchBar();
    renderDocList(lastDocsList);
  });
  if ($("btn-batch-delete")) $("btn-batch-delete").addEventListener("click", batchDeleteSelected);
  if ($("btn-batch-anonymize")) $("btn-batch-anonymize").addEventListener("click", batchAnonymizeSelected);

  // Sidebar: nouveau document
  $("btn-new-doc").addEventListener("click", () => {
    currentDocId = null;
    currentDocName = "";
    currentDocStatus = "";
    currentDocSize = 0;
    document.querySelectorAll(".doc-item").forEach(el => el.classList.remove("selected"));
    updateHeaderContext();
    renderAIDocInsights({});
    updatePipelineTimeline({});
    setStep(1);
  });
  $("filter-client").addEventListener("input", (e) => {
    currentClientFilter = (e.target.value || "").trim();
    saveFilterState();
    loadDocList();
  });
  $("filter-search").addEventListener("input", (e) => {
    currentSearchFilter = (e.target.value || "").trim();
    saveFilterState();
    loadDocList();
  });
  $("filter-status").addEventListener("change", (e) => {
    currentStatusFilter = (e.target.value || "").trim();
    if (currentStatusFilter === "deleted" && !currentIncludeDeleted) {
      currentIncludeDeleted = true;
      $("filter-include-deleted").checked = true;
    }
    saveFilterState();
    loadDocList();
  });
  $("filter-include-deleted").addEventListener("change", async (e) => {
    currentIncludeDeleted = !!e.target.checked;
    saveFilterState();
    await loadClientSuggestions();
    await loadDocList();
  });

  // Upload: drag-and-drop
  const zone = $("upload-zone");
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) enqueueUpload(files);
  });

  // Upload: file input
  const fileInput = $("file-input");
  fileInput.addEventListener("change", () => {
    const files = Array.from(fileInput.files || []);
    if (files.length) enqueueUpload(files);
    fileInput.value = "";
  });

  // Anonymiser
  $("btn-demo")?.addEventListener("click", createDemoDocument);
  $("btn-anonymize").addEventListener("click", anonymize);

  // Valider → discussion IA (avec validation)
  $("btn-validate").addEventListener("click", validate);

  // Discussion directe → step 3 sans re-valider
  $("btn-go-ai").addEventListener("click", goToChat);

  if ($("btn-copy-anonymized")) {
    $("btn-copy-anonymized").addEventListener("click", async () => {
      const txt = $("preview-anon-text")?.textContent || "";
      if (!txt.trim()) return;
      try { await navigator.clipboard.writeText(txt); toast("Texte anonymisé copié", "success"); }
      catch (_e) { toast("Copie impossible", "error"); }
    });
  }

  // Chat IA
  $("btn-send").addEventListener("click", sendMessage);
  $("chat-input").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $("btn-stop-stream").addEventListener("click", stopStream);
  $("btn-copy-answer").addEventListener("click", copyLatestAnswer);

  // Quick actions
  const skipQuickIds = new Set(["btn-report-mode", "btn-copilot-mode", "btn-review-agent", "btn-revue-associe"]);
  document.querySelectorAll(".quick-btn").forEach(btn => {
    if (skipQuickIds.has(btn.id)) return;
    btn.addEventListener("click", () => {
      $("chat-input").value = btn.dataset.q;
      sendMessage();
    });
  });
  // Review agent
  if ($("btn-review-agent")) $("btn-review-agent").addEventListener("click", startReview);
  if ($("btn-revue-associe")) {
    $("btn-revue-associe").addEventListener("click", () => {
      toast("Revue associé : analyse structurée en cours…", "info");
      startReview();
    });
  }
  if ($("cabinet-doc-type")) {
    $("cabinet-doc-type").addEventListener("change", (e) => {
      selectedCabinetDocType = (e.target.value || "generique").trim() || "generique";
    });
  }
  if ($("btn-copilot-compare")) $("btn-copilot-compare").addEventListener("click", runCopilotCompare);
  if ($("btn-review-close")) $("btn-review-close").addEventListener("click", closeReview);
  if ($("btn-review-copy")) $("btn-review-copy").addEventListener("click", copyReviewResult);
  if ($("btn-review-export")) $("btn-review-export").addEventListener("click", exportReviewResult);

  $("btn-report-mode").addEventListener("click", () => {
    reportMode = !reportMode;
    const b = $("btn-report-mode");
    b.dataset.on = reportMode ? "true" : "false";
    b.textContent = reportMode ? "🧱 Mode rapport: ON" : "🧱 Mode rapport: OFF";
    b.classList.toggle("active", reportMode);
    // Show/hide export rapport button
    if ($("btn-export-rapport")) $("btn-export-rapport").style.display = reportMode ? "" : "none";
    toast(reportMode ? "Mode rapport activé — les réponses seront structurées automatiquement" : "Mode rapport désactivé", "info");
  });
  // Export rapport: export latest structured answer as Premium Branded PDF
  if ($("btn-export-rapport")) {
    $("btn-export-rapport").addEventListener("click", () => {
      if (!latestAssistantText.trim()) {
        toast("Aucun rapport à exporter. Posez d'abord une question.", "info");
        return;
      }
      
      const printWindow = window.open("", "_blank");
      if (!printWindow) {
        toast("Veuillez autoriser les pop-ups pour exporter le PDF.", "error");
        return;
      }
      
      // Get the structured HTML content from the chat
      const msgBodies = document.querySelectorAll("#chat-messages .msg-body.structured");
      const lastAnswerHtml = msgBodies.length > 0 ? msgBodies[msgBodies.length - 1].innerHTML : latestAssistantText.replace(/\n/g, '<br>');
      
      const docName = escapeHtml(currentDocName || "Document inconnu");
      const dateStr = new Date().toLocaleDateString("fr-FR");
      
      printWindow.document.write(`
        <!DOCTYPE html>
        <html lang="fr">
        <head>
          <meta charset="UTF-8">
          <title>Rapport d'Analyse IA — ${docName}</title>
          <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
            @page { margin: 20mm; size: A4; }
            body { font-family: 'Inter', sans-serif; color: #1a1a2e; line-height: 1.6; margin: 0; padding: 0; }
            .header { border-bottom: 3px solid #6c5ce7; padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: flex-end; }
            .logo { font-size: 28px; font-weight: 700; color: #6c5ce7; display: flex; align-items: center; gap: 8px; }
            .meta { text-align: right; font-size: 12px; color: #64748b; }
            .meta p { margin: 4px 0; }
            .doc-title { font-size: 18px; font-weight: 600; margin-bottom: 24px; color: #0f172a; padding: 12px; background: #f8fafc; border-radius: 8px; border-left: 4px solid #6c5ce7; }
            
            /* Styles for the structured sections (imported from main css) */
            .ai-section { margin-bottom: 24px; page-break-inside: avoid; }
            .ai-section-title { font-size: 16px; font-weight: 700; color: #6c5ce7; margin-bottom: 12px; display: flex; align-items: center; gap: 6px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }
            .ai-section-risk .ai-section-title { color: #d97706; border-color: #fef08a; }
            .ai-section-action .ai-section-title { color: #059669; border-color: #a7f3d0; }
            .ai-section-data .ai-section-title { color: #0284c7; border-color: #bae6fd; }
            .ai-section ul { padding-left: 20px; margin: 0; }
            .ai-section li { margin-bottom: 8px; color: #334155; }
            
            .footer { margin-top: 50px; font-size: 10px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 15px; }
            
            @media print {
              body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
              .header { border-bottom: 3px solid #6c5ce7 !important; }
            }
          </style>
        </head>
        <body>
          <div class="header">
            <div class="logo">🔒 ConfiDoc</div>
            <div class="meta">
              <p><strong>Date d'analyse :</strong> ${dateStr}</p>
              <p><strong>Modèle d'IA :</strong> Mistral-Large (Contexte Anonymisé)</p>
            </div>
          </div>
          <div class="doc-title">Document analysé : ${docName}</div>
          <div class="content">
            ${lastAnswerHtml}
          </div>
          <div class="footer">
            Rapport confidentiel généré par ConfiDoc. Les données personnelles et financières ont été anonymisées par un système déterministe avant soumission à l'Intelligence Artificielle afin de garantir le strict respect du RGPD et du secret professionnel.
          </div>
          <script>
            window.onload = function() { 
              setTimeout(() => {
                window.print(); 
              }, 300);
            };
          </script>
        </body>
        </html>
      `);
      printWindow.document.close();
      toast("Préparation du PDF Premium...", "success");
    });
  }
  if ($("btn-copilot-mode")) {
    $("btn-copilot-mode").addEventListener("click", () => {
      copilotMode = !copilotMode;
      const b = $("btn-copilot-mode");
      b.dataset.on = copilotMode ? "true" : "false";
      b.textContent = copilotMode ? "🤖 Copilot: ON" : "🤖 Copilot: OFF";
      b.classList.toggle("active", copilotMode);
      if (!copilotMode && $("copilot-insights")) $("copilot-insights").style.display = "none";
      toast(copilotMode ? "Copilot activé" : "Copilot désactivé", "info");
    });
  }

  // Export
  $("btn-export-txt").addEventListener("click", exportText);
  $("btn-export-pdf").addEventListener("click", exportPdf);
  if ($("btn-audit-report")) $("btn-audit-report").addEventListener("click", downloadAuditReport);
  if ($("btn-compliance-report")) $("btn-compliance-report").addEventListener("click", downloadComplianceReport);

  // Logo → dashboard
  if ($("logo-btn")) $("logo-btn").addEventListener("click", showDashboard);

  // Theme
  initTheme();
  if ($("btn-theme")) $("btn-theme").addEventListener("click", toggleTheme);

  // Mobile sidebar toggle
  if ($("btn-sidebar-toggle")) $("btn-sidebar-toggle").addEventListener("click", toggleSidebar);
  if ($("sidebar-backdrop")) $("sidebar-backdrop").addEventListener("click", closeSidebar);

  // Desktop/tablet sidebar collapse
  if ($("btn-sidebar-collapse")) $("btn-sidebar-collapse").addEventListener("click", toggleSidebarCollapse);

  // Sidebar : toujours visible au démarrage — on remet collapsed à false
  localStorage.removeItem("confidoc_sidebar_collapsed");
  const sidebar = document.querySelector(".sidebar");
  if (sidebar) sidebar.classList.remove("collapsed");

  // Bouton d'expansion sidebar (outside sidebar, visible when collapsed)
  if ($("btn-sidebar-expand")) {
    $("btn-sidebar-expand").addEventListener("click", () => {
      const sidebar = document.querySelector(".sidebar");
      if (sidebar) sidebar.classList.remove("collapsed");
      localStorage.setItem("confidoc_sidebar_collapsed", "0");
      const collapseBtn = $("btn-sidebar-collapse");
      if (collapseBtn) { collapseBtn.textContent = "◀"; }
      const expandBtn = $("btn-sidebar-expand");
      if (expandBtn) expandBtn.style.display = "none";
    });
  }

  document.querySelectorAll(".sidebar .doc-item").forEach(el => {
    el.addEventListener("click", closeSidebar);
  });
  document.querySelectorAll(".mobile-nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const nav = btn.dataset.nav;
      if (nav === "dashboard") showDashboard();
      if (nav === "list") document.querySelector(".sidebar")?.classList.add("open");
      if (nav === "upload") setStep(1);
      if (nav === "ai") setStep(3);
    });
  });

  // Notification permission
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }

  // Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js?v=4").catch(() => {});
  }

  // Reprendre la session si token en sessionStorage
  if (token) {
    scheduleTokenRefresh();
    initApp().catch(() => logout());
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeSidebar();
    if ($("confirm-overlay")) $("confirm-overlay").style.display = "none";
    closeReview();
  }
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.shiftKey && e.key.toLowerCase() === "u") {
    e.preventDefault();
    currentDocId = null;
    setStep(1);
    $("upload-client-name")?.focus();
    return;
  }
  if (mod && e.key.toLowerCase() === "k") {
    e.preventDefault();
    $("filter-search")?.focus();
    return;
  }
  if (e.key !== "/") return;
  const target = e.target;
  const isInput = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA");
  if (isInput) return;
  const search = $("filter-search");
  if (!search) return;
  e.preventDefault();
  search.focus();
});
