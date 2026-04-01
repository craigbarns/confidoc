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
let currentClientFilter = "";
let currentIncludeDeleted = false;
let currentSearchFilter = "";
let currentStatusFilter = "";
let activeStream = null; // AbortController pour le streaming SSE
let currentRiskLevel = null; // RGPD risk level from last anonymization
let originalTextCache = {};
let bgPollers = {};

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
}

function updateThemeBtn() {
  const btn = $("btn-theme");
  if (!btn) return;
  const isLight = document.documentElement.classList.contains("theme-light");
  btn.textContent = isLight ? "🌙" : "☀️";
  btn.title = isLight ? "Mode sombre" : "Mode clair";
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
  const open = sidebar.classList.toggle("open");
  if (backdrop) backdrop.classList.toggle("visible", open);
}

function closeSidebar() {
  const sidebar = document.querySelector(".sidebar");
  const backdrop = $("sidebar-backdrop");
  if (sidebar) sidebar.classList.remove("open");
  if (backdrop) backdrop.classList.remove("visible");
}

// ── Toast ──────────────────────────────────────────────────────────────

function toast(msg, type = "info") {
  const el = $("toast");
  el.textContent = msg;
  el.className = `toast${type === "success" ? " success" : type === "error" ? " error" : ""}`;
  el.style.display = "block";
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.style.display = "none"; }, 4000);
}

// ── Confirm dialog ─────────────────────────────────────────────────────

function confirm(message) {
  return new Promise(resolve => {
    $("confirm-msg").textContent = message;
    $("confirm-overlay").style.display = "";
    const onOk = () => {
      $("confirm-overlay").style.display = "none";
      cleanup();
      resolve(true);
    };
    const onCancel = () => {
      $("confirm-overlay").style.display = "none";
      cleanup();
      resolve(false);
    };
    const cleanup = () => {
      $("btn-confirm-ok").removeEventListener("click", onOk);
      $("btn-confirm-cancel").removeEventListener("click", onCancel);
    };
    $("btn-confirm-ok").addEventListener("click", onOk);
    $("btn-confirm-cancel").addEventListener("click", onCancel);
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
  setStep(1);
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
    // Ne pas utiliser `/documents/${qp}` : ça produit `/documents/` ou `/documents/?…` (404 / mauvais match).
    const docs = await apiFetch(`/documents${qp}`);
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
    const name = d.original_filename.length > 26
      ? d.original_filename.slice(0, 24) + "…"
      : d.original_filename;
    const label = statusLabel[d.status] || d.status;
    const selected = d.id === currentDocId ? " selected" : "";
    const size = formatBytes(d.size_bytes);
    const date = formatDate(d.created_at);
    const meta = [date, size].filter(Boolean).join(" · ");
    const clientTag = Array.isArray(d.tags) && d.tags.length
      ? `<span class="doc-client-tag">${d.tags[0]}</span>`
      : "";
    const isDeleted = !!d.is_deleted;
    const deletedBadge = isDeleted ? `<span class="doc-item-status">Corbeille</span>` : "";
    const cardClass = isDeleted ? " trashed" : "";
    const deleteBtn = isDeleted
      ? ""
      : `<button class="doc-item-del" data-id="${d.id}" data-name="${d.original_filename}" title="Supprimer">✕</button>`;
    const trashActions = isDeleted
      ? `<div class="doc-item-actions">
          <button class="btn-tiny doc-item-restore" data-id="${d.id}" data-name="${d.original_filename}">Restaurer</button>
          <button class="btn-tiny doc-item-delete-perm" data-id="${d.id}" data-name="${d.original_filename}">Suppr. définitive</button>
        </div>`
      : "";

    return `<div class="doc-item${selected}${cardClass}" data-id="${d.id}" data-status="${d.status}" data-name="${d.original_filename}" data-size="${d.size_bytes || 0}" data-deleted="${isDeleted ? "1" : "0"}">
      <div class="doc-item-name">${name}</div>
      <div class="doc-item-meta">
        <span class="doc-item-status status-${d.status}">${label}</span>
        ${deletedBadge}
        ${clientTag}
        ${meta ? `<span>${meta}</span>` : ""}
      </div>
      ${deleteBtn}
      ${trashActions}
    </div>`;
  }).join("");

  list.querySelectorAll(".doc-item").forEach(el => {
    if (el.dataset.deleted === "1") return;
    el.addEventListener("click", () => selectDoc(
      el.dataset.id,
      el.dataset.status,
      el.dataset.name,
      parseInt(el.dataset.size, 10) || 0
    ));
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
}

// ── Delete document ─────────────────────────────────────────────────────

async function deleteDoc(id, name) {
  const ok = await confirm(`"${name}" sera déplacé dans la corbeille.`);
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
  const ok = await confirm(`Suppression définitive de "${name}" ? Cette action est irréversible.`);
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

  setStep(2);
  resetAnonPanel();
  updateAnonDocBar(name, sizeBytes);
  updatePipelineTimeline({ status, extractDone: status !== "uploaded", anonymDone: status === "ready" });
  await refreshAIDocInsights(id);

  if (status === "ready") {
    showAnonLoading("Chargement de la prévisualisation…");
    try {
      const preview = await apiFetch(`/documents/${id}/preview`);
      // Use entity_summary if available in preview metadata (if we had it in status)
      // or from a separate call later. For now, we take count from preview.
      showAnonResults(preview.preview_text, preview.detections_count, preview.entity_summary || {});
    } catch (e) {
      console.error("preview load error:", e);
      hideAnonLoading();
      toast("Impossible de charger la prévisualisation.", "error");
    }
  } else if (status === "processing") {
    showAnonLoading("Traitement en cours…");
    pollDocStatus(id);
  } else if (status === "uploaded") {
    // Doc uploadé, pas encore anonymisé — montrer panel vide avec instructions
    $("anon-empty").style.display = "";
    $("anon-empty").querySelector("p").innerHTML =
      "Document uploadé.<br>Cliquez sur <strong>Anonymiser</strong> pour démarrer.";
  } else if (status === "failed") {
    $("anon-empty").style.display = "";
    $("anon-empty").querySelector(".hint-icon").textContent = "⚠️";
    $("anon-empty").querySelector("p").innerHTML =
      "Le traitement a échoué.<br>Cliquez sur <strong>Anonymiser</strong> pour réessayer.";
  }
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
    return;
  }

  try {
    const clientQp = clientName ? `&client_name=${encodeURIComponent(clientName)}` : "";
    const data = await uploadWithProgress(fd, `/uploads?auto_anonymize=false${clientQp}`, fill, statusEl);
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
      $("anon-empty").querySelector("p").innerHTML =
        `<strong>${file.name}</strong> uploadé.<br>Cliquez sur <strong>Anonymiser</strong> pour démarrer.`;
    }, 600);

    toast(`${file.name} uploadé`, "success");
  } catch (e) {
    console.error("uploadFile error:", e);
    zone.style.display = "";
    progress.style.display = "none";
    fill.style.width = "0";
    toast(`Erreur upload: ${e.message}`, "error");
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
  // Reset onglet original
  $("preview-original-text").textContent = "";
  $("original-loading").style.display = "none";
  switchTab("anonymized");
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

  switchTab("anonymized");
}

