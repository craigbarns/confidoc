"""ConfiDoc Backend — UI Console premium."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg-deep:#050816;--bg-card:rgba(15,23,42,0.65);--bg-card-hover:rgba(15,23,42,0.85);
  --glass:rgba(255,255,255,0.03);--glass-border:rgba(148,163,184,0.12);
  --text:#e2e8f0;--text-muted:#94a3b8;--text-dim:#64748b;
  --accent:#3b82f6;--accent-glow:rgba(59,130,246,0.25);
  --violet:#8b5cf6;--violet-glow:rgba(139,92,246,0.2);
  --emerald:#10b981;--emerald-glow:rgba(16,185,129,0.2);
  --amber:#f59e0b;--rose:#f43f5e;
  --radius:16px;--radius-sm:10px;--radius-xs:8px;
  --shadow:0 20px 60px rgba(0,0,0,0.4),0 1px 3px rgba(0,0,0,0.2);
  --transition:all .25s cubic-bezier(.4,0,.2,1);
}
html,body{height:100%;font-family:'Inter',system-ui,sans-serif;background:var(--bg-deep);color:var(--text);overflow-x:hidden}
body{background:var(--bg-deep)}
.screen{display:none;min-height:100vh;animation:fadeIn .5s ease}
.screen.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes float{0%,100%{transform:translate(0,0) scale(1)}33%{transform:translate(30px,-20px) scale(1.05)}66%{transform:translate(-20px,15px) scale(.97)}}
@keyframes pulse-glow{0%,100%{opacity:.4}50%{opacity:.7}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes slideUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
@keyframes slideIn{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}
@keyframes toast-in{from{opacity:0;transform:translateX(100%)}to{opacity:1;transform:translateX(0)}}
@keyframes toast-out{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(100%)}}
@keyframes spin{to{transform:rotate(360deg)}}

/* ===== LOGIN SCREEN ===== */
.login-bg{position:fixed;inset:0;overflow:hidden;z-index:0}
.login-bg .orb{position:absolute;border-radius:50%;filter:blur(80px);animation:float 15s ease-in-out infinite}
.login-bg .orb-1{width:500px;height:500px;background:var(--accent-glow);top:-10%;left:-5%;animation-delay:0s}
.login-bg .orb-2{width:400px;height:400px;background:var(--violet-glow);bottom:-5%;right:-5%;animation-delay:5s}
.login-bg .orb-3{width:300px;height:300px;background:var(--emerald-glow);top:40%;right:30%;animation-delay:10s}
.login-wrap{position:relative;z-index:1;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.login-card{width:100%;max-width:420px;background:var(--bg-card);backdrop-filter:blur(40px) saturate(1.5);border:1px solid var(--glass-border);border-radius:24px;padding:48px 40px;box-shadow:var(--shadow);animation:slideUp .7s ease}
.login-logo{display:flex;align-items:center;gap:12px;margin-bottom:8px}
.login-logo .shield{width:44px;height:44px;background:linear-gradient(135deg,var(--accent),var(--violet));border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;box-shadow:0 8px 24px var(--accent-glow)}
.login-logo span{font-size:24px;font-weight:800;background:linear-gradient(135deg,var(--accent),var(--violet));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.login-card h1{font-size:28px;font-weight:700;margin:20px 0 6px;letter-spacing:-.02em}
.login-card .subtitle{color:var(--text-muted);font-size:14px;margin-bottom:28px;line-height:1.5}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:13px;font-weight:500;color:var(--text-muted);margin-bottom:6px}
.form-input{width:100%;padding:12px 16px;background:rgba(2,6,23,0.7);border:1px solid var(--glass-border);border-radius:var(--radius-sm);color:var(--text);font-size:14px;font-family:inherit;outline:none;transition:var(--transition)}
.form-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.form-input::placeholder{color:var(--text-dim)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:12px 24px;border:none;border-radius:var(--radius-sm);font-family:inherit;font-size:14px;font-weight:600;cursor:pointer;transition:var(--transition);outline:none}
.btn-primary{width:100%;background:linear-gradient(135deg,var(--accent),#2563eb);color:#fff;box-shadow:0 8px 24px var(--accent-glow);margin-top:8px}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 12px 32px var(--accent-glow)}
.btn-primary:active{transform:translateY(0)}
.btn-primary:disabled{opacity:.5;cursor:not-allowed;transform:none}
.btn-ghost{background:var(--glass);border:1px solid var(--glass-border);color:var(--text);padding:8px 16px}
.btn-ghost:hover{background:rgba(255,255,255,0.06);border-color:rgba(148,163,184,0.25)}
.btn-sm{padding:7px 14px;font-size:12px;border-radius:var(--radius-xs)}
.btn-icon{width:36px;height:36px;padding:0;border-radius:var(--radius-xs)}
.spinner{width:16px;height:16px;border:2px solid rgba(255,255,255,0.3);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite}

/* ===== DASHBOARD ===== */
.dash{min-height:100vh;background:var(--bg-deep)}
.topnav{position:sticky;top:0;z-index:100;display:flex;align-items:center;justify-content:space-between;padding:16px 32px;background:rgba(5,8,22,0.8);backdrop-filter:blur(20px);border-bottom:1px solid var(--glass-border)}
.topnav .logo{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:700}
.topnav .logo .shield-sm{width:32px;height:32px;background:linear-gradient(135deg,var(--accent),var(--violet));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px}
.topnav .logo span{background:linear-gradient(135deg,var(--accent),var(--violet));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.topnav .user-area{display:flex;align-items:center;gap:12px}
.topnav .user-pill{display:flex;align-items:center;gap:8px;padding:6px 14px;background:var(--glass);border:1px solid var(--glass-border);border-radius:20px;font-size:13px;color:var(--text-muted)}
.topnav .user-pill .avatar{width:24px;height:24px;background:linear-gradient(135deg,var(--emerald),var(--accent));border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff}
.dash-content{max-width:1280px;margin:0 auto;padding:28px 32px 60px}

/* Stats */
.stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px}
.stat-card{background:var(--bg-card);backdrop-filter:blur(20px);border:1px solid var(--glass-border);border-radius:var(--radius);padding:20px 24px;transition:var(--transition);animation:slideUp .5s ease both}
.stat-card:nth-child(1){animation-delay:.05s}.stat-card:nth-child(2){animation-delay:.1s}.stat-card:nth-child(3){animation-delay:.15s}.stat-card:nth-child(4){animation-delay:.2s}
.stat-card:hover{border-color:rgba(148,163,184,0.2);transform:translateY(-2px)}
.stat-card .stat-label{font-size:12px;font-weight:500;color:var(--text-dim);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.stat-card .stat-value{font-size:32px;font-weight:700;letter-spacing:-.02em}
.stat-card .stat-sub{font-size:12px;color:var(--text-muted);margin-top:4px}
.stat-card.blue .stat-value{color:var(--accent)}
.stat-card.emerald .stat-value{color:var(--emerald)}
.stat-card.violet .stat-value{color:var(--violet)}
.stat-card.amber .stat-value{color:var(--amber)}

/* Main grid */
.main-grid{display:grid;grid-template-columns:380px 1fr;gap:20px;margin-bottom:24px}
.panel{background:var(--bg-card);backdrop-filter:blur(20px);border:1px solid var(--glass-border);border-radius:var(--radius);overflow:hidden;animation:slideUp .6s ease both}
.panel-header{padding:20px 24px 16px;display:flex;align-items:center;justify-content:space-between}
.panel-header h2{font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}
.panel-header h2 .icon{font-size:18px}
.panel-body{padding:0 24px 24px}

/* Upload zone */
.upload-zone{border:2px dashed var(--glass-border);border-radius:var(--radius-sm);padding:36px 24px;text-align:center;transition:var(--transition);cursor:pointer;position:relative}
.upload-zone:hover,.upload-zone.dragover{border-color:var(--accent);background:rgba(59,130,246,0.04)}
.upload-zone.dragover{border-style:solid;box-shadow:0 0 0 4px var(--accent-glow)}
.upload-zone .upload-icon{font-size:40px;margin-bottom:12px;opacity:.7}
.upload-zone h3{font-size:14px;font-weight:600;margin-bottom:4px}
.upload-zone p{font-size:12px;color:var(--text-dim)}
.upload-zone input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer}
.upload-config{margin-top:16px;display:flex;flex-direction:column;gap:12px}
.upload-config select{width:100%;padding:10px 14px;background:rgba(2,6,23,0.7);border:1px solid var(--glass-border);border-radius:var(--radius-xs);color:var(--text);font-size:13px;font-family:inherit;outline:none;transition:var(--transition);appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2394a3b8' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}
.upload-config select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.upload-config .checkbox-row{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-muted)}
.upload-config .checkbox-row input[type=checkbox]{accent-color:var(--accent)}
.upload-progress{margin-top:16px;display:none}
.upload-progress.active{display:block}
.progress-bar{height:4px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden}
.progress-bar .fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--violet));border-radius:4px;width:0;transition:width .4s ease;animation:shimmer 2s infinite;background-size:200% 100%}
.upload-progress .prog-text{font-size:12px;color:var(--text-muted);margin-top:6px;text-align:center}

/* Documents table */
.docs-empty{text-align:center;padding:40px 20px;color:var(--text-dim);font-size:13px}
.docs-empty .empty-icon{font-size:36px;margin-bottom:12px;opacity:.4}
.doc-list{display:flex;flex-direction:column;gap:8px;max-height:520px;overflow-y:auto;padding-right:4px}
.doc-list::-webkit-scrollbar{width:4px}.doc-list::-webkit-scrollbar-track{background:transparent}.doc-list::-webkit-scrollbar-thumb{background:var(--glass-border);border-radius:4px}
.doc-item{display:flex;align-items:center;gap:14px;padding:14px 16px;background:var(--glass);border:1px solid transparent;border-radius:var(--radius-sm);transition:var(--transition);animation:slideIn .4s ease both}
.doc-item:hover{background:var(--bg-card-hover);border-color:var(--glass-border)}
.doc-item .doc-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.doc-item .doc-icon.pdf{background:rgba(239,68,68,0.12);color:#ef4444}
.doc-item .doc-icon.img{background:rgba(168,85,247,0.12);color:#a855f7}
.doc-item .doc-icon.other{background:rgba(59,130,246,0.12);color:var(--accent)}
.doc-item .doc-info{flex:1;min-width:0}
.doc-item .doc-name{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.doc-item .doc-meta{font-size:11px;color:var(--text-dim);margin-top:2px;display:flex;align-items:center;gap:8px}
.doc-item .doc-kpis{font-size:11px;color:var(--text-dim);margin-top:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.doc-item .doc-kpi{display:inline-flex;align-items:center;padding:2px 7px;border-radius:999px;border:1px solid var(--glass-border);background:rgba(2,6,23,0.45)}
.doc-item .doc-status{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;flex-shrink:0}
.doc-status.uploaded{background:rgba(59,130,246,0.12);color:var(--accent)}
.doc-status.processing{background:rgba(245,158,11,0.12);color:var(--amber)}
.doc-status.ready{background:rgba(16,185,129,0.12);color:var(--emerald)}
.doc-status.failed{background:rgba(244,63,94,0.12);color:var(--rose)}
.doc-actions{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}
.doc-actions .btn-act{padding:5px 10px;font-size:11px;font-weight:500;border:1px solid var(--glass-border);border-radius:6px;background:transparent;color:var(--text-muted);cursor:pointer;transition:var(--transition);font-family:inherit;white-space:nowrap}
.doc-actions .btn-act:hover{background:var(--glass);color:var(--text);border-color:rgba(148,163,184,0.25)}
.doc-actions .btn-act.primary{border-color:rgba(59,130,246,0.3);color:var(--accent)}
.doc-actions .btn-act.primary:hover{background:rgba(59,130,246,0.08)}
.doc-actions .btn-act.danger{border-color:rgba(244,63,94,0.2);color:var(--rose)}
.doc-actions .btn-act.danger:hover{background:rgba(244,63,94,0.06)}
.doc-actions .btn-act.success{border-color:rgba(16,185,129,0.3);color:var(--emerald)}
.doc-actions .btn-act.success:hover{background:rgba(16,185,129,0.08)}

/* Preview panel */
.preview-panel{animation-delay:.15s}
.preview-content{background:rgba(2,6,23,0.8);border:1px solid var(--glass-border);border-radius:var(--radius-sm);padding:20px;min-height:160px;max-height:500px;overflow-y:auto;font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.65;color:var(--text-muted);white-space:pre-wrap;word-break:break-word}
.preview-content::-webkit-scrollbar{width:4px}.preview-content::-webkit-scrollbar-thumb{background:var(--glass-border);border-radius:4px}
.preview-content .tag{display:inline;padding:1px 6px;border-radius:4px;font-size:12px;font-weight:600}
.preview-content .tag-email{background:rgba(59,130,246,0.15);color:var(--accent)}
.preview-content .tag-phone{background:rgba(139,92,246,0.15);color:var(--violet)}
.preview-content .tag-person{background:rgba(16,185,129,0.15);color:var(--emerald)}
.preview-content .tag-address,.preview-content .tag-city{background:rgba(245,158,11,0.15);color:var(--amber)}
.preview-content .tag-default{background:rgba(244,63,94,0.12);color:var(--rose)}

/* Before/After split view */
.preview-mode-row{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.preview-mode-btn{padding:7px 10px;font-size:12px;border-radius:var(--radius-xs);border:1px solid var(--glass-border);background:rgba(2,6,23,0.35);color:var(--text-muted);cursor:pointer;transition:var(--transition)}
.preview-mode-btn:hover{border-color:rgba(148,163,184,0.25);background:rgba(255,255,255,0.04);color:var(--text)}
.preview-mode-btn.active{border-color:rgba(59,130,246,0.35);color:var(--accent);background:rgba(59,130,246,0.08)}

.split-view{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.split-pane{background:rgba(2,6,23,0.45);border:1px solid var(--glass-border);border-radius:var(--radius-xs);padding:12px}
.split-title{font-size:12px;color:var(--text-dim);font-weight:600;margin-bottom:8px;letter-spacing:.02em}
.split-content{max-height:420px;overflow:auto;white-space:pre-wrap;word-break:break-word;font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.6;color:var(--text-muted)}
.split-content::-webkit-scrollbar{width:4px}.split-content::-webkit-scrollbar-thumb{background:var(--glass-border);border-radius:4px}

/* Masked panel */
.masked-content{background:rgba(2,6,23,0.8);border:1px solid var(--glass-border);border-radius:var(--radius-sm);padding:16px;max-height:420px;overflow:auto;font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.6;color:var(--text-dim);white-space:pre-wrap;word-break:break-word}

/* KB Ask panel */
.kb-ask-panel{margin-bottom:20px;animation-delay:.14s}
.kb-ask-row{display:flex;gap:10px;align-items:center}
.kb-ask-input{flex:1;padding:12px 14px;background:rgba(2,6,23,0.7);border:1px solid var(--glass-border);border-radius:var(--radius-xs);color:var(--text);font-size:14px;font-family:inherit;outline:none;transition:var(--transition)}
.kb-ask-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.kb-ask-hint{font-size:12px;color:var(--text-dim);margin-top:8px}

/* API Response */
.api-panel{margin-top:20px}
.api-content{background:rgba(2,6,23,0.8);border:1px solid var(--glass-border);border-radius:var(--radius-sm);padding:20px;max-height:300px;overflow:auto;font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.5;color:var(--text-dim);white-space:pre-wrap;word-break:break-word}

/* Toasts */
.toast-container{position:fixed;top:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:10px}
.toast{display:flex;align-items:center;gap:10px;padding:14px 20px;background:var(--bg-card);backdrop-filter:blur(20px);border:1px solid var(--glass-border);border-radius:var(--radius-sm);box-shadow:var(--shadow);font-size:13px;animation:toast-in .4s ease;min-width:280px;max-width:420px}
.toast.removing{animation:toast-out .3s ease forwards}
.toast .toast-icon{font-size:18px;flex-shrink:0}
.toast.success{border-left:3px solid var(--emerald)}.toast.success .toast-icon{color:var(--emerald)}
.toast.error{border-left:3px solid var(--rose)}.toast.error .toast-icon{color:var(--rose)}
.toast.info{border-left:3px solid var(--accent)}.toast.info .toast-icon{color:var(--accent)}

@media(max-width:1024px){.main-grid{grid-template-columns:1fr}.stats-row{grid-template-columns:repeat(2,1fr)}}
@media(max-width:640px){.stats-row{grid-template-columns:1fr}.topnav{padding:14px 16px}.dash-content{padding:20px 16px}.login-card{padding:36px 28px}}
</style>
"""

