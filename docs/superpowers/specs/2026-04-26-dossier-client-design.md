# Système Dossier Client — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructurer ConfiDoc pour les experts-comptables : chaque document appartient à un Client et un Exercice (année), détectés automatiquement à l'upload. La sidebar affiche l'arbre Client > Exercice > Documents ; cliquer un client ouvre une page dédiée (vue dossier complète) dans la zone principale.

**Architecture:** Ajout de 3 colonnes dédiées sur `Document` (client_name, exercice, doc_category), enrichissement du service de classification, nouveau service d'auto-détection de métadonnées, nouveau endpoint dossier, refonte de l'UX upload et sidebar.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL, vanilla JS

---

## 1. Contexte et état actuel

### Ce qui existe

- `Document.tags: list[str]` — le nom client est stocké dans `tags[0]` (hack)
- `Document.doc_type: str` — 4 valeurs: `invoice`, `accounting`, `legal`, `generic`
- `classify_document_type(text, filename)` dans `app/services/classification/service.py` — classification par mots-clés
- Upload API : `POST /uploads?client_name=...` — stocke `client_name` dans `tags[0]`
- Sidebar : liste plate de documents avec filtre client par texte libre

### Ce qui manque

- Pas de champ `exercice` (année fiscale)
- Pas de champ `doc_category` dédié (bilan, liasse, relevé bancaire, contrat…)
- Pas de vue groupée Client > Exercice
- Pas d'auto-détection de l'exercice ni du client depuis le contenu du document

---

## 2. Modèle de données

### 2.1 Nouvelles colonnes sur `Document`

```python
# app/models/document.py — 3 nouvelles colonnes à ajouter

client_name: Mapped[str | None] = mapped_column(
    String(120), nullable=True, default=None, index=True,
)
# Exemples : "DUPONT CONSEIL SAS", "SCI MARTIN", "Jean Dupont"

exercice: Mapped[str | None] = mapped_column(
    String(9), nullable=True, default=None, index=True,
)
# Format : "2024", "2023", "2022" — année civile sur 4 chiffres
# Nullable : documents sans exercice détecté restent accessibles

doc_category: Mapped[str | None] = mapped_column(
    String(30), nullable=True, default=None, index=True,
)
# Valeurs : "bilan" | "liasse_fiscale" | "releve_bancaire" |
#           "grand_livre" | "contrat" | "facture" | "autre"
```

Index composite à ajouter dans `__table_args__` :
```python
Index("ix_documents_client_exercice", "uploaded_by_user_id", "client_name", "exercice"),
```

### 2.2 Migration Alembic

Fichier : `alembic/versions/XXXX_add_client_exercice_doc_category.py`

```python
def upgrade():
    op.add_column("documents", sa.Column("client_name", sa.String(120), nullable=True))
    op.add_column("documents", sa.Column("exercice", sa.String(9), nullable=True))
    op.add_column("documents", sa.Column("doc_category", sa.String(30), nullable=True))
    op.create_index("ix_documents_client_exercice",
                    "documents", ["uploaded_by_user_id", "client_name", "exercice"])
    # Migration des données existantes : tags[0] → client_name
    op.execute("""
        UPDATE documents
        SET client_name = tags[1]
        WHERE tags IS NOT NULL AND array_length(tags, 1) >= 1
          AND client_name IS NULL
    """)

def downgrade():
    op.drop_index("ix_documents_client_exercice")
    op.drop_column("documents", "doc_category")
    op.drop_column("documents", "exercice")
    op.drop_column("documents", "client_name")
```

---

## 3. Service d'auto-détection : `doc_metadata_service.py`

Nouveau fichier : `app/services/doc_metadata_service.py`

### 3.1 `extract_exercice(text: str) -> str | None`

Détecte l'année fiscale dans le texte extrait du document.

```python
import re

EXERCICE_PATTERNS = [
    r"exercice\s+(?:clos?\s+(?:le\s+)?\d{1,2}[/.-]\d{1,2}[/.-](\d{4}))",
    r"bilan\s+au\s+\d{1,2}\s+\w+\s+(\d{4})",
    r"au\s+31[/. ]12[/. ](\d{4})",
    r"p[eé]riode\s+du\s+\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\s+au\s+\d{1,2}[/.-]\d{1,2}[/.-](\d{4})",
    r"ann[eé]e\s+(?:fiscale\s+)?(\d{4})",
    r"exercice\s+(\d{4})",
    r"(\d{4})\s*[/-]\s*\d{4}",  # format 2023-2024
]

def extract_exercice(text: str) -> str | None:
    sample = text[:8000].lower()
    for pattern in EXERCICE_PATTERNS:
        m = re.search(pattern, sample)
        if m:
            year = int(m.group(1))
            if 2010 <= year <= 2030:
                return str(year)
    return None
```

### 3.2 `suggest_client(text: str, detections: list[dict]) -> str | None`

Retourne la première entité SOCIETE ou PERSONNE détectée comme nom de client probable.

```python
def suggest_client(text: str, detections: list[dict]) -> str | None:
    # Chercher d'abord les entités SOCIETE dans les premières détections
    for det in detections[:20]:
        etype = str(det.get("entity_type") or "").upper()
        val = str(det.get("value_excerpt") or "").strip()
        if etype in ("COMPANY", "SOCIETE", "ORGANISATION") and len(val) >= 3:
            return val[:80]
    # Fallback : première entité PERSONNE
    for det in detections[:20]:
        etype = str(det.get("entity_type") or "").upper()
        val = str(det.get("value_excerpt") or "").strip()
        if etype in ("PERSON", "PERSONNE", "PERSON_NAME") and len(val) >= 3:
            return val[:80]
    return None
```

### 3.3 `classify_doc_category(text: str, filename: str) -> str`

Remplace et enrichit `classify_document_type`. Retourne une catégorie métier précise.

```python
CATEGORY_RULES = [
    ("releve_bancaire", [
        "relevé de compte", "releve de compte", "solde", "iban",
        "débit", "crédit", "virement reçu", "prélèvement",
        "numéro de compte", "arrêté du compte",
    ]),
    ("liasse_fiscale", [
        "liasse fiscale", "2065", "2050", "2051", "2052", "2053",
        "2058", "formulaire cerfa", "résultat fiscal",
        "déficit reportable", "impôt sur les sociétés",
    ]),
    ("bilan", [
        "bilan", "actif", "passif", "capitaux propres",
        "immobilisations", "créances", "dettes fournisseurs",
        "résultat de l'exercice", "compte de résultat",
    ]),
    ("grand_livre", [
        "grand livre", "journal", "écriture comptable",
        "balance", "plan comptable", "pcg", "lettrage",
    ]),
    ("contrat", [
        "contrat", "convention", "avenant", "bail",
        "clause", "article", "signataires", "parties",
    ]),
    ("facture", [
        "facture", "invoice", "total ttc", "total ht",
        "tva", "avoir", "devis", "bon de commande",
    ]),
]

def classify_doc_category(text: str, filename: str = "") -> str:
    source = f"{filename}\n{text[:8000]}".lower()
    for category, hints in CATEGORY_RULES:
        score = sum(1 for h in hints if h in source)
        if score >= 2:
            return category
    # Single strong hint
    for category, hints in CATEGORY_RULES:
        if any(h in source for h in hints[:3]):
            return category
    return "autre"
```

### 3.4 `build_metadata_suggestions(text, filename, detections) -> dict`

Point d'entrée unique appelé après l'extraction du texte.

```python
def build_metadata_suggestions(
    text: str,
    filename: str,
    detections: list[dict],
) -> dict:
    return {
        "doc_category": classify_doc_category(text, filename),
        "exercice": extract_exercice(text),
        "client_suggestion": suggest_client(text, detections),
    }
```

---

## 4. Service de classification enrichi

Modifier `app/services/classification/service.py` :

- Remplacer `classify_document_type` par un appel à `classify_doc_category` de `doc_metadata_service`
- Mapper les catégories vers les anciennes valeurs pour la rétrocompatibilité :
  ```python
  CATEGORY_TO_DOC_TYPE = {
      "bilan": "accounting",
      "liasse_fiscale": "accounting",
      "grand_livre": "accounting",
      "facture": "invoice",
      "contrat": "legal",
      "releve_bancaire": "accounting",
      "autre": "generic",
  }
  ```

---

## 5. API — Modifications

### 5.1 Upload endpoint — `app/api/v1/uploads.py`

**Paramètres ajoutés** à `_upload_document_body` :
```python
exercice: str = "",          # ex: "2024", optionnel
doc_category: str = "",      # optionnel, auto-détecté si vide
```

**Changements dans `_upload_document_body`** :
1. Appeler `build_metadata_suggestions(text, filename, detections)` après extraction
2. Utiliser `client_name` fourni OU `client_suggestion` si vide
3. Utiliser `exercice` fourni OU `extract_exercice(text)` si vide
4. Utiliser `doc_category` fourni OU `classify_doc_category(text, filename)` si vide
5. Stocker ces 3 valeurs sur le document
6. Retourner `suggestions` dans la réponse

