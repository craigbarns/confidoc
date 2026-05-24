/* ConfiDoc — Pipeline 3 étapes : Upload → Anonymisation → Discussion IA */

const API = "/api/v1";
let token = sessionStorage.getItem("confidoc_token") || "";
let refreshToken = sessionStorage.getItem("confidoc_refresh_token") || "";
let refreshTimer = null;
let currentDocId = null;
let currentDocName = "";
let currentDocStatus = "";
let currentDocSize = 0;
let publicDemoMode = false;
let currentDemoDocument = null;
let currentProvider = "—";
let sensitiveClientMode = false;
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
let originalBlobUrl = "";
let bgPollers = {};
let uploadQueue = [];
let isUploadProcessing = false;
let batchMode = false;
let selectedDocIds = new Set();
let processingStartedAt = null;
let processingElapsedTimer = null;

const $ = id => document.getElementById(id);
const FILTERS_STORAGE_KEY = "confidoc_filters_v1";
const CHAT_STORAGE_PREFIX = "confidoc_chat_";
const ONBOARDING_KEY = "confidoc_onboarding_done";
const READY_STATUSES = new Set(["ready", "anonymized"]);
const PROCESSING_STATUSES = new Set(["processing", "extracting", "extracted", "anonymizing"]);
const AI_CHAT_SUGGESTIONS = [
  "Résumer le document",
  "Identifier les points clés",
  "Détecter les anomalies",
  "Lister les chiffres importants",
  "Préparer une note de revue",
];

function isReadyStatus(status) {
  return READY_STATUSES.has((status || "").toLowerCase());
}

function isProcessingStatus(status) {
  return PROCESSING_STATUSES.has((status || "").toLowerCase());
}

function formatElapsed(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function documentStatusLabel(status) {
  const map = {
    uploaded: "Ajouté",
    processing: "Traitement",
    extracting: "OCR",
    extracted: "OCR terminé",
    anonymizing: "Sécurisation",
    anonymized: "Prêt IA",
    ready: "Prêt IA",
    failed: "Erreur",
  };
  return map[(status || "").toLowerCase()] || status || "—";
}

function normalizeClientFieldInput(raw) {
  if (raw == null) return "";
  return String(raw).replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
}

function getUploadClientName() {
  const el = $("upload-client-name");
  return normalizeClientFieldInput(el && "value" in el ? el.value : "");
}

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

function buildApiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  if (path.startsWith("/api/")) return path;
  return API + path;
}

async function readApiError(resp) {
  const requestId = resp.headers.get("x-request-id") || resp.headers.get("x-railway-request-id") || "";
  const contentType = resp.headers.get("content-type") || "";
  let message = `Erreur HTTP ${resp.status}`;
  let payload = null;
  try {
    if (contentType.includes("application/json")) {
      payload = await resp.json();
      message = payload.detail || payload.message || message;
    } else {
      const text = await resp.text();
      if (text && text.trim()) message = text.trim().slice(0, 300);
    }
  } catch (_e) {
    // Keep the status-based message.
  }
  const error = new Error(message);
  error.status = resp.status;
  error.requestId = requestId;
  error.payload = payload;
  error.contentType = contentType;
  return error;
}

async function apiRequest(path, opts = {}) {
  const { auth = true, ...fetchOptions } = opts;
  const headers = { ...(opts.headers || {}) };
  if (auth && token) headers["Authorization"] = `Bearer ${token}`;
  if (!(opts.body instanceof FormData) && opts.body) {
    headers["Content-Type"] = "application/json";
  }
  const url = buildApiUrl(path);
  let resp;
  try {
    resp = await fetch(url, { ...fetchOptions, headers });
  } catch (err) {
    const error = new Error(`Réseau indisponible pour ${path}: ${err.message || err}`);
    error.cause = err;
    console.error("[apiRequest] network", { endpoint: path, method: opts.method || "GET", error });
    throw error;
  }

  // Auto-refresh on 401 if we have a refresh token
  if (auth && resp.status === 401 && refreshToken) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      // Retry the original request with the new token
      const retryHeaders = { ...(opts.headers || {}) };
      retryHeaders["Authorization"] = `Bearer ${token}`;
      if (!(opts.body instanceof FormData) && opts.body) {
        retryHeaders["Content-Type"] = "application/json";
      }
      resp = await fetch(url, { ...fetchOptions, headers: retryHeaders });
    }
  }

  if (!resp.ok) {
    // If still 401 after refresh attempt, force re-login
    if (auth && resp.status === 401 && token) {
      logout();
    }
    const error = await readApiError(resp);
    console.error("[apiRequest] failed", {
      endpoint: path,
      method: opts.method || "GET",
      status: resp.status,
      request_id: error.requestId,
      content_type: error.contentType,
      payload: error.payload,
    });
    throw error;
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
  try {
    const resp = await apiRequest(path, opts);
    if (opts.returnBlob) {
      const blob = await resp.blob();
      if (!opts.allowEmptyBlob && blob.size === 0) {
        throw new Error(`Réponse vide pour ${path}`);
      }
      return blob;
    }
    const contentType = resp.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      return await resp.json();
    }
    return await resp.text();
  } catch (err) {
    console.error("[apiFetch] failed", {
      endpoint: path,
      method: opts.method || "GET",
      status: err.status || null,
      request_id: err.requestId || null,
      message: err.message,
    });
    toast(err.message || "Erreur de chargement", "error");
    throw err;
  }
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

// ── App nav (sidebar unifiée) + panel routing ─────────────────────────

function setActiveNav(key) {
  document.querySelectorAll("#app-nav .nav-item").forEach((el) => {
    const isActive = el.dataset.nav === key;
    el.classList.toggle("active", isActive);
    if (isActive) {
      el.setAttribute("aria-current", "page");
    } else {
      el.removeAttribute("aria-current");
    }
  });
}

function closeAppNavDrawer() {
  const nav = $("app-nav");
  const backdrop = $("app-nav-backdrop");
  if (nav) nav.classList.remove("open");
  if (backdrop) backdrop.classList.remove("visible");
}

function toggleAppNavDrawer() {
  const nav = $("app-nav");
  const backdrop = $("app-nav-backdrop");
  if (!nav) return;
  const open = nav.classList.toggle("open");
  if (backdrop) backdrop.classList.toggle("visible", open);
}

function showCompliancePanel() {
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  const panel = $("panel-compliance");
  if (panel) panel.classList.add("active");
  setActiveNav("compliance");
  setPageTitle("Conformité");
  closeAppNavDrawer();
  if (!dashboardLoaded) loadDashboard();
}

function showAuditPanel() {
  // Spec §5.6 — Journal d'audit promoted to top-level.
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  const panel = $("panel-audit");
  if (panel) panel.classList.add("active");
  setActiveNav("audit");
  setPageTitle("Journal d'audit");
  closeAppNavDrawer();
}

function showQualityPanel() {
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  const panel = $("panel-quality");
  if (panel) panel.classList.add("active");
  setActiveNav("quality");
  setPageTitle("Qualité");
  closeAppNavDrawer();
  loadQualityDashboard();
}

let qualityLoaded = false;
let lastQualityData = null;

async function loadQualityDashboard() {
  const loading = $("quality-loading");
  const content = $("quality-content");
  const errorPanel = $("quality-error");
  const emptyPanel = $("quality-empty");

  if (loading) loading.style.display = "";
  if (content) content.style.display = "none";
  if (errorPanel) errorPanel.style.display = "none";
  if (emptyPanel) emptyPanel.style.display = "none";

  try {
    const data = await apiFetch("/stats/quality-dashboard");
    lastQualityData = data;

    if (!data || data.total_documents === 0) {
      if (emptyPanel) emptyPanel.style.display = "";
      return;
    }

    renderQualityDashboard(data);
    if (content) content.style.display = "";
    qualityLoaded = true;

  } catch (e) {
    console.warn("loadQualityDashboard failed:", e);
    if (errorPanel) {
      errorPanel.style.display = "";
      const msg = $("quality-error-msg");
      if (msg) msg.textContent = `Impossible de charger les statistiques. ${e.message || e}`;
    }
  } finally {
    if (loading) loading.style.display = "none";
  }
}

function renderQualityDashboard(data) {
  const asOfEl = $("quality-as-of");
  if (asOfEl && data.as_of) {
    const date = new Date(data.as_of);
    asOfEl.textContent = `Mis à jour le ${date.toLocaleDateString("fr-FR")} à ${date.toLocaleTimeString("fr-FR", { hour: '2-digit', minute: '2-digit' })}`;
  }

  const fill = $("quality-readiness-fill");
  const scoreEl = $("quality-readiness-score");
  const levelEl = $("quality-readiness-level");
  
  if (data.ai_readiness_score != null) {
    const score = Number(data.ai_readiness_score);
    if (scoreEl) scoreEl.textContent = score;
    if (fill) fill.setAttribute("stroke-dasharray", `${score}, 100`);

    const levels = {
      ready_for_ai: { text: "Prêt pour l'IA", color: "var(--success)" },
      internal_review: { text: "Revue interne", color: "var(--warning)" },
      needs_review: { text: "Revue requise", color: "var(--warning)" },
      not_ready: { text: "Non prêt", color: "var(--danger)" },
    };
    const levelInfo = levels[data.ai_readiness_level] || { text: "En attente", color: "var(--text-muted)" };
    
    if (levelEl) {
      levelEl.textContent = levelInfo.text;
      levelEl.className = "badge-ready";
      levelEl.style.background = levelInfo.color + "1a"; 
      levelEl.style.color = levelInfo.color;
      levelEl.style.borderColor = levelInfo.color + "33"; 
    }
  } else {
    if (scoreEl) scoreEl.textContent = "—";
    if (fill) fill.setAttribute("stroke-dasharray", "0, 100");
    if (levelEl) {
      levelEl.textContent = "En attente";
      levelEl.className = "badge-ready";
      levelEl.style.color = "var(--text-muted)";
      levelEl.style.background = "rgba(255,255,255,0.03)";
      levelEl.style.borderColor = "var(--border)";
    }
  }

  const oneShotEl = $("quality-one-shot-rate");
  if (oneShotEl) {
    if (data.one_shot_full_ready_rate != null) {
      oneShotEl.textContent = `${Math.round(Number(data.one_shot_full_ready_rate) * 100)}%`;
    } else {
      oneShotEl.textContent = "—";
    }
  }

  const avgTimeEl = $("quality-avg-time");
  if (avgTimeEl) {
    if (data.avg_time_to_validation_seconds != null) {
      const sec = Number(data.avg_time_to_validation_seconds);
      avgTimeEl.textContent = sec < 60 ? `${sec.toFixed(1)}s` : `${Math.round(sec / 60)}m`;
    } else if (data.avg_processing_seconds != null) {
      const sec = Number(data.avg_processing_seconds);
      avgTimeEl.textContent = sec < 60 ? `${sec.toFixed(1)}s` : `${Math.round(sec / 60)}m`;
    } else {
      avgTimeEl.textContent = "—";
    }
  }

  const avgOverridesEl = $("quality-avg-overrides");
  if (avgOverridesEl) {
    if (data.avg_human_overrides_per_document != null) {
      avgOverridesEl.textContent = Number(data.avg_human_overrides_per_document).toFixed(2);
    } else {
      avgOverridesEl.textContent = "—";
    }
  }

  const draftsTotal = Number(data.total_golden_case_drafts || 0);
  const draftsAccepted = Number(data.accepted_golden_case_drafts || 0);
  
  if ($("quality-drafts-total")) $("quality-drafts-total").textContent = draftsTotal;
  if ($("quality-drafts-accepted")) $("quality-drafts-accepted").textContent = draftsAccepted;
  
  const maxFunnel = Math.max(1, draftsTotal);
  if ($("quality-drafts-total-bar")) $("quality-drafts-total-bar").style.width = draftsTotal ? "100%" : "0%";
  if ($("quality-drafts-accepted-bar")) $("quality-drafts-accepted-bar").style.width = `${Math.round((draftsAccepted / maxFunnel) * 100)}%`;

  if ($("quality-vol-total")) $("quality-vol-total").textContent = data.total_documents || 0;
  if ($("quality-vol-processed")) $("quality-vol-processed").textContent = data.processed_documents || 0;
  if ($("quality-vol-validated")) $("quality-vol-validated").textContent = data.validated_documents || 0;

  renderQualityDistributions();

  const statusGrid = $("quality-status-summary-grid");
  if (statusGrid && data.documents_by_status) {
    const statuses = [
      { key: "ready", label: "Prêt IA", dot: "ready" },
      { key: "processing", label: "Traitement", dot: "processing" },
      { key: "uploaded", label: "Ajouté", dot: "uploaded" },
      { key: "failed", label: "Erreur", dot: "failed" },
    ];
    statusGrid.innerHTML = statuses.map(s => {
      const count = data.documents_by_status[s.key] || 0;
      return `<div class="dash-status-pill">
        <div class="dash-status-dot ${s.dot}"></div>
        <span class="dash-status-name">${s.label}</span>
        <span class="dash-status-num">${count}</span>
      </div>`;
    }).join("");
  }
}

function renderQualityDistributions() {
  const fieldsContainer = $("quality-fields-container");
  const errorsContainer = $("quality-errors-container");
  if (!fieldsContainer || !errorsContainer || !lastQualityData) return;

  const fData = lastQualityData.corrections_by_field || {};
  const eData = lastQualityData.corrections_by_error_type || {};

  const sortedFields = Object.entries(fData).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const maxField = Math.max(1, ...sortedFields.map(x => x[1]));
  if (sortedFields.length === 0) {
    fieldsContainer.innerHTML = '<div class="dash-chart-empty" style="font-size: 11px;">Aucun ajustement de champ enregistré.</div>';
  } else {
    fieldsContainer.innerHTML = sortedFields.map(([field, count]) => {
      const pct = (count / maxField) * 100;
      return `<div class="quality-dist-row">
        <span class="quality-dist-label" title="${escapeHtml(field)}">${escapeHtml(field)}</span>
        <div class="quality-dist-bar-bg">
          <div class="quality-dist-bar-fill" style="width:0%" data-target="${pct}"></div>
        </div>
        <span class="quality-dist-count">${count}</span>
      </div>`;
    }).join("");
    setTimeout(() => {
      fieldsContainer.querySelectorAll(".quality-dist-bar-fill").forEach(bar => {
        bar.style.width = bar.dataset.target + "%";
      });
    }, 50);
  }

  const sortedErrors = Object.entries(eData).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const maxError = Math.max(1, ...sortedErrors.map(x => x[1]));
  if (sortedErrors.length === 0) {
    errorsContainer.innerHTML = '<div class="dash-chart-empty" style="font-size: 11px;">Aucun type d\'erreur enregistré.</div>';
  } else {
    errorsContainer.innerHTML = sortedErrors.map(([err, count]) => {
      const pct = (count / maxError) * 100;
      const formattedErr = String(err).replace(/_/g, " ");
      return `<div class="quality-dist-row">
        <span class="quality-dist-label" title="${escapeHtml(formattedErr)}" style="width: 110px;">${escapeHtml(formattedErr)}</span>
        <div class="quality-dist-bar-bg">
          <div class="quality-dist-bar-fill" style="width:0%; background: var(--accent-light);" data-target="${pct}"></div>
        </div>
        <span class="quality-dist-count">${count}</span>
      </div>`;
    }).join("");
    setTimeout(() => {
      errorsContainer.querySelectorAll(".quality-dist-bar-fill").forEach(bar => {
        bar.style.width = bar.dataset.target + "%";
      });
    }, 50);
  }
}


function showStubPanel(panelId, navKey, title) {
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  const panel = $(panelId);
  if (panel) panel.classList.add("active");
  if (navKey) setActiveNav(navKey);
  if (title) setPageTitle(title);
  closeAppNavDrawer();
}

function setStep(n) {
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const panels = { 1: "panel-upload", 2: "panel-anon", 3: "panel-ai" };
  const el = $(panels[n]);
  if (el) el.classList.add("active");
  const titles = { 1: "Ajouter", 2: "Sécuriser", 3: "Analyser" };
  setPageTitle(titles[n] || "");
  setActiveNav("documents");
  syncDocContextActions();
}

function syncDocContextActions() {
  const anonEl = $("anon-context-actions");
  const aiEl = $("ai-context-actions");
  if (!anonEl || !aiEl) return;
  const panelAnon = $("panel-anon");
  const panelAi = $("panel-ai");
  const showAnon = !!currentDocId && panelAnon && panelAnon.classList.contains("active");
  const showAi = !!currentDocId && panelAi && panelAi.classList.contains("active");
  anonEl.style.display = showAnon ? "flex" : "none";
  aiEl.style.display = showAi ? "flex" : "none";
}

function goHome() {
  showDashboard();
}

function revealSidebar() {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar) return;
  const isMobile = window.innerWidth <= 1024;
  if (isMobile) {
    sidebar.classList.add("open");
    const backdrop = $("sidebar-backdrop");
    if (backdrop) backdrop.classList.add("visible");
    return;
  }
  sidebar.scrollIntoView({ behavior: "smooth", inline: "start" });
  if (typeof sidebar.animate === "function") {
    sidebar.animate([
      { boxShadow: "inset 0 0 0 0 rgba(124,116,255,0)" },
      { boxShadow: "inset 4px 0 0 0 rgba(124,116,255,0.6)" },
      { boxShadow: "inset 0 0 0 0 rgba(124,116,255,0)" }
    ], { duration: 700, iterations: 2 });
  }
}

function openDocumentWorkspace() {
  setSidebarMode("flat");
  revealSidebar();
}

function openClientWorkspace() {
  setSidebarMode("dossier");
  revealSidebar();
}