HTML_LOGIN = """
<div id="loginScreen" class="screen active">
  <div class="login-bg">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
  </div>
  <div class="login-wrap">
    <div class="login-card">
      <div class="login-logo">
        <div class="shield">🛡️</div>
        <span>ConfiDoc</span>
      </div>
      <h1>Bienvenue</h1>
      <p class="subtitle">Plateforme de confidentialité documentaire<br>pour professions réglementées</p>
      <div class="form-group">
        <label>Adresse email</label>
        <input id="email" class="form-input" type="email" placeholder="admin@cabinet.fr" autocomplete="email" />
      </div>
      <div class="form-group">
        <label>Mot de passe</label>
        <input id="password" class="form-input" type="password" placeholder="••••••••••" autocomplete="current-password" />
      </div>
      <button id="loginBtn" class="btn btn-primary">
        <span class="btn-text">Se connecter</span>
      </button>
    </div>
  </div>
</div>
"""

HTML_DASHBOARD = """
<div id="dashScreen" class="screen">
  <div class="dash">
    <nav class="topnav">
      <div class="logo">
        <div class="shield-sm">🛡️</div>
        <span>ConfiDoc</span>
      </div>
      <div class="user-area">
        <div class="user-pill">
          <div class="avatar" id="userAvatar">A</div>
          <span id="userEmail">admin</span>
        </div>
        <button id="logoutBtn" class="btn btn-ghost btn-sm">Déconnexion</button>
      </div>
    </nav>
    <div class="dash-content">
      <div class="stats-row">
        <div class="stat-card blue"><div class="stat-label">Documents</div><div class="stat-value" id="statTotal">0</div><div class="stat-sub">total uploadés</div></div>
        <div class="stat-card emerald"><div class="stat-label">Prêts</div><div class="stat-value" id="statReady">0</div><div class="stat-sub">anonymisés</div></div>
        <div class="stat-card violet"><div class="stat-label">En cours</div><div class="stat-value" id="statProcessing">0</div><div class="stat-sub">en traitement</div></div>
        <div class="stat-card amber"><div class="stat-label">Détections</div><div class="stat-value" id="statDetections">—</div><div class="stat-sub" id="statDetectionsSub">dernier document traité</div></div>
      </div>
      <div class="main-grid">
        <div class="panel" style="animation-delay:.08s">
          <div class="panel-header"><h2><span class="icon">📤</span> Upload</h2></div>
          <div class="panel-body">
            <div class="upload-zone" id="dropZone">
              <div class="upload-icon">📄</div>
              <h3>Glissez un fichier ici</h3>
              <p>ou cliquez pour parcourir — PDF, PNG, JPG, TIFF (max 50 MB)</p>
              <input type="file" id="fileInput" accept=".pdf,.png,.jpg,.jpeg,.tiff" />
            </div>
            <div class="upload-config">
              <div>
                <label class="form-group" style="margin-bottom:4px"><span style="font-size:12px;color:var(--text-dim)">Profil d'anonymisation</span></label>
                <select id="profileSelect" disabled>
                  <option value="dataset_accounting" selected>📊 Dataset comptable</option>
                </select>
              </div>
              <div class="checkbox-row">
                <input type="checkbox" id="autoAnonymize" checked />
                <label for="autoAnonymize">Anonymiser automatiquement</label>
              </div>
            </div>
            <div class="upload-progress" id="uploadProgress">
              <div class="progress-bar"><div class="fill" id="progressFill"></div></div>
              <div class="prog-text" id="progText">Upload en cours…</div>
            </div>
          </div>
        </div>
        <div class="panel" style="animation-delay:.12s">
          <div class="panel-header">
            <h2><span class="icon">📁</span> Mes documents</h2>
            <button id="refreshBtn" class="btn btn-ghost btn-sm">↻ Actualiser</button>
          </div>
          <div class="panel-body">
            <div id="docList" class="doc-list">
              <div class="docs-empty"><div class="empty-icon">📂</div><p>Aucun document.<br>Uploadez votre premier fichier.</p></div>
            </div>
          </div>
        </div>
      </div>
      <div class="panel kb-ask-panel">
        <div class="panel-header"><h2><span class="icon">💬</span> Question à la base anonyme</h2></div>
        <div class="panel-body">
          <div class="kb-ask-row">
            <input id="kbQuestion" class="kb-ask-input" type="text" placeholder="Ex: charges marketing T1, compte 622, facture fournisseur..." />
            <button id="askKbBtn" class="btn btn-ghost btn-sm">Poser la question</button>
          </div>
          <div class="kb-ask-hint">Astuce: commencez par ingérer vos documents via l'API <code>/api/v1/kb/ingest/{document_id}</code>.</div>
        </div>
      </div>
      <div class="panel preview-panel">
        <div class="panel-header"><h2><span class="icon">👁️</span> Prévisualisation</h2></div>
        <div class="panel-body">
          <div class="preview-mode-row">
            <button id="modeAnonOnly" class="preview-mode-btn active" type="button">Anonymisé</button>
            <button id="modeBeforeAfter" class="preview-mode-btn" type="button">Avant / Après</button>
          </div>
          <div class="preview-content" id="previewOutput">Sélectionnez un document et lancez une action pour voir la prévisualisation ici.</div>
        </div>
      </div>
      <div class="panel" style="animation-delay:.22s">
        <div class="panel-header"><h2><span class="icon">🕵️</span> Ce qui a été masqué</h2></div>
        <div class="panel-body">
          <div class="masked-content" id="maskedOutput">Lancez `Anonymiser` / `Traiter tout` pour voir le résumé.</div>
        </div>
      </div>
      <div class="panel api-panel" style="animation-delay:.2s">
        <div class="panel-header"><h2><span class="icon">⚡</span> Réponse API</h2></div>
        <div class="panel-body"><pre class="api-content" id="apiOutput">{}</pre></div>
      </div>
    </div>
  </div>
</div>
<div class="toast-container" id="toastContainer"></div>
"""

