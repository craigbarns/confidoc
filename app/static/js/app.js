/* ConfiDoc — Pipeline 3 étapes : Upload → Anonymisation → Discussion IA */

const API = "/api/v1";
let token = sessionStorage.getItem("confidoc_token") || "";
let currentDocId = null;
let activeStream = null; // AbortController for SSE

const $ = id => document.getElementById(id);

// ── API helpers ────────────────────────────────────────────────────────

async function apiRequest(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(opts.body instanceof FormData) && opts.body) {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(API + path, { ...opts, headers });
  if (!resp.ok) {
    let msg = `Erreur HTTP ${resp.status}`;
    try { const j = await resp.json(); msg = j.detail || j.message || msg; } catch {}
    throw new Error(msg);
  }
  return resp;
}

async function apiFetch(path, opts = {}) {
  const resp = await apiRequest(path, opts);
  return resp.json();
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
  currentDocId = null;
  sessionStorage.removeItem("confidoc_token");
  if (activeStream) { activeStream.abort(); activeStream = null; }
  $("screen-auth").style.display = "";
  $("screen-app").style.display = "none";
  $("btn-logout").style.display = "none";
  $("user-info").textContent = "";
}

async function initApp(email) {
  $("screen-auth").style.display = "none";
  $("screen-app").style.display = "";
  $("btn-logout").style.display = "";
  if (email) $("user-info").textContent = email;
  setStep(1);
  await loadDocList();
}

// ── Document list ──────────────────────────────────────────────────────

async function loadDocList() {
  try {
    const docs = await apiFetch("/documents/");
    renderDocList(docs);
  } catch (e) {
    console.warn("loadDocList failed:", e.message);
  }
}

function renderDocList(docs) {
  const list = $("doc-list");
  if (!docs.length) {
    list.innerHTML = '<div class="empty-state">Aucun document.<br>Uploadez-en un.</div>';
    return;
  }
  list.innerHTML = docs.map(d => {
    const name = d.original_filename.length > 26
      ? d.original_filename.slice(0, 24) + "…"
      : d.original_filename;
    const statusLabel = { uploaded: "Uploadé", processing: "En cours", ready: "Prêt", failed: "Erreur" }[d.status] || d.status;
    const selected = d.id === currentDocId ? " selected" : "";
    return `<div class="doc-item${selected}" data-id="${d.id}" data-status="${d.status}">
      <div class="doc-item-name">${name}</div>
      <span class="doc-item-status status-${d.status}">${statusLabel}</span>
    </div>`;
  }).join("");

  list.querySelectorAll(".doc-item").forEach(el => {
    el.addEventListener("click", () => selectDoc(el.dataset.id, el.dataset.status));
  });
}

async function selectDoc(id, status) {
  currentDocId = id;
  document.querySelectorAll(".doc-item").forEach(el =>
    el.classList.toggle("selected", el.dataset.id === id)
  );

  if (status === "ready") {
    setStep(2);
    resetAnonPanel();
    try {
      const preview = await apiFetch(`/documents/${id}/preview`);
      $("anon-results").style.display = "";
      $("stat-count").textContent = preview.detections_count;
      $("preview-anon-text").innerHTML = highlightTags(preview.preview_text || "");
    } catch {}
  } else if (status === "processing") {
    setStep(2);
    resetAnonPanel();
    showAnonLoading();
    pollDocStatus(id);
  } else {
    setStep(2);
    resetAnonPanel();
  }
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

  try {
    fill.style.width = "70%";
    const data = await apiFetch(`/uploads?auto_anonymize=false`, {
      method: "POST",
      body: fd,
    });
    fill.style.width = "100%";
    statusEl.textContent = "Upload réussi !";
    currentDocId = data.document_id;
    await loadDocList();
    setTimeout(() => {
      zone.style.display = "";
      progress.style.display = "none";
      fill.style.width = "0";
      setStep(2);
      resetAnonPanel();
    }, 600);
    toast(`${file.name} uploadé`, "success");
  } catch (e) {
    zone.style.display = "";
    progress.style.display = "none";
    fill.style.width = "0";
    toast(`Erreur upload: ${e.message}`, "error");
  }
}

// ── Anonymisation ──────────────────────────────────────────────────────

function resetAnonPanel() {
  $("anon-loading").style.display = "none";
  $("anon-results").style.display = "none";
  $("btn-anonymize").disabled = false;
}

function showAnonLoading() {
  $("anon-loading").style.display = "";
  $("anon-results").style.display = "none";
  $("btn-anonymize").disabled = true;
}

function highlightTags(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\[([A-Z][A-Z0-9_]*)\]/g, '<mark class="anon-tag">[$1]</mark>');
}