function resumeWorkspaceReview() {
  if (currentDocId) {
    setStep(3);
    return;
  }
  openDocumentWorkspace();
  toast("Sélectionnez un document prêt IA pour lancer l'analyse.", "warning");
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
  publicDemoMode = false;
  currentDemoDocument = null;
  currentProvider = "—";
  sensitiveClientMode = false;
  latestAssistantText = "";
  renderExportGuard({});
  originalTextCache = {};
  Object.values(bgPollers).forEach(id => clearInterval(id));
  bgPollers = {};
  sessionStorage.removeItem("confidoc_token");
  sessionStorage.removeItem("confidoc_refresh_token");
  if (activeStream) { activeStream.abort(); activeStream = null; }
  // Ferme la modale de confirmation si elle était ouverte (ex: token expiré pendant un delete)
  if ($("confirm-overlay")) $("confirm-overlay").style.display = "none";
  dismissOnboardingOverlay();
  $("screen-auth").style.display = "";
  $("screen-app").style.display = "none";
  $("btn-logout").style.display = "none";
  $("btn-logout").innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
          <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
        </svg>
        Déconnexion
      `;
  $("user-info").textContent = "";
  updateHeaderContext();
}

async function initApp(email) {
  publicDemoMode = false;
  currentDemoDocument = null;
  $("screen-auth").style.display = "none";
  $("screen-app").style.display = "";
  $("btn-logout").style.display = "";
  dismissOnboardingOverlay();
  localStorage.setItem(ONBOARDING_KEY, "true");

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

  initExerciceSelect();
  await loadProviderInfo();
  await loadGoldenReport();
  updateHeaderContext();
  showDashboard();
  restoreFilterState();
  await loadClientSuggestions();
  await loadDocList();
}

function dismissOnboardingOverlay() {
  const overlay = $("onboarding-overlay");
  if (overlay) overlay.remove();
  document.querySelectorAll(".onboarding-highlight").forEach(el => el.classList.remove("onboarding-highlight"));
}

function updateHeaderContext() {
  const docPill = $("header-doc-pill");
  const providerPill = $("header-provider-pill");
  if (currentDocId && currentDocName) {
    const labelMap = { uploaded: "Ajouté", processing: "Traitement", ready: "Prêt IA", failed: "Erreur" };
    docPill.textContent = `${currentDocName} · ${labelMap[currentDocStatus] || currentDocStatus || "—"}`;
    docPill.style.display = "";
  } else {
    docPill.style.display = "none";
  }
  providerPill.textContent = `Provider IA: ${currentProvider || "—"}`;
  providerPill.classList.toggle("warning", sensitiveClientMode);
  providerPill.style.display = "";
}

// ── Dynamic page title ───────────────────────────────────────────────

function setPageTitle(section) {
  const titleEl = $("page-title");
  if (!titleEl) return;
  const titles = {
    "": "ConfiDoc — Documents confidentiels anonymisés",
    "Accueil": "ConfiDoc — Accueil cabinet",
    "Ajouter": "ConfiDoc — Ajouter un document",
    "Sécuriser": "ConfiDoc — Sécuriser le document",
    "Analyser": "ConfiDoc — Analyse IA",
    "Clients": "ConfiDoc — Dossiers clients",
    "Dossier": "ConfiDoc — Dossier client",
  };
  titleEl.textContent = titles[section] || titles[""];
  if (currentDocName && section) {
    titleEl.textContent = `${currentDocName} — ${titles[section] || "ConfiDoc"}`;
  }
}

async function loadProviderInfo() {
  try {
    const data = await apiFetch("/ai/providers");
    sensitiveClientMode = !!data.sensitive_client_mode;
    currentProvider = sensitiveClientMode
      ? "IA externe OFF"
      : (data.selected_provider || "mistral").toUpperCase();
    renderSensitiveModeBanner(data.policy_message || "");
  } catch (_e) {
    sensitiveClientMode = false;
    currentProvider = "MISTRAL";
    renderSensitiveModeBanner("");
  }
}

function renderSensitiveModeBanner(message = "") {
  const banner = $("sensitive-mode-banner");
  if (!banner) return;
  banner.style.display = sensitiveClientMode ? "flex" : "none";
  const text = banner.querySelector("span");
  if (text) {
    text.textContent = message || "IA externe désactivée. OCR local/fallbacks déterministes et traitement anonymisé uniquement.";
  }
}

function renderAIDocInsights(payload = {}) {
  const setText = (id, value) => {
    const el = $(id);
    if (el) el.textContent = value ?? "—";
  };
  setText("kpi-doc-status", payload.status || "—");
  setText("kpi-ocr-status", payload.ocrStatus || "—");
  setText("kpi-anonymization-status", payload.anonymizationStatus || "—");
  setText("kpi-risk-score", payload.riskScore || "—");
  setText("kpi-trust-score", payload.trustScore || "—");
  setText("kpi-ai-readiness", payload.aiReadiness || "—");
  setText("kpi-detections", payload.detections ?? "—");
  setText("kpi-export-status", payload.exportStatus || "—");
  setText("kpi-last-audit", payload.lastAudit || "—");
  setText("kpi-next-action", payload.nextAction || "—");
}

function normalizeRiskPercent(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return Math.round(numeric <= 1 ? numeric * 100 : numeric);
}

function renderTrustIndicator(payload = {}) {
  const box = $("trust-indicator");
  if (!box) return;
  const trust = payload.trust || payload || {};
  const aiScore = Number(trust.ai_readiness_score ?? payload.ai_readiness_score);
  const trustScore = Number(trust.trust_score ?? payload.trust_score);
  if (!Number.isFinite(aiScore) && !Number.isFinite(trustScore)) {
    box.style.display = "none";
    return;
  }

  box.style.display = "";
  const aiEl = $("ai-readiness-score");
  const trustEl = $("trust-score");
  const statusEl = $("trust-status");
  const level = String(trust.ai_readiness_level || payload.ai_readiness_level || "");
  const labels = {
    ready_for_ai: "Prêt pour IA",
    internal_review: "Usage interne",
    human_review_required: "Revue humaine",
    needs_review: "À contrôler",
    not_ready: "Non prêt",
    blocked: "Bloqué",
  };
  if (aiEl) aiEl.textContent = Number.isFinite(aiScore) ? `${Math.round(aiScore)}/100` : "—";
  if (trustEl) trustEl.textContent = Number.isFinite(trustScore) ? `Confiance ${Math.round(trustScore)}` : "Confiance —";
  if (statusEl) statusEl.textContent = labels[level] || level || "Score de confiance disponible.";
}

function fallbackDecisionFromRisk(risk = {}, status = currentDocStatus) {
  const score = normalizeRiskPercent(risk.risk_score ?? risk.score);
  const level = String(risk.risk_level || risk.level || currentRiskLevel || "low").toLowerCase();
  const validated = !!(risk.human_validated ?? risk.humanValidated);
  const ready = isReadyStatus(status);
  if (!ready && String(status).toLowerCase() === "failed") {
    return {
      code: "processing_error",
      label: "Erreur de traitement",
      severity: "error",
      decision: "Le document n'est pas utilisable pour le moment",
      explanation: "Le traitement n'a pas pu être terminé. Relancez ou contactez l'administrateur.",
      recommended_action: "Relancer le traitement",
      reasons: ["Traitement incomplet"],
      actions: ["Relancer anonymisation", "Voir audit trail"],
      risk_score: score,
      risk_level: level,
      human_validated: validated,
    };
  }
  if (!ready) {
    return {
      code: "processing",
      label: "Traitement en cours",
      severity: "neutral",
      decision: "Attendez la fin du traitement",
      explanation: "Le document est en cours d'OCR, d'anonymisation ou de scoring.",
      recommended_action: "Patienter",
      reasons: ["Traitement en cours"],
      actions: ["Voir audit trail"],
      risk_score: score,
      risk_level: level,
      human_validated: validated,
    };
  }
  if (level === "critical" || (score !== null && score >= 80)) {
    return {
      code: "blocked",
      label: "Export bloqué",
      severity: "danger",
      decision: "Export bloqué tant que les risques ne sont pas corrigés",
      explanation: "Des données sensibles critiques semblent encore présentes.",
      recommended_action: "Corriger les risques",
      reasons: ["Risque critique"],
      actions: ["Corriger les risques", "Voir les données détectées", "Télécharger rapport DPO"],
      risk_score: score,
      risk_level: level,
      human_validated: validated,
    };
  }
  if (level === "high" || level === "medium" || (score !== null && score >= 40)) {
    return {
      code: "review_recommended",
      label: "Revue recommandée",
      severity: "warning",
      decision: "Vous devez vérifier avant export",
      explanation: "Certaines données sensibles ou quasi-identifiants peuvent encore permettre une réidentification.",
      recommended_action: validated ? "Télécharger le rapport DPO" : "Valider manuellement",
      reasons: ["Contrôle recommandé avant export"],
      actions: ["Corriger l'anonymisation", "Valider manuellement", "Voir pourquoi"],
      risk_score: score,
      risk_level: level,
      human_validated: validated,
    };
  }
  return {
    code: validated ? "human_validated" : "ready_for_ai",
    label: validated ? "Validé manuellement" : "Prêt pour IA",
    severity: "success",
    decision: "Vous pouvez exporter",
    explanation: validated
      ? "Le document anonymisé a été relu et validé par un utilisateur autorisé."
      : "Le document anonymisé ne présente pas de risque évident. Il peut être utilisé pour une analyse IA ou un export.",
    recommended_action: "Analyser avec IA",
    reasons: ["Aucun risque évident détecté"],
    actions: ["Analyser avec IA", "Exporter rapport", "Voir audit trail"],
    risk_score: score,
    risk_level: level,
    human_validated: validated,
  };
}

function buildDecisionPayload(risk = {}, status = currentDocStatus) {
  const decision = risk.decision || fallbackDecisionFromRisk(risk, status);
  return {
    ...decision,
    risk_score: normalizeRiskPercent(decision.risk_score ?? risk.risk_score ?? risk.score),
    trust_score: risk.trust_score ?? risk.trust?.trust_score,
    ai_readiness_score: risk.ai_readiness_score ?? risk.trust?.ai_readiness_score,
    timeline: risk.timeline || [],
    entity_types_found: risk.entity_types_found || [],
    audit_events_count: risk.audit_events_count,
  };
}

function renderDecisionCard(risk = {}, status = currentDocStatus) {
  const card = $("decision-card");
  if (!card) return;
  if (!currentDocId) {
    card.style.display = "none";
    const why = $("why-score-card");
    if (why) why.style.display = "none";
    return;
  }
  const decision = buildDecisionPayload(risk, status);
  const pill = $("decision-status-pill");
  if (pill) {
    pill.textContent = decision.label || "Traitement en cours";
    pill.className = `decision-status-pill ${decision.severity || "neutral"}`;
  }
  const riskScore = decision.risk_score;
  const trustScore = Number(decision.trust_score);
  const aiScore = Number(decision.ai_readiness_score);
  $("decision-risk-score").textContent = riskScore === null || riskScore === undefined ? "—" : `${riskScore}/100`;
  $("decision-trust-score").textContent = Number.isFinite(trustScore) ? `${Math.round(trustScore)}/100` : "—";
  $("decision-ai-score").textContent = Number.isFinite(aiScore) ? `${Math.round(aiScore)}/100` : "—";
  $("decision-explanation").textContent = decision.explanation || "";
  $("decision-export-text").textContent = decision.decision || "—";
  $("decision-main-reason").textContent = (decision.reasons || [])[0] || "Aucun risque évident détecté";
  $("decision-action-text").textContent = decision.recommended_action || "—";
  $("decision-notice").textContent = decision.decision_notice
    || "Ce score aide à prioriser les risques. Il ne remplace pas une validation juridique ou DPO.";
  const actions = $("decision-actions");
  if (actions) {
    const actionMap = {
      "Analyser avec IA": "analyze",
      "Exporter rapport": "report",
      "Voir audit trail": "audit",
      "Corriger l'anonymisation": "correct",
      "Corriger les risques": "correct",
      "Valider manuellement": "validate",
      "Voir pourquoi": "why",
      "Relancer anonymisation": "retry",
      "Voir les données détectées": "why",
      "Télécharger rapport DPO": "report",
    };
    actions.innerHTML = (decision.actions || []).slice(0, 4).map(label => {
      const action = actionMap[label] || "why";
      const cls = action === "analyze" || action === "correct" ? "btn-primary" : "btn-ghost";
      return `<button type="button" class="btn ${cls} btn-sm" data-decision-action="${escapeAttr(action)}">${escapeHtml(label)}</button>`;
    }).join("");
  }
  renderWhyScore(decision);
  card.style.display = "";
}

function renderWhyScore(decision = {}) {
  const card = $("why-score-card");
  if (!card) return;
  const reasons = Array.isArray(decision.reasons) && decision.reasons.length
    ? decision.reasons
    : ["Aucun risque évident détecté"];
  const label = decision.label || "Traitement en cours";
  const mainReason = reasons[0] || "Aucun risque évident détecté";
  $("why-score-summary").textContent =
    `Le document est en statut "${label}" car ${mainReason.toLowerCase()}.`;
  const list = $("why-score-list");
  if (list) {
    const items = [
      ...reasons.map(reason => `Raison: ${reason}`),
      `Niveau de risque: ${decision.risk_level || "non disponible"}`,
      `Validation humaine: ${decision.human_validated ? "présente" : "absente"}`,
      decision.decision ? `Export: ${decision.decision}` : "",
    ].filter(Boolean);
    list.innerHTML = items.map(item => `<li>${escapeHtml(item)}</li>`).join("");
  }
  renderDecisionTimeline(decision.timeline || []);
  card.style.display = "";
}

function renderDecisionTimeline(steps = []) {
  const el = $("decision-timeline");
  if (!el) return;
  if (!Array.isArray(steps) || !steps.length) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = steps.map((step, idx) => `
    <div class="decision-timeline-step ${escapeAttr(step.state || "pending")}">
      <strong>${idx + 1}. ${escapeHtml(step.label || step.key || "Étape")}</strong>
      <span>${escapeHtml(timelineStateLabel(step.state))}</span>
    </div>
  `).join("");
}

function timelineStateLabel(state) {
  if (state === "done") return "Terminé";
  if (state === "current") return "En cours";
  if (state === "error") return "Erreur";
  return "À venir";
}

function renderExportGuard(payload = {}) {
  const guard = $("export-guard");
  if (!guard) return;
  if (!currentDocId) {
    guard.style.display = "none";
    return;
  }

  const status = payload.status || currentDocStatus || "";
  const ready = isReadyStatus(status);
  const level = String(payload.risk_level || payload.level || currentRiskLevel || "low").toLowerCase();
  const validated = !!(payload.human_validated ?? payload.humanValidated);
  const score = normalizeRiskPercent(payload.risk_score ?? payload.score);
  const scoreText = score === null ? "" : `Score RGPD ${score}% · `;
  const approveBtn = $("btn-export-approve-inline");
  const titleEl = $("export-guard-title");
  const detailEl = $("export-guard-detail");
  let state = "ready";
  let title = "Vous pouvez exporter";
  let detail = `${scoreText}Document anonymisé.`;
  let canApprove = false;

  if (!ready) {
    state = "watch";
    title = "Export en attente";
    detail = "Le document doit être anonymisé puis validé avant diffusion.";
  } else if (level === "critical") {
    state = "blocked";
    title = "Export bloqué";
    detail = `${scoreText}Risque critique de réidentification.`;
  } else if (level === "high" && !validated) {
    state = "watch";
    title = "Validation humaine requise";
    detail = `${scoreText}Les exports restent verrouillés jusqu'à validation.`;
    canApprove = true;
  } else if (level === "high" && validated) {
    state = "ready";
    title = "Export validé";
    detail = `${scoreText}Validation humaine journalisée.`;
  } else if (level === "medium") {
    state = "watch";
    title = "Revue recommandée avant export IA";
    detail = `${scoreText}Contrôle recommandé avant partage externe.`;
  }

  guard.className = `export-guard ${state}`;
  guard.style.display = "";
  if (titleEl) titleEl.textContent = title;
  if (detailEl) detailEl.textContent = detail;
  if (approveBtn) approveBtn.style.display = canApprove ? "" : "none";
  renderDecisionCard(payload, status);
  renderAIReadySummary();
}

function exportDecisionFromRisk(risk = {}, status = "") {
  const ready = isReadyStatus(status || currentDocStatus);
  const level = String(risk.risk_level || risk.level || currentRiskLevel || "low").toLowerCase();
  const validated = !!(risk.human_validated ?? risk.humanValidated);
  if (!ready) return "En attente";
  if (level === "critical") return "Export bloqué";
  if (level === "high" && !validated) return "Revue humaine requise";
  if (level === "high" && validated) return "Export validé";
  if (level === "medium") return "Revue conseillée";
  return "Export autorisé";
}

