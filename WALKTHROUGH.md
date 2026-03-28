# Walkthrough technique — anonymisation, routes API, IA

Ce document résume l’état **implémenté** dans le dépôt : ordre des routes FastAPI, pipeline d’anonymisation, et endpoint JSON pour l’IA / le RAG.

---

## Ordre des routes `GET /api/v1/documents/*` (important)

FastAPI évalue les routes **dans l’ordre de déclaration**. Les chemins **statiques** doivent donc apparaître **avant** la route paramétrée `/{document_id}`, sinon un segment comme `trash` peut être interprété comme un identifiant de document.

Ordre attendu (cf. `app/api/v1/documents.py`) :

| Ordre | Route | Rôle |
|------|--------|------|
| 1 | `GET ""` | Liste des documents |
| 2 | `GET "/clients"` | Liste des noms clients (tags) |
| 3 | `GET "/trash/list"` | Corbeille (documents supprimés) |
| 4 | `GET "/{document_id}"` | Détail d’un document |
| 5 | `GET "/{document_id}/structured"` | **JSON** pour IA / RAG (entités + texte optionnel) |
| … | autres `/{document_id}/…` | preview, anonymize, export, etc. |

> **Note :** `GET /{document_id}/structured` est plus spécifique que `GET /{document_id}` ; elle reste **après** les routes entièrement statiques (`/clients`, `/trash/list`) pour éviter tout conflit historique avec `/trash/...`.

---

## Récap des évolutions (anonymisation & cohérence)

| # | Sujet | Statut |
|---|--------|--------|
| — | Fix routes FastAPI — `/trash/list` accessible (pas confondu avec `document_id`) | Fait |
| 1 | **EntityRegistry** — même valeur normalisée ⇒ même placeholder dans le document | `app/services/entity_registry.py`, branché depuis le dictionnaire / services d’anonymisation |
| 2 | **Quasi-identifiants** — villes, lieux-dits, emprunts, naissances, cadastre, etc. | Règles et passes dans `app/services/dictionary_anonymization_service.py` (y compris nettoyage post-traitement) |
| 3 | **Post-OCR** — normalisation d’identifiants, réduction des fuites résiduelles | `_normalize_ocr_identifiers`, `POST_CLEANUP_RULES`, etc. |
| 4 | **Endpoint structuré** — sortie JSON pour IA / RAG | `GET /api/v1/documents/{document_id}/structured` |
| 5 | **Résumé d’entités** — comptages et tags sémantiques | Champs `entity_summary`, `entity_tags` dans la réponse structurée (dérivés des `EntityDetection`) |

---

## Endpoint `GET /api/v1/documents/{document_id}/structured`

**Query :**

- `include_text` (bool, défaut `true`) — inclut ou non le texte anonymisé complet.

**Réponse (`StructuredDocumentResponse`) :**

- `document_id`, `doc_type`, `status`, `original_filename`, `created_at`
- `entity_summary` — comptage par **type de détection** (clés = types issus des détections)
- `entity_tags` — liste de `{ placeholder, entity_type, occurrences }` avec `entity_type` sémantique inféré (`PERSON`, `COMPANY`, `ADDRESS`, `BANK`, `COMPANY_ID`, etc.) via `_infer_semantic_type`
- `anonymized_text` — texte anonymisé si `include_text=true`
- `text_length`, `detections_count`, `anonymization_method` (réservé / enrichissement futur)

**Exemple :**

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/v1/documents/$DOC_ID/structured?include_text=true"
```

---

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `app/services/entity_registry.py` | Registre valeur → placeholder stable |
| `app/services/dictionary_anonymization_service.py` | Règles de remplacement, OCR, post-nettoyage |
| `app/api/v1/documents.py` | Routes dont `/structured` |
| `app/schemas/document.py` | `StructuredDocumentResponse`, `EntityMappingItem` |

---

## Distinction utile pour l’équipe produit

- **`GET .../structured`** : métadonnées + texte anonymisé + agrégats d’entités pour **chat IA / RAG**.
- **Extraction métier type bilan / liasse** : logique dans `app/services/structured_dataset_service.py` (usage scripts & golden) ; les endpoints HTTP dédiés « export dataset » éventuels sont documentés ailleurs (ex. `RAILWAY_DEPLOY_CHECKLIST.md`) selon la branche déployée.

Pour toute évolution, garder **l’ordre des routes statiques avant `/{document_id}`** et ajouter un commentaire d’avertissement dans `documents.py` lors de nouvelles routes sous `/documents/...`.
