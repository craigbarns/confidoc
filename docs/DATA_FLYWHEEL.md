# ConfiDoc — Data Flywheel (v1)

## Pourquoi cette feature

ConfiDoc traite des documents sensibles (comptables, juridiques) avec une
contrainte d'exactitude forte. Chaque correction humaine au cours d'une
validation est un signal de très haute valeur : elle indique précisément où
l'extraction, la classification ou l'anonymisation se trompent.

Aujourd'hui, ces corrections existent dans le flow `POST /documents/{id}/validate`
(payload `corrected_data`) mais sont seulement re-projetées vers un fichier
golden brouillon. Elles ne sont ni structurées, ni interrogeables, ni
réutilisables pour la curation.

Le **True Data Flywheel** transforme ces corrections en données structurées,
isolées par tenant, prêtes à alimenter :

1. les **golden sets** (cas de régression et benchmarks),
2. les **règles métier** d'extraction (`business_rule_service`),
3. les **prompts LLM** (assistance / extraction structurée),
4. les **dictionnaires d'anonymisation** (entités manquées ou mal catégorisées).

## Architecture v1

```
Validation humaine                 Curation                 Golden set
(POST /validate)                 (PATCH status)             (consommation)
       │                                │                          │
       ▼                                ▼                          ▼
┌──────────────────┐  draft   ┌──────────────────┐  accepted  ┌──────────────┐
│ GoldenCaseDraft  ├─────────►│ GoldenCaseDraft  ├───────────►│ Golden cases │
│   status=draft   │          │ status=accepted  │            │  curated     │
└──────────────────┘          └──────────────────┘            └──────────────┘
        ▲                            │
        │                            ▼ rejected
        │                     ┌──────────────────┐
        └─────────────────────┤ Triage / cleanup │
                              └──────────────────┘
```

## Modèle `GoldenCaseDraft`

Stocké dans `golden_case_drafts`. Hérite de `TenantModel` : `org_id` est
**obligatoire** et indexé.

Champs :


| Champ                | Type      | Notes                                                            |
| -------------------- | --------- | ---------------------------------------------------------------- |
| `id`                 | UUID      | Clé primaire.                                                    |
| `org_id`             | UUID      | Tenant. Toutes les requêtes filtrent dessus.                     |
| `document_id`        | UUID FK   | Document source (CASCADE on delete).                             |
| `created_by_user_id` | UUID FK   | Utilisateur ayant validé (SET NULL on delete).                   |
| `field_name`         | str(120)  | Champ corrigé (ex. `total_ttc`).                                 |
| `predicted_value`    | encrypted | Valeur prédite par le pipeline. Optionnelle.                     |
| `corrected_value`    | encrypted | Valeur corrigée par l'humain. Obligatoire.                       |
| `source_snippet`     | encrypted | Extrait court (≤ 500 chars) **du texte anonymisé**.              |
| `error_type`         | str(60)   | Catégorie d'erreur (`manual_correction`, `wrong_extraction`, …). |
| `confidence_before`  | float     | Score du prédicteur avant correction (0..1).                     |
| `document_type`      | str(60)   | Type du document (`invoice`, `bilan`, …).                        |
| `status`             | enum      | `draft` / `accepted` / `rejected`.                               |
| `created_at`         | tz dt     | Hérité de `TimestampMixin`.                                      |
| `updated_at`         | tz dt     | Hérité.                                                          |


**Index composites optimisés** : `(org_id, created_at)`, `(org_id, status)`,
`(org_id, document_type)`, `(org_id, error_type)`.

### Garanties RGPD / sécurité

- `predicted_value`, `corrected_value` et `source_snippet` utilisent le type
`EncryptedString` (Fernet via `ENCRYPTION_MASTER_KEY`). Les valeurs sont
chiffrées **at rest**.
- Le snippet est **plafonné à 500 caractères**. **Aucun document complet**
n'est jamais stocké dans un draft.
- Les snippets passés depuis le flow `validate_document` proviennent du texte
**déjà anonymisé** (`PREVIEW_ANONYMIZED` / `FINAL_ANONYMIZED`), pas du texte
brut.
- Toutes les requêtes (CRUD) filtrent strictement sur `org_id` ; un draft d'une
autre organisation est invisible (404).