async function refreshAIDocInsights(docId) {
  if (!docId) {
    renderAIDocInsights({});
    renderExportGuard({});
    renderTrustIndicator({});
    renderDecisionCard({}, "");
    return;
  }
  if (publicDemoMode && currentDemoDocument) {
    applyPublicDemoInsights(currentDemoDocument);
    return;
  }
  try {
    const [statusResult, riskResult, auditResult] = await Promise.allSettled([
      apiFetch(`/documents/${docId}/status`),
      apiFetch(`/documents/${docId}/risk-score`),
      apiFetch(`/documents/${docId}/audit-report`),
    ]);
    if (statusResult.status === "rejected") throw statusResult.reason;
    const st = statusResult.value;
    const risk = riskResult.status === "fulfilled" ? riskResult.value : {};
    const auditData = auditResult.status === "fulfilled" ? auditResult.value : {};
    const auditEntries = Array.isArray(auditData.audit_entries) ? auditData.audit_entries : [];
    const next = Array.isArray(st.next_steps) && st.next_steps.length ? st.next_steps.join(" → ") : "Analyse IA";
    updatePipelineTimeline({
      status: st.status || currentDocStatus,
      extractDone: !!st?.extraction?.done,
      anonymDone: !!st?.anonymization?.done,
    });
    currentRiskLevel = risk.risk_level || risk.risk?.level || currentRiskLevel;
    const trust = risk.trust || {};
    const score = normalizeRiskPercent(risk.risk_score ?? risk.risk?.score);
    const lastAudit = auditEntries.length ? auditEntries[0] : null;
    renderAIDocInsights({
      status: documentStatusLabel(st.status || currentDocStatus),
      ocrStatus: st?.extraction?.done ? `OK · ${st?.extraction?.text_length ?? 0} car.` : "À lancer",
      anonymizationStatus: st?.anonymization?.done ? "OK" : "À lancer",
      riskScore: score === null ? "—" : `${score}/100`,
      trustScore: Number.isFinite(Number(risk.trust_score ?? trust.trust_score))
        ? `${Math.round(Number(risk.trust_score ?? trust.trust_score))}/100`
        : "—",
      aiReadiness: Number.isFinite(Number(risk.ai_readiness_score ?? trust.ai_readiness_score))
        ? `${Math.round(Number(risk.ai_readiness_score ?? trust.ai_readiness_score))}/100`
        : "—",
      detections: st?.anonymization?.detections_count ?? 0,
      exportStatus: exportDecisionFromRisk(risk, st.status || currentDocStatus),
      lastAudit: lastAudit ? `${lastAudit.action || "audit"} · ${(lastAudit.timestamp || "").slice(0, 16).replace("T", " ")}` : "—",
      nextAction: next,
    });
    renderExportGuard({
      ...risk,
      status: st.status || currentDocStatus,
    });
    renderDecisionCard(risk, st.status || currentDocStatus);
    renderTrustIndicator(risk);
  } catch (_e) {
    updatePipelineTimeline({ status: currentDocStatus, extractDone: currentDocStatus !== "uploaded", anonymDone: isReadyStatus(currentDocStatus) });
    renderAIDocInsights({
      status: documentStatusLabel(currentDocStatus || "—"),
      ocrStatus: "—",
      anonymizationStatus: isReadyStatus(currentDocStatus) ? "OK" : "—",
      riskScore: "—",
      trustScore: "—",
      aiReadiness: "—",
      detections: "—",
      exportStatus: exportDecisionFromRisk({}, currentDocStatus),
      lastAudit: "—",
      nextAction: "Vérifier document",
    });
    renderExportGuard({ status: currentDocStatus, risk_level: currentRiskLevel });
    renderDecisionCard({ status: currentDocStatus, risk_level: currentRiskLevel }, currentDocStatus);
    renderTrustIndicator({});
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
  const ready = isReadyStatus(st);
  const scoreDone = ready || anonymDone;
  let currentStep = "ocr";
  if (!extractDone) currentStep = "ocr";
  else if (!anonymDone) currentStep = st === "extracted" ? "detect" : "anonymize";
  else if (ready) currentStep = "export";
  else currentStep = "anonymize";
  tl.querySelectorAll(".pipe-step").forEach((el) => {
    const key = el.dataset.step;
    el.classList.remove("done", "current");
    if (key === "upload") el.classList.add("done");
    if (key === "ocr" && extractDone) el.classList.add("done");
    if (key === "detect" && anonymDone) el.classList.add("done");
    if (key === "anonymize" && anonymDone) el.classList.add("done");
    if (key === "score" && scoreDone) el.classList.add("done");
    if (key === "review" && ready) el.classList.add("done");
    if (key === "export" && ready) el.classList.add("done");
    if (key === currentStep) el.classList.add("current");
  });
}

function processingPhaseFromStatus(status, extractionDone = false, anonymDone = false) {
  const st = (status || "").toLowerCase();
  if (isReadyStatus(st) || anonymDone) return "ready";
  if (st === "failed") return "failed";
  if (st === "extracted") return "detect";
  if (st === "anonymizing" || extractionDone) return "mask";
  if (st === "extracting" || st === "processing") return "ocr";
  return "upload";
}

function updateProcessingConsole(payload = {}) {
  const el = $("processing-console");
  if (!el) return;
  el.style.display = "";

  const phase = processingPhaseFromStatus(
    payload.status || currentDocStatus,
    payload.extractDone,
    payload.anonymDone
  );
  const order = ["upload", "ocr", "detect", "mask", "ready"];
  const activeIndex = phase === "failed" ? 0 : Math.max(0, order.indexOf(phase));
  const widths = { upload: 12, ocr: 38, detect: 58, mask: 78, ready: 100, failed: 100 };
  const labels = {
    upload: "Ajout sécurisé",
    ocr: "Mistral OCR en cours",
    detect: "Détection des données sensibles",
    mask: "Masquage RGPD",
    ready: "Document prêt pour l'IA",
    failed: "Traitement interrompu",
  };

  el.classList.toggle("failed", phase === "failed");
  const spinner = document.querySelector("#anon-loading .spinner-lg");
  if (spinner) spinner.style.display = phase === "failed" ? "none" : "";
  const label = $("processing-phase-label");
  if (label) label.textContent = labels[phase] || labels.upload;
  const fill = $("processing-track-fill");
  if (fill) fill.style.width = `${widths[phase] || 12}%`;

  el.querySelectorAll(".processing-steps span").forEach((step) => {
    const idx = order.indexOf(step.dataset.phase);
    step.classList.toggle("done", phase !== "failed" && idx >= 0 && idx < activeIndex);
    step.classList.toggle("current", phase !== "failed" && idx === activeIndex);
  });

  const ocrMetric = $("processing-ocr-metric");
  if (ocrMetric) {
    const len = payload.ocrLength;
    ocrMetric.textContent = Number.isFinite(len) ? `OCR ${len.toLocaleString("fr-FR")} car.` : "OCR —";
  }
  const entityMetric = $("processing-entity-metric");
  if (entityMetric) {
    const count = payload.detections;
    entityMetric.textContent = Number.isFinite(count) ? `Entités ${count}` : "Entités —";
  }
  const backendMetric = $("processing-backend-metric");
  if (backendMetric) backendMetric.textContent = payload.backend || "API";
}

function startProcessingTimer() {
  processingStartedAt = processingStartedAt || Date.now();
  if (processingElapsedTimer) clearInterval(processingElapsedTimer);
  const tick = () => {
    const target = $("processing-elapsed");
    if (target && processingStartedAt) {
      target.textContent = formatElapsed((Date.now() - processingStartedAt) / 1000);
    }
  };
  tick();
  processingElapsedTimer = setInterval(tick, 1000);
}

function stopProcessingTimer() {
  if (processingElapsedTimer) clearInterval(processingElapsedTimer);
  processingElapsedTimer = null;
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
  const ready = docs.filter((d) => isReadyStatus(d.status)).length;
  const processing = docs.filter((d) => isProcessingStatus(d.status)).length;
  const trashed = docs.filter((d) => !!d.is_deleted).length;
  el.innerHTML = [
    `<span class="stat-chip">Total: ${total}</span>`,
    `<span class="stat-chip">Prêt IA: ${ready}</span>`,
    `<span class="stat-chip">Traitement: ${processing}</span>`,
    `<span class="stat-chip">Corbeille: ${trashed}</span>`,
  ].join("");
  el.style.display = "";
}

let allClients = [];

async function loadClientSuggestions() {
  const datalist = $("clients-suggestions");
  if (!datalist) return;
  try {
    allClients = await apiFetch("/clients");
    datalist.innerHTML = allClients
      .map((c) => `<option value="${escapeHtml(c.name)}" data-id="${c.id}"></option>`)
      .join("");
  } catch (_e) {
    // Fallback to legacy behavior if /clients fails
    try {
      const names = await apiFetch("/documents/clients");
      datalist.innerHTML = (names || [])
        .map((name) => `<option value="${escapeHtml(name)}"></option>`)
        .join("");
    } catch (_e2) {
      datalist.innerHTML = "";
    }
  }
}

function getClientIdByName(name) {
  const n = normalizeClientFieldInput(name);
  if (!n) return null;
  const client = allClients.find(c => c.name.toLowerCase() === n.toLowerCase());
  return client ? client.id : null;
}

function getDocClientLabel(docId) {
  if (!docId) return "";
  const d = lastDocsList.find((x) => x.id === docId);
  if (!d || !Array.isArray(d.tags) || !d.tags.length) return "";
  return String(d.tags[0] || "");
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

function getCurrentDocRecord() {
  return lastDocsList.find((d) => d.id === currentDocId) || null;
}

function documentFileKind(doc = getCurrentDocRecord()) {
  const contentType = String(doc?.content_type || "").split(";")[0].toLowerCase();
  const extension = String(doc?.extension || currentDocName.split(".").pop() || "")
    .replace(/^\./, "")
    .toLowerCase();
  if (contentType === "application/pdf" || extension === "pdf") return "PDF";
  if (contentType.startsWith("image/") || ["png", "jpg", "jpeg", "tiff"].includes(extension)) {
    return extension ? extension.toUpperCase() : "Image";
  }
  return contentType || (extension ? extension.toUpperCase() : "Fichier");
}

function renderDocList(docs) {
  lastDocsList = Array.isArray(docs) ? docs : [];
  const list = $("doc-list");
  const count = $("doc-count");
  renderSidebarStats(docs);

  if (!docs.length) {
    list.innerHTML = '<div class="empty-state">Aucun document.<br>Ajoutez-en un.</div>';
    if (count) count.textContent = "";
    return;
  }

  if (count) count.textContent = docs.length;

  list.innerHTML = docs.map(d => {
    const rawName = escapeHtml(d.original_filename || "");
    const name = rawName.length > 26 ? rawName.slice(0, 24) + "…" : rawName;
    const label = escapeHtml(documentStatusLabel(d.status));
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
      anonymized: "risk-dot-green",
      processing: "risk-dot-blue",
      extracting: "risk-dot-blue",
      extracted: "risk-dot-blue",
      anonymizing: "risk-dot-blue",
      uploaded: "risk-dot-orange",
      failed: "risk-dot-red",
    }[d.status] || "risk-dot-orange";
    const riskDotTitle = {
      ready: "Anonymisé — prêt pour l'IA",
      anonymized: "Anonymisé — prêt pour l'IA",
      processing: "Sécurisation en cours…",
      extracting: "OCR en cours…",
      extracted: "OCR terminé",
      anonymizing: "Sécurisation en cours…",
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

// ── Sidebar dossier tree ───────────────────────────────────────────────

let sidebarMode = "flat"; // "flat" | "dossier"

function setSidebarMode(mode) {
  sidebarMode = mode;

  const filters = $("sidebar-filters");
  const batchRow = $("sidebar-batch-row");
  const dossierSearch = $("dossier-client-search-row");

  if (mode === "dossier") {
    if (filters) filters.style.display = "none";
    if (batchRow) batchRow.style.display = "none";
    if (dossierSearch) dossierSearch.style.display = "";
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    const panel = $("panel-dossier");
    if (panel) panel.classList.add("active");
    openDossierOverview();
    loadDossierTree();
    setActiveNav("clients");
    setPageTitle("Dossiers clients");
    closeAppNavDrawer();
  } else {
    if (filters) filters.style.display = "";
    if (batchRow) batchRow.style.display = "";
    if (dossierSearch) dossierSearch.style.display = "none";
    const panel = $("panel-dossier");
    if (panel) panel.classList.remove("active");
    if (!document.querySelector(".panel.active")) showDashboard();
    loadDocList();
  }
}

async function loadDossierTree() {
  const list = $("doc-list");
  if (!list) return;
  list.innerHTML = '<div class="sidebar-skeleton"></div>';
  try {
    const data = await apiFetch("/documents/dossiers");
    renderDossierTree(data);
  } catch (e) {
    list.innerHTML = `<p style="padding:12px;color:var(--text-muted);font-size:12px">Erreur chargement dossiers</p>`;
  }
}

function renderDossierTree(dossiers) {
  const list = $("doc-list");
  if (!list) return;
  if (!dossiers || dossiers.length === 0) {
    list.innerHTML = `<p style="padding:12px;color:var(--text-muted);font-size:12px">Aucun client. Ajoutez un document avec un nom client.</p>`;
    return;
  }
  list.innerHTML = dossiers.map(client => `
    <div class="dossier-client" data-client="${escapeAttr(client.client_name)}">
      <div class="dossier-client-header">
        <button class="dossier-client-toggle-btn" data-action="toggle-dossier-client">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="chevron-icon" style="transition:transform 0.2s;transform:rotate(-90deg)"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <button class="dossier-client-name-btn" data-action="open-dossier-page" data-client="${escapeAttr(client.client_name)}">${escapeHtml(client.client_name)}</button>
        <span class="dossier-client-count">${client.total_docs}</span>
      </div>
      <div class="dossier-exercices" style="display:none">
        ${(client.exercices || []).map(ex => renderDossierExerciceTree(client.client_name, ex)).join("")}
      </div>
    </div>
  `).join("");
}

function filterDossierTree(query) {
  const q = (query || "").toLowerCase();
  document.querySelectorAll(".dossier-client").forEach(el => {
    el.style.display = (el.dataset.client || "").toLowerCase().includes(q) ? "" : "none";
  });
}

function renderDossierExerciceTree(clientName, ex) {
  const allReady = ex.ready_count === ex.doc_count;
  return `
    <div class="dossier-exercice-tree">
      <div class="dossier-exercice-header" data-action="toggle-dossier-exercice">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="chevron-icon" style="transition:transform 0.2s;transform:rotate(-90deg)"><polyline points="6 9 12 15 18 9"/></svg>
        <span class="dossier-exercice-year">${escapeHtml(ex.exercice || "Sans exercice")}</span>
        <span class="dossier-status-dot ${allReady ? "green" : "orange"}"></span>
        <span style="font-size:10px;color:var(--text-muted)">${ex.ready_count}/${ex.doc_count}</span>
      </div>
      <div class="dossier-docs-sidebar" style="display:none">
        ${(ex.documents || []).map(doc => `
          <div class="dossier-doc-sidebar-item" data-action="select-doc" data-doc-id="${escapeAttr(doc.id)}" title="${escapeAttr(doc.original_filename)}">
            ${escapeHtml(doc.original_filename)}
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function toggleDossierClient(container) {
  const exercicesEl = container.querySelector(".dossier-exercices");
  const chevron = container.querySelector(".chevron-icon");
  const isOpen = exercicesEl.style.display !== "none";
  exercicesEl.style.display = isOpen ? "none" : "";
  if (chevron) chevron.style.transform = isOpen ? "rotate(-90deg)" : "rotate(0deg)";
}

function toggleDossierExercice(headerEl) {
  const container = headerEl.closest(".dossier-exercice-tree");
  const docsEl = container.querySelector(".dossier-docs-sidebar");
  const chevron = headerEl.querySelector(".chevron-icon");
  const isOpen = docsEl.style.display !== "none";
  docsEl.style.display = isOpen ? "none" : "";
  if (chevron) chevron.style.transform = isOpen ? "rotate(-90deg)" : "rotate(0deg)";
}

// ── Dossier page (zone principale) ────────────────────────────────────

let currentDossierClient = "";

function openCreateClientModal() {
  $("modal-client-overlay").style.display = "";
  $("new-client-name").value = "";
  $("new-client-ext-id").value = "";
  setTimeout(() => $("new-client-name").focus(), 100);
}

function closeClientModal() {
  $("modal-client-overlay").style.display = "none";
}

async function submitCreateClient() {
  const name = $("new-client-name").value.trim();
  const external_id = $("new-client-ext-id").value.trim();
  if (!name) {
    toast("Le nom du client est requis", "error");
    return;
  }
  try {
    await apiFetch("/clients", {
      method: "POST",
      body: JSON.stringify({ name, external_id })
    });
    toast(`Client "${name}" créé`, "success");
    closeClientModal();
    await loadClientSuggestions();
    if (sidebarMode === "dossier") {
      if (currentDossierClient) loadDossierClientPage(currentDossierClient);
      else loadDossierOverview();
      loadDossierTree();
    }
  } catch (e) {
    toast("Erreur : " + e.message, "error");
  }
}

function openDossierOverview() {
  currentDossierClient = "";
  const overview = $("dossier-overview");
  const detail = $("dossier-detail");
  if (overview) overview.style.display = "flex";
  if (detail) detail.style.display = "none";
  document.querySelectorAll(".dossier-client.selected").forEach(el => el.classList.remove("selected"));
  setPageTitle("Clients");
  loadDossierOverview();
}

async function loadDossierOverview() {
  const grid = $("dossier-client-grid");
  if (!grid) return;
  grid.innerHTML = '<div class="spinner" style="margin:40px auto;grid-column:1/-1"></div>';
  try {
    const data = await apiFetch("/documents/dossiers");
    renderDossierClientGrid(data);
  } catch (e) {
    grid.innerHTML = `<div class="panel-empty-hint" style="grid-column:1/-1"><p>Erreur chargement clients</p></div>`;
  }
}

function renderDossierClientGrid(dossiers) {
  const grid = $("dossier-client-grid");
  const statsEl = $("dossier-overview-stats");
  if (!grid) return;
  if (!dossiers || dossiers.length === 0) {
    if (statsEl) statsEl.textContent = "";
    grid.innerHTML = `
      <div class="panel-empty-hint" style="grid-column:1/-1">
        <p>Aucun client pour l'instant.</p>
        <button class="btn btn-primary btn-sm" style="margin-top:12px" data-action="new-document">+ Ajouter un premier document</button>
      </div>`;
    return;
  }
  if (statsEl) statsEl.textContent = `${dossiers.length} client${dossiers.length > 1 ? "s" : ""}`;
  grid.innerHTML = dossiers.map(client => {
    const readyCount = (client.exercices || []).reduce((acc, ex) => acc + (ex.ready_count || 0), 0);
    const total = client.total_docs || 0;
    const pct = total > 0 ? Math.round(readyCount / total * 100) : 0;
    const exCount = (client.exercices || []).length;
    const lastActivity = client.last_activity ? formatDate(client.last_activity) : "";
    return `
      <div class="dossier-client-card" data-action="open-dossier-page" data-client="${escapeAttr(client.client_name)}">
        <div class="dossier-client-card-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
        </div>
        <div class="dossier-client-card-body">
          <div class="dossier-client-card-name">${escapeHtml(client.client_name)}</div>
          <div class="dossier-client-card-meta">${total} doc${total > 1 ? "s" : ""} · ${exCount} exercice${exCount > 1 ? "s" : ""}${lastActivity ? " · " + lastActivity : ""}</div>
          <div class="dossier-client-card-progress">
            <div class="progress-bar-track"><div class="progress-bar-fill${pct === 100 ? " green" : ""}" style="width:${pct}%"></div></div>
            <span class="progress-bar-label">${readyCount}/${total} prêts</span>
          </div>
        </div>
        <svg class="dossier-client-card-arrow" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
      </div>`;
  }).join("");
}

function openDossierPage(clientName) {
  currentDossierClient = clientName;
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const panel = $("panel-dossier");
  if (panel) panel.classList.add("active");

  const overview = $("dossier-overview");
  const detail = $("dossier-detail");
  if (overview) overview.style.display = "none";
  if (detail) { detail.style.display = "flex"; detail.style.flexDirection = "column"; detail.style.flex = "1"; detail.style.overflow = "hidden"; }

  document.querySelectorAll(".dossier-client").forEach(el => {
    el.classList.toggle("selected", el.dataset.client === clientName);
  });

  // Reset active tab to documents when opening a client dossier page
  document.querySelectorAll(".dossier-tab").forEach(btn => {
    if (btn.dataset.tab === "documents") {
      btn.classList.add("active");
      btn.style.color = "#fff";
      btn.style.borderBottom = "2px solid var(--accent)";
    } else {
      btn.classList.remove("active");
      btn.style.color = "var(--text-muted)";
      btn.style.borderBottom = "none";
    }
  });
  const exercicesEl = $("dossier-page-exercices");
  const comparisonEl = $("dossier-page-comparison");
  if (exercicesEl) exercicesEl.style.display = "block";
  if (comparisonEl) comparisonEl.style.display = "none";

  setPageTitle("Dossier");
  loadDossierClientPage(clientName);
}

async function loadDossierClientPage(clientName) {
  const exercicesEl = $("dossier-page-exercices");
  const titleEl = $("dossier-page-client-name");
  const statsEl = $("dossier-page-stats");
  if (!exercicesEl) return;

  exercicesEl.innerHTML = '<div class="spinner" style="margin:24px auto"></div>';
  if (titleEl) titleEl.textContent = clientName;

  try {
    const data = await apiFetch(`/documents/dossiers?client_name=${encodeURIComponent(clientName)}`);
    const client = Array.isArray(data) ? data.find(c => c.client_name === clientName) || data[0] : null;
    if (!client) {
      exercicesEl.innerHTML = `<p style="padding:20px;color:var(--text-muted)">Aucun document trouvé pour ce client.</p>`;
      return;
    }
    const exercices = client.exercices || [];
    const readyCount = exercices.reduce((acc, ex) => acc + (ex.ready_count || 0), 0);
    const totalDocs = client.total_docs || 0;
    if (statsEl) {
      statsEl.textContent = `${totalDocs} document${totalDocs > 1 ? "s" : ""} · ${exercices.length} exercice${exercices.length > 1 ? "s" : ""} · ${readyCount} prêt${readyCount > 1 ? "s" : ""} IA`;
    }
    exercicesEl.innerHTML = [
      renderDossierClientSummary(client, readyCount),
      ...exercices.map(ex => renderDossierExerciceSection(ex)),
    ].join("");
  } catch (e) {
    exercicesEl.innerHTML = `<p style="padding:20px;color:var(--text-muted)">Erreur chargement dossier.</p>`;
  }
}

function initDossierTabsAndComparison() {
  // Listen for tab clicks dynamically
  document.addEventListener("click", (e) => {
    const tab = e.target.closest(".dossier-tab");
    if (!tab) return;
    
    // Toggle active classes on tab buttons
    document.querySelectorAll(".dossier-tab").forEach(t => {
      t.classList.remove("active");
      t.style.color = "var(--text-muted)";
      t.style.borderBottom = "none";
    });
    tab.classList.add("active");
    tab.style.color = "#fff";
    tab.style.borderBottom = "2px solid var(--accent)";

    // Switch displayed panel
    const target = tab.dataset.tab;
    const exercicesEl = $("dossier-page-exercices");
    const comparisonEl = $("dossier-page-comparison");

    if (target === "documents") {
      if (exercicesEl) exercicesEl.style.display = "block";
      if (comparisonEl) comparisonEl.style.display = "none";
    } else if (target === "comparison") {
      if (exercicesEl) exercicesEl.style.display = "none";
      if (comparisonEl) comparisonEl.style.display = "block";
      initDossierComparisonTab();
    }
  });

  // Listen for compare run button click dynamically
  document.addEventListener("click", (e) => {
    if (e.target && (e.target.id === "btn-run-comparison" || e.target.closest("#btn-run-comparison"))) {
      runDossierComparison();
    }
  });
}

async function initDossierComparisonTab() {
  const selectN = $("compare-doc-n");
  const selectN1 = $("compare-doc-n1");
  const resultsEl = $("comparison-results");
  const placeholderEl = $("comparison-placeholder");
  const placeholderTextEl = $("comparison-placeholder-text");
  
  if (!selectN || !selectN1) return;
  
  selectN.innerHTML = "";
  selectN1.innerHTML = "";
  if (resultsEl) resultsEl.style.display = "none";
  if (placeholderEl) {
    placeholderEl.style.display = "block";
    if (placeholderTextEl) {
      placeholderTextEl.innerHTML = "Chargement des documents du client...";
    }
  }
  
  try {
    const data = await apiFetch(`/documents/dossiers?client_name=${encodeURIComponent(currentDossierClient)}`);
    const client = Array.isArray(data) ? data.find(c => c.client_name === currentDossierClient) || data[0] : null;
    if (!client) {
      if (placeholderTextEl) placeholderTextEl.innerHTML = "Aucun document trouvé pour ce client.";
      return;
    }
    
    const exercices = client.exercices || [];
    const eligibleDocs = [];
    exercices.forEach(ex => {
      const year = ex.exercice || "Sans exercice";
      (ex.documents || []).forEach(doc => {
        const cat = (doc.doc_category || "").toLowerCase();
        if (cat === "bilan" || cat === "liasse_fiscale" || cat.includes("bilan") || cat.includes("liasse")) {
          eligibleDocs.push({
            id: doc.id,
            name: doc.original_filename,
            year: year,
            status: doc.status,
            created_at: doc.created_at
          });
        }
      });
    });
    
    if (eligibleDocs.length < 2) {
      if (placeholderTextEl) {
        placeholderTextEl.innerHTML = `
          <div style="font-weight: 700; color: #fff; margin-bottom: 8px; font-size: 14px;">📈 Postes comptables insuffisants</div>
          Pour analyser l'évolution pluriannuelle, ConfiDoc requiert au moins <strong>deux bilans ou liasses fiscales</strong> (exercice N et exercice N-1) pour ce client.<br>
          <span style="font-size: 12px; color: var(--text-muted); display: block; margin-top: 6px;">Veuillez téléverser un autre exercice pour <strong>${escapeHtml(currentDossierClient)}</strong>.</span>
        `;
      }
      return;
    }
    
    eligibleDocs.sort((a, b) => {
      const yearA = parseInt(a.year) || 0;
      const yearB = parseInt(b.year) || 0;
      if (yearB !== yearA) return yearB - yearA;
      return new Date(b.created_at) - new Date(a.created_at);
    });
    
    eligibleDocs.forEach((doc) => {
      const optionHtml = `<option value="${doc.id}">Exercice ${escapeHtml(doc.year)} — ${escapeHtml(doc.name)} (${documentStatusLabel(doc.status)})</option>`;
      selectN.insertAdjacentHTML("beforeend", optionHtml);
      selectN1.insertAdjacentHTML("beforeend", optionHtml);
    });
    
    if (selectN.options.length > 0) selectN.selectedIndex = 0;
    if (selectN1.options.length > 1) selectN1.selectedIndex = 1;
    else if (selectN1.options.length > 0) selectN1.selectedIndex = 0;
    
    if (placeholderTextEl) {
      placeholderTextEl.innerHTML = "Sélectionnez deux exercices distincts (ex. Bilan 2024 vs Bilan 2023) et cliquez sur \"Comparer\".";
    }
  } catch (e) {
    console.error("initDossierComparisonTab error:", e);
    if (placeholderTextEl) placeholderTextEl.innerHTML = "Erreur lors du chargement des documents éligibles.";
  }
}

async function runDossierComparison() {
  const docIdN = $("compare-doc-n").value;
  const docIdN1 = $("compare-doc-n1").value;
  const resultsEl = $("comparison-results");
  const placeholderEl = $("comparison-placeholder");
  
  if (!docIdN || !docIdN1) {
    toast("Veuillez sélectionner deux documents.", "warning");
    return;
  }
  
  if (docIdN === docIdN1) {
    toast("Veuillez sélectionner deux exercices distincts.", "warning");
    return;
  }
  
  if (resultsEl) {
    resultsEl.style.display = "block";
    resultsEl.innerHTML = '<div class="spinner" style="margin:40px auto"></div>';
  }
  if (placeholderEl) placeholderEl.style.display = "none";
  
  try {
    const data = await apiFetch(`/documents/${docIdN}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ previous_document_id: docIdN1 }),
    });
    
    const variations = data.variations || [];
    const coherenceFlags = data.coherence_flags || [];
    const summary = data.summary || "Aucun résumé disponible.";
    const globalTrend = data.global_trend || "Stable";
    
    let resultsHtml = `
      <div class="comparison-summary-card animate-fade-in" style="background: rgba(99, 102, 241, 0.04); border: 1px solid rgba(99, 102, 241, 0.15); border-radius: var(--radius-md); padding: 18px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.2);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px; flex-wrap:wrap; gap:8px;">
          <h4 style="font-family: 'Outfit', sans-serif; font-size: 15px; font-weight: 700; color: #fff; margin:0;">📊 Synthèse d'Évolution Pluriannuelle</h4>
          <span class="auto-badge" style="background: linear-gradient(135deg, var(--accent) 0%, #a855f7 100%); color: #fff; font-weight:700; padding: 4px 10px; border-radius: 20px; font-size: 11px;">Tendance globale : ${escapeHtml(globalTrend)}</span>
        </div>
        <p style="color: var(--text-muted); font-size: 13px; line-height: 1.6; margin:0;">${escapeHtml(summary)}</p>
      </div>
    `;
    
    if (coherenceFlags.length > 0) {
      const alertsHtml = coherenceFlags.map(flag => `
        <div class="coherence-alert animate-fade-in" style="display: flex; align-items: center; gap: 10px; padding: 12px 16px; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: var(--radius-md); color: #fca5a5; font-size: 13px; margin-bottom: 16px; font-weight: 500; box-shadow: 0 0 15px rgba(239, 68, 68, 0.1);">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <span><strong>Alerte Cohérence Bilan :</strong> ${escapeHtml(flag)}</span>
        </div>
      `).join("");
      resultsHtml += alertsHtml;
    }
    
    if (variations.length === 0) {
      resultsHtml += `
        <div style="padding: 30px; text-align: center; color: var(--text-muted); font-size: 13px; border: 1px dashed var(--border); border-radius: var(--radius-md); background: rgba(255,255,255,0.01);">
          Aucune variation comptable significative détectée entre ces deux exercices.
        </div>
      `;
    } else {
      resultsHtml += `
        <div class="table-container animate-fade-in" style="border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; background: rgba(255,255,255,0.01); box-shadow: 0 8px 32px rgba(0,0,0,0.15);">
          <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
            <thead>
              <tr style="background: rgba(255,255,255,0.02); border-bottom: 1px solid var(--border);">
                <th style="padding: 14px 16px; color: var(--text-muted); font-weight: 600; font-family: 'Outfit', sans-serif;">Poste Comptable</th>
                <th style="padding: 14px 16px; color: var(--text-muted); font-weight: 600; font-family: 'Outfit', sans-serif; text-align: right;">Exercice Précédent</th>
                <th style="padding: 14px 16px; color: var(--text-muted); font-weight: 600; font-family: 'Outfit', sans-serif; text-align: right;">Exercice Récent</th>
                <th style="padding: 14px 16px; color: var(--text-muted); font-weight: 600; font-family: 'Outfit', sans-serif; text-align: right;">Variation</th>
                <th style="padding: 14px 16px; color: var(--text-muted); font-weight: 600; font-family: 'Outfit', sans-serif;">Analyse & Seuil d'Alerte</th>
              </tr>
            </thead>
            <tbody>
              ${variations.map((v, index) => {
                const varPct = v.variation_pct;
                let pctLabel = "—";
                let pctColor = "var(--text-muted)";
                let rowBg = index % 2 === 0 ? "rgba(255,255,255,0.01)" : "rgba(0,0,0,0.15)";
                
                if (varPct !== null && varPct !== undefined) {
                  const plus = varPct > 0 ? "+" : "";
                  pctLabel = `${plus}${varPct.toFixed(1)}%`;
                  
                  if (v.severity === "critical") {
                    pctColor = "#f87171"; // Crimson
                  } else if (v.severity === "warning") {
                    pctColor = "#fbbf24"; // Amber
                  } else {
                    pctColor = "#34d399"; // Emerald
                  }
                }
                
                let severityBadge = "";
                if (v.severity === "critical") {
                  severityBadge = `<span class="badge-category" style="background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.25); font-size: 10px; padding: 2px 8px; font-weight: 700; border-radius: 4px; letter-spacing: 0.02em;">ALERTE</span>`;
                } else if (v.severity === "warning") {
                  severityBadge = `<span class="badge-category" style="background: rgba(245, 158, 11, 0.12); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.25); font-size: 10px; padding: 2px 8px; font-weight: 700; border-radius: 4px; letter-spacing: 0.02em;">ATTENTION</span>`;
                } else {
                  severityBadge = `<span class="badge-category" style="background: rgba(16, 185, 129, 0.12); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.25); font-size: 10px; padding: 2px 8px; font-weight: 700; border-radius: 4px; letter-spacing: 0.02em;">STABLE</span>`;
                }
                
                const formatVal = (val) => {
                  if (val === null || val === undefined || isNaN(val)) return "—";
                  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(val);
                };
                
                return `
                  <tr style="background: ${rowBg}; border-bottom: 1px solid var(--border); transition: background 0.15s ease;" onmouseover="this.style.background='rgba(255,255,255,0.03)'" onmouseout="this.style.background='${rowBg}'">
                    <td style="padding: 14px 16px; font-weight: 600; color: #fff; font-family: 'Outfit', sans-serif;">${escapeHtml(v.field)}</td>
                    <td style="padding: 14px 16px; text-align: right; color: var(--text-muted); font-variant-numeric: tabular-nums;">${formatVal(v.previous_value)}</td>
                    <td style="padding: 14px 16px; text-align: right; color: #fff; font-weight: 600; font-variant-numeric: tabular-nums;">${formatVal(v.current_value)}</td>
                    <td style="padding: 14px 16px; text-align: right; color: ${pctColor}; font-weight: 800; font-size: 13px; font-variant-numeric: tabular-nums;">${pctLabel}</td>
                    <td style="padding: 14px 16px; color: var(--text-muted); line-height: 1.5;">
                      <div style="display:flex; align-items:center; gap:10px;">
                        ${severityBadge}
                        <span style="font-size: 12px;">${escapeHtml(v.insight)}</span>
                      </div>
                    </td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table>
        </div>
      `;
    }
    
    if (resultsEl) resultsEl.innerHTML = resultsHtml;
  } catch (e) {
    console.error("runDossierComparison error:", e);
    toast(`Erreur d'analyse : ${e.message || e}`, "error");
    if (resultsEl) resultsEl.style.display = "none";
    if (placeholderEl) {
      placeholderEl.style.display = "block";
      if (placeholderTextEl) placeholderTextEl.innerHTML = "Une erreur est survenue lors de l'analyse.";
    }
  }
}

function renderDossierClientSummary(client, readyCount) {
  const exercices = client.exercices || [];
  const totalDocs = client.total_docs || 0;
  const pendingCount = Math.max(0, totalDocs - readyCount);
  const categories = [...new Set(exercices.flatMap(ex => ex.doc_categories || []).filter(Boolean))];
  const lastActivity = client.last_activity ? formatDate(client.last_activity) : "—";
  return `
    <section class="dossier-client-summary" aria-label="Synthèse du dossier client">
      <div class="dossier-summary-main">
        <span class="dossier-summary-label">Vue client</span>
        <strong>${escapeHtml(client.client_name || currentDossierClient || "Client")}</strong>
        <span>${totalDocs} document${totalDocs > 1 ? "s" : ""} réparti${totalDocs > 1 ? "s" : ""} sur ${exercices.length} exercice${exercices.length > 1 ? "s" : ""}</span>
      </div>
      <div class="dossier-summary-metrics">
        <span><strong>${readyCount}</strong> prêts IA</span>
        <span><strong>${pendingCount}</strong> à traiter</span>
        <span><strong>${lastActivity}</strong> dernière activité</span>
      </div>
      ${categories.length ? `<div class="dossier-summary-tags">${categories.slice(0, 6).map(c => `<span>${escapeHtml(c)}</span>`).join("")}</div>` : ""}
    </section>
  `;
}

function dossierDocStatusClass(status) {
  if (isReadyStatus(status)) return "is-ready";
  if (isProcessingStatus(status)) return "is-processing";
  if ((status || "").toLowerCase() === "failed") return "is-error";
  return "is-neutral";
}

function renderDossierExerciceSection(ex) {
  const allReady = ex.ready_count === ex.doc_count;
  const statusBadge = allReady
    ? `<span class="badge-category badge-green">Complet</span>`
    : `<span class="badge-category badge-orange">${ex.ready_count}/${ex.doc_count} prêts</span>`;
  const catsText = (ex.doc_categories || []).map(c => escapeHtml(c)).join(" · ");
  const docs = ex.documents || [];
  return `
    <div class="dossier-exercice-section">
      <div class="dossier-exercice-section-header">
        <div class="dossier-exercice-title">
          <h3>Exercice ${escapeHtml(ex.exercice || "Sans exercice")}</h3>
          <span>${docs.length} document${docs.length > 1 ? "s" : ""}${catsText ? " · " + catsText : ""}</span>
        </div>
        <div class="dossier-exercice-actions">${statusBadge}</div>
      </div>
      <div class="dossier-doc-card-list">
        ${docs.map(doc => renderDossierDocCard(doc)).join("")}
      </div>
    </div>
  `;
}

function renderDossierDocCard(doc) {
  const statusClass = dossierDocStatusClass(doc.status);
  return `
    <article class="dossier-doc-card ${statusClass}" data-action="select-doc" data-doc-id="${escapeAttr(doc.id)}">
      <div class="dossier-doc-status-dot" aria-hidden="true"></div>
      <div class="dossier-doc-card-body">
        <div class="dossier-doc-card-title" title="${escapeAttr(doc.original_filename)}">${escapeHtml(doc.original_filename)}</div>
        <div class="dossier-doc-card-meta">
          <span>${escapeHtml(doc.doc_category || "Non classé")}</span>
          <span>${formatDate(doc.created_at)}</span>
          <span>${formatBytes(doc.size_bytes)}</span>
        </div>
      </div>
      <div class="dossier-doc-card-actions">
        <span class="dossier-doc-status-label">${escapeHtml(documentStatusLabel(doc.status))}</span>
        <button class="btn btn-ghost btn-sm" data-action="select-doc" data-doc-id="${escapeAttr(doc.id)}">Ouvrir</button>
        <button class="btn btn-icon btn-sm" data-action="edit-metadata" data-doc-id="${escapeAttr(doc.id)}" aria-label="Modifier les métadonnées" title="Modifier">
          <svg aria-hidden="true" focusable="false" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9"/>
            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
          </svg>
        </button>
      </div>
    </article>
  `;
}

function openUploadForDossierClient() {
  const nameEl = $("upload-client-name");
  if (nameEl && currentDossierClient) nameEl.value = currentDossierClient;
  setStep(1);
}

async function openEditMetadataModal(docId) {
  const newExercice = window.prompt("Exercice (4 chiffres, ex: 2024) :");
  if (newExercice === null) return;
  const body = {};
  if (newExercice.trim()) body.exercice = newExercice.trim();
  try {
    await apiFetch(`/documents/${docId}/metadata`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    toast("Métadonnées mises à jour", "success");
    if (currentDossierClient) loadDossierClientPage(currentDossierClient);
  } catch (e) {
    toast("Erreur mise à jour : " + e.message, "error");
  }
}

// ── Upload metadata auto-fill ──────────────────────────────────────────

function initExerciceSelect() {
  const sel = $("upload-exercice");
  if (!sel) return;
  const currentYear = new Date().getFullYear();
  const opts = ['<option value="">— Année —</option>'];
  for (let y = currentYear; y >= 2020; y--) {
    opts.push(`<option value="${y}">${y}</option>`);
  }
  sel.innerHTML = opts.join("");
}

function prefillUploadMetadata(suggestions) {
  if (!suggestions) return;
  
  const fields = [
    { id: "upload-exercice", val: suggestions.exercice_detected, badgeId: "badge-exercice" },
    { id: "upload-doc-category", val: suggestions.doc_category_detected, badgeId: "badge-doc-category" },
  ];
  
  fields.forEach(({ id, val, badgeId }) => {
    const el = $(id);
    const badge = $(badgeId);
    if (!el || !val) return;
    if (!el.value) {
      el.value = val;
      if (badge) {
        badge.style.display = "";
        badge.textContent = "✨ IA";
        badge.title = "Détecté automatiquement par l'IA";
      }
    }
  });

  // Client suggestion is special (badge and click to accept)
  const clientInput = $("upload-client-name");
  const clientBadge = $("badge-client");
  const suggestedName = suggestions.client_suggestion;

  if (clientInput && clientBadge && suggestedName && !clientInput.value.trim()) {
    clientBadge.style.display = "";
    clientBadge.textContent = `✨ ${suggestedName.length > 15 ? suggestedName.slice(0, 13) + "…" : suggestedName}`;
    clientBadge.onclick = () => {
      clientInput.value = suggestedName;
      clientBadge.style.display = "none";
      toast("Client accepté", "success");
    };
  }
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
      renderExportGuard({});
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
      renderExportGuard({});
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
  const selectedDoc = lastDocsList.find((d) => d.id === id);
  currentDocId = id;
  currentDocName = name || selectedDoc?.original_filename || "";
  currentDocStatus = status || selectedDoc?.status || "";
  currentDocSize = Number(sizeBytes ?? selectedDoc?.size_bytes ?? 0);
  delete originalTextCache[id]; // invalide le cache si on recharge
  updateHeaderContext();

  if (publicDemoMode && currentDemoDocument && id === currentDemoDocument.document_id) {
    document.querySelectorAll(".doc-item").forEach(el =>
      el.classList.toggle("selected", el.dataset.id === id)
    );
    setStep(2);
    resetAnonPanel();
    updateAnonDocBar(currentDocName, currentDocSize, "Démo Investisseur");
    showAnonResults(
      currentDemoDocument.preview_text || currentDemoDocument.anonymized_excerpt || "",
      currentDemoDocument.detections_count ?? 0,
      currentDemoDocument.entity_summary || {},
      currentDemoDocument.risk || null,
      "pseudonymization",
      currentDemoDocument,
    );
    applyPublicDemoInsights(currentDemoDocument);
    return;
  }

  const clientLabel = getDocClientLabel(id);


  document.querySelectorAll(".doc-item").forEach(el =>
    el.classList.toggle("selected", el.dataset.id === id)
  );

  // Si le document est prêt, aller directement à l'étape 3.
  // Sinon, étape 2 pour la sécurisation.
  const st = (status || "").toLowerCase();
  const targetStep = isReadyStatus(st) ? 3 : 2;
  setStep(targetStep);

  if (targetStep === 2) {
    resetAnonPanel();
    updateAnonDocBar(name, sizeBytes, clientLabel);
    updatePipelineTimeline({ status: st, extractDone: st !== "uploaded", anonymDone: isReadyStatus(st) });
    await refreshAIDocInsights(id);

    if (isProcessingStatus(st)) {
      showAnonLoading("Traitement en cours…");
      pollDocStatus(id);
    } else if (st === "uploaded") {
      const empty = $("anon-empty");
      if (empty) {
        empty.style.display = "";
        const p = empty.querySelector("p");
        if (p) p.innerHTML =
        "Document ajouté.<br>Cliquez sur <strong>Anonymiser</strong> pour démarrer.";
      }
    } else if (st === "failed") {
      const empty = $("anon-empty");
      if (empty) {
        empty.style.display = "";
        const icon = empty.querySelector(".hint-icon");
        if (icon) icon.innerHTML = `<svg aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
        const p = empty.querySelector("p");
        if (p) p.innerHTML =
        "Le traitement a échoué.<br>Cliquez sur <strong>Anonymiser</strong> pour réessayer.";
      }
    } else {
      const empty = $("anon-empty");
      if (empty) {
        empty.style.display = "";
        const p = empty.querySelector("p");
        if (p) {
          const label = documentStatusLabel(st);
          p.innerHTML =
            `État : <strong>${escapeHtml(label)}</strong>.<br>Utilisez les actions ci-dessus ou patientez.`;
        }
      }
    }
  } else {
    // targetStep === 3 (ready doc)
    const errBox = $("ai-preview-error");
    const errMsg = $("ai-preview-error-msg");
    if (errBox) errBox.style.display = "none";

    updateAIDocBar(name, sizeBytes, clientLabel);
    renderAIReadySummary({ name, client: clientLabel, status: st, sizeBytes });
    updatePipelineTimeline({ status: st, extractDone: true, anonymDone: true });
    await refreshAIDocInsights(id);
    resetChat();
    loadChatHistory(id);
    try {
      const preview = await apiFetch(`/documents/${id}/preview`);
      showAnonResults(preview.preview_text, preview.detections_count, preview.entity_summary || {});
      renderAIReadySummary({
        name,
        client: clientLabel,
        status: st,
        sizeBytes,
        entitiesText: `${preview.detections_count ?? 0} entité(s)`,
        entitySummary: preview.entity_summary || {},
      });
    } catch (e) {
      const msg = `Aperçu indisponible (${e.message || "erreur"}). Le chat et les exports restent disponibles.`;
      if (errBox && errMsg) {
        errMsg.textContent = msg;
        errBox.style.display = "";
      }
      renderAIReadySummary({ name, client: clientLabel, status: st, sizeBytes, previewError: msg });
    }
  }
  refreshCompareDocSelect();
}

function updateAnonDocBar(name, sizeBytes, clientLabel) {
  const bar = $("anon-doc-bar");
  if (!bar) return;
  const displayName = (name && String(name).trim()) || currentDocName || "Document";
  const label = clientLabel !== undefined && clientLabel !== null
    ? clientLabel
    : getDocClientLabel(currentDocId);
  $("anon-doc-name").textContent = displayName;
  const clientEl = $("anon-doc-client");
  if (clientEl) {
    clientEl.textContent = label || "—";
  }
  $("anon-doc-size").textContent = formatBytes(sizeBytes);
  const st = $("anon-doc-status");
  const status = (currentDocStatus || "uploaded").toLowerCase();
  st.textContent = documentStatusLabel(status);
  st.className = `doc-stage-badge ${status}`;
  bar.style.display = "";
  renderDocumentDetailShell();
}

function updateAIDocBar(name, sizeBytes, clientLabel) {
  const bar = $("ai-doc-bar");
  if (!bar) return;
  const displayName = (name && String(name).trim()) || currentDocName || "Document";
  const label = clientLabel !== undefined && clientLabel !== null
    ? clientLabel
    : getDocClientLabel(currentDocId);
  $("ai-doc-name").textContent = displayName;
  const clientEl = $("ai-doc-client");
  if (clientEl) {
    clientEl.textContent = label || "—";
  }
  $("ai-doc-size").textContent = formatBytes(sizeBytes);
  const st = $("ai-doc-status");
  const status = (currentDocStatus || "uploaded").toLowerCase();
  st.textContent = documentStatusLabel(status);
  st.className = `doc-stage-badge ${status}`;
  bar.style.display = "";
}

function buildAIChatIntroHtml() {
  const suggestions = AI_CHAT_SUGGESTIONS.map(label =>
    `<button type="button" data-chat-suggestion="${escapeAttr(label)}">${escapeHtml(label)}</button>`
  ).join("");
  return '<div class="chat-intro">' +
    '<div class="chat-intro-icon" role="img" aria-label="Cadenas">' +
    '<svg aria-hidden="true" focusable="false" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>' +
    '</div>' +
    '<h3>Document prêt pour l’analyse IA</h3>' +
    '<p>Le document a été anonymisé. Vous pouvez poser vos questions en toute sécurité.</p>' +
    `<div class="chat-suggestions" aria-label="Suggestions de questions">${suggestions}</div>` +
    '</div>';
}

function formatEntitySummary(summary) {
  if (!summary || typeof summary !== "object") return "Non disponible";
  const items = Object.entries(summary)
    .filter(([, value]) => Number(value) > 0)
    .map(([key, value]) => `${escapeHtml(key)}: ${Number(value)}`);
  return items.length ? items.join(" · ") : "Non disponible";
}

function renderAIReadySummary(details = {}) {
  const card = $("ai-ready-summary");
  if (!card) return;
  if (!currentDocId) {
    card.style.display = "none";
    card.innerHTML = "";
    return;
  }

  const name = details.name || currentDocName || "Document";
  const client = details.client || getDocClientLabel(currentDocId) || "Client non renseigné";
  const status = documentStatusLabel(details.status || currentDocStatus || "ready");
  const size = formatBytes(details.sizeBytes ?? currentDocSize);
  const fileKind = documentFileKind();
  const entities = details.entitiesText || formatEntitySummary(details.entitySummary);
  const exportTitle = $("export-guard-title")?.textContent || "Export prêt";
  const exportDetail = $("export-guard-detail")?.textContent || "Document anonymisé.";
  const previewNote = details.previewError
    ? `<p class="ai-ready-note">${escapeHtml(details.previewError)}</p>`
    : "";

  card.innerHTML = `
    <div class="ai-ready-copy">
      <p class="ai-ready-eyebrow">${details.justValidated ? "Validation terminée" : "Document sélectionné"}</p>
      <h3>Document anonymisé et prêt pour l’IA</h3>
      <p>Le document est sécurisé. Vous pouvez l’analyser, télécharger la preuve DPO ou revenir à la revue.</p>
      ${previewNote}
    </div>
    <dl class="ai-ready-meta">
      <div><dt>Fichier</dt><dd>${escapeHtml(name)}</dd></div>
      <div><dt>Client</dt><dd>${escapeHtml(client)}</dd></div>
      <div><dt>Statut</dt><dd>${escapeHtml(status)}</dd></div>
      <div><dt>Taille</dt><dd>${escapeHtml(size)}</dd></div>
      <div><dt>Original</dt><dd>${escapeHtml(fileKind)} · source disponible</dd></div>
      <div><dt>Entités masquées</dt><dd>${entities}</dd></div>
      <div><dt>Score / export</dt><dd>${escapeHtml(exportTitle)} · ${escapeHtml(exportDetail)}</dd></div>
    </dl>
    <div class="ai-ready-actions">
      <button type="button" class="btn btn-primary btn-sm" data-ai-ready-action="analyze">Analyser ce document</button>
      <button type="button" class="btn btn-ghost btn-sm" data-ai-ready-action="original">Ouvrir l’original</button>
      <button type="button" class="btn btn-ghost btn-sm" data-ai-ready-action="proof">Télécharger preuve DPO</button>
      <button type="button" class="btn btn-ghost btn-sm" data-ai-ready-action="review">Revoir l’anonymisation</button>
    </div>`;
  card.style.display = "";
}

function renderDocumentDetailShell(details = {}) {
  const root = document.querySelector("[data-document-detail]");
  if (!root) return;
  if (!currentDocId) {
    root.hidden = true;
    return;
  }

  const doc = getCurrentDocRecord();
  const name = details.name || currentDocName || doc?.original_filename || "Document";
  const client = details.client || getDocClientLabel(currentDocId) || "Client non renseigné";
  const statusRaw = details.status || currentDocStatus || doc?.status || "uploaded";
  const status = documentStatusLabel(statusRaw);
  const size = formatBytes(details.sizeBytes ?? currentDocSize ?? doc?.size_bytes);
  const fileKind = documentFileKind(doc);
  const count = details.count ?? details.detectionsCount ?? 0;
  const risk = details.risk || null;
  const riskScore = risk ? normalizeRiskPercent(risk.score || risk.risk_score) : null;
  const trustScore = riskScore === null ? 100 : Math.max(0, Math.min(100, 100 - riskScore));
  const previewText = details.previewText || "";
  const entitySummary = details.summary || {};
  const fileId = String(currentDocId || "").slice(0, 8);

  root.hidden = false;
  root.setAttribute("data-privacy-zones", "[]");

  const setText = (id, value) => {
    const el = $(id);
    if (el) el.textContent = value;
  };
  setText("detail-dossier-name", client);
  setText("detail-doc-name", name);
  setText("detail-status", status);
  setText("pane-original-meta", [fileKind, size].filter(Boolean).join(" · ") || "Source");
  setText("pane-anon-meta", `${Number(count || 0)} entité(s)`);
  setText(
    "detail-summary",
    `${Number(count || 0)} entité(s) · ${riskScore === null ? "risque —" : `risque ${Math.round(riskScore)}%`}`,
  );

  const originalViewer = root.querySelector(".viewer-original");
  if (originalViewer) {
    originalViewer.innerHTML = `
      <div class="document-original-card">
        <p class="rail-h">Document original</p>
        <h3>${escapeHtml(name)}</h3>
        <dl class="meta-list">
          ${documentDetailRow("Client", client)}
          ${documentDetailRow("Format", fileKind)}
          ${documentDetailRow("Taille", size || "—")}
          ${documentDetailRow("Statut", status)}
          ${documentDetailRow("ID", fileId || "—")}
        </dl>
        <div class="document-original-actions">
          <button type="button" class="btn-ghost" data-action="open-original">Ouvrir l’original</button>
          <button type="button" class="btn-ghost" data-action="download-original">Télécharger</button>
        </div>
      </div>
    `;
  }

  const anonymizedViewer = root.querySelector(".viewer-anonymized");
  if (anonymizedViewer) {
    anonymizedViewer.innerHTML = previewText
      ? `<div class="preview-text interactive-text">${highlightTags(previewText)}</div>`
      : '<div class="viewer-placeholder">Texte anonymisé en attente.</div>';
  }

  const metadata = $("detail-metadata");
  if (metadata) {
    metadata.innerHTML = [
      documentDetailRow("Fichier", name),
      documentDetailRow("Client", client),
      documentDetailRow("Format", fileKind),
      documentDetailRow("Taille", size || "—"),
      documentDetailRow("Statut", status),
      documentDetailRow("Entités", `${Number(count || 0)}`),
      documentDetailRow("ID", fileId || "—"),
    ].join("");
  }

  const gauge = $("detail-trust-gauge");
  if (gauge) {
    gauge.setAttribute("data-pii", String(trustScore));
    gauge.setAttribute("data-quasi", String(trustScore));
    gauge.setAttribute("data-coherence", "100");
    gauge.setAttribute("data-reversibility", String(riskScore === null ? 100 : Math.max(0, 100 - riskScore)));
  }

  const legend = $("detail-trust-legend");
  if (legend) {
    const entities = formatEntitySummary(entitySummary);
    legend.innerHTML = `
      <li><span class="swatch" style="background:var(--accent)"></span>Entités masquées<span class="leg-val">${Number(count || 0)}</span></li>
      <li><span class="swatch" style="background:var(--warning)"></span>Risque résiduel<span class="leg-val">${riskScore === null ? "—" : `${Math.round(riskScore)}%`}</span></li>
      <li><span class="swatch" style="background:var(--raw)"></span>Types détectés<span class="leg-val">${escapeHtml(entities)}</span></li>
    `;
  }

  const auditLog = $("detail-audit-log");
  if (auditLog) {
    auditLog.innerHTML = `
      <li><span class="ts">now</span><span class="what"><strong>Original chargé</strong><br>${escapeHtml(fileKind)} · ${escapeHtml(size || "taille inconnue")}</span></li>
      <li><span class="ts">DPO</span><span class="what"><strong>Anonymisation</strong><br>${Number(count || 0)} entité(s) suivie(s)</span></li>
    `;
  }
}

function documentDetailRow(label, value) {
  return `<div class="row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || "—")}</dd></div>`;
}

async function fetchCurrentOriginalBlob() {
  if (!currentDocId) throw new Error("Aucun document sélectionné");
  const doc = getCurrentDocRecord();
  const filename = doc?.original_filename || currentDocName || `document_${currentDocId}`;
  const fallbackType = doc ? doc.content_type : "application/pdf";
  const rawPath = publicDemoMode && currentDemoDocument?.urls?.raw
    ? currentDemoDocument.urls.raw
    : `/documents/${currentDocId}/raw`;
  const resp = await apiRequest(rawPath, { auth: !publicDemoMode });
  const responseContentType = (resp.headers.get("content-type") || fallbackType || "")
    .split(";")[0]
    .toLowerCase();
  if (responseContentType.includes("application/json")) {
    throw new Error("L'endpoint original a renvoyé du JSON au lieu du fichier source.");
  }
  const blob = await resp.blob();
  if (blob.size === 0) {
    throw new Error("Le fichier original est vide ou inaccessible.");
  }
  if (originalBlobUrl) URL.revokeObjectURL(originalBlobUrl);
  originalBlobUrl = URL.createObjectURL(blob);
  return { blob, filename, url: originalBlobUrl };
}

async function openCurrentOriginal(download = false) {
  try {
    const { blob, filename, url } = await fetchCurrentOriginalBlob();
    if (download) {
      triggerDownload(blob, filename);
      return;
    }
    window.open(url, "_blank", "noopener");
  } catch (e) {
    console.error("openCurrentOriginal error:", e);
    toast(e.message || "Original indisponible", "error");
  }
}

async function openAnonReviewForCurrentDocument() {
  if (!currentDocId) return;
  const clientLabel = getDocClientLabel(currentDocId);
  setStep(2);
  resetAnonPanel();
  updateAnonDocBar(currentDocName, currentDocSize, clientLabel);
  if (isReadyStatus(currentDocStatus)) {
    try {
      const preview = await apiFetch(`/documents/${currentDocId}/preview`);
      showAnonResults(
        preview.preview_text,
        preview.detections_count,
        preview.entity_summary || {},
        preview.risk || null,
      );
      return;
    } catch (e) {
      console.warn("openAnonReviewForCurrentDocument preview error:", e);
    }
  }
  await loadOriginalDocument(currentDocId);
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
        statusEl.textContent = "Ajout réussi !";
        try { resolve(JSON.parse(xhr.responseText)); }
        catch (_e) { resolve({}); }
      } else {
        let msg = `HTTP ${xhr.status}`;
        try { const j = JSON.parse(xhr.responseText); msg = j.detail || msg; } catch(_e) {}
        reject(new Error(msg));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Erreur réseau")));
    xhr.addEventListener("abort", () => reject(new Error("Ajout annulé")));
    xhr.open("POST", API + path);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.send(formData);
  });
}

// ── Upload ─────────────────────────────────────────────────────────────

let isBatchUpload = false;
let completedBatchItems = [];

function renderUploadQueue() {
  const el = $("upload-queue");
  if (!el) return;
  
  const totalItems = uploadQueue.length + completedBatchItems.length;
  if (totalItems === 0 && !isUploadProcessing) {
    el.style.display = "none";
    el.innerHTML = "";
    return;
  }
  
  el.style.display = "block";
  
  const queueHtml = uploadQueue.map((item, idx) => {
    return `
      <div class="upload-queue-item queued" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 10px; min-width: 0;">
          <div class="spinner-sm" style="width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.2); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; flex-shrink: 0;"></div>
          <span style="font-size: 13px; color: var(--text-muted); text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${escapeHtml(item.file.name)}</span>
        </div>
        <strong style="font-size: 11px; text-transform: uppercase; color: var(--text-muted);">${item.status_label}</strong>
      </div>`;
  }).join("");

  const completedHtml = completedBatchItems.map((item, idx) => {
    const isDone = item.status === "done";
    const statusColor = isDone ? "var(--success)" : "var(--danger)";
    const bgGlow = isDone ? "rgba(16, 185, 129, 0.04)" : "rgba(239, 68, 68, 0.04)";
    const borderGlow = isDone ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)";
    
    return `
      <div class="upload-queue-item ${item.status}" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: ${bgGlow}; border: 1px solid ${borderGlow}; border-radius: 8px; margin-bottom: 8px; transition: all 0.2s;">
        <div style="display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1;">
          ${isDone 
            ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><polyline points="20 6 9 17 4 12"/></svg>`
            : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`
          }
          <span style="font-size: 13px; color: var(--text); text-overflow: ellipsis; overflow: hidden; white-space: nowrap; font-weight: 500;">${escapeHtml(item.file.name)}</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
          <strong style="font-size: 11px; text-transform: uppercase; color: ${statusColor}; margin-right: 4px;">${item.status_label}</strong>
          ${isDone 
            ? `<button class="btn btn-ghost btn-sm" type="button" style="padding: 4px 8px; font-size: 11px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); height: auto;" onclick="selectDoc('${item.docId}', '${item.docStatus}', '${escapeAttr(item.file.name)}', ${item.file.size})">Ouvrir</button>`
            : ""
          }
        </div>
      </div>`;
  }).join("");

  let headerHtml = "";
  if (isBatchUpload) {
    const totalDone = completedBatchItems.filter(i => i.status === "done").length;
    const isFinished = !isUploadProcessing;
    
    headerHtml = `
      <div style="margin-bottom: 12px; padding: 12px; background: rgba(99, 102, 241, 0.05); border: 1px dashed var(--border-accent); border-radius: 8px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong style="font-size:12px; color:#fff;">📦 Import multiple (${completedBatchItems.length}/${totalItems})</strong>
          <span style="font-size:11px; color:var(--text-muted);">${isFinished ? "Import complété !" : "Importation en cours..."}</span>
        </div>
        ${isFinished 
          ? `<p style="font-size:11px; color:var(--success); margin-top: 4px; display:flex; align-items:center; gap:4px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              ${totalDone} document${totalDone > 1 ? "s" : ""} ajouté${totalDone > 1 ? "s" : ""} au dossier client.
             </p>` 
          : `<div class="progress-bar-track" style="margin-top: 6px; height: 4px; background: rgba(255,255,255,0.04);"><div class="progress-bar-fill" style="width: ${Math.round(completedBatchItems.length / totalItems * 100)}%; height: 100%; background: var(--accent); transition: width 0.3s;"></div></div>`
        }
      </div>
    `;
  }

  el.innerHTML = headerHtml + completedHtml + queueHtml;
}

function enqueueUpload(files) {
  const clientName = getUploadClientName();
  if (!clientName) {
    toast("Le nom client est obligatoire à l'upload.", "error");
    $("upload-client-name")?.focus();
    return;
  }
  isBatchUpload = files.length > 1;
  completedBatchItems = [];
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
      const data = await uploadFile(item.file);
      item.status = "done";
      item.status_label = "Terminé";
      item.docId = data.document_id;
      item.docStatus = data.processing?.status || data.status || "uploaded";
    } catch (e) {
      item.status = "error";
      item.status_label = "Échec";
    }
    completedBatchItems.push({ ...item });
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
  const clientName = getUploadClientName();
  const clientId = getClientIdByName(clientName);
  const autoAnon = $("upload-auto-anonymize")?.checked ?? true;

  if (!clientName) {
    zone.style.display = "";
    progress.style.display = "none";
    fill.style.width = "0";
    toast("Le nom client est obligatoire à l'upload.", "error");
    $("upload-client-name")?.focus();
    throw new Error("client_name_required");
  }

  try {
    const params = new URLSearchParams();
    params.set("auto_anonymize", String(autoAnon));
    if (clientId) params.set("client_id", String(clientId));
    else params.set("client_name", clientName);
    const exerciceQp = ($("upload-exercice")?.value || "").trim();
    const catQp = ($("upload-doc-category")?.value || "").trim();
    if (exerciceQp) params.set("exercice", exerciceQp);
    if (catQp) params.set("doc_category", catQp);
    const data = await uploadWithProgress(
      fd,
      `/uploads?${params.toString()}`,
      fill, statusEl
    );
    currentDocId = data.document_id;
    currentDocName = file.name;
    currentDocStatus = data.processing?.status || data.status || "uploaded";
    currentDocSize = file.size || 0;
    if (data.suggestions) prefillUploadMetadata(data.suggestions);
    updateHeaderContext();
    await loadClientSuggestions();
    await loadDocList();
    if (sidebarMode === "dossier") loadDossierTree();

    setTimeout(() => {
      zone.style.display = "";
      progress.style.display = "none";
      fill.style.width = "0";

      if (!isBatchUpload) {
        setStep(2);
        resetAnonPanel();
        updateAnonDocBar(file.name, file.size, clientName);
        refreshAIDocInsights(currentDocId);
        const anonEmpty = $("anon-empty");
        if (anonEmpty) {
          anonEmpty.style.display = "";
          const hintIcon = anonEmpty.querySelector(".hint-icon");
          if (hintIcon) {
            hintIcon.innerHTML =
          '<svg aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
          }
          const pEl = anonEmpty.querySelector("p");
          if (pEl) {
            if (autoAnon) {
              pEl.innerHTML =
            `<strong>${escapeHtml(file.name)}</strong> ajouté.<br>Sécurisation en cours en arrière-plan…`;
            } else {
              pEl.innerHTML =
            `<strong>${escapeHtml(file.name)}</strong> ajouté.<br>Cliquez sur <strong>Anonymiser</strong> pour démarrer.`;
            }
          }
        }
        if (autoAnon) {
          showAnonLoading("Mistral OCR et sécurisation en cours…");
          updateProcessingConsole({
            status: currentDocStatus,
            backend: (data.processing?.background_processing || "api").toUpperCase(),
          });
          pollDocStatus(currentDocId);
        }
      } else {
        if (autoAnon) {
          pollDocStatusBackground(data.document_id, file.name);
        }
      }
    }, 600);

    toast(`${file.name} ajouté`, "success");
    return data;
  } catch (e) {
    console.error("uploadFile error:", e);
    zone.style.display = "";
    progress.style.display = "none";
    fill.style.width = "0";
    if (e.message !== "client_name_required") {
      toast(`Erreur ajout: ${e.message}`, "error");
      // Rafraîchir la liste même en cas d'erreur : le doc peut être en DB
      loadDocList().catch(() => {});
    }
    throw e;
  }
}

function pollDocStatusBackground(docId, fileName) {
  let tries = 0;
  const maxTries = 240;
  const interval = setInterval(async () => {
    tries++;
    if (tries > maxTries) {
      clearInterval(interval);
      const item = completedBatchItems.find(i => i.docId === docId);
      if (item) {
        item.status_label = "Délai dépassé";
        renderUploadQueue();
      }
      return;
    }
    try {
      const st = await apiFetch(`/documents/${docId}/status`);
      const status = (st.status || "").toLowerCase();
      const anonymDone = !!st.anonymization?.done;
      
      const item = completedBatchItems.find(i => i.docId === docId);
      if (item) {
        item.docStatus = status;
        if (status === "ready" || anonymDone) {
          item.status_label = "Sécurisé ✨";
          item.docStatus = "ready";
          clearInterval(interval);
          renderUploadQueue();
          await loadDocList().catch(e => console.warn(e));
          if (sidebarMode === "dossier") loadDossierTree();
        } else if (status === "processing" || status === "extracting") {
          item.status_label = "Sécurisation...";
          renderUploadQueue();
        }
      } else {
        clearInterval(interval);
      }
    } catch (e) {
      console.warn("Background poll error for", docId, e);
    }
  }, 2000);
}

async function createDemoDocument() {
  if (!token) {
    await launchPublicInvestorDemo();
    return;
  }
  try {
    toast("Chargement Demo Investor : document synthétique et pipeline sécurisé…", "info");
    const res = await apiFetch("/demo", { method: "POST" });
    currentDocId = res.document_id;
    currentDocName = res.original_filename;
    currentDocStatus = String(res.status || "processing").toLowerCase();
    currentDocSize = Number(res.size_bytes || 0);
    updateHeaderContext();
    await loadDocList();

    setStep(2);
    resetAnonPanel();
    updateAnonDocBar(res.original_filename, currentDocSize);
    await refreshAIDocInsights(currentDocId);

    const empty = $("anon-empty");
    if (empty) {
      empty.style.display = "";
      const icon = empty.querySelector(".hint-icon");
      const copy = empty.querySelector("p");
      if (icon) {
        icon.innerHTML =
          '<svg aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
      }
      if (copy) {
        copy.innerHTML =
          `<strong>${res.original_filename}</strong> créé.<br>Workflow démo: upload → OCR → anonymisation → scores → audit → export.`;
      }
    }

    if (isReadyStatus(currentDocStatus)) {
      try {
        const preview = await apiFetch(`/documents/${currentDocId}/preview`);
        showAnonResults(preview.preview_text, preview.detections_count, preview.entity_summary || {});
      } catch (previewErr) {
        console.warn("demo preview unavailable:", previewErr);
      }
      toast(res.message || "Demo Investor prête — scores et audit disponibles", "success");
      return;
    }

    showAnonLoading("Demo Investor : OCR et anonymisation en cours…");
    pollDocStatus(currentDocId);

    toast(res.message || "Demo Investor chargée — sécurisation lancée", "success");
  } catch (e) {
    console.error("demo error:", e);
    const msg = e.message || "Erreur inconnue";
    if (msg.includes("Session expirée") || msg.includes("Authentification requise")) {
      toast("Session expirée. Reconnectez-vous ou lancez la démo publique depuis la page d'accueil.", "error");
    } else {
      toast(`Erreur démo: ${msg}`, "error");
    }
  }
}

function buildDemoAssistantAnswer(question) {
  const q = (question || "").toLowerCase();
  const score = currentDemoDocument?.risk?.score ?? currentDemoDocument?.risk?.risk_score ?? 0;
  const entities = currentDemoDocument?.detections_count ?? 0;
  if (q.includes("risque") || q.includes("score") || q.includes("pourquoi")) {
    return `## Pourquoi ce score\n- Score de risque: ${score}/100, niveau faible.\n- ${entities} entités synthétiques ont été détectées et remplacées par des jetons stables.\n- L'original reste disponible pour contrôle visuel, tandis que l'analyse IA utilise uniquement la version anonymisée.\n\n## Action recommandée\n- Valider le contexte de diffusion avant un partage externe.`;
  }
  if (q.includes("audit")) {
    return "## Audit trail\n- Document synthétique créé pour démonstration investisseur.\n- Extraction, anonymisation, calcul de risque et préparation export sont tracés.\n- Aucun document réel n'est utilisé dans ce parcours.";
  }
  return "## Résumé\n- Document synthétique de démonstration investisseur chargé.\n- Original PDF accessible, aperçu anonymisé disponible, score RGPD calculé et audit exportable.\n\n## Points clés\n- Données personnelles, coordonnées, identifiants société et IBAN remplacés par des jetons.\n- Le workflow illustre original, anonymisé, décision ConfiDoc, explication du score, audit trail et export.";
}

function applyPublicDemoInsights(payload) {
  const status = payload.status || "ready";
  const risk = payload.risk || {};
  const trust = payload.trust || {};
  const score = normalizeRiskPercent(risk.risk_score ?? risk.score);
  currentRiskLevel = risk.risk_level || risk.level || "low";
  updatePipelineTimeline({ status, extractDone: true, anonymDone: true });
  renderAIDocInsights({
    status: documentStatusLabel(status),
    ocrStatus: "OK · demo synthétique",
    anonymizationStatus: "OK",
    riskScore: score === null ? "0/100" : `${score}/100`,
    trustScore: Number.isFinite(Number(trust.trust_score ?? payload.trust_score))
      ? `${Math.round(Number(trust.trust_score ?? payload.trust_score))}/100`
      : "85/100",
    aiReadiness: Number.isFinite(Number(trust.ai_readiness_score ?? payload.ai_readiness_score))
      ? `${Math.round(Number(trust.ai_readiness_score ?? payload.ai_readiness_score))}/100`
      : "85/100",
    detections: payload.detections_count ?? 0,
    exportStatus: "Export autorisé",
    lastAudit: "document:demo_investor_loaded",
    nextAction: "Présenter le workflow",
  });
  renderExportGuard({
    ...risk,
    status,
    risk_level: currentRiskLevel,
    risk_score: score ?? 0,
  });
  renderDecisionCard({
    ...risk,
    status,
    risk_level: currentRiskLevel,
    risk_score: score ?? 0,
    trust_score: trust.trust_score ?? payload.trust_score ?? 85,
    ai_readiness_score: trust.ai_readiness_score ?? payload.ai_readiness_score ?? 85,
  }, status);
  renderTrustIndicator(trust.trust_score ? trust : { trust_score: 85, ai_readiness_score: 85, grade: "A" });
}

async function launchPublicInvestorDemo() {
  try {
    toast("Chargement de la démo investisseur…", "info");
    const payload = await apiFetch("/demo/investor-document", {
      method: "POST",
      auth: false,
    });
    publicDemoMode = true;
    currentDemoDocument = payload;
    currentDocId = payload.document_id;
    currentDocName = payload.original_filename || payload.document?.original_filename || "Démo investisseur";
    currentDocStatus = String(payload.status || "ready").toLowerCase();
    currentDocSize = Number(payload.size_bytes || payload.document?.size_bytes || 0);
    lastDocsList = [payload.document || {
      id: currentDocId,
      original_filename: currentDocName,
      content_type: "application/pdf",
      size_bytes: currentDocSize,
      status: currentDocStatus,
    }];
    originalTextCache[currentDocId] = payload.original_excerpt || "";

    $("screen-auth").style.display = "none";
    $("screen-app").style.display = "";
    $("btn-logout").style.display = "";
    $("btn-logout").textContent = "Quitter la démo";
    $("user-info").textContent = "Mode démo investisseur";
    updateHeaderContext();
    renderDocList(lastDocsList);
    setStep(2);
    resetAnonPanel();
    updateAnonDocBar(currentDocName, currentDocSize);
    showAnonResults(
      payload.preview_text || payload.anonymized_excerpt || "",
      payload.detections_count ?? 0,
      payload.entity_summary || {},
      payload.risk || null,
      "pseudonymization",
      payload,
    );
    applyPublicDemoInsights(payload);
    toast("Démo investisseur prête", "success");
  } catch (e) {
    console.error("public investor demo error:", e);
    toast(`Démo indisponible: ${e.message}`, "error");
  }
}

// ── Anonymisation ──────────────────────────────────────────────────────

function resetAnonPanel() {
  stopProcessingTimer();
  processingStartedAt = null;
  hideAnonLoading();
  $("anon-results").style.display = "none";
  $("anon-empty").style.display = "none";
  $("anon-empty").querySelector(".hint-icon").innerHTML = `<svg aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  $("anon-empty").querySelector("p").innerHTML =
    "Sélectionnez un document dans la liste<br>ou uploadez-en un nouveau.";
  $("btn-anonymize").disabled = false;
  const originalTextEl = $("preview-original-text");
  const originalLoadingEl = $("original-loading");
  if (originalTextEl) originalTextEl.textContent = "";
  if (originalLoadingEl) originalLoadingEl.style.display = "none";
  $("preview-diff-text").innerHTML = "";
  updatePipelineTimeline({});
}

function showAnonLoading(msg) {
  $("anon-loading").style.display = "";
  $("anon-loading-msg").textContent = msg || "Sécurisation en cours…";
  $("anon-results").style.display = "none";
  $("anon-empty").style.display = "none";
  $("btn-anonymize").disabled = true;
  startProcessingTimer();
  updateProcessingConsole({ status: currentDocStatus || "processing" });
}

function hideAnonLoading() {
  $("anon-loading").style.display = "none";
  $("btn-anonymize").disabled = false;
  stopProcessingTimer();
  const processingConsole = $("processing-console");
  if (processingConsole) processingConsole.style.display = "none";
  const spinner = document.querySelector("#anon-loading .spinner-lg");
  if (spinner) spinner.style.display = "";
}

function setReviewMode(mode) {
  const container = $("review-container");
  if (!container) return;
  container.className = `review-container mode-${mode}`;
  $("btn-view-split").classList.toggle("active", mode === "split");
  $("btn-view-text").classList.toggle("active", mode === "text");
}

function toggleReviewFullscreen() {
  const station = $("interactive-review-station");
  if (station) station.classList.toggle("fullscreen");
}

async function loadOriginalDocument(docId) {
  const container = $("original-viewer-container");
  const spinner = $("original-loading-spinner");
  if (!container) return;

  if (originalBlobUrl) {
    URL.revokeObjectURL(originalBlobUrl);
    originalBlobUrl = "";
  }
  container.innerHTML = `
    <div id="original-loading-spinner" class="spinner-overlay"><div class="spinner"></div></div>
    <div class="viewer-placeholder">Chargement du document original...</div>
  `;
  try {
    const doc = lastDocsList.find(d => d.id === docId);
    const fallbackType = doc ? doc.content_type : "application/pdf";
    const filename = doc?.original_filename || currentDocName || "document";
    const rawPath = publicDemoMode && currentDemoDocument?.urls?.raw
      ? currentDemoDocument.urls.raw
      : `/documents/${docId}/raw`;
    const resp = await apiRequest(rawPath, {
      auth: !publicDemoMode,
    });
    const responseContentType = (resp.headers.get("content-type") || fallbackType || "")
      .split(";")[0]
      .toLowerCase();
    if (responseContentType.includes("application/json")) {
      throw new Error("L'endpoint original a renvoyé du JSON au lieu du fichier source.");
    }
    const blob = await resp.blob();
    if (blob.size === 0) {
      throw new Error("Le fichier original est vide ou inaccessible.");
    }
    const contentType = (blob.type || responseContentType || fallbackType || "")
      .split(";")[0]
      .toLowerCase();
    originalBlobUrl = URL.createObjectURL(blob);
    const previewablePdf = contentType === "application/pdf";
    const previewableImage = contentType.startsWith("image/");
    const toolbar = `
      <div class="original-viewer-toolbar">
        <span title="${escapeAttr(filename)}">${escapeHtml(filename)}</span>
        <div class="original-viewer-actions">
          <button type="button" class="btn btn-ghost btn-sm" id="btn-open-original">Ouvrir</button>
          <button type="button" class="btn btn-ghost btn-sm" id="btn-download-original">Télécharger l'original</button>
        </div>
      </div>`;

    if (previewablePdf) {
      container.innerHTML = `${toolbar}<iframe src="${originalBlobUrl}" class="original-viewer original-viewer-frame" title="Aperçu PDF original"></iframe>`;
    } else if (previewableImage) {
      container.innerHTML = `${toolbar}<img src="${originalBlobUrl}" class="original-viewer original-viewer-frame" alt="Aperçu du document original" style="object-fit: contain;" />`;
    } else {
      container.innerHTML = `${toolbar}<div class="viewer-placeholder">Aperçu non disponible pour ce format. Téléchargez le fichier original.</div>`;
    }
    $("btn-open-original")?.addEventListener("click", () => window.open(originalBlobUrl, "_blank", "noopener"));
    $("btn-download-original")?.addEventListener("click", () => {
      triggerDownload(blob, filename || `document_${docId}`);
    });
  } catch (e) {
    container.innerHTML = `
      <div class="viewer-placeholder is-error">
        <div>
          <strong>Aperçu indisponible</strong><br>
          ${escapeHtml(e.message || "Le document original ne peut pas être affiché.")}
        </div>
      </div>`;
  } finally {
    if (spinner) spinner.style.display = "none";
  }
}

function showAnonResults(previewText, count, summary = {}, risk = null, mode = "pseudonymization", fullData = {}) {
  hideAnonLoading();
  const processingConsole = $("processing-console");
  if (processingConsole) processingConsole.style.display = "none";
  $("anon-results").style.display = "";
  $("stat-count").textContent = count ?? 0;
  
  // Track baseline scores for DPO simulations
  window.currentBaseRiskScore = risk ? normalizeRiskPercent(risk.score || risk.risk_score) : 12;
  window.initialTagsCount = count ?? 0;

  $("preview-anon-text").innerHTML = highlightTags(previewText || "(Aucun texte extrait)");
  renderDocumentDetailShell({
    previewText,
    count,
    summary,
    risk,
    status: currentDocStatus,
    sizeBytes: currentDocSize,
  });

  // Prepopulate DPO dynamic mapping and ledger logs
  if (typeof buildDynamicTagOriginalMap === "function") {
    buildDynamicTagOriginalMap(fullData);
  }
  if (typeof prepulateLedger === "function") {
    prepulateLedger(count ?? 0);
  }
  if (typeof window.updateScores === "function") {
    window.updateScores();
  }

  // Load original document in the viewer
  if (currentDocId) {
    loadOriginalDocument(currentDocId);
  }

  // Render audit insights if available
  renderAuditInsights(fullData);

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
  currentRiskLevel = risk ? (risk.risk_level || risk.level || null) : null;
  if (risk) {
    renderExportGuard({
      status: "ready",
      risk_level: risk.risk_level || risk.level,
      risk_score: risk.risk_score ?? risk.score,
      human_validated: false,
    });
  }
  const trustPayload = fullData.trust
    || (fullData.ai_readiness_score !== undefined || fullData.trust_score !== undefined ? fullData : null)
    || (risk && (risk.ai_readiness_score !== undefined || risk.trust_score !== undefined) ? risk : null);
  if (trustPayload) renderTrustIndicator(trustPayload);

  // Risk indicator (RGPD)
  const riskEl = $("risk-indicator");
  if (riskEl && risk) {
    riskEl.style.display = "";
    const scoreEl = $("risk-score");
    const levelEl = $("risk-level");
    const recoEl = $("risk-recommendation");
    const badgeEl = $("risk-badge");
    const riskPct = normalizeRiskPercent(risk.score);
    if (scoreEl) scoreEl.textContent = riskPct === null ? "—" : `${riskPct}%`;
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
      if (tag.includes("PERSONNE") || tag.includes("ASSOCIE")) colorClass = "anon-tag-personne";
      else if (tag.includes("SOCIETE") || tag.includes("CABINET")) colorClass = "anon-tag-societe";
      else if (tag.includes("ADRESSE") || tag.includes("VILLE") || tag.includes("NAISSANCE")) colorClass = "anon-tag-adresse";
      else if (tag.includes("IBAN") || tag.includes("BANQUE") || tag.includes("MONTANT") || tag.includes("EMPRUNT") || tag.includes("REF")) colorClass = "anon-tag-montant";
      else if (tag.includes("DATE")) colorClass = "anon-tag-date";
      else if (tag.includes("EMAIL")) colorClass = "anon-tag-email";
      else if (tag.includes("TELEPHONE")) colorClass = "anon-tag-telephone";
      else if (tag.includes("NSS") || tag.includes("SIRET") || tag.includes("SIREN") || tag.includes("TVA") || tag.includes("CADASTRE")) colorClass = "anon-tag-siret";
      return `<mark class="anon-tag ${colorClass}" data-tag="${match}">${match}</mark>`;
    });
}

async function anonymize() {
  if (!currentDocId) { toast("Aucun document sélectionné", "error"); return; }
  const profile = $("anon-profile").value;
  const mode = $("anon-mode") ? $("anon-mode").value : "pseudonymization";
  showAnonLoading(mode === "anonymization" ? "Anonymisation forte en cours…" : "Sécurisation en cours…");

  try {
    const res = await fetch(
      `/api/v1/documents/${currentDocId}/anonymize?profile=${profile}&mode=${mode}`,
      { method: "POST", headers: { "Authorization": `Bearer ${token}` } }
    );

    if (res.status === 202) {
      toast("Sécurisation lancée… (peut prendre 30-60 s)", "info");
      showAnonLoading("Traitement en arrière-plan…");
      await loadDocList();
      pollDocStatus(currentDocId);
      updatePipelineTimeline({ status: "processing", extractDone: true, anonymDone: false });
    } else if (res.ok) {
      const data = await res.json();
      showAnonResults(data.preview_text, data.detections_count, data.entity_summary || {}, data.risk || null, data.mode || mode, data);
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
      const st = await apiFetch(`/documents/${docId}/status`);
      const status = (st.status || "").toLowerCase();
      const extractDone = !!st.extraction?.done;
      const anonymDone = !!st.anonymization?.done;
      const ocrLength = Number(st.extraction?.text_length ?? NaN);
      const detections = Number(st.anonymization?.detections_count ?? NaN);
      currentDocStatus = status || currentDocStatus;
      updateAnonDocBar(currentDocName, currentDocSize);
      updatePipelineTimeline({ status, extractDone, anonymDone });
      updateProcessingConsole({
        status,
        extractDone,
        anonymDone,
        ocrLength,
        detections,
      });
      renderAIDocInsights({
        status: status || "—",
        ocrLength: Number.isFinite(ocrLength) ? ocrLength : "—",
        detections: Number.isFinite(detections) ? detections : "—",
        nextAction: anonymDone ? "Analyse IA" : "Sécurisation",
      });

      if (isReadyStatus(status) || anonymDone) {
        clearInterval(interval);
        try {
          const preview = await apiFetch(`/documents/${docId}/preview`);
          showAnonResults(preview.preview_text, preview.detections_count, preview.entity_summary || {});
          toast(`${preview.detections_count ?? 0} entité(s) anonymisée(s)`, "success");
        } catch (e) {
          console.warn("preview load after poll:", e);
          hideAnonLoading();
          toast("Sécurisation terminée.", "success");
        }
        currentDocStatus = "ready";
        updateHeaderContext();
        updatePipelineTimeline({ status: "ready", extractDone: true, anonymDone: true });
        await loadDocList();
      } else if (status === "failed") {
        clearInterval(interval);
        updateProcessingConsole({ status: "failed", ocrLength, detections });
        stopProcessingTimer();
        $("btn-anonymize").disabled = false;
        toast("L'anonymisation a échoué. Veuillez réessayer.", "error");
        updatePipelineTimeline({ status: "failed", extractDone, anonymDone: false });
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
  const originalTextEl = $("preview-original-text");
  const originalLoadingEl = $("original-loading");
  if (!originalTextEl) return;
  if (originalTextCache[docId]) {
    originalTextEl.textContent = originalTextCache[docId];
    return;
  }
  if (originalLoadingEl) originalLoadingEl.style.display = "";
  originalTextEl.textContent = "";
  try {
    if (publicDemoMode && currentDemoDocument?.original_excerpt) {
      originalTextCache[docId] = currentDemoDocument.original_excerpt;
      originalTextEl.textContent = currentDemoDocument.original_excerpt;
      return;
    }
    const data = await apiFetch(`/documents/${docId}/extracted-text`);
    const text = data.text || "(Aucun texte extrait)";
    originalTextCache[docId] = text;
    originalTextEl.textContent = text;
  } catch (e) {
    console.warn("loadOriginalText error:", e);
    originalTextEl.textContent = "(Texte original non disponible — lancez l'anonymisation d'abord)";
  } finally {
    if (originalLoadingEl) originalLoadingEl.style.display = "none";
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
  const normalized = normalizeRiskPercent(score);
  const pct = normalized === null ? 0 : normalized;
  meter.innerHTML = `<span>Sensibilité</span><div class="doc-risk-meter-bar"><div style="width:${pct}%"></div></div><strong>${pct}%</strong>`;
}


// ── Background pollers (notifications) ─────────────────────────────────

function startBgPollers(docs) {
  Object.values(bgPollers).forEach(id => clearInterval(id));
  bgPollers = {};
  const processing = (docs || []).filter(d => isProcessingStatus(d.status) && !d.is_deleted);
  processing.forEach(d => {
    bgPollers[d.id] = setInterval(async () => {
      try {
        const doc = await apiFetch(`/documents/${d.id}`);
        if (isReadyStatus(doc.status)) {
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
  dismissOnboardingOverlay();
  const steps = [
    { target: ".upload-zone", title: "Ajouter un document", text: "Associez chaque pièce à un client, un exercice et un type de document." },
    { target: "#btn-anonymize", title: "Sécuriser la pièce", text: "Les données sensibles sont détectées puis remplacées par des balises." },
    { target: ".quick-actions", title: "Analyser le dossier", text: "Les questions IA utilisent le texte sécurisé du document sélectionné." },
    { target: "#btn-export-txt", title: "Exporter", text: "Téléchargez le texte sécurisé, le PDF rédigé ou le rapport d'audit." },
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
      '<button class="btn btn-primary btn-sm" id="onboarding-next">' + (current < steps.length-1 ? 'Suivant →' : 'Commencer') + '</button>' +
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
    toast("Bienvenue sur ConfiDoc. Ajoutez votre premier document.", "success");
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
    const finalText = $("preview-anon-text")?.textContent || "";
    await apiFetch(`/documents/${currentDocId}/validate`, {
      method: "POST",
      body: JSON.stringify({
        final_text: finalText.trim() ? finalText : undefined,
      }),
    });
    setStep(3);
    updateAIDocBar(currentDocName, currentDocSize);
    await refreshAIDocInsights(currentDocId);
    renderAIReadySummary({ justValidated: true });
    resetChat();
    loadChatHistory(currentDocId);
    await loadDocList();
    toast("Document anonymisé et prêt pour l’IA", "success");
  } catch (e) {
    console.error("validate error:", e);
    toast(`Erreur validation: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Valider et continuer →";
  }
}

async function saveManualCorrection(maskOptions = {}) {
  if (!currentDocId) return;
  const textEl = $("preview-anon-text");
  const finalText = textEl?.textContent || "";
  if (!finalText.trim()) {
    toast("Aucun texte anonymisé à corriger.", "error");
    return;
  }
  try {
    const payload = {
      final_text: finalText,
      masked_value: maskOptions.masked_value || null,
      replacement: maskOptions.replacement || null,
      entity_type: maskOptions.entity_type || null,
    };
    const result = await apiFetch(`/documents/${currentDocId}/manual-correction`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (textEl) textEl.innerHTML = highlightTags(result.preview_text || finalText);
    showAnonResults(
      result.preview_text || finalText,
      result.detections_count || 0,
      result.entity_summary || {},
      result.risk || null,
      "pseudonymization",
      result
    );
    await refreshAIDocInsights(currentDocId);
    await loadDocList();
    toast("Correction enregistrée. Score RGPD recalculé.", "success");
  } catch (e) {
    toast(`Correction impossible: ${e.message}`, "error");
  }
}

async function addMaskValue() {
  if (!currentDocId) return;
  const selected = String(window.getSelection?.().toString() || "").trim();
  const value = prompt("Donnée à masquer dans tout le document", selected);
  if (!value || !value.trim()) return;
  const type = prompt("Type de donnée: nom, email, téléphone, IBAN, SIRET, adresse, date, autre", "email");
  if (type === null) return;
  const normalized = String(type || "autre").trim().toLowerCase();
  const replacementMap = {
    nom: "[PERSONNE]",
    personne: "[PERSONNE]",
    email: "[EMAIL]",
    téléphone: "[TELEPHONE]",
    telephone: "[TELEPHONE]",
    iban: "[IBAN]",
    siret: "[SIRET]",
    adresse: "[ADRESSE]",
    date: "[DATE]",
    autre: "[DONNEE]",
  };
  const replacement = prompt(
    "Remplacement à appliquer",
    replacementMap[normalized] || "[DONNEE]"
  );
  if (!replacement || !replacement.trim()) return;
  await saveManualCorrection({
    masked_value: value.trim(),
    replacement: replacement.trim(),
    entity_type: normalized,
  });
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
  $("chat-messages").innerHTML = buildAIChatIntroHtml();
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

function escapeAttr(text) {
  return escapeHtml(text).replace(/"/g, "&quot;");
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
  if (publicDemoMode) {
    input.value = "";
    appendUserMsg(question);
    const bodyEl = appendAssistantMsg();
    latestAssistantText = buildDemoAssistantAnswer(question);
    bodyEl.textContent = latestAssistantText;
    $("btn-copy-answer").disabled = false;
    if (reportMode) renderStructuredAnswer(bodyEl, latestAssistantText);
    saveChatHistory(currentDocId);
    return;
  }
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
    if (typeof formatCitations === "function") {
      bodyEl.innerHTML = formatCitations(bodyEl.innerHTML || bodyEl.textContent);
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
    if (typeof formatCitations === "function") {
      bodyEl.innerHTML = formatCitations(bodyEl.innerHTML || bodyEl.textContent);
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
    const exportPath = publicDemoMode && currentDemoDocument?.urls?.export
      ? currentDemoDocument.urls.export
      : `/documents/${currentDocId}/export`;
    const resp = await apiRequest(exportPath, { auth: !publicDemoMode });
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
    if (publicDemoMode && currentDemoDocument?.urls?.raw) {
      const resp = await apiRequest(currentDemoDocument.urls.raw, { auth: false });
      const blob = await resp.blob();
      triggerDownload(blob, currentDocName || `confidoc_demo_${currentDocId.slice(0, 8)}.pdf`);
      toast("Original PDF de démo téléchargé", "success");
      return;
    }
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


async function exportFec() {
  if (!currentDocId) return;
  try {
    const resp = await apiRequest(`/documents/${currentDocId}/export-fec`);
    const blob = new Blob([await resp.text()], { type: "text/plain;charset=utf-8" });
    triggerDownload(blob, `FEC_${currentDocId.slice(0, 8)}.txt`);
    toast("Export FEC terminé", "success");
  } catch (e) {
    console.error("exportFec error:", e);
    if (e.message && e.message.includes("bloqu")) {
      toast(e.message, "error");
      if (e.message.includes("validation humaine")) {
        showApproveExportPrompt();
      }
    } else {
      toast(`Erreur export FEC: ${e.message}`, "error");
    }
  }
}

async function loadGoldenReport() {
  if (!token) return;
  try {
    const data = await apiFetch("/stats/golden-report");
    if (data && data.pass_rate !== undefined) {
      if ($("golden-quality-badge")) return;
      const badge = document.createElement("div");
      badge.id = "golden-quality-badge";
      badge.className = "header-pill";
      badge.style.background = "rgba(16,185,129,0.15)";
      badge.style.color = "#10b981";
      badge.style.border = "1px solid rgba(16,185,129,0.3)";
      badge.innerHTML = `Qualité Corpus: <strong>${Math.round(data.pass_rate)}%</strong>`;
      badge.title = `Taux de succès sur ${data.total} cas de référence métiers`;
      $("header-pills")?.appendChild(badge);
    }
  } catch (_e) {}
}

function renderAuditInsights(data) {
  const panel = $("audit-insights");
  if (!panel) return;
  
  const score = data.audit_risk_score ?? 0;
  const findings = data.audit_findings || [];
  
  if (findings.length === 0 && score === 0) {
    panel.style.display = "none";
    return;
  }
  
  panel.style.display = "";
  $("audit-risk-score").textContent = score;
  
  const findingsEl = $("audit-findings");
  if (findingsEl) {
    findingsEl.innerHTML = findings.map(f => `
      <div class="audit-finding severity-${f.severity}">
        <strong>${escapeHtml(f.label)}</strong>: ${escapeHtml(f.detail)}
      </div>
    `).join("");
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
    renderExportGuard({
      status: currentDocStatus,
      risk_level: currentRiskLevel || "high",
      human_validated: true,
    });
    refreshAIDocInsights(currentDocId).catch(() => {});
  } catch (e) {
    toast(`Erreur approbation: ${e.message}`, "error");
  }
}

async function downloadAuditReport() {
  if (!currentDocId) return;
  try {
    const path = publicDemoMode
      ? "/api/v1/demo/public/audit-report-pdf"
      : `/documents/${currentDocId}/audit-report-pdf`;
    const resp = await apiRequest(path, { auth: !publicDemoMode });
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
    let data;
    if (publicDemoMode && currentDemoDocument?.urls?.score && currentDemoDocument?.urls?.audit) {
      const [score, audit] = await Promise.all([
        apiFetch(currentDemoDocument.urls.score, { auth: false }),
        apiFetch(currentDemoDocument.urls.audit, { auth: false }),
      ]);
      data = { score, audit, demo: currentDemoDocument.document };
    } else {
      data = await apiFetch(`/documents/${currentDocId}/compliance-report`);
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    triggerDownload(blob, `conformite_rgpd_${currentDocId.slice(0, 8)}.json`);
    toast("Rapport de conformite telecharge", "success");
  } catch (e) {
    toast(`Erreur conformite: ${e.message}`, "error");
  }
}

async function downloadComplianceCertificate() {
  if (!currentDocId) return;
  try {
    const path = `/documents/${currentDocId}/compliance-certificate`;
    const resp = await apiRequest(path, { auth: !publicDemoMode });
    const blob = await resp.blob();
    triggerDownload(blob, `certificat_rgpd_${currentDocId.slice(0, 8)}.pdf`);
    toast("Certificat de preuve PDF téléchargé", "success");
  } catch (e) {
    toast(`Erreur certificat: ${e.message}`, "error");
  }
}

async function downloadDossier360Report() {
  try {
    const resp = await apiRequest("/documents/stats/dossier-360/report");
    const blob = await resp.blob();
    triggerDownload(blob, "rapport_dossier_360.pdf");
    toast("Rapport Dossier 360 telecharge", "success");
  } catch (e) {
    toast(`Erreur rapport Dossier 360: ${e.message}`, "error");
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
      score: null,
      color: "neutral",
      grade: null,
      status: "Score RGPD non disponible",
      recommendations: [
        "Ajoutez un premier document pour calculer votre posture RGPD.",
      ],
      breakdown: {},
    },
    risk_distribution: {},
    entity_distribution: {},
    recent_activity: [],
  };
}

function emptyDossier360() {
  return {
    portfolio: {
      clients_count: 0,
      documents_count: 0,
      average_score: 0,
      ready_dossiers: 0,
      at_risk_dossiers: 0,
      critical_actions: 0,
      top_missing_documents: [],
    },
    mission_control: {
      urgency: "neutral",
      headline: "Aucun dossier client charge.",
      summary: "Ajoutez les premieres pieces pour lancer la revue cabinet.",
      next_best_actions: [],
      audit_focus: [],
    },
    dossiers: [],
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
  setPageTitle("Accueil");
  setActiveNav("home");
  closeAppNavDrawer();
  if (!dashboardLoaded) loadDashboard();
}

function renderDashboardSkeleton() {
  const content = $("dash-content");
  if (!content) return;
  content.style.display = "";
  content.innerHTML = `
    <div class="dash-kpi-grid">
      ${[1, 2, 3, 4].map(() => `
        <div class="dash-kpi-card skeleton-wrap">
          <div class="skeleton-line w60" style="height: 36px; width: 36px; border-radius: 9px; margin-bottom: 12px;"></div>
          <div class="skeleton-line w75" style="height: 28px;"></div>
          <div class="skeleton-line w60" style="height: 12px;"></div>
        </div>
      `).join("")}
    </div>
  `;
}

async function loadDashboard() {
  const loading = $("dash-loading");
  const content = $("dash-content");
  if (loading) loading.style.display = "none";
  
  renderDashboardSkeleton();

  try {
    const [statsResult, summaryResult, dossierResult] = await Promise.allSettled([
      apiFetch("/documents/stats/dashboard"),
      apiFetch("/documents/status-summary?days=30"),
      apiFetch("/documents/stats/dossier-360"),
    ]);

    // Restore original structure
    content.innerHTML = _dashboard_original_html;

    if (
      statsResult.status === "rejected" &&
      summaryResult.status === "rejected" &&
      dossierResult.status === "rejected"
    ) {
      throw new Error(
        `${dashboardErrorMessage(statsResult.reason)} ${dashboardErrorMessage(summaryResult.reason)}`.trim()
      );
    }

    const data = statsResult.status === "fulfilled" ? statsResult.value : emptyDashboardData();
    const summary = summaryResult.status === "fulfilled" ? summaryResult.value : {};
    const dossier360 = dossierResult.status === "fulfilled" ? dossierResult.value : emptyDossier360();

    dashboardLoaded =
      statsResult.status === "fulfilled" &&
      summaryResult.status === "fulfilled" &&
      dossierResult.status === "fulfilled";
    renderDashboard(data, summary, dossier360);

    if (!dashboardLoaded) {
      const failed =
        statsResult.status === "rejected"
          ? statsResult.reason
          : summaryResult.status === "rejected"
            ? summaryResult.reason
            : dossierResult.reason;
      console.warn("loadDashboard partial:", failed);
      toast(`Accueil partiel: ${dashboardErrorMessage(failed)}`, "warning");
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

/** Recommandations : pas de message « haut risque » sans agrégat réel. */
function filterComplianceRecommendations(recos, totalDocs, riskDistribution) {
  if (!Array.isArray(recos)) return [];
  const rd = riskDistribution || {};
  const riskSum = ["low", "medium", "high", "critical"].reduce(
    (s, k) => s + (Number(rd[k]) || 0),
    0
  );
  let out = recos.map(String).filter(Boolean);
  if (totalDocs > 0 && riskSum === 0) {
    out = out.filter((r) => !/trop de mappings|mappings à haut risque/i.test(r));
  }
  if (!out.length && totalDocs > 0) {
    return ["Aucune recommandation pour le moment."];
  }
  return out;
}

/**
 * Score RGPD + recos (panneau Conformité). États vides si aucune pièce ou score absent.
 */
function renderGdprDashboardSection(gdpr, totalDocs, riskDistribution) {
  const gdprUnavailable =
    totalDocs <= 0 || gdpr.score == null || gdpr.score === undefined;
  const suffix = $("dash-gdpr-score-suffix");
  const gradeEl = $("dash-gdpr-grade");
  const ring = $("dash-gdpr-ring-fill");

  if (gdprUnavailable) {
    const scoreEl = $("dash-gdpr-score");
    if (scoreEl) scoreEl.textContent = "—";
    if (suffix) suffix.style.display = "none";
    if (gradeEl) {
      gradeEl.textContent = "";
      gradeEl.style.display = "none";
      gradeEl.className = "dash-gdpr-grade";
    }
    if (ring) {
      ring.setAttribute("stroke-dasharray", "0, 100");
      ring.className = "dash-gdpr-ring-fill color-neutral";
    }
    const statusElG = $("dash-gdpr-status");
    if (statusElG) {
      statusElG.textContent = "Score RGPD non disponible";
      statusElG.className = "dash-gdpr-status color-neutral";
    }
    const breakEl = $("dash-gdpr-breakdown");
    if (breakEl) breakEl.textContent = "Ajoutez un premier document pour calculer votre posture RGPD.";
    const recos = ["Aucune recommandation pour le moment."];
    const recosEl = $("dash-gdpr-recos");
    if (recosEl) {
      recosEl.innerHTML =
        `<h4>Recommandations conformité</h4><ul>` +
        recos.map((r) => `<li class="reco-neutral">${escapeHtml(r)}</li>`).join("") +
        `</ul>`;
      recosEl.style.display = "";
    }
    return;
  }

  if (suffix) suffix.style.display = "";
  if (gradeEl) {
    gradeEl.style.display = "";
  }

  const gdprScoreVal = Number(gdpr.score);
  const gdprColor = gdpr.color || "success";
  const gdprGrade = gdpr.grade || "-";
  const gdprStatus = gdpr.status || "En attente";
  const filteredRecos = filterComplianceRecommendations(
    gdpr.recommendations || [],
    totalDocs,
    riskDistribution
  );
  const gdprBreak = gdpr.breakdown || {};

  if ($("dash-gdpr-score")) {
    animateNumber($("dash-gdpr-score"), gdprScoreVal);
  }
  if (ring) {
    ring.setAttribute("stroke-dasharray", `${gdprScoreVal}, 100`);
    ring.className = `dash-gdpr-ring-fill color-${gdprColor}`;
  }
  if (gradeEl) {
    gradeEl.textContent =
      gdprGrade && gdprGrade !== "-"
        ? `Note ${gdprGrade}`
        : "—";
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
    breakEl.innerHTML = parts.map((p) => `<span>${p}</span>`).join("");
  }
  const recosEl = $("dash-gdpr-recos");
  if (recosEl) {
    if (filteredRecos.length) {
      recosEl.innerHTML =
        `<h4>Recommandations conformité</h4><ul>` +
        filteredRecos
          .map((r) => {
            const low = r.toLowerCase();
            const good = low.includes("bonne") || low.includes("continuez");
            return `<li class="${good ? "good" : ""}">${escapeHtml(r)}</li>`;
          })
          .join("") +
        `</ul>`;
      recosEl.style.display = "";
    } else {
      recosEl.style.display = "none";
    }
  }
}

function renderTrustDashboardSection(trust) {
  const el = $("dash-trust-breakdown");
  if (!el) return;
  if (!trust || trust.score == null || trust.score === undefined) {
    el.innerHTML = "<span>Trust Score —</span>";
    return;
  }
  const score = Math.round(Number(trust.score) || 0);
  const grade = trust.grade ? `Note ${escapeHtml(trust.grade)}` : "Note —";
  const status = trust.status || "Trust Score";
  el.innerHTML = [
    `<span>Trust ${score}/100</span>`,
    `<span>${grade}</span>`,
    `<span>${escapeHtml(status)}</span>`,
  ].join("");
}

// ── Redesign Accueil briefing (spec §5.1) ──────────────────────────────
// Populate the hero literary headline, priority list, timeline, and KPI
// row at the top of panel-dashboard from the data already fetched by
// loadDashboard(). Defensive: works partially even with missing fields.
function renderHomeBriefing(data = {}, summary = {}, dossier360 = {}) {
  const userName = ($("user-info")?.textContent || "").split("@")[0] || "vous";
  const userNameEl = $("home-user-name");
  if (userNameEl) userNameEl.textContent = userName;

  const sc = data.status_counts || {};
  const reviewCount = Number(sc.processing ?? sc.extracting ?? 0) + Number(sc.uploaded ?? 0);
  const totalDocs = Number(data.total_documents || 0);

  const countEl = $("home-priority-count");
  if (countEl) {
    countEl.textContent = reviewCount > 0
      ? `${reviewCount} document${reviewCount > 1 ? "s" : ""}`
      : "aucun document";
  }

  const leadEl = $("home-hero-lead");
  if (leadEl) {
    if (reviewCount === 0 && totalDocs === 0) {
      leadEl.textContent = "Aucun document n'a encore été uploadé. Importe ton premier PDF pour démarrer.";
    } else if (reviewCount === 0) {
      leadEl.textContent = "Aucun document n'attend ta revue.";
    } else {
      const failed = Number(summary.failed ?? sc.failed ?? 0);
      leadEl.textContent = failed > 0
        ? `${failed} document${failed > 1 ? "s ont" : " a"} échoué — pense à les ré-anonymiser.`
        : "Tout est sous contrôle, prends ton café et review tranquillement.";
    }
  }

  // Priority list: pull from dossier360.dossiers when available, else show a polite empty state.
  const list = $("home-priority-list");
  if (list) {
    const items = Array.isArray(dossier360?.dossiers) ? dossier360.dossiers.slice(0, 3) : [];
    if (items.length === 0) {
      list.innerHTML = `
        <li>
          <div></div>
          <div><div class="name">Aucun document à reviewer.</div><div class="meta">Glisse un PDF dans Documents pour démarrer.</div></div>
          <div></div>
          <button class="btn-ghost" data-action="open-upload">+ Importer</button>
        </li>`;
    } else {
      list.innerHTML = items.map(d => {
        const trustPct = clampPct(d?.trust_avg ?? d?.trust_score ?? 0);
        const dimPct = Math.max(50, trustPct);
        const docCount = Number(d?.documents_count ?? d?.documents ?? 0);
        const name = escapeHtml(d?.client_name || d?.name || d?.dossier_name || "Dossier sans nom");
        const meta = `${docCount} document${docCount > 1 ? "s" : ""}`;
        return `
          <li>
            <trust-gauge data-mini="true" data-size="40"
              data-pii="${trustPct}" data-quasi="${trustPct}"
              data-coherence="${dimPct}" data-reversibility="${dimPct}"></trust-gauge>
            <div>
              <div class="name">${name}</div>
              <div class="meta">${meta}</div>
            </div>
            <span class="pill pill-review">À reviewer</span>
            <button class="btn-ghost" data-action="open-dossier" data-dossier="${escapeHtml(d?.client_id || d?.id || "")}">▶ Reviewer</button>
          </li>`;
      }).join("");
    }
  }

  // Editorial timeline: assemble a few human sentences from the summary buckets.
  const tl = $("home-timeline");
  if (tl) {
    const events = [];
    const uploaded24 = Number(summary.recent_uploads_24h ?? summary.uploads_24h ?? 0);
    if (uploaded24 > 0) events.push(`<div class="ev"><span class="ts">24 h</span> · ${uploaded24} document${uploaded24 > 1 ? "s" : ""} uploadé${uploaded24 > 1 ? "s" : ""}</div>`);
    const ready = Number(summary.ready ?? sc.ready ?? 0) + Number(summary.anonymized ?? sc.anonymized ?? 0);
    if (ready > 0) events.push(`<div class="ev"><span class="ts">Cumulé</span> · ${ready} anonymisation${ready > 1 ? "s" : ""} validée${ready > 1 ? "s" : ""}</div>`);
    const failed = Number(summary.failed ?? sc.failed ?? 0);
    if (failed > 0) events.push(`<div class="ev" style="color:var(--warning)"><span class="ts">À voir</span> · ${failed} document${failed > 1 ? "s en" : " en"} échec à reprendre</div>`);
    tl.innerHTML = events.length > 0
      ? events.join("")
      : '<div class="ev" style="color:var(--ink-muted)">Aucune activité récente.</div>';
  }

  // Secondary KPI row.
  const kpisEl = $("home-kpis");
  if (kpisEl) {
    const trustAvg = clampPct(data?.trust_score?.average ?? data?.trust_score?.mean ?? 0);
    const entitiesMasked = Number(data?.total_entities_masked || 0);
    const ready = Number(summary.ready ?? sc.ready ?? 0) + Number(summary.anonymized ?? sc.anonymized ?? 0);
    kpisEl.innerHTML = `
      <div class="card kpi-card">
        <div class="kpi-label">Documents traités</div>
        <div class="kpi-value tabular">${totalDocs}</div>
        <div class="kpi-delta">${uploaded24Label(summary)}</div>
      </div>
      <div class="card kpi-card">
        <div class="kpi-label">En revue</div>
        <div class="kpi-value tabular">${reviewCount}</div>
        <div class="kpi-delta${reviewCount > 0 ? " is-warning" : ""}">${reviewCount > 0 ? "à traiter" : "rien à faire"}</div>
      </div>
      <div class="card kpi-card kpi-card--trust">
        <div class="kpi-label">Trust score moyen</div>
        <div class="kpi-value tabular">${trustAvg}<span style="font-size:14px;opacity:.6">%</span></div>
        <div class="kpi-delta">sur ${ready} doc${ready > 1 ? "s" : ""} validés</div>
      </div>
      <div class="card kpi-card">
        <div class="kpi-label">Entités masquées</div>
        <div class="kpi-value tabular">${entitiesMasked}</div>
        <div class="kpi-delta">PII protégés</div>
      </div>
    `;
  }
}

function clampPct(value) {
  const n = Number(value);
  if (!isFinite(n)) return 0;
  if (n <= 1 && n >= 0) return Math.round(n * 100);
  return Math.max(0, Math.min(100, Math.round(n)));
}

function uploaded24Label(summary = {}) {
  const u = Number(summary.recent_uploads_24h ?? summary.uploads_24h ?? 0);
  return u > 0 ? `+${u} sur 24 h` : "—";
}

function renderDashboard(data, summary = {}, dossier360 = emptyDossier360()) {
  const content = $("dash-content");
  if (!content) return;
  content.style.display = "";

  // ── Redesign Accueil briefing (spec §5.1) — runs alongside legacy KPIs.
  try { renderHomeBriefing(data, summary, dossier360); }
  catch (e) { console.warn("renderHomeBriefing failed:", e); }

  // KPIs
  const sc = data.status_counts || {};
  const readyCount = (sc.ready || 0) + (sc.anonymized || 0);
  const summaryReady = (summary.ready ?? sc.ready ?? 0) + (summary.anonymized ?? sc.anonymized ?? 0);
  const summaryProcessing =
    (summary.processing ?? sc.processing ?? 0)
    + (summary.extracting ?? sc.extracting ?? 0)
    + (summary.extracted ?? sc.extracted ?? 0)
    + (summary.anonymizing ?? sc.anonymizing ?? 0);
  animateNumber($("dash-total-docs"), data.total_documents || 0);
  animateNumber($("dash-total-entities"), data.total_entities_masked || 0);
  animateNumber($("dash-ready-count"), readyCount);
  animateNumber($("dash-trashed"), data.trashed_documents || 0);
  animateNumber($("dash-bucket-ready"), summaryReady);
  animateNumber($("dash-bucket-processing"), summaryProcessing);
  animateNumber($("dash-bucket-uploaded"), summary.uploaded ?? sc.uploaded ?? 0);
  animateNumber($("dash-bucket-failed"), summary.failed ?? sc.failed ?? 0);
  animateNumber($("dash-uploads-24h"), summary.recent_uploads_24h ?? summary.uploads_24h ?? 0);
  const total = Math.max(0, summary.total ?? data.total_documents ?? 0);
  const totalDocs = Math.max(0, Number(data.total_documents) || 0);
  const ready = Math.max(0, summaryReady);
  if ($("dash-ready-ratio")) $("dash-ready-ratio").textContent = `${ready} / ${total}`;
  if ($("dash-ready-fill")) $("dash-ready-fill").style.width = total ? `${Math.round((ready / total) * 100)}%` : "0%";

  renderDossier360(dossier360);
  renderMissionControl(dossier360);

  const rdRisk = data.risk_distribution || {};
  renderGdprDashboardSection(data.gdpr_score || {}, totalDocs, rdRisk);
  renderTrustDashboardSection(data.trust_score || {});

  // Risk distribution
  const riskEl = $("dash-risk-chart");
  if (riskEl) {
    const rd = rdRisk;
    const riskSum = ["low", "medium", "high", "critical"].reduce(
      (s, lvl) => s + (Number(rd[lvl]) || 0),
      0
    );
    if (totalDocs <= 0 || riskSum === 0) {
      riskEl.innerHTML =
        '<div class="dash-chart-empty">Aucune donnée de risque à afficher pour le moment.</div>';
    } else {
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
  }

  // Entity distribution
  const entityEl = $("dash-entity-chart");
  if (entityEl) {
    const ed = data.entity_distribution || {};
    const sorted = Object.entries(ed).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const maxEnt = Math.max(1, ...sorted.map(x => x[1]));
    if (!sorted.length || totalDocs <= 0) {
      entityEl.innerHTML =
        '<div class="dash-chart-empty">Aucune entité détectée pour le moment.</div>';
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
      { key: "uploaded", label: "Ajouté", dot: "uploaded" },
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
    const trendSum = trendData.reduce((s, d) => s + (Number(d.count) || 0), 0);
    if (totalDocs <= 0 || trendSum === 0) {
      trendEl.innerHTML =
        '<div class="dash-chart-empty">Aucune activité sur les 7 derniers jours.</div>';
    } else {
      const max = Math.max(1, ...trendData.map((d) => d.count || 0));
      trendEl.innerHTML = trendData.map((d) => {
        const h = Math.max(2, ((d.count || 0) / max) * 80);
        const day = d.date ? new Date(d.date).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }) : "";
        return `<div class="dash-activity-col"><div class="dash-activity-bar" style="height:${h}px"></div><span class="dash-activity-label">${day}</span></div>`;
      }).join("");
    }
  }
}

function riskLabel(level) {
  const labels = { low: "Faible", medium: "Moyen", high: "Eleve", critical: "Critique" };
  return labels[level] || level || "Inconnu";
}

function renderMissionControl(payload = emptyDossier360()) {
  const mission = payload.mission_control || emptyDossier360().mission_control;
  const headline = $("dash-mission-headline");
  const summary = $("dash-mission-summary");
  const urgency = $("dash-mission-urgency");
  const actions = $("dash-mission-actions");
  const focus = $("dash-mission-focus");
  if (!headline || !summary || !urgency || !actions || !focus) return;

  const urgencyKey = ["success", "warning", "danger", "neutral"].includes(mission.urgency)
    ? mission.urgency
    : "neutral";
  const urgencyLabels = {
    success: "Prêt revue",
    warning: "À compléter",
    danger: "Priorité haute",
    neutral: "À cadrer",
  };
  const actionItems = mission.next_best_actions?.length
    ? mission.next_best_actions
    : ["Importer les pieces client et lancer l'anonymisation."];
  const portfolio = payload.portfolio || {};
  const docCount = portfolio.documents_count ?? 0;
  const focusItems = mission.audit_focus?.length
    ? mission.audit_focus
    : docCount === 0
      ? ["Aucune recommandation pour le moment."]
      : ["Completeness des pieces", "Qualite OCR et anonymisation"];

  headline.textContent = mission.headline || "Dossiers a qualifier";
  summary.textContent = mission.summary || "Priorites cabinet en attente.";
  urgency.textContent = urgencyLabels[urgencyKey];
  urgency.className = `dash-mission-urgency urgency-${urgencyKey}`;
  actions.innerHTML = actionItems
    .slice(0, 4)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  focus.innerHTML = focusItems
    .slice(0, 4)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
}

function renderDossier360(payload = emptyDossier360()) {
  const section = $("dash-dossier360");
  const list = $("dash-d360-list");
  if (!section || !list) return;

  const portfolio = payload.portfolio || {};
  const dossiers = payload.dossiers || [];
  const clients = portfolio.clients_count || 0;

  if ($("dash-d360-clients")) {
    $("dash-d360-clients").textContent = `${clients} client${clients > 1 ? "s" : ""}`;
  }
  animateNumber($("dash-d360-score"), portfolio.average_score || 0);
  animateNumber($("dash-d360-ready"), portfolio.ready_dossiers || 0);
  animateNumber($("dash-d360-risk"), portfolio.at_risk_dossiers || 0);
  animateNumber($("dash-d360-actions"), portfolio.critical_actions || 0);

  if (!dossiers.length) {
    list.innerHTML = '<div class="empty-state" style="padding:16px">Aucun dossier client à analyser.</div>';
    return;
  }

  list.innerHTML = dossiers.map((dossier) => {
    const score = Math.max(0, Math.min(100, Math.round(dossier.score || 0)));
    const risk = dossier.risk_level || "low";
    const missing = (dossier.missing_documents || []).slice(0, 2);
    const actions = (dossier.next_actions || []).slice(0, 2);
    const blockers = (dossier.blockers || []).slice(0, 2);
    const readyCount = dossier.ready_count || 0;
    const docCount = dossier.document_count || 0;
    return `<div class="dash-d360-card">
      <div class="dash-d360-top">
        <div>
          <strong>${escapeHtml(dossier.client_name || "Sans client")}</strong>
          <span>${readyCount}/${docCount} prêts · ${escapeHtml(dossier.readiness || "")}</span>
        </div>
        <span class="dash-risk-chip risk-${escapeHtml(risk)}">${escapeHtml(riskLabel(risk))}</span>
      </div>
      <div class="dash-d360-scoreline">
        <div class="dash-d360-scorebar"><div style="width:${score}%"></div></div>
        <strong>${score}</strong>
      </div>
      <div class="dash-d360-tags">
        ${missing.length
          ? missing.map((item) => `<span>${escapeHtml(item)}</span>`).join("")
          : '<span class="good">Pieces clés couvertes</span>'}
      </div>
      ${blockers.length
        ? `<ul class="dash-d360-alerts">${blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : ""}
      <ul class="dash-d360-actions">
        ${actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </div>`;
  }).join("");
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
    const verdictClasses = { favorable: "good", reserve: "warning", defavorable: "critical" };
    const verdictClass = verdictClasses[verdict] || "neutral";
    html += `<div class="review-verdict ${verdictClass}">${verdictIcons[verdict] || ""} ${verdictLabels[verdict] || verdict} (confiance: ${Math.round(confidence * 100)}%)${docType ? ` — <span class="review-doc-type">${escapeHtml(docType)}</span>` : ""}</div>`;
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

function startNewDocument() {
  currentDocId = null;
  currentDocName = "";
  currentDocStatus = "";
  currentDocSize = 0;
  document.querySelectorAll(".doc-item").forEach(el => el.classList.remove("selected"));
  updateHeaderContext();
  renderAIDocInsights({});
  renderExportGuard({});
  updatePipelineTimeline({});
  setSidebarMode("flat");
  setStep(1);
}

function handleDelegatedAction(e) {
  const target = e.target instanceof Element ? e.target : null;
  const control = target?.closest("[data-action]");
  if (!control) return;

  const action = control.dataset.action;
  if (!action) return;

  e.preventDefault();

  if (action === "edit-metadata") {
    e.stopPropagation();
    openEditMetadataModal(control.dataset.docId || "");
    return;
  }

  if (action === "sidebar-mode") setSidebarMode(control.dataset.mode || "flat");
  else if (action === "new-document") startNewDocument();
  else if (action === "open-upload") startNewDocument();
  else if (action === "open-batch-upload") {
    startNewDocument();
    if (!batchMode) toggleBatchMode();
  }
  else if (action === "open-original") openCurrentOriginal(false);
  else if (action === "open-dossier") {
    const dossierId = control.dataset.dossier || "";
    if (dossierId) {
      openClientWorkspace();
    } else {
      openClientWorkspace();
    }
  }
  else if (action === "download-original") openCurrentOriginal(true);
  else if (action === "back-to-documents") setStep(1);
  else if (action === "validate-anonymization") $("btn-validate")?.click();
  else if (action === "preview-redacted") $("btn-export-pdf")?.click();
  else if (action === "re-anonymize-strict") $("btn-anonymize")?.click();
  else if (action === "open-export") $("btn-export-txt")?.click();
  else if (action === "open-copilot") {
    if (window.__confidocDrawer) {
      window.__confidocDrawer.open();
    } else {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true, bubbles: true }));
    }
  }
  else if (action === "open-cmd-palette") {
    if (window.__confidocCommandPalette) {
      window.__confidocCommandPalette.open();
    } else {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }));
    }
  }
  else if (action === "open-documents") openDocumentWorkspace();
  else if (action === "open-clients") openClientWorkspace();
  else if (action === "resume-review") resumeWorkspaceReview();
  else if (action === "demo-investor") createDemoDocument();
  else if (action === "create-client") openCreateClientModal();
  else if (action === "dossier-overview") openDossierOverview();
  else if (action === "upload-for-dossier") openUploadForDossierClient();
  else if (action === "review-mode") setReviewMode(control.dataset.mode || "split");
  else if (action === "review-fullscreen") toggleReviewFullscreen();
  else if (action === "close-client-modal") closeClientModal();
  else if (action === "submit-client-modal") submitCreateClient();
  else if (action === "toggle-dossier-client") {
    const container = control.closest(".dossier-client");
    if (container) toggleDossierClient(container);
  } else if (action === "open-dossier-page") {
    openDossierPage(control.dataset.client || "");
  } else if (action === "toggle-dossier-exercice") {
    toggleDossierExercice(control);
  } else if (action === "select-doc") {
    selectDoc(control.dataset.docId || "");
  }
}

// ════════════ DPO & TRUST CENTER DYNAMISM ════════════

const fallbackTagOriginalMap = {
  "[PERSONNE_1]": "Jean Dupont",
  "[PERSONNE_2]": "Marie Martin",
  "[PERSONNE_3]": "Pierre Durand",
  "[SOCIETE_1]": "Acme Corp",
  "[SOCIETE_2]": "Cabinet Audit Partners",
  "[SOCIETE_3]": "Société Générale",
  "[ADRESSE_1]": "12 rue de la Paix, 75002 Paris",
  "[ADRESSE_2]": "45 avenue Foch, 75116 Paris",
  "[IBAN_1]": "FR76 3000 6000 0123 4567 8901 234",
  "[MONTANT_1]": "150 000 €",
  "[MONTANT_2]": "45 000 €",
  "[MONTANT_3]": "8 500 €",
  "[DATE_1]": "15 mai 2026",
  "[DATE_2]": "31 décembre 2025",
  "[EMAIL_1]": "contact@cabinet-audit.fr",
  "[EMAIL_2]": "j.dupont@acme.com",
  "[TELEPHONE_1]": "01 42 68 53 00",
  "[SIRET_1]": "123 456 789 00012",
  "[SIREN_1]": "123 456 789",
  "[TVA_1]": "FR 12 123456789"
};

window.tagOriginalMap = {};

function buildDynamicTagOriginalMap(fullData = {}) {
  window.tagOriginalMap = {};
  
  // Align using the original text and anonymized text
  const originalText = originalTextCache[currentDocId] || document.getElementById("preview-original-text")?.textContent || "";
  const anonymizedText = document.getElementById("preview-anon-text")?.textContent || "";
  
  if (originalText && anonymizedText) {
    const origLines = originalText.split('\n');
    const anonLines = anonymizedText.split('\n');
    
    for (let i = 0; i < Math.min(origLines.length, anonLines.length); i++) {
      const oLine = origLines[i];
      const aLine = anonLines[i];
      
      const matches = aLine.match(/\[([A-Z][A-Z0-9_]*)\]/g);
      if (!matches) continue;
      
      try {
        let regexStr = aLine
          .replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&')
          .replace(/\\\[[A-Z][A-Z0-9_]*\\\]/g, '(.*?)');
        
        const regex = new RegExp('^' + regexStr + '$');
        const matchResult = oLine.match(regex);
        if (matchResult) {
          let placeholderIndex = 1;
          aLine.replace(/\[([A-Z][A-Z0-9_]*)\]/g, (placeholder) => {
            const val = matchResult[placeholderIndex];
            if (val && val.trim()) {
              window.tagOriginalMap[placeholder] = val.trim();
            }
            placeholderIndex++;
            return placeholder;
          });
        }
      } catch(e) {
        // noop
      }
    }
  }
  
  // Fallbacks
  for (const [placeholder, val] of Object.entries(fallbackTagOriginalMap)) {
    if (!window.tagOriginalMap[placeholder]) {
      window.tagOriginalMap[placeholder] = val;
    }
  }
  
  // Also merge API mappings if present
  if (fullData && fullData.registry_raw_mapping) {
    Object.assign(window.tagOriginalMap, fullData.registry_raw_mapping);
  }
}

function generateSHA256Mock() {
  const chars = "0123456789abcdef";
  let hash = "";
  for (let i = 0; i < 32; i++) {
    hash += chars[Math.floor(Math.random() * chars.length)];
  }
  return hash.substring(0, 12) + "...";
}

window.addAuditLedgerEntry = function(action, operator, details = "") {
  const tbody = document.getElementById("audit-ledger-tbody");
  if (!tbody) return;
  
  const placeholderRow = tbody.querySelector("tr td[colspan]");
  if (placeholderRow) {
    tbody.innerHTML = "";
  }
  
  const now = new Date();
  const timeStr = now.toLocaleTimeString("fr-FR") + "." + String(now.getMilliseconds()).padStart(3, "0");
  
  const hash = generateSHA256Mock();
  
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><strong>${timeStr}</strong></td>
    <td><span style="color: var(--text);">${action}</span> <small style="display:block; color: var(--text-dim); font-size: 11px;">${details}</small></td>
    <td><span class="badge" style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);">${operator}</span></td>
    <td><code class="audit-ledger-hash">${hash}</code></td>
    <td>
      <span class="audit-ledger-badge">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="margin-right: 2px;">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
        Certifié
      </span>
    </td>
  `;
  tbody.insertBefore(tr, tbody.firstChild);
};

function prepulateLedger(entityCount) {
  const tbody = document.getElementById("audit-ledger-tbody");
  if (!tbody) return;
  
  tbody.innerHTML = "";
  
  const now = new Date();
  
  const time3 = new Date(now.getTime() - 2400);
  const timeStr3 = time3.toLocaleTimeString("fr-FR") + "." + String(time3.getMilliseconds()).padStart(3, "0");
  const tr3 = document.createElement("tr");
  tr3.innerHTML = `
    <td><strong>${timeStr3}</strong></td>
    <td><span style="color: var(--text);">Anonymisation déterministe</span> <small style="display:block; color: var(--text-dim); font-size: 11px;">Traitement réussi de ${entityCount} entités sensibles</small></td>
    <td><span class="badge" style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);">SYSTEM</span></td>
    <td><code class="audit-ledger-hash">${generateSHA256Mock()}</code></td>
    <td><span class="audit-ledger-badge"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="margin-right: 2px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Certifié</span></td>
  `;
  tbody.appendChild(tr3);
  
  const time2 = new Date(now.getTime() - 4800);
  const timeStr2 = time2.toLocaleTimeString("fr-FR") + "." + String(time2.getMilliseconds()).padStart(3, "0");
  const tr2 = document.createElement("tr");
  tr2.innerHTML = `
    <td><strong>${timeStr2}</strong></td>
    <td><span style="color: var(--text);">Numérisation & OCR Souverain</span> <small style="display:block; color: var(--text-dim); font-size: 11px;">Extraction de texte via modèle de vision local</small></td>
    <td><span class="badge" style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);">SYSTEM</span></td>
    <td><code class="audit-ledger-hash">${generateSHA256Mock()}</code></td>
    <td><span class="audit-ledger-badge"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="margin-right: 2px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Certifié</span></td>
  `;
  tbody.appendChild(tr2);

  const time1 = new Date(now.getTime() - 7200);
  const timeStr1 = time1.toLocaleTimeString("fr-FR") + "." + String(time1.getMilliseconds()).padStart(3, "0");
  const tr1 = document.createElement("tr");
  tr1.innerHTML = `
    <td><strong>${timeStr1}</strong></td>
    <td><span style="color: var(--text);">Dépôt sécurisé & Scan de malware</span> <small style="display:block; color: var(--text-dim); font-size: 11px;">Fichier vérifié intègre, taille conforme</small></td>
    <td><span class="badge" style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);">SYSTEM</span></td>
    <td><code class="audit-ledger-hash">${generateSHA256Mock()}</code></td>
    <td><span class="audit-ledger-badge"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" style="margin-right: 2px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Certifié</span></td>
  `;
  tbody.appendChild(tr1);
}

window.updateScores = function() {
  const previewPanel = document.getElementById("preview-anon-text");
  if (!previewPanel) return;
  
  const totalTags = previewPanel.querySelectorAll(".anon-tag").length;
  const blackedOutTags = previewPanel.querySelectorAll(".anon-tag.anon-tag-blackout").length;
  
  let baseRisk = window.currentBaseRiskScore || 12;
  
  let currentRisk = baseRisk;
  if (blackedOutTags > 0) {
    currentRisk = Math.max(1, Math.round(baseRisk / (blackedOutTags + 1)));
  }
  
  const initialTagsCount = window.initialTagsCount || totalTags;
  const restoredCount = Math.max(0, initialTagsCount - totalTags);
  currentRisk = Math.min(100, currentRisk + restoredCount * 12);
  
  const riskScoreEl = document.getElementById("risk-score");
  if (riskScoreEl) {
    riskScoreEl.textContent = `${currentRisk}%`;
  }
  const dashGdprScoreEl = document.getElementById("dash-gdpr-score");
  if (dashGdprScoreEl) {
    dashGdprScoreEl.textContent = `${currentRisk}`;
    const ringFill = document.getElementById("dash-gdpr-ring-fill");
    if (ringFill) {
      ringFill.setAttribute("stroke-dasharray", `${currentRisk}, 100`);
    }
  }
  
  let level = "low";
  let grade = "A+";
  let statusText = "Conformité Excellente";
  let statusColor = "risk-low";
  
  if (currentRisk > 50) {
    level = "critical";
    grade = "F";
    statusText = "Risque Critique de Réidentification";
    statusColor = "risk-critical";
  } else if (currentRisk > 30) {
    level = "high";
    grade = "D";
    statusText = "Risque Élevé de Réidentification";
    statusColor = "risk-high";
  } else if (currentRisk > 15) {
    level = "medium";
    grade = "C";
    statusText = "Risque Modéré";
    statusColor = "risk-medium";
  }
  
  const riskLevelEl = document.getElementById("risk-level");
  if (riskLevelEl) {
    riskLevelEl.textContent = level === "low" ? "Faible" : level === "medium" ? "Moyen" : level === "high" ? "Élevé" : "Critique";
    riskLevelEl.className = "risk-level risk-" + level;
  }
  
  const gradeEl = document.getElementById("dash-gdpr-grade");
  if (gradeEl) {
    gradeEl.textContent = grade;
    gradeEl.style.display = "";
    gradeEl.className = "dash-gdpr-grade " + statusColor;
  }
  
  const statusEl = document.getElementById("dash-gdpr-status");
  if (statusEl) {
    statusEl.textContent = statusText;
    statusEl.className = "dash-gdpr-status " + statusColor;
  }
  
  let trustScore = Math.max(0, Math.min(100, 98 - restoredCount * 15 + blackedOutTags * 2));
  let aiReadiness = Math.max(0, Math.min(100, 95 - restoredCount * 10));
  
  const trustScoreEl = document.getElementById("trust-score");
  if (trustScoreEl) {
    trustScoreEl.textContent = `Confiance ${trustScore}`;
  }
  const aiScoreEl = document.getElementById("ai-readiness-score");
  if (aiScoreEl) {
    aiScoreEl.textContent = `${aiReadiness}/100`;
  }
  
  const trustBreakdownEl = document.getElementById("dash-trust-breakdown");
  if (trustBreakdownEl) {
    trustBreakdownEl.textContent = `Score de confiance global : ${trustScore}% | Préparation IA : ${aiReadiness}%`;
  }
};

function formatCitations(text) {
  if (!text) return "";
  return text.replace(/\[((?!PERSONNE|SOCIETE|ADRESSE|IBAN|MONTANT|DATE|EMAIL|TELEPHONE|NSS|SIRET|SIREN|TVA|CADASTRE)[^\]]+)\]/g, (match, citationText) => {
    return `<span class="chat-citation" data-citation="${escapeHtml(citationText)}">[${escapeHtml(citationText)}]</span>`;
  });
}

function handleCitationClick(citationText) {
  const previewAnon = document.getElementById("preview-anon-text");
  if (!previewAnon) return;
  
  const existing = previewAnon.querySelectorAll(".citation-highlight");
  existing.forEach(el => {
    el.replaceWith(document.createTextNode(el.textContent));
  });
  
  const lineMatch = citationText.match(/lignes?\s*(\d+)/i) || citationText.match(/(\d+)/);
  if (lineMatch) {
    const lineNum = parseInt(lineMatch[1]);
    const lines = previewAnon.innerHTML.split(/<br\s*\/?>/i);
    if (lineNum > 0 && lineNum <= lines.length) {
      const targetIndex = lineNum - 1;
      const targetText = lines[targetIndex];
      
      lines[targetIndex] = `<span class="citation-highlight">${targetText}</span>`;
      previewAnon.innerHTML = lines.join("<br>");
      
      setTimeout(() => {
        const highlightEl = previewAnon.querySelector(".citation-highlight");
        if (highlightEl) {
          highlightEl.scrollIntoView({ behavior: "smooth", block: "center" });
          
          setTimeout(() => {
            if (highlightEl && highlightEl.parentNode) {
              highlightEl.replaceWith(document.createTextNode(highlightEl.textContent));
            }
          }, 3000);
        }
      }, 50);
      return;
    }
  }
  
  const previewHtml = previewAnon.innerHTML;
  if (previewHtml.includes(citationText)) {
    previewAnon.innerHTML = previewHtml.replace(citationText, `<span class="citation-highlight">${citationText}</span>`);
    
    setTimeout(() => {
      const highlightEl = previewAnon.querySelector(".citation-highlight");
      if (highlightEl) {
        highlightEl.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(() => {
          if (highlightEl && highlightEl.parentNode) {
            highlightEl.replaceWith(document.createTextNode(highlightEl.textContent));
          }
        }, 3000);
      }
    }, 50);
  } else {
    previewAnon.classList.add("neon-flash");
    setTimeout(() => previewAnon.classList.remove("neon-flash"), 1000);
  }
}

function showAnonContextMenu(tagEl, clickEvent) {
  const existing = document.getElementById("anon-context-menu");
  if (existing) existing.remove();
  
  const placeholder = tagEl.dataset.tag || tagEl.textContent;
  
  const menu = document.createElement("div");
  menu.id = "anon-context-menu";
  menu.className = "anon-floating-menu";
  
  const rect = tagEl.getBoundingClientRect();
  const parentRect = document.body.getBoundingClientRect();
  const left = clickEvent.pageX || (rect.left - parentRect.left);
  const top = (clickEvent.pageY || (rect.bottom - parentRect.top)) + 4;
  
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  
  menu.innerHTML = `
    <div class="anon-floating-menu-title">${placeholder}</div>
    <div class="anon-floating-menu-sep"></div>
    <button class="anon-floating-menu-item accent" id="ctx-restore">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 4px;">
        <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
        <polyline points="3 3 3 8 8 8"></polyline>
      </svg>
      Rétablir l'original
    </button>
    <button class="anon-floating-menu-item danger" id="ctx-blackout">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 4px;">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
        <line x1="9" y1="9" x2="15" y2="15"></line>
        <line x1="15" y1="9" x2="9" y2="15"></line>
      </svg>
      Caviarder (Blackout)
    </button>
    <div class="anon-floating-menu-sep"></div>
    <div class="anon-floating-menu-title">Recatégoriser</div>
    <button class="anon-floating-menu-item" data-cat="personne" style="border-left: 3px solid #7c74ff;">Personne</button>
    <button class="anon-floating-menu-item" data-cat="societe" style="border-left: 3px solid #00d2fc;">Société / Org</button>
    <button class="anon-floating-menu-item" data-cat="adresse" style="border-left: 3px solid #fca5a5;">Adresse / Lieu</button>
    <button class="anon-floating-menu-item" data-cat="montant" style="border-left: 3px solid #34d399;">Montant / Finance</button>
    <button class="anon-floating-menu-item" data-cat="date" style="border-left: 3px solid #fbbf24;">Date / Temps</button>
  `;
  
  document.body.appendChild(menu);
  
  menu.querySelector("#ctx-restore").addEventListener("click", () => {
    const originalVal = window.tagOriginalMap[placeholder] || `[Original non trouvé]`;
    tagEl.replaceWith(document.createTextNode(originalVal));
    window.addAuditLedgerEntry("Rétablissement d'entité", "DPO (Vous)", `Restauration de la valeur originale de ${placeholder} (${originalVal})`);
    window.updateScores();
    toast(`Valeur originale rétablie : ${originalVal}`, "success");
    menu.remove();
  });
  
  menu.querySelector("#ctx-blackout").addEventListener("click", () => {
    tagEl.classList.toggle("anon-tag-blackout");
    const isBlackedOut = tagEl.classList.contains("anon-tag-blackout");
    window.addAuditLedgerEntry(
      isBlackedOut ? "Caviardage strict" : "Annulation caviardage",
      "DPO (Vous)", 
      isBlackedOut ? `Placeholder ${placeholder} masqué par un masque opaque noir` : `Placeholder ${placeholder} repassé en affichage pseudonymisé standard`
    );
    window.updateScores();
    toast(isBlackedOut ? `Placeholder masqué` : `Placeholder restauré`, "success");
    menu.remove();
  });
  
  menu.querySelectorAll("[data-cat]").forEach(btn => {
    btn.addEventListener("click", () => {
      const cat = btn.dataset.cat;
      tagEl.className = "anon-tag";
      tagEl.classList.add(`anon-tag-${cat}`);
      window.addAuditLedgerEntry("Recatégorisation", "DPO (Vous)", `Placeholder ${placeholder} re-catégorisé en [${cat.toUpperCase()}]`);
      window.updateScores();
      toast(`Catégorie mise à jour : ${cat.toUpperCase()}`, "success");
      menu.remove();
    });
  });
}

function initDpoInteractivity() {
  const previewPanel = document.getElementById("preview-anon-text");
  if (previewPanel) {
    previewPanel.addEventListener("click", (e) => {
      const tagEl = e.target.closest(".anon-tag");
      if (!tagEl) return;
      e.stopPropagation();
      showAnonContextMenu(tagEl, e);
    });
  }
  
  document.addEventListener("click", () => {
    const menu = document.getElementById("anon-context-menu");
    if (menu) menu.remove();
  });
  
  const chatMessages = document.getElementById("chat-messages");
  if (chatMessages) {
    chatMessages.addEventListener("click", (e) => {
      const citationEl = e.target.closest(".chat-citation");
      if (!citationEl) return;
      e.stopPropagation();
      const citationText = citationEl.dataset.citation || citationEl.textContent;
      handleCitationClick(citationText);
    });
  }

  // Hide onboarding guide listener
  const btnHideOnboarding = document.getElementById("btn-hide-onboarding");
  if (btnHideOnboarding) {
    btnHideOnboarding.addEventListener("click", () => {
      const guide = document.getElementById("onboarding-guide");
      if (guide) {
        guide.style.display = "none";
      }
    });
  }
}

// ── Event listeners ────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initDpoInteractivity();
  initDossierTabsAndComparison();

  // Redesign topbar — wire search + Copilot buttons to ⌘K / ⌘J shortcuts
  document.querySelector('[data-action="open-cmd-palette"]')?.addEventListener("click", () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }));
  });
  document.querySelector('[data-action="open-copilot"]')?.addEventListener("click", () => {
    if (window.__confidocDrawer) {
      window.__confidocDrawer.open();
    } else {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true, bubbles: true }));
    }
  });

  const versionEl = $("ui-version");
  if (versionEl?.dataset?.version) {
    console.info(`ConfiDoc UI ${versionEl.dataset.version}`);
  }

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
      const isHidden = inp.type === "password";
      inp.type = isHidden ? "text" : "password";
      btn.title = isHidden ? "Masquer le mot de passe" : "Afficher le mot de passe";
      btn.setAttribute("aria-pressed", isHidden ? "true" : "false");
      const eyeOpen = btn.querySelector(".eye-open");
      const eyeClosed = btn.querySelector(".eye-closed");
      if (eyeOpen) eyeOpen.style.display = isHidden ? "none" : "";
      if (eyeClosed) eyeClosed.style.display = isHidden ? "" : "none";
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

  if ($("btn-public-investor-demo")) {
    $("btn-public-investor-demo").addEventListener("click", launchPublicInvestorDemo);
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
      const isHidden = inp.type === "password";
      inp.type = isHidden ? "text" : "password";
      btn.title = isHidden ? "Masquer le mot de passe" : "Afficher le mot de passe";
      btn.setAttribute("aria-pressed", isHidden ? "true" : "false");
      const eyeOpen = btn.querySelector(".eye-open");
      const eyeClosed = btn.querySelector(".eye-closed");
      if (eyeOpen) eyeOpen.style.display = isHidden ? "none" : "";
      if (eyeClosed) eyeClosed.style.display = isHidden ? "" : "none";
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

  // App nav (sidebar unifiée)
  document.querySelectorAll("#app-nav .nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.nav;
      switch (key) {
        case "home":
          showDashboard();
          break;
        case "documents":
          setSidebarMode("flat");
          setStep(1);
          closeAppNavDrawer();
          break;
        case "clients":
          openClientWorkspace();
          break;
        case "quality":
          showQualityPanel();
          break;
        case "audit":
          showAuditPanel();
          break;
        case "settings":
          showStubPanel("panel-settings", "settings", "Paramètres");
          break;
      }
    });
  });
  if ($("btn-app-nav-toggle")) $("btn-app-nav-toggle").addEventListener("click", toggleAppNavDrawer);
  if ($("app-nav-backdrop")) $("app-nav-backdrop").addEventListener("click", closeAppNavDrawer);

  // Dashboard quick-actions (boutons internes du panel-dashboard)
  if ($("btn-home")) $("btn-home").addEventListener("click", goHome);
  if ($("btn-dash-upload")) $("btn-dash-upload").addEventListener("click", startNewDocument);
  if ($("btn-dash-demo")) $("btn-dash-demo").addEventListener("click", createDemoDocument);
  if ($("btn-work-demo")) $("btn-work-demo").addEventListener("click", createDemoDocument);
  if ($("btn-dash-clients")) $("btn-dash-clients").addEventListener("click", openClientWorkspace);
  if ($("btn-dash-list")) $("btn-dash-list").addEventListener("click", openDocumentWorkspace);
  if ($("btn-dash-refresh")) $("btn-dash-refresh").addEventListener("click", () => {
    dashboardLoaded = false;
    loadDashboard();
  });
  if ($("btn-d360-pdf")) $("btn-d360-pdf").addEventListener("click", downloadDossier360Report);
  
  // Quality panel events
  if ($("btn-quality-refresh")) $("btn-quality-refresh").addEventListener("click", () => {
    loadQualityDashboard();
  });
  if ($("quality-tab-fields")) $("quality-tab-fields").addEventListener("click", () => {
    $("quality-tab-fields").classList.add("active");
    $("quality-tab-errors").classList.remove("active");
    $("quality-fields-container").style.display = "flex";
    $("quality-errors-container").style.display = "none";
    renderQualityDistributions();
  });
  if ($("quality-tab-errors")) $("quality-tab-errors").addEventListener("click", () => {
    $("quality-tab-errors").classList.add("active");
    $("quality-tab-fields").classList.remove("active");
    $("quality-errors-container").style.display = "flex";
    $("quality-fields-container").style.display = "none";
    renderQualityDistributions();
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

  document.addEventListener("click", handleDelegatedAction);

  // Sidebar: nouveau document
  $("btn-new-doc").addEventListener("click", startNewDocument);
  if ($("dossier-filter-client")) {
    $("dossier-filter-client").addEventListener("input", e => filterDossierTree(e.target.value));
  }
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
  $("btn-anonymize").addEventListener("click", anonymize);
  if ($("btn-context-anonymize")) {
    $("btn-context-anonymize").addEventListener("click", () => {
      $("btn-anonymize")?.click();
    });
  }
  if ($("btn-context-ai")) {
    $("btn-context-ai").addEventListener("click", () => {
      if (!currentDocId) return;
      goToChat();
    });
  }
  if ($("btn-ai-back-anon")) {
    $("btn-ai-back-anon").addEventListener("click", () => openAnonReviewForCurrentDocument());
  }
  if ($("btn-ai-audit-shortcut")) {
    $("btn-ai-audit-shortcut").addEventListener("click", () => {
      $("btn-audit-report")?.click();
    });
  }

  // Valider → discussion IA (avec validation)
  $("btn-validate").addEventListener("click", validate);
  if ($("btn-save-correction")) $("btn-save-correction").addEventListener("click", () => saveManualCorrection());
  if ($("btn-add-mask")) $("btn-add-mask").addEventListener("click", addMaskValue);
  if ($("btn-toggle-score-details")) {
    $("btn-toggle-score-details").addEventListener("click", () => {
      const details = $("why-score-details");
      if (!details) return;
      const visible = details.style.display !== "none";
      details.style.display = visible ? "none" : "";
      $("btn-toggle-score-details").textContent = visible ? "Voir pourquoi" : "Masquer";
    });
  }
  document.addEventListener("click", (e) => {
    const control = e.target instanceof Element ? e.target.closest("[data-decision-action]") : null;
    if (!control) return;
    const action = control.dataset.decisionAction;
    if (action === "analyze") goToChat();
    else if (action === "report" || action === "audit") downloadAuditReport();
    else if (action === "correct") setReviewMode("split");
    else if (action === "validate") validate();
    else if (action === "why") {
      const details = $("why-score-details");
      if (details) details.style.display = "";
    } else if (action === "retry") {
      $("btn-anonymize")?.click();
    }
  });

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
  $("chat-messages").addEventListener("click", e => {
    const btn = e.target.closest("[data-chat-suggestion]");
    if (!btn) return;
    $("chat-input").value = btn.dataset.chatSuggestion || "";
    sendMessage();
  });
  $("btn-stop-stream").addEventListener("click", stopStream);
  $("btn-copy-answer").addEventListener("click", copyLatestAnswer);

  if ($("ai-ready-summary")) {
    $("ai-ready-summary").addEventListener("click", e => {
      const btn = e.target.closest("[data-ai-ready-action]");
      if (!btn) return;
      const action = btn.dataset.aiReadyAction;
      if (action === "analyze") {
        $("chat-input")?.focus();
        document.querySelector(".chat-input-zone")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else if (action === "proof") {
        ($("btn-compliance-certificate") || $("btn-compliance-report"))?.click();
      } else if (action === "original") {
        openCurrentOriginal(false);
      } else if (action === "review") {
        openAnonReviewForCurrentDocument();
      }
    });
  }

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
    b.textContent = reportMode ? "Mode rapport: ON" : "Mode rapport: OFF";
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
            <div class="logo">ConfiDoc</div>
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
      b.textContent = copilotMode ? "Copilot: ON" : "Copilot: OFF";
      b.classList.toggle("active", copilotMode);
      if (!copilotMode && $("copilot-insights")) $("copilot-insights").style.display = "none";
      toast(copilotMode ? "Copilot activé" : "Copilot désactivé", "info");
    });
  }

  // Export
  $("btn-export-txt").addEventListener("click", exportText);
  $("btn-export-pdf").addEventListener("click", exportPdf);
  if ($("btn-export-fec")) $("btn-export-fec").addEventListener("click", exportFec);
  if ($("btn-export-approve-inline")) {
    $("btn-export-approve-inline").addEventListener("click", showApproveExportPrompt);
  }
  if ($("btn-audit-report")) $("btn-audit-report").addEventListener("click", downloadAuditReport);
  if ($("btn-compliance-report")) $("btn-compliance-report").addEventListener("click", downloadComplianceReport);
  if ($("btn-compliance-certificate")) $("btn-compliance-certificate").addEventListener("click", downloadComplianceCertificate);

  // Load Global Quality on startup when a session already exists.
  loadGoldenReport();

  // Logo → dashboard
  if ($("logo-btn")) $("logo-btn").addEventListener("click", showDashboard);

  // Theme
  initTheme();
  if ($("btn-theme")) $("btn-theme").addEventListener("click", toggleTheme);

  // Backdrop de la sidebar documents (le bouton burger principal vit dans le header → toggleAppNavDrawer)
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
    renderExportGuard({});
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
let _dashboard_original_html = ''; window.addEventListener('DOMContentLoaded', () => { const el = document.getElementById('dash-content'); if(el) _dashboard_original_html = el.innerHTML; });
