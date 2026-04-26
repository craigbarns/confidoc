# Dossier Client — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter la structure Dossier Client à ConfiDoc : 3 nouveaux champs sur Document (client_name, exercice, doc_category), auto-détection à l'upload, sidebar en arbre, et page dédiée par client dans la zone principale.

**Architecture:** Migration Alembic pour les nouvelles colonnes + backfill depuis tags[0]. Nouveau service `doc_metadata_service.py` pour la détection automatique. Nouveau sous-module `_doc_dossier.py` (GET /dossiers, PATCH /{id}/metadata) inclus dans le router documents existant. Frontend : toggle sidebar tree + panel-dossier dans main-content.

**Tech Stack:** FastAPI, SQLAlchemy async (mapped_column), Alembic (raw SQL), Pydantic v2, PostgreSQL, vanilla JS

---

## File Map

| Fichier | Action | Contenu |
|---|---|---|
| `alembic/versions/e4f5a6b7c8d9_add_client_exercice_doc_category.py` | Créer | Migration : 3 colonnes + index + backfill tags[0] |
| `app/models/document.py` | Modifier | 3 nouveaux `mapped_column` + entrée index composite |
| `app/services/doc_metadata_service.py` | Créer | `extract_exercice`, `suggest_client`, `classify_doc_category`, `build_metadata_suggestions` |
| `app/services/classification/service.py` | Modifier | Déléguer à `classify_doc_category`, garder `classify_document_type` exporté |
| `app/schemas/document.py` | Modifier | Champs sur `DocumentResponse` + `DocumentMetadataPatch` + `DossierDoc` + `DossierExercice` + `DossierClient` |
| `app/api/v1/uploads.py` | Modifier | Paramètres `exercice`/`doc_category`, appel auto-detect, persistance sur document, `suggestions` dans réponse |
| `app/api/v1/_doc_dossier.py` | Créer | `GET /dossiers`, `PATCH /{document_id}/metadata` |
| `app/api/v1/_doc_crud.py` | Modifier | `GET /clients` : lire `client_name` colonne au lieu de `tags[0]` |
| `app/api/v1/documents.py` | Modifier | Inclure `_doc_dossier` router |
| `tests/unit/test_doc_metadata_service.py` | Créer | Tests unitaires pure-Python |
| `tests/api/test_dossiers_api.py` | Créer | Tests routes existence + auth |
| `app/static/css/style.css` | Modifier | Classes `.dossier-*`, `.upload-meta-row`, `.auto-badge`, `.badge-category` |
| `app/templates/index.html` | Modifier | Upload meta row (exercice + doc_category) + `#panel-dossier` |
| `app/static/js/app.js` | Modifier | Tree sidebar, page dédiée, prefill upload, toggle mode |

---

### Task 1: Alembic migration — 3 colonnes + index + backfill

**Files:**
- Create: `alembic/versions/e4f5a6b7c8d9_add_client_exercice_doc_category.py`

- [ ] **Step 1: Écrire le fichier de migration**

```python
"""Add client_name, exercice, doc_category to documents

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-26 00:00:00.000000

"""

from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS client_name varchar(120),
            ADD COLUMN IF NOT EXISTS exercice varchar(9),
            ADD COLUMN IF NOT EXISTS doc_category varchar(30)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_client_exercice
            ON documents (uploaded_by_user_id, client_name, exercice)
        """
    )
    # Backfill client_name from tags[0] where client_name is NULL
    op.execute(
        """
        UPDATE documents
        SET client_name = tags[1]
        WHERE tags IS NOT NULL
          AND array_length(tags, 1) >= 1
          AND client_name IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_client_exercice")
    op.execute(
        """
        ALTER TABLE documents
            DROP COLUMN IF EXISTS doc_category,
            DROP COLUMN IF EXISTS exercice,
            DROP COLUMN IF EXISTS client_name
        """
    )
```

- [ ] **Step 2: Vérifier que la migration est détectée**

Run: `cd /Users/gregorybaranes/Desktop/QWEN/confidoc && python -m alembic history | head -5`
Expected: la ligne `e4f5a6b7c8d9 -> ...` apparaît

- [ ] **Step 3: Valider la syntaxe Python**

Run: `python -c "import alembic.versions.e4f5a6b7c8d9_add_client_exercice_doc_category"`
Expected: no output (no syntax errors)

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/e4f5a6b7c8d9_add_client_exercice_doc_category.py
git commit -m "feat: migration add client_name, exercice, doc_category to documents"
```

---

### Task 2: Document model — 3 nouveaux champs + index composite

**Files:**
- Modify: `app/models/document.py:27-36` (table_args) et `62-73` (champs)

- [ ] **Step 1: Ajouter l'import String si nécessaire** — il est déjà importé ligne 7.

- [ ] **Step 2: Ajouter les 3 colonnes dans la classe `Document`**

Après la ligne `doc_type: Mapped[str | None] = mapped_column(...)` (actuellement ligne 67), ajouter :

```python
    # Dossier metadata (auto-detected or user-provided)
    client_name: Mapped[str | None] = mapped_column(
        String(120), nullable=True, default=None,
    )
    exercice: Mapped[str | None] = mapped_column(
        String(9), nullable=True, default=None,
    )
    doc_category: Mapped[str | None] = mapped_column(
        String(30), nullable=True, default=None,
    )
```

- [ ] **Step 3: Ajouter l'index composite dans `__table_args__`**

Ajouter en dernière entrée du tuple (avant le `)` fermant) :

```python
        Index("ix_documents_client_exercice", "uploaded_by_user_id", "client_name", "exercice"),
```

- [ ] **Step 4: Vérifier que le modèle s'importe sans erreur**

Run: `python -c "from app.models.document import Document; print('ok')"` depuis le répertoire du projet
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add app/models/document.py
git commit -m "feat: add client_name, exercice, doc_category to Document model"
```

---

### Task 3: Service doc_metadata_service — détection automatique

**Files:**
- Create: `app/services/doc_metadata_service.py`

- [ ] **Step 1: Écrire les tests d'abord**

Créer `tests/unit/test_doc_metadata_service.py` avec :

```python
"""Tests unitaires pour doc_metadata_service."""

import pytest
from app.services.doc_metadata_service import (
    extract_exercice,
    suggest_client,
    classify_doc_category,
    build_metadata_suggestions,
)


class TestExtractExercice:
    def test_bilan_au_31_decembre(self):
        assert extract_exercice("Bilan au 31 décembre 2024") == "2024"

    def test_exercice_clos(self):
        assert extract_exercice("Exercice clos le 31/12/2023") == "2023"

    def test_exercice_bare(self):
        assert extract_exercice("Exercice 2022") == "2022"

    def test_annee_fiscale(self):
        assert extract_exercice("Année fiscale 2021") == "2021"

    def test_au_31_12(self):
        assert extract_exercice("au 31/12/2020") == "2020"

    def test_not_found(self):
        assert extract_exercice("Document sans date") is None

    def test_year_out_of_range(self):
        assert extract_exercice("exercice 1999") is None

    def test_year_future_out_of_range(self):
        assert extract_exercice("exercice 2035") is None


class TestClassifyDocCategory:
    def test_bilan(self):
        result = classify_doc_category(
            "bilan actif passif capitaux propres immobilisations résultat", "bilan.pdf"
        )
        assert result == "bilan"

    def test_releve_bancaire(self):
        result = classify_doc_category(
            "relevé de compte IBAN solde débit crédit virement reçu", "releve.pdf"
        )
        assert result == "releve_bancaire"

    def test_liasse_fiscale(self):
        result = classify_doc_category(
            "liasse fiscale 2058 résultat fiscal impôt sur les sociétés", "liasse.pdf"
        )
        assert result == "liasse_fiscale"

    def test_grand_livre(self):
        result = classify_doc_category(
            "grand livre écriture comptable balance lettrage", "gl.pdf"
        )
        assert result == "grand_livre"

    def test_contrat(self):
        result = classify_doc_category(
            "contrat de bail clause article signataires les parties", "contrat.pdf"
        )
        assert result == "contrat"

    def test_facture(self):
        result = classify_doc_category(
            "facture total ttc tva règlement bon de commande", "facture.pdf"
        )
        assert result == "facture"

    def test_default_autre(self):
        result = classify_doc_category("document quelconque", "doc.pdf")
        assert result == "autre"


class TestSuggestClient:
    def test_societe(self):
        dets = [{"entity_type": "SOCIETE", "value_excerpt": "DUPONT CONSEIL SAS"}]
        assert suggest_client("", dets) == "DUPONT CONSEIL SAS"

    def test_company(self):
        dets = [{"entity_type": "COMPANY", "value_excerpt": "MARTIN SA"}]
        assert suggest_client("", dets) == "MARTIN SA"

    def test_person_fallback(self):
        dets = [{"entity_type": "PERSON", "value_excerpt": "Jean Dupont"}]
        assert suggest_client("", dets) == "Jean Dupont"

    def test_none_when_empty(self):
        assert suggest_client("", []) is None

    def test_short_value_ignored(self):
        dets = [{"entity_type": "SOCIETE", "value_excerpt": "AB"}]
        assert suggest_client("", dets) is None


class TestBuildMetadataSuggestions:
    def test_returns_all_keys(self):
        result = build_metadata_suggestions(
            text="bilan actif passif capitaux propres exercice 2024",
            filename="bilan_2024.pdf",
            detections=[{"entity_type": "SOCIETE", "value_excerpt": "DUPONT SAS"}],
        )
        assert "doc_category" in result
        assert "exercice" in result
        assert "client_suggestion" in result
        assert result["exercice"] == "2024"
        assert result["doc_category"] == "bilan"
        assert result["client_suggestion"] == "DUPONT SAS"
```

- [ ] **Step 2: Vérifier que les tests échouent (service non encore créé)**

Run: `pytest tests/unit/test_doc_metadata_service.py -v 2>&1 | head -20`
Expected: `ModuleNotFoundError` ou `ImportError` (le fichier n'existe pas encore)

- [ ] **Step 3: Créer `app/services/doc_metadata_service.py`**

```python
"""ConfiDoc — Détection automatique des métadonnées de documents."""

from __future__ import annotations

import re

EXERCICE_PATTERNS = [
    r"exercice\s+clos?\s+le\s+\d{1,2}[/.-]\d{1,2}[/.-](\d{4})",
    r"bilan\s+au\s+\d{1,2}\s+\w+\s+(\d{4})",
    r"au\s+31[/. ]12[/. ](\d{4})",
    r"p[eé]riode\s+du\s+\d{1,2}[/.-]\d{1,2}[/.-]\d{4}\s+au\s+\d{1,2}[/.-]\d{1,2}[/.-](\d{4})",
    r"ann[eé]e\s+fiscale\s+(\d{4})",
    r"exercice\s+(\d{4})",
]

CATEGORY_RULES = [
    ("releve_bancaire", [
        "relevé de compte", "releve de compte", "solde", "iban",
        "débit", "crédit", "virement reçu", "prélèvement",
        "numéro de compte", "arrêté du compte",
    ]),
    ("liasse_fiscale", [
        "liasse fiscale", "2065", "2050", "2051", "2052", "2053",
        "2058", "résultat fiscal",
        "impôt sur les sociétés",
    ]),
    ("bilan", [
        "bilan", "actif", "passif", "capitaux propres",
        "immobilisations", "résultat de l'exercice",
        "compte de résultat",
    ]),
    ("grand_livre", [
        "grand livre", "écriture comptable",
        "balance", "lettrage",
    ]),
    ("contrat", [
        "contrat", "convention", "avenant", "bail",
        "clause", "article", "signataires",
    ]),
    ("facture", [
        "facture", "invoice", "total ttc", "total ht",
        "tva", "avoir", "bon de commande",
    ]),
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


def suggest_client(text: str, detections: list[dict]) -> str | None:
    for det in detections[:20]:
        etype = str(det.get("entity_type") or "").upper()
        val = str(det.get("value_excerpt") or "").strip()
        if etype in ("COMPANY", "SOCIETE", "ORGANISATION") and len(val) >= 3:
            return val[:80]
    for det in detections[:20]:
        etype = str(det.get("entity_type") or "").upper()
        val = str(det.get("value_excerpt") or "").strip()
        if etype in ("PERSON", "PERSONNE", "PERSON_NAME") and len(val) >= 3:
            return val[:80]
    return None


def classify_doc_category(text: str, filename: str = "") -> str:
    source = f"{filename}\n{text[:8000]}".lower()
    best: str | None = None
    best_score = 0
    for category, hints in CATEGORY_RULES:
        score = sum(1 for h in hints if h in source)
        if score > best_score:
            best_score = score
            best = category
    if best_score >= 2:
        return best  # type: ignore[return-value]
    # Single strong hint (first 3 hints per category)
    for category, hints in CATEGORY_RULES:
        if any(h in source for h in hints[:3]):
            return category
    return "autre"


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

- [ ] **Step 4: Lancer les tests**

Run: `pytest tests/unit/test_doc_metadata_service.py -v`
Expected: tous les tests PASS (aucun FAIL)

- [ ] **Step 5: Commit**

```bash
git add app/services/doc_metadata_service.py tests/unit/test_doc_metadata_service.py
git commit -m "feat: add doc_metadata_service (exercice detection, category classifier, client suggestion)"
```

---

### Task 4: Classification service — déléguer à doc_metadata_service

**Files:**
- Modify: `app/services/classification/service.py`

- [ ] **Step 1: Remplacer le corps de `classify_document_type` par une délégation**

```python
"""ConfiDoc Backend — Document Classification Service."""

from app.core.logging import get_logger
from app.services.doc_metadata_service import classify_doc_category

logger = get_logger(__name__)

_CATEGORY_TO_DOC_TYPE: dict[str, str] = {
    "bilan": "accounting",
    "liasse_fiscale": "accounting",
    "grand_livre": "accounting",
    "releve_bancaire": "accounting",
    "facture": "invoice",
    "contrat": "legal",
    "autre": "generic",
}


def classify_document_type(text: str, filename: str = "") -> str:
    """Classify document to legacy 4-value type (invoice/accounting/legal/generic)."""
    category = classify_doc_category(text, filename)
    return _CATEGORY_TO_DOC_TYPE.get(category, "generic")
```

- [ ] **Step 2: Vérifier que l'import fonctionne**

Run: `python -c "from app.services.classification.service import classify_document_type; print(classify_document_type('facture total ttc', 'f.pdf'))"`
Expected: `invoice`

- [ ] **Step 3: Vérifier que les tests existants passent toujours**

Run: `pytest tests/ -k "classif" -v 2>&1 | tail -20`
Expected: no FAIL (si aucun test de classification n'existe, output vide est ok)

- [ ] **Step 4: Commit**

```bash
git add app/services/classification/service.py
git commit -m "refactor: classification service delegates to doc_metadata_service"
```

---

### Task 5: Schémas Pydantic — nouveaux champs et schémas dossier

**Files:**
- Modify: `app/schemas/document.py`

- [ ] **Step 1: Ajouter 3 champs à `DocumentResponse`**

Après `doc_type: str | None = None` (ligne 21), ajouter :

```python
    client_name: str | None = None
    exercice: str | None = None
    doc_category: str | None = None
```

- [ ] **Step 2: Ajouter les nouveaux schémas à la fin du fichier**

```python
class DocumentMetadataPatch(BaseModel):
    client_name: str | None = Field(default=None, max_length=120)
    exercice: str | None = Field(default=None, pattern=r"^\d{4}$")
    doc_category: str | None = Field(default=None, max_length=30)


class DossierDoc(BaseModel):
    id: uuid.UUID
    original_filename: str
    doc_category: str | None = None
    status: str
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        return str(v)


class DossierExercice(BaseModel):
    exercice: str | None
    doc_count: int
    ready_count: int
    processing_count: int
    doc_categories: list[str]
    documents: list[DossierDoc]


class DossierClient(BaseModel):
    client_name: str
    exercices: list[DossierExercice]
    total_docs: int
    last_activity: datetime | None
```

- [ ] **Step 3: Vérifier l'import**

Run: `python -c "from app.schemas.document import DocumentMetadataPatch, DossierClient, DossierExercice; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/schemas/document.py
git commit -m "feat: add client_name/exercice/doc_category to DocumentResponse + dossier schemas"
```

---

### Task 6: Upload endpoint — auto-détection + réponse enrichie

**Files:**
- Modify: `app/api/v1/uploads.py`

- [ ] **Step 1: Ajouter les imports en haut du fichier**

Après `from app.services.storage_service import store_file`, ajouter :

```python
from app.services.doc_metadata_service import build_metadata_suggestions
```

- [ ] **Step 2: Ajouter les paramètres `exercice` et `doc_category` à `upload_document`**

Dans `upload_document` (après `client_name: str = Query(default="")`), ajouter :

```python
    exercice: str = Query(default=""),
    doc_category: str = Query(default=""),
```

Passer ces valeurs à `_upload_document_body` :

```python
        return await _upload_document_body(
            ...
            client_name=client_name,
            exercice=exercice,
            doc_category=doc_category,
            background_tasks=background_tasks,
        )
```

Faire la même chose pour `upload_batch` (mêmes 2 paramètres + passage dans le call à `_upload_document_body`).

- [ ] **Step 3: Mettre à jour la signature de `_upload_document_body`**

Ajouter après `client_name: str = "",` :

```python
    exercice: str = "",
    doc_category: str = "",
```

- [ ] **Step 4: Remplacer le bloc création de `Document` dans `_upload_document_body`**

Remplacer la création du `Document` et le bloc `logger.info` qui suit par :

```python
    # Auto-detect metadata from raw file bytes if not provided
    # (runs before storing to external backend — we already have the file in temp_path)
    raw_text = ""
    detections_for_suggest: list[dict] = []
    try:
        from app.services.anonymization_service import extract_text_from_file
        raw_bytes = file_path.read_bytes()
        raw_text = await extract_text_from_file(raw_bytes, extension) or ""
    except Exception:
        pass  # auto-detect is best-effort; silently skip on extraction failure

    suggestions = build_metadata_suggestions(raw_text, filename, detections_for_suggest)

    resolved_client_name = normalized_client_name
    resolved_exercice = exercice.strip() or suggestions["exercice"] or None
    resolved_doc_category = doc_category.strip() or suggestions["doc_category"] or None

    document = Document(
        org_id=org_id,
        uploaded_by_user_id=current_user.id,
        original_filename=filename,
        content_type=file.content_type or "application/octet-stream",
        extension=extension,
        size_bytes=size,
        sha256=sha256,
        storage_backend=storage_backend,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED,
        raw_content=file_path.read_bytes() if storage_backend == "database" else None,
        tags=[normalized_client_name],
        client_name=resolved_client_name,
        exercice=resolved_exercice,
        doc_category=resolved_doc_category,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info(
        "document_uploaded",
        doc_id=str(document.id),
        filename=filename,
        size=size,
        backend=storage_backend,
        client_name=resolved_client_name,
        exercice=resolved_exercice,
        doc_category=resolved_doc_category,
    )
```

- [ ] **Step 5: Enrichir le `return` de `_upload_document_body`**

Ajouter `"suggestions"` dans le dict retourné :

```python
    return {
        "status": document.status.value,
        "document_id": str(document.id),
        "storage_backend": document.storage_backend,
        "sha256": document.sha256,
        "original_filename": filename,
        "content_type": file.content_type,
        "size_bytes": size,
        "uploaded_by": uploaded_by_snapshot,
        "client_name": resolved_client_name,
        "exercice": resolved_exercice,
        "doc_category": resolved_doc_category,
        "processing": processing,
        "suggestions": {
            "client_suggestion": suggestions["client_suggestion"],
            "exercice_detected": suggestions["exercice"],
            "doc_category_detected": suggestions["doc_category"],
            "auto_filled": [
                k for k, v in [
                    ("exercice", not exercice.strip() and suggestions["exercice"]),
                    ("doc_category", not doc_category.strip() and suggestions["doc_category"]),
                ]
                if v
            ],
        },
    }
```

- [ ] **Step 6: Vérifier la syntaxe**

Run: `python -c "from app.api.v1.uploads import upload_document; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/uploads.py
git commit -m "feat: upload auto-detects exercice/doc_category, returns suggestions"
```

---

### Task 7: _doc_dossier.py — GET /dossiers + PATCH /{id}/metadata

**Files:**
- Create: `app/api/v1/_doc_dossier.py`
- Modify: `app/api/v1/documents.py`

- [ ] **Step 1: Créer `app/api/v1/_doc_dossier.py`**

```python
"""ConfiDoc — Dossier endpoints: GET /dossiers, PATCH /{id}/metadata."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import desc, select

from app.api.deps import CurrentUser, DbSession
from app.api.v1._doc_shared import _get_user_document_or_404
from app.models.document import Document, DocumentStatus
from app.schemas.document import (
    DocumentMetadataPatch,
    DocumentResponse,
    DossierClient,
    DossierDoc,
    DossierExercice,
)

router = APIRouter()

_READY_STATUSES = {DocumentStatus.READY, DocumentStatus.ANONYMIZED}
_PROCESSING_STATUSES = {
    DocumentStatus.PROCESSING,
    DocumentStatus.EXTRACTING,
    DocumentStatus.EXTRACTED,
    DocumentStatus.ANONYMIZING,
}


@router.get(
    "/dossiers",
    response_model=list[DossierClient],
    status_code=status.HTTP_200_OK,
    summary="Structure Dossier groupée Client > Exercice",
)
async def get_dossiers(
    current_user: CurrentUser,
    db: DbSession,
    client_name: str = Query(default="", description="Filtrer par client (sous-chaîne, insensible à la casse)"),
) -> list[DossierClient]:
    query = (
        select(Document)
        .where(
            Document.uploaded_by_user_id == current_user.id,
            Document.is_deleted.is_(False),
            Document.client_name.isnot(None),
        )
        .order_by(Document.client_name, desc(Document.exercice), desc(Document.created_at))
    )
    if client_name.strip():
        query = query.where(Document.client_name.ilike(f"%{client_name.strip()}%"))

    result = await db.execute(query)
    docs = list(result.scalars().all())

    # Group in Python: client_name → exercice → list[doc]
    clients: dict[str, dict[str | None, list[Document]]] = {}
    for doc in docs:
        cname = doc.client_name or ""
        if cname not in clients:
            clients[cname] = {}
        ex = doc.exercice  # may be None
        if ex not in clients[cname]:
            clients[cname][ex] = []
        clients[cname][ex].append(doc)

    out: list[DossierClient] = []
    for cname, exercice_map in clients.items():
        exercices: list[DossierExercice] = []
        all_dates: list[datetime] = []
        total = 0
        for ex, ex_docs in exercice_map.items():
            ready = sum(1 for d in ex_docs if d.status in _READY_STATUSES)
            processing = sum(1 for d in ex_docs if d.status in _PROCESSING_STATUSES)
            cats = sorted({d.doc_category for d in ex_docs if d.doc_category})
            dossier_docs = [
                DossierDoc(
                    id=d.id,
                    original_filename=d.original_filename,
                    doc_category=d.doc_category,
                    status=d.status.value if hasattr(d.status, "value") else str(d.status),
                    size_bytes=d.size_bytes,
                    created_at=d.created_at,
                )
                for d in ex_docs
            ]
            exercices.append(DossierExercice(
                exercice=ex,
                doc_count=len(ex_docs),
                ready_count=ready,
                processing_count=processing,
                doc_categories=cats,
                documents=dossier_docs,
            ))
            total += len(ex_docs)
            all_dates.extend(d.created_at for d in ex_docs if d.created_at)

        out.append(DossierClient(
            client_name=cname,
            exercices=exercices,
            total_docs=total,
            last_activity=max(all_dates) if all_dates else None,
        ))

    return sorted(out, key=lambda c: c.client_name.lower())


@router.patch(
    "/{document_id}/metadata",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Modifier les métadonnées dossier d'un document",
)
async def patch_document_metadata(
    document_id: str,
    patch: DocumentMetadataPatch,
    current_user: CurrentUser,
    db: DbSession,
) -> Document:
    doc = await _get_user_document_or_404(db, document_id, current_user.id)
    if patch.client_name is not None:
        doc.client_name = patch.client_name
        doc.tags = [patch.client_name]  # keep tags in sync for backward compat
    if patch.exercice is not None:
        doc.exercice = patch.exercice
    if patch.doc_category is not None:
        doc.doc_category = patch.doc_category
    await db.commit()
    await db.refresh(doc)
    return doc
```

- [ ] **Step 2: Inclure le router dans `documents.py`**

Dans `app/api/v1/documents.py`, ajouter l'import et l'inclusion :

```python
from app.api.v1._doc_dossier import router as dossier_router
```

Puis dans le corps du fichier, avant `router.include_router(crud_router)` :

```python
router.include_router(dossier_router)   # /dossiers, /{id}/metadata
```

L'ordre final doit être :
```python
router.include_router(stats_router)     # /stats/dashboard, /status-summary
router.include_router(dossier_router)   # /dossiers, /{id}/metadata (avant /{id})
router.include_router(crud_router)      # /, /clients, /trash/list, /all, /{id}
router.include_router(processing_router)
router.include_router(export_router)
```

- [ ] **Step 3: Vérifier l'import**

Run: `python -c "from app.api.v1.documents import router; paths = [r.path for r in router.routes]; print([p for p in paths if 'dossier' in p or 'metadata' in p])"`
Expected: `['/dossiers', '/{document_id}/metadata']` (ou similaire)

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/_doc_dossier.py app/api/v1/documents.py
git commit -m "feat: add GET /dossiers and PATCH /{id}/metadata endpoints"
```

---

### Task 8: Update /clients endpoint — utiliser la colonne client_name

**Files:**
- Modify: `app/api/v1/_doc_crud.py:119-150`

- [ ] **Step 1: Remplacer `list_clients` pour lire `client_name` colonne**

```python
@router.get(
    "/clients",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
    summary="Lister les clients connus",
)
async def list_clients(
    current_user: CurrentUser,
    db: DbSession,
    include_deleted: bool = Query(default=False),
) -> list[str]:
    query = (
        select(Document.client_name)
        .where(
            Document.uploaded_by_user_id == current_user.id,
            Document.client_name.isnot(None),
        )
        .distinct()
    )
    if not include_deleted:
        query = query.where(Document.is_deleted.is_(False))

    result = await db.execute(query)
    names = [row[0] for row in result.all() if row[0]]

    # Fallback: also collect from tags[0] for docs without client_name
    fallback_q = (
        select(Document)
        .where(
            Document.uploaded_by_user_id == current_user.id,
            Document.client_name.is_(None),
            Document.tags.isnot(None),
        )
    )
    if not include_deleted:
        fallback_q = fallback_q.where(Document.is_deleted.is_(False))
    fb_result = await db.execute(fallback_q)
    for doc in fb_result.scalars().all():
        tags = list(getattr(doc, "tags", []) or [])
        if tags and tags[0]:
            names.append(tags[0])

    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(name.strip())
    return sorted(out, key=lambda x: x.lower())
```

- [ ] **Step 2: Vérifier la syntaxe**

Run: `python -c "from app.api.v1._doc_crud import list_clients; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/_doc_crud.py
git commit -m "feat: /clients uses client_name column with fallback to tags[0]"
```

---

### Task 9: Tests API — routes dossier + auth

**Files:**
- Create: `tests/api/test_dossiers_api.py`

- [ ] **Step 1: Créer `tests/api/test_dossiers_api.py`**

```python
"""Tests API routes /documents/dossiers et /{id}/metadata."""

import pytest


class TestDossiersRoutes:
    """Vérifie que les nouvelles routes sont bien enregistrées."""

    def _get_paths(self):
        from app.api.v1.documents import router
        return [r.path for r in router.routes]

    def test_dossiers_route_exists(self):
        assert "/dossiers" in self._get_paths()

    def test_metadata_patch_route_exists(self):
        assert "/{document_id}/metadata" in self._get_paths()

    def test_dossiers_route_before_document_id(self):
        paths = self._get_paths()
        dossiers_idx = next(i for i, p in enumerate(paths) if p == "/dossiers")
        doc_id_idx = next(i for i, p in enumerate(paths) if p == "/{document_id}")
        assert dossiers_idx < doc_id_idx, "/dossiers doit être avant /{document_id}"


class TestDossiersAuth:
    """Vérifie que les nouvelles routes exigent une authentification."""

    @pytest.mark.asyncio
    async def test_get_dossiers_requires_auth(self, client):
        resp = await client.get("/api/v1/documents/dossiers")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_patch_metadata_requires_auth(self, client):
        resp = await client.patch(
            "/api/v1/documents/00000000-0000-0000-0000-000000000001/metadata",
            json={"exercice": "2024"},
        )
        assert resp.status_code == 401


class TestDocumentResponseSchema:
    """Vérifie que DocumentResponse inclut les nouveaux champs."""

    def test_client_name_field_exists(self):
        from app.schemas.document import DocumentResponse
        fields = DocumentResponse.model_fields
        assert "client_name" in fields

    def test_exercice_field_exists(self):
        from app.schemas.document import DocumentResponse
        fields = DocumentResponse.model_fields
        assert "exercice" in fields

    def test_doc_category_field_exists(self):
        from app.schemas.document import DocumentResponse
        fields = DocumentResponse.model_fields
        assert "doc_category" in fields


class TestDocumentMetadataPatchSchema:
    """Vérifie la validation du schéma DocumentMetadataPatch."""

    def test_valid_exercice(self):
        from app.schemas.document import DocumentMetadataPatch
        p = DocumentMetadataPatch(exercice="2024")
        assert p.exercice == "2024"

    def test_invalid_exercice_format(self):
        from pydantic import ValidationError
        from app.schemas.document import DocumentMetadataPatch
        with pytest.raises(ValidationError):
            DocumentMetadataPatch(exercice="24")

    def test_all_none_is_valid(self):
        from app.schemas.document import DocumentMetadataPatch
        p = DocumentMetadataPatch()
        assert p.client_name is None
        assert p.exercice is None
        assert p.doc_category is None
```

- [ ] **Step 2: Lancer les tests**

Run: `pytest tests/api/test_dossiers_api.py -v`
Expected: tous les tests PASS

- [ ] **Step 3: Lancer tous les tests pour vérifier les régressions**

Run: `pytest tests/ -x -q 2>&1 | tail -20`
Expected: pas de nouveau FAIL

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_dossiers_api.py
git commit -m "test: add dossier API route + schema tests"
```

---

### Task 10: Frontend CSS — classes dossier + upload meta

**Files:**
- Modify: `app/static/css/style.css` (fin du fichier)

- [ ] **Step 1: Ajouter les styles à la fin de `style.css`**

```css
/* ── Dossier sidebar tree ───────────────────────────────────────────── */
.dossier-client { border-bottom: 1px solid var(--border); }
.dossier-client-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; cursor: pointer;
  font-size: 12px; font-weight: 700; color: var(--text);
  letter-spacing: 0.3px; transition: background var(--t);
  user-select: none;
}
.dossier-client-header:hover { background: var(--bg-hover); }
.dossier-client-count {
  margin-left: auto; font-size: 10px; color: var(--text-muted);
  background: var(--border); border-radius: 999px; padding: 1px 6px;
}
.dossier-exercice-header {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 14px 7px 28px; cursor: pointer;
  font-size: 11px; color: var(--text-muted);
  transition: background var(--t); user-select: none;
}
.dossier-exercice-header:hover { background: var(--bg-hover); }
.dossier-exercice-year { font-weight: 600; color: var(--text); }
.dossier-status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.dossier-status-dot.green { background: #22c55e; }
.dossier-status-dot.orange { background: #f59e0b; }
.dossier-docs-sidebar { padding-left: 12px; }
.dossier-doc-sidebar-item {
  padding: 6px 14px 6px 40px; cursor: pointer;
  font-size: 11px; color: var(--text-muted);
  transition: background var(--t); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.dossier-doc-sidebar-item:hover { background: var(--bg-hover); color: var(--text); }
.sidebar-mode-toggle {
  display: flex; gap: 4px; padding: 8px 12px 0;
}
.sidebar-mode-btn {
  flex: 1; padding: 4px 8px; font-size: 11px; font-weight: 600;
  border: 1px solid var(--border); border-radius: 6px; cursor: pointer;
  background: transparent; color: var(--text-muted);
  transition: background var(--t), color var(--t);
}
.sidebar-mode-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }

/* ── Dossier page (zone principale) ───────────────────────────────── */
#panel-dossier { padding: 0; overflow: hidden; display: flex; flex-direction: column; }
.dossier-page-header {
  display: flex; align-items: center; gap: 12px;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.dossier-page-title { flex: 1; min-width: 0; }
.dossier-page-title h2 { margin: 0; font-size: 18px; font-weight: 700; color: var(--text); }
.dossier-page-stats { font-size: 12px; color: var(--text-muted); margin-top: 2px; display: block; }
.dossier-page-exercices {
  padding: 0 24px 32px; overflow-y: auto; flex: 1;
}
.dossier-exercice-section {
  margin-top: 24px; border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden;
}
.dossier-exercice-section-header {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px;
  background: var(--bg-subtle, rgba(255,255,255,0.03));
  border-bottom: 1px solid var(--border);
}
.dossier-exercice-section-header h3 {
  margin: 0; font-size: 14px; font-weight: 700; color: var(--text);
}
.dossier-docs-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.dossier-docs-table th {
  padding: 8px 12px; text-align: left;
  color: var(--text-muted); font-weight: 600;
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px;
  border-bottom: 1px solid var(--border);
}
.dossier-doc-row { cursor: pointer; transition: background var(--t); }
.dossier-doc-row:hover { background: var(--bg-hover); }
.dossier-doc-row td {
  padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.05);
  color: var(--text);
}
.dossier-doc-row:last-child td { border-bottom: none; }
.badge-category {
  font-size: 10px; padding: 2px 7px; border-radius: 999px;
  background: var(--border); color: var(--text-muted);
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
}
.badge-green { background: rgba(34,197,94,0.15); color: #22c55e; }
.badge-orange { background: rgba(245,158,11,0.15); color: #f59e0b; }

/* ── Upload metadata row ───────────────────────────────────────────── */
.upload-meta-row {
  display: grid;
  grid-template-columns: 1fr 90px 1fr;
  gap: 10px; margin-top: 12px;
}
.upload-meta-field { position: relative; }
.upload-meta-field label {
  display: block; font-size: 11px; font-weight: 600;
  color: var(--text-muted); margin-bottom: 4px;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.auto-badge {
  position: absolute; right: 8px; top: 2px;
  font-size: 10px; color: var(--accent); pointer-events: none;
}

@media (max-width: 640px) {
  .upload-meta-row { grid-template-columns: 1fr; }
  .dossier-page-header { padding: 14px 16px 12px; flex-wrap: wrap; }
  .dossier-page-exercices { padding: 0 12px 24px; }
}
```

- [ ] **Step 2: Vérifier qu'il n'y a pas d'erreurs de syntaxe CSS (recherche accolades)**

Run: `python -c "
text = open('app/static/css/style.css').read()
opens = text.count('{')
closes = text.count('}')
print(f'opens={opens} closes={closes} balanced={opens==closes}')
"` depuis le répertoire du projet
Expected: `balanced=True`

- [ ] **Step 3: Commit**

```bash
git add app/static/css/style.css
git commit -m "feat: add dossier tree/page CSS and upload meta CSS classes"
```

---

### Task 11: Frontend HTML — upload meta row + panel-dossier

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Ajouter le toggle de mode dans la sidebar**

Après `<div id="sidebar-filters" class="sidebar-filters">` (chercher cette ligne), ajouter AVANT les filtres :

```html
        <!-- Mode toggle: liste plate vs arbre dossier -->
        <div class="sidebar-mode-toggle">
          <button class="sidebar-mode-btn active" id="btn-mode-flat" onclick="setSidebarMode('flat')">Docs</button>
          <button class="sidebar-mode-btn" id="btn-mode-dossier" onclick="setSidebarMode('dossier')">Dossiers</button>
        </div>
```

- [ ] **Step 2: Ajouter les champs exercice et doc_category dans l'upload form**

Dans `#panel-upload`, après la `<div class="field-inline">` du `upload-client-name` (ligne ~437), ajouter :

```html
        <div class="upload-meta-row">
          <div class="upload-meta-field">
            <label>Exercice</label>
            <select id="upload-exercice" class="input-sm">
              <option value="">— Année —</option>
            </select>
            <span class="auto-badge" id="badge-exercice" style="display:none">✨ Auto</span>
          </div>
          <div class="upload-meta-field">
            <label>Type doc</label>
            <select id="upload-doc-category" class="input-sm">
              <option value="">— Type —</option>
              <option value="bilan">Bilan</option>
              <option value="liasse_fiscale">Liasse fiscale</option>
              <option value="releve_bancaire">Relevé bancaire</option>
              <option value="grand_livre">Grand livre</option>
              <option value="contrat">Contrat</option>
              <option value="facture">Facture</option>
              <option value="autre">Autre</option>
            </select>
            <span class="auto-badge" id="badge-doc-category" style="display:none">✨ Auto</span>
          </div>
        </div>
```

- [ ] **Step 3: Ajouter le panel dossier dans la zone main**

Chercher `<!-- DASHBOARD -->` dans `index.html`. Ajouter AVANT ce commentaire :

```html
      <!-- DOSSIER CLIENT -->
      <div id="panel-dossier" class="panel">
        <div class="dossier-page-header">
          <button class="btn btn-ghost btn-sm" onclick="showDashboard()" style="flex-shrink:0">← Retour</button>
          <div class="dossier-page-title">
            <h2 id="dossier-page-client-name">Client</h2>
            <span class="dossier-page-stats" id="dossier-page-stats"></span>
          </div>
          <button class="btn btn-primary btn-sm" id="btn-dossier-upload" onclick="openUploadForDossierClient()">
            + Ajouter
          </button>
        </div>
        <div id="dossier-page-exercices" class="dossier-page-exercices">
          <div class="panel-empty-hint">
            <p>Sélectionnez un client dans la sidebar pour voir son dossier.</p>
          </div>
        </div>
      </div>

```

- [ ] **Step 4: Vérifier la syntaxe HTML (balises fermantes)**

Run: `python -c "
from html.parser import HTMLParser
class Check(HTMLParser): pass
Check().feed(open('app/templates/index.html').read())
print('html syntax ok')
"`
Expected: `html syntax ok` (pas d'exception)

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: add sidebar mode toggle, upload meta row, panel-dossier in HTML"
```

---

### Task 12: Frontend JS — arbre dossier sidebar

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Ajouter les fonctions dossier sidebar juste après `renderDocList`**

Chercher la ligne `function renderDocList(docs)` dans `app.js` et ajouter ce bloc APRÈS la fonction complète (après sa `}` fermante) :

```javascript
// ── Sidebar dossier tree ───────────────────────────────────────────

let sidebarMode = "flat"; // "flat" | "dossier"

function setSidebarMode(mode) {
  sidebarMode = mode;
  const btnFlat = $("btn-mode-flat");
  const btnDossier = $("btn-mode-dossier");
  if (btnFlat) btnFlat.classList.toggle("active", mode === "flat");
  if (btnDossier) btnDossier.classList.toggle("active", mode === "dossier");
  if (mode === "dossier") {
    loadDossierTree();
  } else {
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
    list.innerHTML = `<p style="padding:12px;color:var(--text-muted);font-size:12px">Aucun dossier. Uploadez un document avec un nom client.</p>`;
    return;
  }
  list.innerHTML = dossiers.map(client => `
    <div class="dossier-client" data-client="${escapeHtml(client.client_name)}">
      <div class="dossier-client-header" onclick="toggleDossierClient(this)" ondblclick="openDossierPage('${escapeHtml(client.client_name)}')">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="chevron-icon" style="transition:transform 0.2s;transform:rotate(-90deg)"><polyline points="6 9 12 15 18 9"/></svg>
        <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis">${escapeHtml(client.client_name)}</span>
        <span class="dossier-client-count">${client.total_docs}</span>
      </div>
      <div class="dossier-exercices" style="display:none">
        ${(client.exercices || []).map(ex => renderDossierExerciceTree(client.client_name, ex)).join("")}
      </div>
    </div>
  `).join("");
}

function renderDossierExerciceTree(clientName, ex) {
  const allReady = ex.ready_count === ex.doc_count;
  return `
    <div class="dossier-exercice-tree">
      <div class="dossier-exercice-header" onclick="toggleDossierExercice(this)">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="chevron-icon" style="transition:transform 0.2s;transform:rotate(-90deg)"><polyline points="6 9 12 15 18 9"/></svg>
        <span class="dossier-exercice-year">${escapeHtml(ex.exercice || "Sans exercice")}</span>
        <span class="dossier-status-dot ${allReady ? "green" : "orange"}"></span>
        <span style="font-size:10px;color:var(--text-muted)">${ex.ready_count}/${ex.doc_count}</span>
      </div>
      <div class="dossier-docs-sidebar" style="display:none">
        ${(ex.documents || []).map(doc => `
          <div class="dossier-doc-sidebar-item" onclick="selectDoc('${escapeHtml(doc.id)}')" title="${escapeHtml(doc.original_filename)}">
            ${escapeHtml(doc.original_filename)}
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function toggleDossierClient(headerEl) {
  const container = headerEl.closest(".dossier-client");
  const exercicesEl = container.querySelector(".dossier-exercices");
  const chevron = headerEl.querySelector(".chevron-icon");
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
```

- [ ] **Step 2: Vérifier la syntaxe JavaScript**

Run: `node --check app/static/js/app.js 2>&1`
Expected: no output (no syntax errors)

- [ ] **Step 3: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: dossier sidebar tree JS (loadDossierTree, toggle, renderDossierTree)"
```

---

### Task 13: Frontend JS — page dédiée dossier client

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Ajouter les fonctions page dossier client juste après le bloc Task 12**

Ajouter à la suite immédiate du bloc précédent :

```javascript
// ── Dossier page (zone principale) ────────────────────────────────

let currentDossierClient = "";

function openDossierPage(clientName) {
  currentDossierClient = clientName;
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const panel = $("panel-dossier");
  if (panel) panel.classList.add("active");
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
    if (statsEl) statsEl.textContent = `${client.total_docs} document${client.total_docs > 1 ? "s" : ""} · ${client.exercices.length} exercice${client.exercices.length > 1 ? "s" : ""}`;
    exercicesEl.innerHTML = (client.exercices || []).map(ex => renderDossierExerciceSection(ex)).join("");
  } catch (e) {
    exercicesEl.innerHTML = `<p style="padding:20px;color:var(--text-muted)">Erreur chargement dossier.</p>`;
  }
}

function renderDossierExerciceSection(ex) {
  const allReady = ex.ready_count === ex.doc_count;
  const statusBadge = allReady
    ? `<span class="badge-category badge-green">Complet</span>`
    : `<span class="badge-category badge-orange">${ex.ready_count}/${ex.doc_count} prêts</span>`;
  const catsText = (ex.doc_categories || []).map(c => escapeHtml(c)).join(" · ");
  return `
    <div class="dossier-exercice-section">
      <div class="dossier-exercice-section-header">
        <h3>Exercice ${escapeHtml(ex.exercice || "Sans exercice")}</h3>
        ${statusBadge}
        ${catsText ? `<span style="font-size:11px;color:var(--text-muted)">${catsText}</span>` : ""}
      </div>
      <table class="dossier-docs-table">
        <thead><tr>
          <th>Document</th><th>Type</th><th>Taille</th><th>Date</th><th>Statut</th><th></th>
        </tr></thead>
        <tbody>
          ${(ex.documents || []).map(doc => `
            <tr class="dossier-doc-row" onclick="selectDoc('${escapeHtml(doc.id)}')">
              <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(doc.original_filename)}">${escapeHtml(doc.original_filename)}</td>
              <td><span class="badge-category">${escapeHtml(doc.doc_category || "—")}</span></td>
              <td style="color:var(--text-muted)">${formatBytes(doc.size_bytes)}</td>
              <td style="color:var(--text-muted)">${formatDate(doc.created_at)}</td>
              <td>${escapeHtml(documentStatusLabel(doc.status))}</td>
              <td>
                <button class="btn btn-ghost" style="font-size:11px;padding:2px 6px" onclick="event.stopPropagation();openEditMetadataModal('${escapeHtml(doc.id)}')">✏️</button>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
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
```

- [ ] **Step 2: Vérifier la syntaxe JavaScript**

Run: `node --check app/static/js/app.js 2>&1`
Expected: no output (no syntax errors)

- [ ] **Step 3: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: dossier page JS (openDossierPage, renderDossierExerciceSection, edit metadata)"
```

---

### Task 14: Frontend JS — upload auto-prefill + exercice select

**Files:**
- Modify: `app/static/js/app.js`

- [ ] **Step 1: Ajouter la génération du select exercice et la fonction prefill**

Ajouter à la suite du bloc Task 13 :

```javascript
// ── Upload metadata auto-fill ──────────────────────────────────────

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
      if (badge) badge.style.display = "";
    }
  });
}
```

- [ ] **Step 2: Appeler `initExerciceSelect()` dans `initApp()`**

Chercher `async function initApp(email)` dans `app.js`. Ajouter `initExerciceSelect();` dans le corps de la fonction, juste après la ligne d'initialisation du theme ou d'autres inits (avant les appels async).

Pour trouver la bonne ligne : chercher `scheduleTokenRefresh()` dans `initApp`. Ajouter après :

```javascript
  initExerciceSelect();
```

- [ ] **Step 3: Appeler `prefillUploadMetadata` dans `uploadFile` après upload**

Dans `uploadFile`, chercher la ligne :
```javascript
    currentDocStatus = data.processing?.status || data.status || "uploaded";
```

Juste après, ajouter :
```javascript
    if (data.suggestions) prefillUploadMetadata(data.suggestions);
```

- [ ] **Step 4: Inclure `exercice` et `doc_category` dans l'URL d'upload de `uploadFile`**

Chercher dans `uploadFile` :
```javascript
    const clientQp = clientName ? `&client_name=${encodeURIComponent(clientName)}` : "";
    const autoAnon = $("upload-auto-anonymize")?.checked ?? true;
    const data = await uploadWithProgress(fd, `/uploads?auto_anonymize=${autoAnon}${clientQp}`, fill, statusEl);
```

Remplacer par :
```javascript
    const clientQp = clientName ? `&client_name=${encodeURIComponent(clientName)}` : "";
    const exerciceQp = ($("upload-exercice")?.value || "").trim();
    const catQp = ($("upload-doc-category")?.value || "").trim();
    const autoAnon = $("upload-auto-anonymize")?.checked ?? true;
    const extraQp = [
      exerciceQp && `exercice=${encodeURIComponent(exerciceQp)}`,
      catQp && `doc_category=${encodeURIComponent(catQp)}`,
    ].filter(Boolean).join("&");
    const data = await uploadWithProgress(
      fd,
      `/uploads?auto_anonymize=${autoAnon}${clientQp}${extraQp ? "&" + extraQp : ""}`,
      fill, statusEl
    );
```

- [ ] **Step 5: Rafraîchir le tree dossier après upload si on est en mode dossier**

Dans `uploadFile`, chercher `await loadClientSuggestions();` et après `await loadDocList();`, ajouter :

```javascript
    if (sidebarMode === "dossier") loadDossierTree();
```

- [ ] **Step 6: Vérifier la syntaxe JavaScript**

Run: `node --check app/static/js/app.js 2>&1`
Expected: no output (no syntax errors)

- [ ] **Step 7: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: upload auto-prefill exercice/doc_category from server suggestions"
```

---

## Self-Review

Spec coverage check:

| Spec requirement | Task |
|---|---|
| 3 colonnes Document (client_name, exercice, doc_category) | Task 1 (migration) + Task 2 (model) |
| Index composite | Task 1 + Task 2 |
| Backfill tags[0] → client_name | Task 1 |
| doc_metadata_service (extract_exercice, suggest_client, classify_doc_category) | Task 3 |
| classification/service.py délégation | Task 4 |
| DocumentResponse enrichi + nouveaux schémas | Task 5 |
| Upload: exercice/doc_category params + auto-detect + suggestions | Task 6 |
| GET /dossiers | Task 7 |
| PATCH /{id}/metadata | Task 7 |
| GET /clients update | Task 8 |
| Tests unitaires | Task 3 (TDD), Task 9 |
| CSS classes | Task 10 |
| HTML upload meta row | Task 11 |
| HTML panel-dossier | Task 11 |
| Sidebar tree | Task 12 |
| Page dédiée client | Task 13 |
| Upload prefill + exercice select | Task 14 |
| Rétrocompatibilité tags | Task 7 (PATCH sync), Task 8 (fallback), Task 6 (tags=[...]) |