JAVASCRIPT = """
<script>
let accessToken = "";
let currentDocs = [];
let docDetectionMap = {};
let lastAnonDocId = null;
let lastAnonText = "";
let lastOriginalDocId = null;
let lastOriginalText = "";
let previewMode = "anon"; // "anon" | "beforeafter"

const $ = id => document.getElementById(id);
const previewOut = $("previewOutput");
const maskedOut = $("maskedOutput");
const apiOut = $("apiOutput");
const docList = $("docList");
const toastBox = $("toastContainer");

function toast(msg, type="info") {
  const icons = {success:"✅",error:"❌",info:"ℹ️"};
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type]||"ℹ️"}</span><span>${msg}</span>`;
  toastBox.appendChild(el);
  setTimeout(() => { el.classList.add("removing"); setTimeout(() => el.remove(), 300); }, 4000);
}

function showApi(data) { apiOut.textContent = JSON.stringify(data, null, 2); }

function highlightTags(text) {
  if (!text) return "Aucune donnée.";
  const map = {"EMAIL":"tag-email","PHONE":"tag-phone","PERSON":"tag-person","ADDRESS":"tag-address","CITY":"tag-city"};
  return text.replace(/\\[(\\w+)\\]/g, (m, tag) => {
    const cls = map[tag.toUpperCase()] || "tag-default";
    return `<span class="tag ${cls}">${m}</span>`;
  });
}

function showPreview(text) { previewOut.innerHTML = highlightTags(text); }
function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setPreviewMode(mode) {
  previewMode = mode;
  const btnAnon = $("modeAnonOnly");
  const btnBA = $("modeBeforeAfter");
  if (btnAnon) btnAnon.classList.toggle("active", mode === "anon");
  if (btnBA) btnBA.classList.toggle("active", mode === "beforeafter");
}

function showBeforeAfter(originalText, anonymizedText) {
  previewOut.innerHTML = `
    <div class="split-view">
      <div class="split-pane">
        <div class="split-title">Avant (original)</div>
        <div class="split-content">${escapeHtml(originalText)}</div>
      </div>
      <div class="split-pane">
        <div class="split-title">Après (anonymisé)</div>
        <div class="split-content">${highlightTags(anonymizedText)}</div>
      </div>
    </div>
  `;
}

async function refreshMaskedSummary(docId) {
  if (!docId) return;
  try {
    const {res, data} = await api(`/api/v1/documents/${docId}/proof`);
    if (!res.ok) return;

    const types = data && data.detections_entity_types_count ? data.detections_entity_types_count : {};
    const entries = Object.entries(types).sort((a,b) => (b[1]||0) - (a[1]||0));
    const total = entries.reduce((sum, it) => sum + (it[1]||0), 0);

    const LABELS = {
      "email":"Email",
      "phone_fr":"Telephone",
      "phone_intl":"Telephone",
      "iban":"IBAN",
      "iban_compact":"IBAN",
      "bic":"BIC",
      "siret":"SIRET",
      "siren":"SIREN",
      "vat_fr":"TVA",
      "nss":"NIR/NSS",
      "address_line":"Adresse",
      "postal_city":"Ville",
      "person_title":"Nom/Personne",
      "person_name":"Nom/Personne",
      "person_uppercase":"Nom/Personne",
      "company_legal_name":"Raison sociale",
      "invoice_number":"Reference facture",
      "date_fr":"Date",
      "date_iso":"Date",
      "date_text_fr":"Date",
      "amount_eur":"Montant",
      "amount_plain":"Montant",
      "address_residence":"Adresse",
      "bank_account_code_label":"Compte bancaire",
      "country":"Pays",
      "invoice_identity_block":"Bloc identite",
      "labeled_sensitive_value":"Valeur sensible (libelle:valeur)",
    };

    const EXPL = {
      "email":"Masquage des emails (identification directe).",
      "phone_fr":"Masquage des numeros de telephone.",
      "phone_intl":"Masquage des numeros de telephone internationaux.",
      "iban":"Masquage des IBAN.",
      "bic":"Masquage des BIC.",
      "siret":"Masquage des SIRET (identifiant entreprise).",
      "siren":"Masquage des SIREN (identifiant entreprise).",
      "vat_fr":"Masquage des identifiants TVA FR.",
      "nss":"Masquage des numeros personnels (NIR/NSS).",
      "address_line":"Masquage des adresses completes.",
      "postal_city":"Masquage partiel de la localisation (ville).",
      "person_title":"Masquage des noms de personnes.",
      "person_name":"Masquage des noms de personnes.",
      "person_uppercase":"Masquage des noms de personnes (majuscule).",
      "company_legal_name":"Masquage des raisons sociales (selon regles).",
      "invoice_number":"Masquage ou redaction des references de factures selon profil.",
      "date_fr":"Masquage/normalisation des dates.",
      "amount_eur":"Montants conserves ou masques selon profil (dataset comptable: preserve).",
      "amount_plain":"Montants conserves ou masques selon profil (dataset comptable: preserve).",
      "address_residence":"Masquage de blocs adresses typiques.",
      "bank_account_code_label":"Masquage du label bancaire en conservant le code comptable si applicable.",
      "country":"Masquage des pays.",
      "invoice_identity_block":"Masquage d'un bloc identite detecte dans l'en-tete.",
      "labeled_sensitive_value":"Masquage des paires libelle:valeur sensibles (RGPD).",
    };

    const top = entries.slice(0, 10).map(([k,v]) => {
      const label = LABELS[k] || k;
      const expl = EXPL[k] || "Masquage automatique d'une donnee sensible detectee.";
      return `- ${label}: ${v}\n  ${expl}`;
    });

    maskedOut.textContent =
      `Ce qui a ete masque (compteur spans): ${total}\n\n` +
      (top.length ? top.join("\n") : "Aucune donnee sensible detectee.");
  } catch (e) {
    // no-op
  }
}

function setAnonymizedPreview(docId, text) {
  lastAnonDocId = docId;
  lastAnonText = text || "";
  lastOriginalDocId = null;
  lastOriginalText = "";
  showPreview(lastAnonText);
  refreshMaskedSummary(docId);
  if (previewMode === "beforeafter" && lastOriginalDocId === docId && lastOriginalText) {
    showBeforeAfter(lastOriginalText, lastAnonText);
  }
}

async function loadOriginalForBeforeAfter() {
  if (!lastAnonDocId || !lastAnonText) { toast("Chargez d'abord un document", "error"); return; }
  const docId = lastAnonDocId;
  if (!confirm("Afficher la version originale peut exposer des donnees sensibles. Continuer ?")) return;
  toast("Chargement version originale…", "info");
  try {
    const res = await fetch(
      `/api/v1/documents/${docId}/original?allow_original=true&max_chars=8000`,
      {headers:{Authorization:`Bearer ${accessToken}`}}
    );
    const raw = await res.text();
    if (!res.ok) {
      let detail = raw;
      try { detail = JSON.parse(raw).detail || raw; } catch {}
      toast(detail || "Erreur chargement original", "error");
      return;
    }
    lastOriginalDocId = docId;
    lastOriginalText = raw || "";
    showBeforeAfter(lastOriginalText, lastAnonText);
  } catch (e) {
    toast("Erreur reseau", "error");
  }
}
function setDetections(count, context) {
  $("statDetections").textContent = count;
  $("statDetectionsSub").textContent = context || "dernier document traité";
}
function showPlain(text) {
  previewOut.textContent = text || "";
}

function showProofSummary(data) {
  if (!data) { showPlain("Aucune preuve RGPD."); return; }
  const steps = [];
  if (data.preview_version_present) steps.push("Anonymisation générée (preview)");
  if (data.final_version_present) steps.push("Version finale validée");
  if ((data.detections_count || 0) > 0) steps.push("Données sensibles détectées");

  const types = data.detections_entity_types_count || {};
  const entries = Object.entries(types)
    .sort((a,b) => (b[1]||0) - (a[1]||0))
    .slice(0, 8);

  const topTypes = entries.length
    ? entries.map(([k,v]) => `${k}: ${v}`).join("\n")
    : "(aucune détection)";

  const finalPresent = data.final_version_present ? "oui" : "non";
  showPlain(
    `PREUVE RGPD — document ${data.document_id}\n\n` +
    `sha256 source: ${data.document_sha256}\n` +
    `sha256 preview: ${data.preview_version_sha256 || "(absent)"}\n` +
    `sha256 final: ${data.final_version_sha256 || "(absent)"}\n\n` +
    `Final validé: ${finalPresent}\n` +
    `Détections: ${data.detections_count || 0}\n` +
    `Requêtes LLM: ${data.llm_requests_count || 0}\n\n` +
    `Timeline: ${steps.length ? "" : "(non disponible)"}\n` +
    `${steps.map(s => `- ${s}`).join("\n")}\n\n` +
    `Top entités masquées (résumé):\n${topTypes}\n`
  );
}

function showAuditSummary(data) {
  if (!data) { showPlain("Aucun audit export."); return; }
  const types = data.detections_entity_types_count || {};
  const entries = Object.entries(types)
    .sort((a,b) => (b[1]||0) - (a[1]||0))
    .slice(0, 10);
  const topTypes = entries.length
    ? entries.map(([k,v]) => `${k}: ${v}`).join("\n")
    : "(aucun type)";

  const llmReqs = Array.isArray(data.llm_requests) ? data.llm_requests : [];
  const llmLine = llmReqs.length ? `LLM requêtes: ${llmReqs.length}` : "LLM requêtes: 0";

  showPlain(
    `AUDIT EXPORT (RGPD) — ${data.document_id}\n\n` +
    `document_sha256: ${data.document_sha256}\n\n` +
    `types entités (top):\n${topTypes}\n\n` +
    `${llmLine}\n`
  );
}
function setDocDetection(docId, count) {
  docDetectionMap[docId] = count;
  const el = document.querySelector(`[data-doc-detection="${docId}"]`);
  if (el) el.textContent = `entités: ${count}`;
}

async function api(path, opts={}) {
  const headers = opts.headers || {};
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const res = await fetch(path, {...opts, headers});
  const raw = await res.text();
  let data;
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = {raw}; }
  return {res, data};
}

function formatSize(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b/1024).toFixed(1) + " KB";
  return (b/1048576).toFixed(1) + " MB";
}

function docIcon(ext) {
  ext = (ext||"").toLowerCase();
  if (ext === "pdf") return {cls:"pdf",icon:"📕"};
  if (["png","jpg","jpeg","tiff"].includes(ext)) return {cls:"img",icon:"🖼️"};
  return {cls:"other",icon:"📄"};
}

function renderDocs(items) {
  currentDocs = items || [];
  const total = currentDocs.length;
  const ready = currentDocs.filter(d=>d.status==="ready").length;
  const processing = currentDocs.filter(d=>d.status==="processing").length;
  $("statTotal").textContent = total;
  $("statReady").textContent = ready;
  $("statProcessing").textContent = processing;

  if (!currentDocs.length) {
    docList.innerHTML = '<div class="docs-empty"><div class="empty-icon">📂</div><p>Aucun document.<br>Uploadez votre premier fichier.</p></div>';
    return;
  }
  docList.innerHTML = "";
  currentDocs.forEach((doc, i) => {
    const ic = docIcon(doc.extension);
    const el = document.createElement("div");
    el.className = "doc-item";
    el.style.animationDelay = `${i*0.05}s`;
    el.innerHTML = `
      <div class="doc-icon ${ic.cls}">${ic.icon}</div>
      <div class="doc-info">
        <div class="doc-name" title="${doc.original_filename}">${doc.original_filename}</div>
        <div class="doc-meta"><span>${formatSize(doc.size_bytes)}</span><span class="doc-status ${doc.status}">${doc.status}</span></div>
        <div class="doc-kpis">
          <span class="doc-kpi" data-doc-detection="${doc.id}">${docDetectionMap[doc.id] != null ? `entités: ${docDetectionMap[doc.id]}` : "entités: —"}</span>
        </div>
        <div class="doc-actions">
          <button class="btn-act success" data-a="processall" data-id="${doc.id}">🚀 Traiter tout</button>
          <button class="btn-act primary" data-a="anonymize" data-id="${doc.id}">🔒 Anonymiser</button>
          <button class="btn-act" data-a="preview" data-id="${doc.id}">👁️ Preview</button>
          <button class="btn-act success" data-a="validate" data-id="${doc.id}">✓ Valider</button>
          <button class="btn-act" data-a="exportdataset" data-id="${doc.id}">📊 Dataset</button>
          <button class="btn-act" data-a="proof" data-id="${doc.id}">🛡️ Preuve RGPD</button>
          <button class="btn-act" data-a="auditexport" data-id="${doc.id}">🧾 Audit export</button>
          <button class="btn-act danger" data-a="delete" data-id="${doc.id}">🗑️</button>
        </div>
      </div>`;
    docList.appendChild(el);
  });
}

async function refreshDocs() {
  if (!accessToken) return;
  try {
    const {res, data} = await api("/api/v1/documents");
    showApi(data);
    if (res.ok) {
      renderDocs(data);
      await refreshDocDetections(data);
    }
  } catch(e) { toast("Erreur réseau", "error"); }
}

async function refreshDocDetections(items) {
  const docs = (items || []).filter(d => d.status === "ready");
  for (const doc of docs) {
    try {
      const {res, data} = await api(`/api/v1/documents/${doc.id}/preview`);
      if (res.ok) setDocDetection(doc.id, data.detections_count || 0);
    } catch {}
  }
}

// Preview mode (anonymisé / avant-apres)
const modeAnonBtn = $("modeAnonOnly");
const modeBeforeAfterBtn = $("modeBeforeAfter");
if (modeAnonBtn) {
  modeAnonBtn.addEventListener("click", () => {
    setPreviewMode("anon");
    if (lastAnonText) showPreview(lastAnonText);
  });
}
if (modeBeforeAfterBtn) {
  modeBeforeAfterBtn.addEventListener("click", async () => {
    setPreviewMode("beforeafter");
    await loadOriginalForBeforeAfter();
  });
}

// Login
$("loginBtn").addEventListener("click", async () => {
  const btn = $("loginBtn");
  const email = $("email").value.trim();
  const pw = $("password").value;
  if (!email || !pw) { toast("Remplissez tous les champs", "error"); return; }
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner"></div>';
  try {
    const {res, data} = await api("/api/v1/auth/login", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({email, password: pw})
    });
    showApi(data);
    if (!res.ok) {
      const detail = (data && data.detail) || (data && data.raw) || `Échec login (${res.status})`;
      toast(detail, "error");
      return;
    }
    accessToken = data.access_token || "";
    $("userEmail").textContent = email.split("@")[0];
    $("userAvatar").textContent = email[0].toUpperCase();
    $("loginScreen").classList.remove("active");
    $("dashScreen").classList.add("active");
    toast("Connecté avec succès", "success");
    await refreshDocs();
  } catch(e) { toast("Erreur réseau", "error"); }
  finally { btn.disabled = false; btn.innerHTML = '<span class="btn-text">Se connecter</span>'; }
});

// Enter key login
$("password").addEventListener("keydown", e => { if (e.key === "Enter") $("loginBtn").click(); });
$("email").addEventListener("keydown", e => { if (e.key === "Enter") $("password").focus(); });

// Logout
$("logoutBtn").addEventListener("click", async () => {
  try { await api("/api/v1/auth/logout", {method:"POST"}); } catch {}
  accessToken = "";
  $("dashScreen").classList.remove("active");
  $("loginScreen").classList.add("active");
  toast("Déconnecté", "info");
});

// Upload drag & drop
const dropZone = $("dropZone");
const fileInput = $("fileInput");
["dragenter","dragover"].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add("dragover"); }));
["dragleave","drop"].forEach(ev => dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove("dragover"); }));
dropZone.addEventListener("drop", e => { if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; doUpload(); } });
fileInput.addEventListener("change", () => { if (fileInput.files.length) doUpload(); });

async function doUpload() {
  if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
  const file = fileInput.files[0];
  if (!file) return;
  const prog = $("uploadProgress");
  const fill = $("progressFill");
  const progText = $("progText");
  prog.classList.add("active");
  fill.style.width = "30%";
  progText.textContent = `Upload de ${file.name}…`;

  const form = new FormData();
  form.append("file", file);
  const profile = $("profileSelect").value;
  const auto = $("autoAnonymize").checked;

  try {
    fill.style.width = "60%";
    const {res, data} = await api(`/api/v1/uploads?auto_anonymize=${auto}&profile=${encodeURIComponent(profile)}&document_type=auto`, {method:"POST", body:form});
    showApi(data);
    if (!res.ok) {
      toast(`Upload échoué: ${data.detail||res.status}`, "error");
      fill.style.width = "100%"; fill.style.background = "var(--rose)";
      progText.textContent = "Échec";
    } else {
      fill.style.width = "100%";
      progText.textContent = "Terminé !";
      const count = data && data.processing ? data.processing.detections_count : null;
      toast(`${file.name} uploadé — ${count != null ? count + " détections" : "prêt"}`, "success");
      await refreshDocs();
    }
  } catch(e) { toast("Erreur réseau", "error"); }
  finally { setTimeout(() => { prog.classList.remove("active"); fill.style.width = "0"; fill.style.background = ""; }, 2500); fileInput.value = ""; }
}

// Refresh
$("refreshBtn").addEventListener("click", () => { refreshDocs(); toast("Liste actualisée", "info"); });

// KB ask
async function askKb() {
  const input = $("kbQuestion");
  const query = (input.value || "").trim();
  if (!accessToken) { toast("Connectez-vous d'abord", "error"); return; }
  if (!query) { toast("Saisissez une question", "error"); return; }

  const askBtn = $("askKbBtn");
  askBtn.disabled = true;
  try {
    // Ingestion automatique des documents "ready" avant recherche KB
    const readyDocs = (currentDocs || []).filter(d => d.status === "ready");
    if (readyDocs.length) {
      toast("Indexation KB en cours…", "info");
      for (const doc of readyDocs) {
        const {res: ingestRes} = await api(`/api/v1/kb/ingest/${doc.id}`, {method: "POST"});
        if (!ingestRes.ok && ingestRes.status !== 404) {
          // On continue sur les autres docs: un doc invalide ne doit pas bloquer les questions
        }
      }
    }

    toast("Recherche dans la base anonyme…", "info");
    $("statDetectionsSub").textContent = "compteur d'anonymisation, pas des questions";
    const {res, data} = await api("/api/v1/kb/search", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({query, limit: 20, include_needs_review: true}),
    });
    showApi(data);
    if (!res.ok) { toast(data.detail || "Recherche KB échouée", "error"); return; }

    const results = Array.isArray(data.results) ? data.results : [];
    if (!results.length) {
      showPreview("Aucun résultat dans la base anonyme pour cette question.");
      toast("Aucun résultat", "info");
      return;
    }

    const lines = results.slice(0, 8).map((r, idx) => {
      if (r.type === "accounting_record") {
        return `${idx + 1}. [record] ${r.code_comptable || "-"} | ${r.categorie_pcg || "-"} | ${r.montant_raw || "-"}\n${r.libelle || ""}`;
      }
      return `${idx + 1}. [chunk] ${r.chunk_text || ""}`;
    });
    showPreview(`Question: ${query}\n\nRésultats (${results.length}):\n\n${lines.join("\\n\\n")}`);
    toast(`${results.length} résultat(s) trouvés`, "success");
  } catch (e) {
    toast("Erreur réseau", "error");
  } finally {
    askBtn.disabled = false;
  }
}

$("askKbBtn").addEventListener("click", askKb);
$("kbQuestion").addEventListener("keydown", e => { if (e.key === "Enter") askKb(); });

// Document actions
docList.addEventListener("click", async e => {
  const btn = e.target.closest("[data-a]");
  if (!btn || !accessToken) return;
  const action = btn.dataset.a;
  const id = btn.dataset.id;
  const profile = $("profileSelect").value;
  btn.disabled = true;
  try {
    if (action === "processall") {
      toast("Traitement complet en cours…", "info");
      const a1 = await api(`/api/v1/documents/${id}/anonymize?profile=${encodeURIComponent(profile)}&document_type=auto`, {method:"POST"});
      showApi(a1.data);
      if (!a1.res.ok) { toast(a1.data.detail||"Échec anonymisation", "error"); return; }
      setDetections(a1.data.detections_count||0, "dernier document traité");
      setDocDetection(id, a1.data.detections_count||0);

      const a2 = await api(`/api/v1/documents/${id}/preview`);
      showApi(a2.data);
      if (!a2.res.ok) { toast(a2.data.detail||"Échec preview", "error"); return; }
      setAnonymizedPreview(id, a2.data.preview_text||"");

      const a3 = await api(`/api/v1/documents/${id}/validate`, {method:"POST"});
      showApi(a3.data);
      if (!a3.res.ok) { toast(a3.data.detail||"Échec validation", "error"); return; }

      const a4 = await fetch(`/api/v1/documents/${id}/export-dataset`, {headers:{Authorization:`Bearer ${accessToken}`}});
      const a4data = await a4.json().catch(()=>({}));
      showApi(a4data);
      if (!a4.ok) { toast("Échec export dataset", "error"); return; }
      showPreview(a4data.anonymized_text||"Dataset exporté");
      const q4 = a4data && a4data.quality ? a4data.quality : {};
      toast(`Terminé ✓ entités=${q4.detections_count||0} review=${q4.needs_review}`, "success");
    } else if (action === "anonymize") {
      toast("Anonymisation en cours…", "info");
      const {res, data} = await api(`/api/v1/documents/${id}/anonymize?profile=${encodeURIComponent(profile)}&document_type=auto`, {method:"POST"});
      showApi(data);
      if (res.ok) { setAnonymizedPreview(id, data.preview_text||""); toast(`${data.detections_count||0} entités détectées`, "success"); setDetections(data.detections_count||0, "dernier document traité"); setDocDetection(id, data.detections_count||0); }
      else toast(data.detail||"Échec", "error");
    } else if (action === "preview") {
      const {res, data} = await api(`/api/v1/documents/${id}/preview`);
      showApi(data);
      if (res.ok) setAnonymizedPreview(id, data.preview_text||""); else toast(data.detail||"Pas de preview", "error");
    } else if (action === "validate") {
      const {res, data} = await api(`/api/v1/documents/${id}/validate`, {method:"POST"});
      showApi(data);
      if (res.ok) toast("Version finale validée ✓", "success"); else toast(data.detail||"Échec", "error");
    } else if (action === "exporttxt") {
      const res = await fetch(`/api/v1/documents/${id}/export`, {headers:{Authorization:`Bearer ${accessToken}`}});
      const text = await res.text();
      if (res.ok) { showPreview(text); toast("Export texte prêt", "success"); } else toast("Export échoué", "error");
    } else if (action === "exportpdf") {
      toast("Génération du PDF…", "info");
      const res = await fetch(`/api/v1/documents/${id}/export-pdf`, {headers:{Authorization:`Bearer ${accessToken}`}});
      if (!res.ok) { toast("Export PDF échoué", "error"); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href=url; a.download=`redacted_${id}.pdf`; a.click(); URL.revokeObjectURL(url);
      toast("PDF redacté téléchargé", "success");
    } else if (action === "exportdataset") {
      const res = await fetch(`/api/v1/documents/${id}/export-dataset`, {headers:{Authorization:`Bearer ${accessToken}`}});
      const data = await res.json().catch(()=>({}));
      showApi(data);
      if (res.ok) {
        const q = data && data.quality ? data.quality : {};
        setAnonymizedPreview(id, data.anonymized_text||"Dataset exporté");
        toast(`Dataset: ${q.detections_count||0} entités, review=${q.needs_review}`, "success");
      }
      else toast("Export dataset échoué", "error");
    } else if (action === "proof") {
      const {res, data} = await api(`/api/v1/documents/${id}/proof`);
      showApi(data);
      if (res.ok) { showProofSummary(data); toast("Preuve RGPD affichée", "success"); }
      else toast(data.detail || "Erreur preuve RGPD", "error");
    } else if (action === "auditexport") {
      const {res, data} = await api(`/api/v1/documents/${id}/audit-export`);
      showApi(data);
      if (res.ok) { showAuditSummary(data); toast("Audit export prêt", "success"); }
      else toast(data.detail || "Erreur audit export", "error");
    } else if (action === "delete") {
      // Effacement RGPD en 2 étapes : aperçu (compteurs) puis confirmation forte.
      const {res: prevRes, data: prevData} = await api(`/api/v1/documents/${id}/deletion-preview`);
      if (!prevRes.ok) {
        toast(prevData.detail || "Impossible de charger l'aperçu suppression", "error");
        return;
      }
      showApi(prevData);
      const typed = prompt("Effacement RGPD : tapez exactement SUPPRIMER pour confirmer.");
      if (typed !== "SUPPRIMER") { toast("Suppression annulée", "info"); return; }
      const res = await fetch(`/api/v1/documents/${id}`, {method:"DELETE",headers:{Authorization:`Bearer ${accessToken}`}});
      if (res.ok) { toast("Document supprimé", "success"); showPreview("Document supprimé."); } else toast("Suppression échouée", "error");
    }
  } catch(e) { toast("Erreur réseau", "error"); }
  finally { btn.disabled = false; await refreshDocs(); }
});
</script>
"""


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def upload_ui() -> str:
    """Interface web ConfiDoc — Console premium."""
    return HTMLResponse(
        content=f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ConfiDoc — Console</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🛡️</text></svg>">
  {CSS}
</head>
<body>
  {HTML_LOGIN}
  {HTML_DASHBOARD}
  {JAVASCRIPT}
</body>
</html>""",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )
