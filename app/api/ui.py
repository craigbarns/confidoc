"""ConfiDoc Backend — UI de test (login + upload)."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def upload_ui() -> str:
    """Interface de test minimale pour login + upload document."""
    return """
<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ConfiDoc Upload UI</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 30px; max-width: 720px; }
    h1 { margin-bottom: 8px; }
    .box { border: 1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 16px; }
    label { display: block; margin-top: 8px; }
    input, button { margin-top: 6px; padding: 8px; width: 100%; box-sizing: border-box; }
    button { cursor: pointer; font-weight: 600; }
    pre { background: #f7f7f7; padding: 12px; border-radius: 6px; overflow: auto; }
    .ok { color: #0a7a2f; }
    .err { color: #b50000; }
  </style>
</head>
<body>
  <h1>ConfiDoc — Interface Upload</h1>
  <p>Connecte-toi puis charge un document (PDF, PNG, JPG, JPEG, TIFF).</p>

  <div class="box">
    <h2>1) Connexion</h2>
    <label>Email</label>
    <input id="email" type="email" placeholder="admin@cabinet.fr" />
    <label>Mot de passe</label>
    <input id="password" type="password" placeholder="••••••••" />
    <button id="loginBtn">Se connecter</button>
    <p id="loginStatus"></p>
  </div>

  <div class="box">
    <h2>2) Upload document</h2>
    <input id="fileInput" type="file" />
    <button id="uploadBtn">Uploader</button>
    <p id="uploadStatus"></p>
  </div>

  <div class="box">
    <h2>Réponse API</h2>
    <pre id="output">{}</pre>
  </div>

  <script>
    let accessToken = "";

    const output = document.getElementById("output");
    const loginStatus = document.getElementById("loginStatus");
    const uploadStatus = document.getElementById("uploadStatus");

    function show(data) {
      output.textContent = JSON.stringify(data, null, 2);
    }

    document.getElementById("loginBtn").addEventListener("click", async () => {
      loginStatus.textContent = "";
      const email = document.getElementById("email").value.trim();
      const password = document.getElementById("password").value;

      try {
        const res = await fetch("/api/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });
        const raw = await res.text();
        let data;
        try {
          data = raw ? JSON.parse(raw) : {};
        } catch {
          data = { raw };
        }
        show(data);

        if (!res.ok) {
          loginStatus.className = "err";
          loginStatus.textContent = `Echec login (${res.status})`;
          return;
        }

        accessToken = data.access_token || "";
        loginStatus.className = "ok";
        loginStatus.textContent = "Connecté";
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

      try {
        const res = await fetch("/api/v1/uploads", {
          method: "POST",
          headers: { "Authorization": `Bearer ${accessToken}` },
          body: form
        });
        const raw = await res.text();
        let data;
        try {
          data = raw ? JSON.parse(raw) : {};
        } catch {
          data = { raw };
        }
        show(data);

        if (!res.ok) {
          uploadStatus.className = "err";
          uploadStatus.textContent = `Upload échoué (${res.status})`;
          return;
        }

        uploadStatus.className = "ok";
        uploadStatus.textContent = "Upload réussi";
      } catch (e) {
        uploadStatus.className = "err";
        uploadStatus.textContent = "Erreur réseau/upload";
      }
    });
  </script>
</body>
</html>
"""