function highlightTags(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\[([A-Z][A-Z0-9_]*)\]/g, (match, tag) => {
      let colorClass = "";
      if (tag.includes("PERSONNE") || tag.includes("ASSOCIE")) colorClass = "tag-person";
      else if (tag.includes("SOCIETE") || tag.includes("CABINET")) colorClass = "tag-org";
      else if (tag.includes("ADRESSE") || tag.includes("VILLE")) colorClass = "tag-geo";
      else if (tag.includes("BANQUE") || tag.includes("IBAN")) colorClass = "tag-bank";
      else if (tag.includes("DATE")) colorClass = "tag-date";
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
  const maxTries = 60;
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

// ── Preview tabs ───────────────────────────────────────────────────────

function switchTab(tabName) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === tabName)
  );
  $("tab-anonymized").style.display = tabName === "anonymized" ? "" : "none";
  $("tab-original").style.display = tabName === "original" ? "" : "none";

  // Chargement lazy du texte original
  const diffTab = $("tab-diff");
  if (diffTab) diffTab.style.display = tabName === "diff" ? "" : "none";

  if (tabName === "original" && currentDocId) loadOriginalText(currentDocId);
  if (tabName === "diff" && currentDocId) loadDiffView();
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
    { target: ".upload-zone", title: "1. Uploadez un document", text: "Glissez un PDF ou cliquez pour choisir un fichier. Le nom du client est obligatoire." },
    { target: "#btn-anonymize", title: "2. Anonymisez", text: "Choisissez un mode RGPD et un profil, puis lancez le traitement." },
    { target: ".quick-actions", title: "3. Discutez avec l'IA", text: "Posez des questions en toute securite. L'IA ne voit que le texte masque." },
    { target: "#btn-export-txt", title: "4. Exportez", text: "Telechargez le texte anonymise, le PDF redacte ou le rapport d'audit RGPD." },
  ];
  let current = 0;
  const overlay = document.createElement("div");
  overlay.className = "onboarding-overlay";
  overlay.id = "onboarding-overlay";

  function renderStep() {
    const step = steps[current];
    const targetEl = document.querySelector(step.target);
    overlay.innerHTML = '<div class="onboarding-backdrop"></div>' +
      '<div class="onboarding-card">' +
      '<div class="onboarding-step-indicator">' + (current+1) + ' / ' + steps.length + '</div>' +
      '<h3>' + step.title + '</h3>' +
      '<p>' + step.text + '</p>' +
      '<div class="onboarding-actions">' +
      '<button class="btn btn-ghost btn-sm" id="onboarding-skip">Passer</button>' +
      '<button class="btn btn-primary btn-sm" id="onboarding-next">' + (current < steps.length-1 ? 'Suivant' : 'Commencer !') + '</button>' +
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
    overlay.querySelector("#onboarding-skip").addEventListener("click", () => {
      document.querySelectorAll(".onboarding-highlight").forEach(el => el.classList.remove("onboarding-highlight"));
      finishOnboarding();
    });
  }

  function finishOnboarding() {
    overlay.remove();
    document.querySelectorAll(".onboarding-highlight").forEach(el => el.classList.remove("onboarding-highlight"));
    localStorage.setItem(ONBOARDING_KEY, "true");
    toast("Bienvenue sur ConfiDoc !", "success");
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
    const heading = line.match(/^#{1,3}\s+(.+)$/) || line.match(/^([A-Za-zÀ-ÿ0-9 \-]+)\s*:\s*$/);
    if (heading) {
      if (current.items.length) sections.push(current);
      current = { title: heading[1], items: [] };
      continue;
    }
    current.items.push(line.replace(/^[\-•]\s*/, ""));
  }
  if (current.items.length) sections.push(current);
  if (!sections.length) return;
  bodyEl.classList.add("structured");
  bodyEl.innerHTML = sections
    .map((s) => `<div class="ai-section"><div class="ai-section-title">${escapeHtml(s.title)}</div><ul>${s.items.map((it) => `<li>${escapeHtml(it)}</li>`).join("")}</ul></div>`)
    .join("");
}