## Endpoints

Tous les endpoints sont sous `/api/v1/quality` et exigent l'authentification
standard (JWT ou API key). Tous sont scopés à `current_user.org_id`.

### `POST /api/v1/quality/golden-drafts`

Crée un draft à partir d'une correction humaine. Le `document_id` doit
appartenir à l'organisation du caller (sinon 404).

```json
{
  "document_id": "…",
  "field_name": "total_ttc",
  "predicted_value": "1200.00",
  "corrected_value": "1234.56",
  "source_snippet": "Total TTC: [MONTANT_1]",
  "error_type": "wrong_extraction",
  "confidence_before": 0.42,
  "document_type": "invoice"
}
```

Retour : `201 Created` + `GoldenDraftResponse`.

### `GET /api/v1/quality/golden-drafts`

Liste les drafts de l'organisation. Filtres optionnels :

- `status` : `draft` | `accepted` | `rejected`
- `document_type` : ex. `invoice`
- `error_type` : ex. `manual_correction`
- `document_id` : UUID

Pagination : `skip`, `limit` (1..500).

### `PATCH /api/v1/quality/golden-drafts/{id}/status`

Curation : passe un draft à `accepted` ou `rejected`.

```json
{ "status": "accepted" }
```

Un draft d'une autre organisation renvoie `404` — pas `403` — pour ne pas
fuiter l'existence du draft.

## Branchement automatique sur la validation

Dans `app/api/v1/_doc_processing.py` (`validate_document`), lorsque l'utilisateur
poste `corrected_data` + `doc_type`, on crée **un `GoldenCaseDraft` par champ
corrigé** en plus du draft fichier déjà existant.

Les échecs sont **non-bloquants** : si la persistance échoue, la validation
reste un succès et l'erreur est logguée (`golden_draft_db_persist_failed`).

## Pourquoi c'est un moat

1. **Données propriétaires**. Chaque cabinet client génère, en utilisant le
  produit, des paires `(prédiction, correction)` parfaitement étiquetées. Ces
   paires sont introuvables sur le marché — elles sont propres au métier
   (comptabilité, juridique) et propres à la langue (français formel).
2. **Effet boucle**. Plus on traite de documents → plus on a de drafts → plus
  on durcit golden / règles / prompts → meilleure qualité → plus de cabinets
   adoptent → plus de drafts. La courbe est self-reinforcing.
3. **Barrière d'entrée**. Un nouvel entrant qui copie l'API n'aura *pas* la
  distribution d'erreurs réelles. Il devra payer un coût de bootstrap (golden
   manuel, RLHF) que ConfiDoc amortit en continu.
4. **Privacy-compatible**. Les drafts sont chiffrés au repos, plafonnés en
  taille, isolés par tenant et basés sur du texte déjà anonymisé. Le moat ne
   contredit pas la promesse RGPD ; il la *renforce* (les drafts sont
   curables sans réintroduire de PII).

## Suite (v2+)

- Job de curation périodique : passer des drafts `accepted` au format
`golden/cases/.../expected.min.json` consommé par
`tests/golden/test_golden_json_schema.py`.
- Métriques exposées : drafts par `error_type`, taux d'acceptation, couverture
par `document_type`.
- Boucle vers `business_rule_service` : règles automatiquement re-générées à
partir des drafts `accepted` au-dessus d'un seuil de confiance.
- Boucle vers `dictionary_anonymization_service` : entités manquantes ou
mal-catégorisées rejouées comme cas de régression d'anonymisation.
- Intégration Copilot : un draft accepté devient automatiquement un
contre-exemple pour le prompt système.

## Tests associés

- `tests/api/test_quality_api.py` : routes, auth, validation, isolation
multi-tenant, changement de statut, cross-org bloqué.
- `tests/unit/test_golden_case_draft_model.py` : colonnes, index,
chiffrement des champs sensibles.
- `tests/unit/test_golden_draft_service.py` : truncation, agrégation depuis
`corrected_data`, no-op si vide.