**Réponse enrichie** :
```json
{
  "document_id": "...",
  "status": "uploaded",
  "client_name": "DUPONT CONSEIL SAS",
  "exercice": "2024",
  "doc_category": "bilan",
  "suggestions": {
    "client_suggestion": "DUPONT CONSEIL SAS",
    "exercice_detected": "2024",
    "doc_category_detected": "bilan",
    "auto_filled": ["client_name", "exercice", "doc_category"]
  }
}
```

### 5.2 Nouveau endpoint dossiers — `app/api/v1/documents.py`

```
GET /api/v1/documents/dossiers
```

Retourne la structure groupée Client > Exercice avec statistiques.

**Réponse** :
```json
[
  {
    "client_name": "DUPONT CONSEIL SAS",
    "exercices": [
      {
        "exercice": "2024",
        "doc_count": 3,
        "ready_count": 2,
        "processing_count": 1,
        "doc_categories": ["bilan", "liasse_fiscale", "contrat"],
        "documents": [
          {
            "id": "...",
            "original_filename": "bilan_2024.pdf",
            "doc_category": "bilan",
            "status": "ready",
            "size_bytes": 483328,
            "created_at": "2026-04-25T17:18:18Z"
          }
        ]
      },
      {
        "exercice": "2023",
        "doc_count": 2,
        "ready_count": 2,
        "processing_count": 0,
        "doc_categories": ["bilan", "liasse_fiscale"],
        "documents": [...]
      }
    ],
    "total_docs": 5,
    "last_activity": "2026-04-25T17:18:18Z"
  }
]
```

**Filtre optionnel** : `?client_name=DUPONT` pour un seul client.

### 5.3 Endpoint PATCH document — métadonnées modifiables

```
PATCH /api/v1/documents/{id}/metadata
Body: { "client_name": "...", "exercice": "2024", "doc_category": "bilan" }
```

Permet à l'utilisateur de corriger les métadonnées auto-détectées.

### 5.4 Endpoint clients existants — conserver

```
GET /api/v1/documents/clients
```

Adapter pour retourner les `client_name` distincts (actuellement retourne `tags[0]`).

---

## 6. Schémas Pydantic — `app/schemas/document.py`

Ajouter dans `DocumentResponse` :
```python
client_name: str | None = Field(default=None)
exercice: str | None = Field(default=None)
doc_category: str | None = Field(default=None)
```

Nouveau schéma `DocumentMetadataPatch` :
```python
class DocumentMetadataPatch(BaseModel):
    client_name: str | None = Field(default=None, max_length=120)
    exercice: str | None = Field(default=None, pattern=r"^\d{4}$")
    doc_category: str | None = Field(default=None)
```

Nouveau schéma `DossierExercice` + `DossierClient` pour le endpoint `/dossiers`.

---

## 7. Frontend — `app/static/js/app.js`

### 7.1 Upload form : pré-remplissage auto

Après réception de la réponse d'upload (ou pendant, si détection rapide côté client) :

```javascript
function prefillUploadMetadata(suggestions) {
  const fields = {
    "upload-client-name": suggestions.client_suggestion,
    "upload-exercice":    suggestions.exercice_detected,
    "upload-doc-category": suggestions.doc_category_detected,
  };
  Object.entries(fields).forEach(([id, val]) => {
    const el = $(id);
    if (!el || !val) return;
    el.value = val;
    // Badge visuel "✨ Auto"
    const badge = el.parentElement.querySelector(".auto-badge");
    if (badge) badge.style.display = "";
  });
}
```

Nouveau formulaire HTML dans `index.html` (section upload) :
```html
<div class="upload-meta-row">
  <div class="upload-meta-field">
    <label>Client</label>
    <input id="upload-client-name" class="input-sm" placeholder="Nom du client" />
    <span class="auto-badge" style="display:none">✨ Auto</span>
  </div>
  <div class="upload-meta-field">
    <label>Exercice</label>
    <select id="upload-exercice" class="input-sm">
      <option value="">— Année —</option>
      <!-- 2020 → année courante, généré en JS -->
    </select>
    <span class="auto-badge" style="display:none">✨ Auto</span>
  </div>
  <div class="upload-meta-field">
    <label>Type de doc</label>
    <select id="upload-doc-category" class="input-sm">
      <option value="autre">Autre</option>
      <option value="bilan">Bilan comptable</option>
      <option value="liasse_fiscale">Liasse fiscale</option>
      <option value="releve_bancaire">Relevé bancaire</option>
      <option value="grand_livre">Grand livre</option>
      <option value="contrat">Contrat</option>
      <option value="facture">Facture</option>
    </select>
    <span class="auto-badge" style="display:none">✨ Auto</span>
  </div>
</div>
```

