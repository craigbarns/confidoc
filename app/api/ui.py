"""ConfiDoc Backend — UI de test (login + upload)."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def upload_ui() -> str:
    """Interface web V1: login, upload, anonymisation, export."""
    return """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ConfiDoc Console</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #111827;
      --border: #374151;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --ok: #22c55e;
      --err: #ef4444;
      --btn: #2563eb;
    }
    body { font-family: -apple-system, Segoe UI, Arial, sans-serif; margin: 24px; background: var(--bg); color: var(--text); }
    h1 { margin: 0 0 8px 0; font-size: 24px; }
    h2 { margin: 0 0 10px 0; font-size: 18px; }
    p { color: var(--muted); margin-top: 0; }
    .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .full { grid-column: 1 / -1; }
    .box { border: 1px solid var(--border); background: var(--card); padding: 14px; border-radius: 10px; }
    label { display: block; margin-top: 8px; color: var(--muted); }
    input, button, select { margin-top: 6px; padding: 9px; width: 100%; box-sizing: border-box; border-radius: 8px; border: 1px solid var(--border); background: #0b1220; color: var(--text); }
    button { cursor: pointer; font-weight: 600; background: var(--btn); border: none; }
    button.secondary { background: #334155; }
    button.small { width: auto; padding: 6px 10px; font-size: 12px; margin-right: 6px; }
    pre { background: #020617; padding: 12px; border-radius: 8px; overflow: auto; border: 1px solid var(--border); }
    .ok { color: var(--ok); }
    .err { color: var(--err); }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { border-bottom: 1px solid var(--border); padding: 8px; font-size: 13px; text-align: left; vertical-align: top; }
    .actions { white-space: nowrap; }
    @media (max-width: 980px) { .layout { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <h1>ConfiDoc Console</h1>
  <p>Upload, anonymisation, preview, validation, export texte et PDF redacted.</p>
  <div class="box full" style="border-color:#22c55e">
    <strong>UI v2 active</strong> — build forced: 2026-03-19-13:40
  </div>

  <div class="layout">
  <div class="box">
    <h2>1) Connexion</h2>
    <label>Email</label><input id="email" type="email" placeholder="admin@cabinet.fr" />
    <label>Mot de passe</label><input id="password" type="password" placeholder="••••••••" />
    <button id="loginBtn">Se connecter</button>
    <p id="loginStatus"></p>
  </div>

  <div class="box">
    <h2>2) Upload document</h2>
    <label>Profil d'anonymisation</label>
    <select id="profileSelect">
      <option value="moderate" selected>Modéré</option>
      <option value="strict">Strict</option>
      <option value="dataset_strict">Dataset strict</option>
      <option value="dataset_accounting">Dataset comptable (garde montants)</option>
    </select>
    <label style="margin-top:8px"><input id="autoAnonymize" type="checkbox" checked style="width:auto; margin-right:8px" /> Anonymiser automatiquement après upload</label>
    <input id="fileInput" type="file" />
    <button id="uploadBtn">Uploader</button>
    <p id="uploadStatus"></p>
  </div>

  <div class="box full">
    <h2>3) Mes documents</h2>
    <button id="refreshDocsBtn" class="secondary">Rafraîchir la liste</button>
    <table>
      <thead>
        <tr>
          <th>Nom</th>
          <th>Statut</th>
          <th>Taille</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="docsBody"></tbody>
    </table>
  </div>

  <div class="box full">
    <h2>4) Preview anonymisation</h2>
    <pre id="previewOutput">Aucune preview.</pre>
  </div>

  <div class="box full">
    <h2>Réponse API</h2>
    <pre id="output">{}</pre>
  </div>
  </div>

  <script>
    let accessToken = "";

    const output = document.getElementById("output");
    const previewOutput = document.getElementById("previewOutput");
    const docsBody = document.getElementById("docsBody");
    const loginStatus = document.getElementById("loginStatus");
    const uploadStatus = document.getElementById("uploadStatus");

    function show(data) {
      output.textContent = JSON.stringify(data, null, 2);
    }

    function showPreview(text) {
      previewOutput.textContent = text || "Aucune preview.";
    }

    async function api(path, options = {}) {
      const headers = options.headers || {};
      if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
      const res = await fetch(path, { ...options, headers });
      const raw = await res.text();
      let data;
      try { data = raw ? JSON.parse(raw) : {}; } catch { data = { raw }; }
      return { res, data };
    }

    function renderDocuments(items) {
      docsBody.innerHTML = "";
      if (!items || items.length === 0) {
        docsBody.innerHTML = `<tr><td colspan="4">Aucun document.</td></tr>`;
        return;
      }

      for (const doc of items) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${doc.original_filename}<br><small>${doc.id}</small></td>
          <td>${doc.status}</td>
          <td>${doc.size_bytes} bytes</td>
          <td class="actions">
            <button class="small" data-action="anonymize" data-id="${doc.id}">Anonymiser</button>
            <button class="small" data-action="preview" data-id="${doc.id}">Preview</button>
            <button class="small" data-action="validate" data-id="${doc.id}">Valider</button>
            <button class="small" data-action="exporttxt" data-id="${doc.id}">Export TXT</button>
            <button class="small" data-action="exportpdf" data-id="${doc.id}">Export PDF</button>
          </td>
        `;
        docsBody.appendChild(tr);
      }
    }

    async function refreshDocuments() {
      if (!accessToken) return;
      const { res, data } = await api("/api/v1/documents");
      show(data);
      if (res.ok) renderDocuments(data);
    }

    document.getElementById("loginBtn").addEventListener("click", async () => {
      loginStatus.textContent = "";
      const email = document.getElementById("email").value.trim();
      const password = document.getElementById("password").value;

      try {
        const { res, data } = await api("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });
        show(data);

        if (!res.ok) {
          loginStatus.className = "err";
          loginStatus.textContent = `Echec login (${res.status})`;
          return;
        }

        accessToken = data.access_token || "";
        loginStatus.className = "ok";
        loginStatus.textContent = "Connecté";
        await refreshDocuments();
      } catch (e) {
        loginStatus.className = "err";
        loginStatus.textContent = "Erreur réseau/login";
      }
    });

    document.getElementById("uploadBtn").addEventListener("click", async () => {
      uploadStatus.textContent = "";
      if (!accessToken) {
        uploadStatus.className = "err";
        uploadStatus.textContent = "Connecte-toi d'abord";
        return;
      }

      const file = document.getElementById("fileInput").files[0];
      if (!file) {
        uploadStatus.className = "err";
        uploadStatus.textContent = "Choisis un fichier";
        return;
      }

      const form = new FormData();
      form.append("file", file);
      const profile = document.getElementById("profileSelect").value;
      const autoAnonymize = document.getElementById("autoAnonymize").checked;

      try {
        const { res, data } = await api(`/api/v1/uploads?auto_anonymize=${autoAnonymize ? "true" : "false"}&profile=${encodeURIComponent(profile)}&document_type=auto`, {
          method: "POST",
          body: form
        });
        show(data);

        if (!res.ok) {
          uploadStatus.className = "err";
          uploadStatus.textContent = `Upload échoué (${res.status})`;
          return;
        }

        uploadStatus.className = "ok";
        uploadStatus.textContent = "Upload réussi";
        await refreshDocuments();
      } catch (e) {
        uploadStatus.className = "err";
        uploadStatus.textContent = "Erreur réseau/upload";
      }
    });

    document.getElementById("refreshDocsBtn").addEventListener("click", refreshDocuments);

    docsBody.addEventListener("click", async (event) => {
      const btn = event.target.closest("button[data-action]");
      if (!btn) return;
      if (!accessToken) { show({ detail: "Connecte-toi d'abord" }); return; }
      const action = btn.dataset.action;
      const id = btn.dataset.id;
      const profile = document.getElementById("profileSelect").value;

      try {
        if (action === "anonymize") {
          const { res, data } = await api(`/api/v1/documents/${id}/anonymize?profile=${encodeURIComponent(profile)}&document_type=auto`, { method: "POST" });
          show(data);
          if (res.ok) showPreview(data.preview_text || "");
        } else if (action === "preview") {
          const { res, data } = await api(`/api/v1/documents/${id}/preview`);
          show(data);
          if (res.ok) showPreview(data.preview_text || "");
        } else if (action === "validate") {
          const { data } = await api(`/api/v1/documents/${id}/validate`, { method: "POST" });
          show(data);
        } else if (action === "exporttxt") {
          const res = await fetch(`/api/v1/documents/${id}/export`, { headers: { Authorization: `Bearer ${accessToken}` } });
          const text = await res.text();
          showPreview(text);
          show({ status: res.status, exported_text_preview: text.slice(0, 1000) });
        } else if (action === "exportpdf") {
          const res = await fetch(`/api/v1/documents/${id}/export-pdf`, { headers: { Authorization: `Bearer ${accessToken}` } });
          if (!res.ok) {
            const txt = await res.text();
            show({ status: res.status, error: txt });
            return;
          }
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `redacted_${id}.pdf`;
          a.click();
          URL.revokeObjectURL(url);
          show({ status: "ok", message: "PDF redacted téléchargé" });
        }
      } catch (e) {
        show({ detail: "Erreur réseau/action", error: String(e) });
      } finally {
        await refreshDocuments();
      }
    });
  </script>
</body>
</html>
"""