async function sendMessage() {
  const input = $("chat-input");
  const question = input.value.trim();
  if (!question || !currentDocId) return;
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
    const effectiveQuestion = reportMode
      ? `${question}\n\nRéponds en format rapport structuré avec sections: Résumé, Points clés, Risques, Actions recommandées.`
      : question;
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
    if (e.message && e.message.includes("bloque")) {
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
    if (e.message && e.message.includes("bloque")) {
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
  const ok = confirm(
    "Ce document a un risque de réidentification élevé.\n\n" +
    "En tant que responsable, confirmez-vous avoir vérifié manuellement " +
    "que l'anonymisation est suffisante pour un export externe ?\n\n" +
    "Cette action sera journalisée."
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

function showDashboard() {
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const dash = $("panel-dashboard");
  if (dash) dash.classList.add("active");
  [1, 2, 3].forEach(i => {
    const s = $(`step-${i}`);
    if (s) s.className = "step";
  });
  if (!dashboardLoaded) loadDashboard();
}

async function loadDashboard() {
  const loading = $("dash-loading");
  const content = $("dash-content");
  if (loading) loading.style.display = "";
  if (content) content.style.display = "none";

  try {
    const data = await apiFetch("/documents/stats/dashboard");
    dashboardLoaded = true;
    renderDashboard(data);
  } catch (e) {
    console.warn("loadDashboard failed:", e);
    if (content) {
      content.style.display = "";
      content.innerHTML = '<div class="empty-state">Impossible de charger les statistiques.</div>';
    }
  } finally {
    if (loading) loading.style.display = "none";
  }
}

function renderDashboard(data) {
  const content = $("dash-content");
  if (!content) return;
  content.style.display = "";

  // KPIs
  const sc = data.status_counts || {};
  animateNumber($("dash-total-docs"), data.total_documents || 0);
  animateNumber($("dash-total-entities"), data.total_entities_masked || 0);
  animateNumber($("dash-ready-count"), sc.ready || 0);
  animateNumber($("dash-trashed"), data.trashed_documents || 0);

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
    actSection.style.display = "";
    const maxAct = Math.max(1, ...data.recent_activity.map(a => a.count));
    actEl.innerHTML = data.recent_activity.map(a => {
      const h = Math.max(2, (a.count / maxAct) * 80);
      const day = a.date ? new Date(a.date).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }) : "";
      return `<div class="dash-activity-col">
        <div class="dash-activity-bar" style="height:${h}px"></div>
        <span class="dash-activity-label">${day}</span>
      </div>`;
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
  { id: "extract", icon: "2", label: "Extraction des donnees cles" },
  { id: "analyze", icon: "3", label: "Analyse metier" },
  { id: "anomalies", icon: "4", label: "Detection d'anomalies" },
  { id: "synthesize", icon: "5", label: "Redaction de la note de revue" },
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

  // Verdict badge
  const synthesize = data.synthesize || data;
  const sections = synthesize.sections || data.sections || {};
  const verdict = synthesize.verdict || data.verdict || "";
  const confidence = synthesize.confiance || synthesize.confidence || data.confidence || 0;
  const reviewNote = synthesize.resume_executif || synthesize.review_note || data.review_note || "";
  const nextActions = synthesize.prochaines_actions || data.prochaines_actions || [];
  const titre = synthesize.titre || "Note de revue";

  if (verdict) {
    const verdictIcons = { favorable: "\u2705", reserve: "\u26A0\uFE0F", defavorable: "\u274C" };
    const verdictLabels = { favorable: "Favorable", reserve: "Reserve", defavorable: "Defavorable" };
    html += `<div class="review-verdict ${verdict}">${verdictIcons[verdict] || ""} ${verdictLabels[verdict] || verdict} (confiance: ${Math.round(confidence * 100)}%)</div>`;
  }

  // Resume
  if (reviewNote) {
    html += `<div class="review-section">
      <div class="review-section-title">\uD83D\uDCCB Resume executif</div>
      <div class="review-section-body">${escapeHtml(reviewNote)}</div>
    </div>`;
  }

  // Sections
  const sectionIcons = {
    identification: "\uD83D\uDCC4",
    chiffres_cles: "\uD83D\uDCCA",
    analyse: "\uD83D\uDD0D",
    alertes: "\u26A0\uFE0F",
    recommandations: "\u2705",
  };
  for (const [key, value] of Object.entries(sections)) {
    if (!value) continue;
    const icon = sectionIcons[key] || "\uD83D\uDCDD";
    const label = key.replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
    html += `<div class="review-section">
      <div class="review-section-title">${icon} ${label}</div>
      <div class="review-section-body">${escapeHtml(String(value))}</div>
    </div>`;
  }

  // Anomalies
  const anomalies = data.anomalies || [];
  if (anomalies.length) {
    html += `<div class="review-section">
      <div class="review-section-title">\u26A0\uFE0F Anomalies detectees (${anomalies.length})</div>`;
    anomalies.forEach(a => {
      const sev = a.severite || "information";
      html += `<div class="review-anomaly ${sev}">
        <span class="review-anomaly-sev">${sev}</span>
        <div>
          <strong>${escapeHtml(a.description || "")}</strong>
          ${a.recommandation ? `<br><em style="color:var(--text-muted)">${escapeHtml(a.recommandation)}</em>` : ""}
        </div>
      </div>`;
    });
    html += `</div>`;
  }

  // Next actions
  if (nextActions.length) {
    html += `<div class="review-section">
      <div class="review-section-title">\u27A1\uFE0F Prochaines actions</div>
      <div class="review-section-body">${nextActions.map((a, i) => `${i + 1}. ${escapeHtml(a)}`).join("\n")}</div>
    </div>`;
  }

  el.innerHTML = html;
  $("review-actions").style.display = "";
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
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (raw === "[DONE]") break;

        try {
          const event = JSON.parse(raw);
          const step = event.step;
          const status = event.status;

          if (status === "done" && step !== "complete") {
            if (!completedSteps.includes(step)) completedSteps.push(step);
            if (event.data) {
              Object.assign(allData, event.data);
              if (step === "anomalies" && event.data.anomalies) {
                allData.anomalies = event.data.anomalies;
              }
            }
            renderReviewSteps(null, completedSteps);
          } else if (status === "running") {
            currentStep = step;
            renderReviewSteps(step, completedSteps);
          } else if (status === "complete") {
            renderReviewSteps(null, completedSteps);
            reviewResult = allData;
            renderReviewResult(allData);
            toast("Analyse documentaire terminee", "success");
          } else if (status === "error") {
            renderReviewSteps(null, completedSteps);
            toast(`Erreur analyse: ${event.data?.error || "inconnue"}`, "error");
          }
        } catch (e) {
          console.warn("Review SSE parse error:", e);
        }
      }
    }
  } catch (e) {
    console.error("startReview error:", e);
    toast(`Erreur analyse: ${e.message}`, "error");
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
  const sections = reviewResult.sections || {};
  const note = reviewResult.review_note || reviewResult.resume_executif || "";
  let text = "=== NOTE DE REVUE ===\n\n";
  text += note + "\n\n";
  for (const [key, value] of Object.entries(sections)) {
    text += `--- ${key.toUpperCase()} ---\n${value}\n\n`;
  }
  if (reviewResult.anomalies?.length) {
    text += "--- ANOMALIES ---\n";
    reviewResult.anomalies.forEach(a => {
      text += `[${a.severite}] ${a.description}\n`;
      if (a.recommandation) text += `  -> ${a.recommandation}\n`;
    });
  }
  navigator.clipboard.writeText(text).then(
    () => toast("Note de revue copiee", "success"),
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
  if ($("btn-dash-refresh")) $("btn-dash-refresh").addEventListener("click", () => {
    dashboardLoaded = false;
    loadDashboard();
  });

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
    const f = e.dataTransfer.files[0];
    if (f) uploadFile(f);
  });

  // Upload: file input
  const fileInput = $("file-input");
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) uploadFile(fileInput.files[0]);
    fileInput.value = "";
  });

  // Anonymiser
  $("btn-anonymize").addEventListener("click", anonymize);

  // Valider → discussion IA (avec validation)
  $("btn-validate").addEventListener("click", validate);

  // Discussion directe → step 3 sans re-valider
  $("btn-go-ai").addEventListener("click", goToChat);

  // Onglets preview
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // Chat IA
  $("btn-send").addEventListener("click", sendMessage);
  $("chat-input").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $("btn-stop-stream").addEventListener("click", stopStream);
  $("btn-copy-answer").addEventListener("click", copyLatestAnswer);

  // Quick actions
  document.querySelectorAll(".quick-btn").forEach(btn => {
    if (btn.id === "btn-report-mode") return;
    btn.addEventListener("click", () => {
      $("chat-input").value = btn.dataset.q;
      sendMessage();
    });
  });
  // Review agent
  if ($("btn-review-agent")) $("btn-review-agent").addEventListener("click", startReview);
  if ($("btn-review-close")) $("btn-review-close").addEventListener("click", closeReview);
  if ($("btn-review-copy")) $("btn-review-copy").addEventListener("click", copyReviewResult);
  if ($("btn-review-export")) $("btn-review-export").addEventListener("click", exportReviewResult);

  $("btn-report-mode").addEventListener("click", () => {
    reportMode = !reportMode;
    const b = $("btn-report-mode");
    b.dataset.on = reportMode ? "true" : "false";
    b.textContent = reportMode ? "🧱 Mode rapport: ON" : "🧱 Mode rapport: OFF";
    b.classList.toggle("active", reportMode);
    toast(reportMode ? "Mode rapport activé" : "Mode rapport désactivé", "info");
  });

  // Export
  $("btn-export-txt").addEventListener("click", exportText);
  $("btn-export-pdf").addEventListener("click", exportPdf);
  if ($("btn-audit-report")) $("btn-audit-report").addEventListener("click", downloadAuditReport);

  // Theme
  initTheme();
  if ($("btn-theme")) $("btn-theme").addEventListener("click", toggleTheme);

  // Mobile sidebar toggle
  if ($("btn-sidebar-toggle")) $("btn-sidebar-toggle").addEventListener("click", toggleSidebar);
  if ($("sidebar-backdrop")) $("sidebar-backdrop").addEventListener("click", closeSidebar);
  document.querySelectorAll(".sidebar .doc-item").forEach(el => {
    el.addEventListener("click", closeSidebar);
  });

  // Notification permission
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }

  // Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  }

  // Reprendre la session si token en sessionStorage
  if (token) {
    scheduleTokenRefresh();
    initApp().catch(() => logout());
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "/") return;
  const target = e.target;
  const isInput = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA");
  if (isInput) return;
  const search = $("filter-search");
  if (!search) return;
  e.preventDefault();
  search.focus();
});