### 7.2 Sidebar : arbre Dossier

Remplacer la liste plate par un arbre Client > Exercice > Documents.

```javascript
async function loadDossierTree() {
  const data = await apiFetch("/documents/dossiers");
  renderDossierTree(data);
}

function renderDossierTree(dossiers) {
  const list = $("doc-list");
  list.innerHTML = dossiers.map(client => `
    <div class="dossier-client" data-client="${escapeHtml(client.client_name)}">
      <div class="dossier-client-header" onclick="toggleDossierClient(this)">
        <svg ...><!-- chevron --></svg>
        <span class="dossier-client-name">${escapeHtml(client.client_name)}</span>
        <span class="dossier-client-count">${client.total_docs}</span>
      </div>
      <div class="dossier-exercices">
        ${client.exercices.map(ex => renderExercice(client.client_name, ex)).join("")}
      </div>
    </div>
  `).join("");
}

function renderExercice(clientName, ex) {
  const allReady = ex.ready_count === ex.doc_count;
  return `
    <div class="dossier-exercice">
      <div class="dossier-exercice-header" onclick="toggleDossierExercice(this)">
        <svg ...><!-- chevron --></svg>
        <span class="dossier-exercice-year">${ex.exercice || "Sans exercice"}</span>
        <span class="dossier-status-dot ${allReady ? "green" : "orange"}"></span>
        <span class="dossier-count">${ex.ready_count}/${ex.doc_count}</span>
      </div>
      <div class="dossier-docs">
        ${ex.documents.map(doc => renderDossierDoc(doc)).join("")}
      </div>
    </div>
  `;
}
```

### 7.3 Page dédiée Dossier Client

Cliquer sur un nom de client dans la sidebar affiche la **vue dossier** dans la zone principale (remplace le document preview). La vue revient au document normal en cliquant "← Retour" ou en sélectionnant un document.

**Déclencheur :**
```javascript
function openDossierView(clientName) {
  // Cache la zone preview/analyse, affiche #dossier-view
  $("main-panel").style.display = "none";
  $("dossier-view").style.display = "";
  loadDossierClientPage(clientName);
}

async function loadDossierClientPage(clientName) {
  $("dossier-view").innerHTML = `<div class="dossier-loading">Chargement…</div>`;
  const data = await apiFetch(`/documents/dossiers?client_name=${encodeURIComponent(clientName)}`);
  const client = data[0];
  if (!client) { $("dossier-view").innerHTML = `<p>Aucun dossier trouvé.</p>`; return; }
  renderDossierClientPage(client);
}
```

**Structure HTML de la page dossier** (rendu en JS dans `#dossier-view`) :
```html
<!-- Généré dynamiquement dans la zone principale -->
<div id="dossier-view" style="display:none">
  <!-- En-tête client -->
  <div class="dossier-page-header">
    <button class="btn-ghost btn-sm" onclick="closeDossierView()">← Retour</button>
    <div class="dossier-page-title">
      <h2 id="dossier-page-client-name"></h2>
      <span class="dossier-page-stats"></span> <!-- "5 documents · 2 exercices" -->
    </div>
    <button class="btn btn-primary btn-sm" onclick="openUploadForClient()">
      + Ajouter un document
    </button>
  </div>

  <!-- Exercices en sections accordéon -->
  <div id="dossier-page-exercices" class="dossier-page-exercices"></div>
</div>
```