async function anonymize() {
  if (!currentDocId) { toast("Aucun document sélectionné", "error"); return; }
  const profile = $("anon-profile").value;
  showAnonLoading();
  try {
    const res = await fetch(
      `/api/v1/documents/${currentDocId}/anonymize?profile=${profile}`,
      { method: "POST", headers: { "Authorization": `Bearer ${token}` } }
    );
    if (res.status === 202) {
      // Traitement en background — on poll jusqu'à ce que le doc soit READY
      toast("Anonymisation en cours… (peut prendre 30-60s)", "info");
      await loadDocList();
      pollDocStatus(currentDocId);
    } else if (res.ok) {
      const data = await res.json();
      $("anon-loading").style.display = "none";
      $("anon-results").style.display = "";
      $("stat-count").textContent = data.detections_count || 0;
      $("preview-anon-text").innerHTML = highlightTags(data.preview_text || "(Aucun texte extrait)");
      $("btn-anonymize").disabled = false;
      switchTab("anonymized");
      toast(`${data.detections_count} entité(s) anonymisée(s)`, "success");
      await loadDocList();
    } else {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
  } catch (e) {
    $("anon-loading").style.display = "none";
    $("btn-anonymize").disabled = false;
    toast(`Erreur: ${e.message}`, "error");
  }
}

function pollDocStatus(docId) {
  let tries = 0;
  const interval = setInterval(async () => {
    tries++;
    if (tries > 60) {
      clearInterval(interval);
      $("anon-loading").style.display = "none";
      $("btn-anonymize").disabled = false;
      toast("Délai d'attente dépassé. Veuillez réessayer.", "error");
      await loadDocList().catch(() => {});
      return;
    }
    try {
      const doc = await apiFetch(`/documents/${docId}`);
      if (doc.status === "ready") {
        clearInterval(interval);
        $("anon-loading").style.display = "none";
        $("btn-anonymize").disabled = false;
        try {
          const preview = await apiFetch(`/documents/${docId}/preview`);
          $("anon-results").style.display = "";
          $("stat-count").textContent = preview.detections_count;
          $("preview-anon-text").innerHTML = highlightTags(preview.preview_text || "");
          toast(`${preview.detections_count || 0} entité(s) anonymisée(s)`, "success");
        } catch {
          toast("Anonymisation terminée.", "success");
        }
        await loadDocList();
      } else if (doc.status !== "processing") {
        clearInterval(interval);
        $("anon-loading").style.display = "none";
        $("btn-anonymize").disabled = false;
        toast("L'anonymisation a échoué. Veuillez réessayer.", "error");
        await loadDocList();
      }
    } catch {
      clearInterval(interval);
      $("anon-loading").style.display = "none";
      $("btn-anonymize").disabled = false;
      toast("Erreur de connexion pendant l'anonymisation.", "error");
      await loadDocList().catch(() => {});
    }
  }, 2000);
}

// ── Preview tabs ───────────────────────────────────────────────────────

function switchTab(tabName) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === tabName)
  );
  $("tab-anonymized").style.display = tabName === "anonymized" ? "" : "none";
  $("tab-original").style.display = tabName === "original" ? "" : "none";
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
    resetChat();
    await loadDocList();
    toast("Document validé — posez vos questions !", "success");
  } catch (e) {
    toast(`Erreur validation: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Valider et continuer →";
  }
}

// ── AI Chat ────────────────────────────────────────────────────────────

function resetChat() {
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

async function sendMessage() {
  const input = $("chat-input");
  const question = input.value.trim();
  if (!question || !currentDocId) return;
  if (activeStream) return;

  input.value = "";
  appendUserMsg(question);
  const bodyEl = appendAssistantMsg();

  $("btn-send").style.display = "none";
  $("btn-stop-stream").style.display = "";

  const controller = new AbortController();
  activeStream = controller;

  try {
    const resp = await fetch(
      `${API}/ai/stream/${currentDocId}?question=${encodeURIComponent(question)}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      }
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

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
            $("chat-messages").scrollTop = $("chat-messages").scrollHeight;
          } else if (parsed.error) {
            bodyEl.textContent += `\n[Erreur: ${parsed.error}]`;
          }
        } catch {}
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") {
      bodyEl.textContent += `\n[Erreur: ${e.message}]`;
    }
  } finally {
    activeStream = null;
    $("btn-send").style.display = "";
    $("btn-stop-stream").style.display = "none";
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
  } catch (e) {
    toast(`Erreur export texte: ${e.message}`, "error");
  }
}

async function exportPdf() {
  if (!currentDocId) return;
  try {
    const resp = await apiRequest(`/documents/${currentDocId}/export-pdf`);
    const blob = await resp.blob();
    triggerDownload(blob, `confidoc_${currentDocId.slice(0, 8)}.pdf`);
  } catch (e) {
    toast(`Erreur export PDF: ${e.message}`, "error");
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

// ── Event listeners ────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {

  // Login form
  $("form-login").addEventListener("submit", async e => {
    e.preventDefault();
    const btn = e.target.querySelector("button[type=submit]");
    const errEl = $("auth-error");
    btn.disabled = true;
    errEl.style.display = "none";
    try {
      const email = $("email").value;
      const data = await login(email, $("password").value);
      token = data.access_token;
      sessionStorage.setItem("confidoc_token", token);
      await initApp(data.email || email);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = "";
    } finally {
      btn.disabled = false;
    }
  });

  $("btn-logout").addEventListener("click", logout);

  // Sidebar: new document
  $("btn-new-doc").addEventListener("click", () => {
    currentDocId = null;
    document.querySelectorAll(".doc-item").forEach(el => el.classList.remove("selected"));
    setStep(1);
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

  // Anonymize
  $("btn-anonymize").addEventListener("click", anonymize);

  // Validate
  $("btn-validate").addEventListener("click", validate);

  // Preview tabs
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // AI chat
  $("btn-send").addEventListener("click", sendMessage);
  $("chat-input").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  $("btn-stop-stream").addEventListener("click", stopStream);

  // Quick action buttons
  document.querySelectorAll(".quick-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      $("chat-input").value = btn.dataset.q;
      sendMessage();
    });
  });

  // Export
  $("btn-export-txt").addEventListener("click", exportText);
  $("btn-export-pdf").addEventListener("click", exportPdf);

  // Resume session if token exists
  if (token) {
    initApp().catch(() => logout());
  }
});