**Rendu d'un exercice (section dans la page) :**
```javascript
function renderDossierExerciceSection(ex) {
  const allReady = ex.ready_count === ex.doc_count;
  const statusLabel = allReady
    ? `<span class="badge badge-green">Complet</span>`
    : `<span class="badge badge-orange">${ex.ready_count}/${ex.doc_count} prêts</span>`;
  return `
    <div class="dossier-exercice-section">
      <div class="dossier-exercice-section-header">
        <h3>Exercice ${ex.exercice || "Sans exercice"}</h3>
        ${statusLabel}
        <span class="text-muted">${ex.doc_categories.join(" · ")}</span>
      </div>
      <table class="dossier-docs-table">
        <thead><tr>
          <th>Document</th><th>Type</th><th>Taille</th><th>Date</th><th>Statut</th><th></th>
        </tr></thead>
        <tbody>
          ${ex.documents.map(doc => `
            <tr class="dossier-doc-row" onclick="selectDoc('${doc.id}')">
              <td class="doc-name">${escapeHtml(doc.original_filename)}</td>
              <td><span class="badge badge-category">${escapeHtml(doc.doc_category || "—")}</span></td>
              <td class="text-muted">${formatFileSize(doc.size_bytes)}</td>
              <td class="text-muted">${formatDate(doc.created_at)}</td>
              <td>${renderStatusBadge(doc.status)}</td>
              <td>
                <button class="btn-ghost btn-xs" onclick="event.stopPropagation(); openEditMetadata('${doc.id}')">
                  ✏️
                </button>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}
```

**Fermeture :**
```javascript
function closeDossierView() {
  $("dossier-view").style.display = "none";
  $("main-panel").style.display = "";
}
```

**Pré-remplissage upload depuis la page dossier :**
```javascript
function openUploadForClient(clientName) {
  // Pré-remplit le champ client et ouvre la modale upload
  $("upload-client-name").value = clientName || currentDossierClient;
  openUploadModal();
}
```

### 7.4 CSS — nouvelles classes

Ajouter dans `style.css` :

```css
/* Dossier tree */
.dossier-client { border-bottom: 1px solid var(--border); }
.dossier-client-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; cursor: pointer;
  font-size: 12px; font-weight: 700;
  color: var(--text); letter-spacing: 0.3px;
  transition: background var(--t);
}
.dossier-client-header:hover { background: var(--bg-hover); }
.dossier-client-count {
  margin-left: auto;
  font-size: 10px; color: var(--text-muted);
  background: var(--border); border-radius: 999px;
  padding: 1px 6px;
}
.dossier-exercice-header {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 14px 7px 28px; cursor: pointer;
  font-size: 11px; color: var(--text-muted);
  transition: background var(--t);
}
.dossier-exercice-header:hover { background: var(--bg-hover); }
.dossier-exercice-year { font-weight: 600; color: var(--text); }
.dossier-status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  flex-shrink: 0;
}
.dossier-status-dot.green { background: var(--success); }
.dossier-status-dot.orange { background: var(--warning); }
.dossier-docs { padding-left: 12px; }

/* Dossier page (zone principale) */
.dossier-page-header {
  display: flex; align-items: center; gap: 12px;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border);
}
.dossier-page-title { flex: 1; }
.dossier-page-title h2 {
  margin: 0; font-size: 18px; font-weight: 700;
  color: var(--text);
}
.dossier-page-stats {
  font-size: 12px; color: var(--text-muted); margin-top: 2px;
}
.dossier-page-exercices { padding: 0 24px 32px; overflow-y: auto; }
.dossier-exercice-section {
  margin-top: 24px;
  border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden;
}
.dossier-exercice-section-header {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px;
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border);
}
.dossier-exercice-section-header h3 {
  margin: 0; font-size: 14px; font-weight: 700;
}
.dossier-docs-table {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.dossier-docs-table th {
  padding: 8px 12px; text-align: left;
  color: var(--text-muted); font-weight: 600;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px;
  border-bottom: 1px solid var(--border);
}
.dossier-doc-row {
  cursor: pointer;
  transition: background var(--t);
}
.dossier-doc-row:hover { background: var(--bg-hover); }
.dossier-doc-row td { padding: 10px 12px; border-bottom: 1px solid var(--border-subtle); }
.dossier-doc-row:last-child td { border-bottom: none; }
.badge-category {
  font-size: 10px; padding: 2px 7px;
  border-radius: 999px; background: var(--border);
  color: var(--text-muted); font-weight: 600;
  text-transform: uppercase;
}

/* Upload metadata row */
.upload-meta-row {
  display: grid;
  grid-template-columns: 1fr 90px 1fr;
  gap: 10px;
  margin-top: 12px;
}
.upload-meta-field { position: relative; }
.upload-meta-field label {
  display: block;
  font-size: 11px; font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 4px;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.auto-badge {
  position: absolute; right: 8px; top: 2px;
  font-size: 10px; color: var(--accent);
  pointer-events: none;
}
```

---

## 8. Fichiers à créer ou modifier

| Fichier | Action | Description |
|---|---|---|
| `app/models/document.py` | Modifier | Ajouter `client_name`, `exercice`, `doc_category`, index |
| `alembic/versions/XXXX_add_client_exercice_doc_category.py` | Créer | Migration + backfill |
| `app/services/doc_metadata_service.py` | Créer | `extract_exercice`, `suggest_client`, `classify_doc_category`, `build_metadata_suggestions` |
| `app/services/classification/service.py` | Modifier | Déléguer à `classify_doc_category`, garder rétrocompat |
| `app/schemas/document.py` | Modifier | Ajouter champs, schémas `DocumentMetadataPatch`, `DossierClient` |
| `app/api/v1/uploads.py` | Modifier | Accepter `exercice`, `doc_category`, appeler auto-détection, retourner suggestions |
| `app/api/v1/documents.py` | Modifier | Ajouter `GET /dossiers`, `PATCH /{id}/metadata`, adapter `/clients` |
| `app/templates/index.html` | Modifier | Formulaire upload avec 3 champs méta + badges Auto ; bloc `#dossier-view` dans zone principale |
| `app/static/js/app.js` | Modifier | `loadDossierTree`, `renderDossierTree`, `openDossierView`, `loadDossierClientPage`, `renderDossierExerciceSection`, `closeDossierView`, `prefillUploadMetadata`, toggle accordéon |
| `app/static/css/style.css` | Modifier | Classes `.dossier-*`, `.upload-meta-row`, `.auto-badge` |

---

## 9. Tests

### Tests unitaires

```python
# tests/unit/test_doc_metadata_service.py

def test_extract_exercice_from_bilan():
    text = "Bilan au 31 décembre 2024"
    assert extract_exercice(text) == "2024"

def test_extract_exercice_clos():
    text = "Exercice clos le 31/12/2023"
    assert extract_exercice(text) == "2023"

def test_extract_exercice_not_found():
    text = "Document sans date"
    assert extract_exercice(text) is None

def test_classify_doc_category_bilan():
    text = "bilan actif passif capitaux propres immobilisations"
    assert classify_doc_category(text, "bilan.pdf") == "bilan"

def test_classify_doc_category_releve():
    text = "relevé de compte IBAN solde débit crédit virement reçu"
    assert classify_doc_category(text, "releve.pdf") == "releve_bancaire"

def test_classify_doc_category_liasse():
    text = "liasse fiscale 2058 résultat fiscal impôt sur les sociétés"
    assert classify_doc_category(text, "liasse.pdf") == "liasse_fiscale"

def test_suggest_client_from_detections():
    detections = [
        {"entity_type": "SOCIETE", "value_excerpt": "DUPONT CONSEIL SAS"}
    ]
    assert suggest_client("", detections) == "DUPONT CONSEIL SAS"
```

### Tests API

```python
# tests/api/test_dossiers.py

async def test_get_dossiers_grouped(auth_client, seed_documents):
    resp = await auth_client.get("/api/v1/documents/dossiers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    assert "client_name" in data[0]
    assert "exercices" in data[0]
    assert "exercice" in data[0]["exercices"][0]
    assert "documents" in data[0]["exercices"][0]

async def test_patch_document_metadata(auth_client, seed_document):
    doc_id = seed_document["id"]
    resp = await auth_client.patch(
        f"/api/v1/documents/{doc_id}/metadata",
        json={"client_name": "NOUVEAU CLIENT", "exercice": "2024"}
    )
    assert resp.status_code == 200
    assert resp.json()["client_name"] == "NOUVEAU CLIENT"
```

---

## 10. Rétrocompatibilité

- Le champ `tags` reste sur le modèle — pas de suppression. Backward compat totale.
- `classify_document_type` reste exporté depuis `classification/service.py` — il délègue simplement à `classify_doc_category` avec mapping.
- Les documents existants sans `client_name` restent accessibles. La migration Alembic les backfille depuis `tags[0]`.
- Le filtre `?client_name=` sur `/documents` continue à fonctionner (adapter la query pour lire `client_name` plutôt que `tags[0]`).

---

## 11. Ce qui est hors scope (cette version)

- Modèle `Dossier` dédié en base (table séparée) — trop tôt, on groupe par `client_name + exercice` dynamiquement
- Mode multi-docs IA (chat croisé plusieurs documents) — spec séparée
- Relevé bancaire avec détection IBAN spécialisée — spec séparée
- Gestion des exercices décalés (ex: 01/07/2023 - 30/06/2024) — v2
- Partage de dossier entre utilisateurs — hors scope
