# ConfiDoc — Quality & Business Metrics

## Pourquoi ces métriques

ConfiDoc traite des documents sensibles dans un contexte où le ROI doit être
mesurable. Trois questions doivent pouvoir être répondues, par organisation, à
tout moment :

1. **Le pipeline tourne-t-il ?** (volumes traités, statuts)
2. **Va-t-il vite ?** (time-to-value, time-to-validation)
3. **Produit-il quelque chose d'utilisable du premier coup ?** (taux de
   correction humaine, distribution des erreurs)

La 3ᵉ question est la plus importante : c'est elle qui prouve que ConfiDoc
réduit le coût marginal d'un document et alimente le **Data Flywheel**
(`docs/DATA_FLYWHEEL.md`).

## Endpoint

```
GET /api/v1/stats/quality-dashboard
```

Authentification standard (JWT ou API Key). Tous les agrégats sont **scopés
sur `current_user.org_id`** — aucun calcul cross-org n'est exposé. Si
l'utilisateur n'a pas d'organisation active, l'endpoint renvoie un payload
"vide" avec des métriques à zéro et `org_id = null`.

### Réponse (`QualityDashboardResponse`)

| Champ | Type | Source / méthode | Notes |
| --- | --- | --- | --- |
| `org_id` | UUID \| null | `current_user.org_id` | Null si pas de membership. |
| `as_of` | datetime | `now()` | Snapshot time. |
| `total_documents` | int | `COUNT(documents)` org-scopé, hors soft-delete | |
| `processed_documents` | int | `COUNT(DISTINCT)` documents avec `PREVIEW_ANONYMIZED` | |
| `validated_documents` | int | `COUNT(DISTINCT)` documents avec `FINAL_ANONYMIZED` | |
| `avg_processing_seconds` | float \| null | moyenne `min(version.created_at) - document.created_at` pour `PREVIEW_ANONYMIZED` | Null si aucun document n'a encore été traité. |
| `avg_time_to_validation_seconds` | float \| null | moyenne idem pour `FINAL_ANONYMIZED` | Null si aucune validation. |
| `one_shot_full_ready_rate` | float \| null | `(validated − validated_with_drafts) / validated` | Part des validations sans aucune correction humaine. Null si zéro validation. |
| `avg_human_overrides_per_document` | float \| null | `total_drafts / validated` | Charge moyenne de correction. Null si zéro validation. |
| `total_golden_case_drafts` | int | `COUNT(golden_case_drafts)` org-scopé | |
| `accepted_golden_case_drafts` | int | `COUNT(... WHERE status='accepted')` | |
| `corrections_by_field` | `{field: int}` | `GROUP BY field_name` | Permet de cibler les champs qui se trompent le plus souvent. |
| `corrections_by_error_type` | `{error_type: int}` | `GROUP BY error_type` | Sépare `manual_correction`, `wrong_extraction`, `missed_field`, etc. |
| `documents_by_status` | `{status: int}` | `GROUP BY documents.status` | Tableau de bord opérationnel. |

### Convention "honnête" de valeurs nulles

Quand une métrique ne peut pas être calculée de manière fiable
(ex. division par zéro, aucune donnée encore présente), elle est explicitement
retournée à `null` et **non** à `0`. Cela évite de "vendre" un taux artificiel
de 100 % de one-shot quand aucun document n'a encore été validé.

## Sources réutilisées

| Métrique | Source dans le code |
| --- | --- |
| Upload timestamp | `Document.created_at` (`app/models/document.py`) |
| Processing completed | `DocumentVersion(version_type=PREVIEW_ANONYMIZED).created_at` |
| Validation timestamp | `DocumentVersion(version_type=FINAL_ANONYMIZED).created_at` |
| Document status | `Document.status` (enum `DocumentStatus`) |
| Human corrections | `GoldenCaseDraft` (Data Flywheel, `docs/DATA_FLYWHEEL.md`) |
| Field-level corrections | `GoldenCaseDraft.field_name` |
| Error categorization | `GoldenCaseDraft.error_type` |

Aucune nouvelle table n'est nécessaire. Aucune écriture n'est faite par
l'endpoint : c'est un pur agrégateur read-only.

## Comment lire ces métriques côté investisseur

### 1. Volume → traction

`total_documents` + `processed_documents` + `validated_documents` montrent
l'activité réelle d'une organisation. La courbe `validated_documents / mois`
est l'indicateur de stickiness produit (il faut une vraie validation humaine,
donc un usage réel et non un POC dormant).

### 2. Time-to-value → ROI

`avg_processing_seconds` et `avg_time_to_validation_seconds` se traduisent
directement en gain de temps humain par rapport au workflow manuel
(anonymisation + validation traditionnellement faits à la main). Plus ces
chiffres baissent, plus ConfiDoc déloge un goulot d'étranglement.

### 3. Qualité du modèle → moat

- **`one_shot_full_ready_rate`** : la métrique-phare. Un taux qui monte au fil
  du temps prouve que le pipeline apprend de ses erreurs (couplé au Data
  Flywheel).
- **`avg_human_overrides_per_document`** : doit baisser. Une baisse = moins
  d'effort humain par document = ROI client qui s'améliore.
- **`corrections_by_field` / `corrections_by_error_type`** : pointent
  exactement où investir l'effort produit (extracteurs, dictionnaires
  d'anonymisation, prompts). Ces deux distributions sont aussi *propriétaires*
  par cabinet — un concurrent qui copie l'API n'a pas accès à ces
  distributions réelles.
- **`accepted_golden_case_drafts / total_golden_case_drafts`** : taux de
  curation. Un taux d'acceptation élevé indique que les corrections humaines
  sont structurellement réutilisables (signal de qualité de la donnée
  collectée).

### 4. Pour un deck investisseur

Les graphes les plus convaincants à plotter à partir de cet endpoint :

- Courbe **`one_shot_full_ready_rate`** par mois — démontre l'effet flywheel.
- Histogramme **`corrections_by_field`** — démontre la profondeur du dataset
  propriétaire.
- Courbe **`avg_time_to_validation_seconds`** — démontre la décroissance du
  coût de production d'un document validé.
- KPI brut **`validated_documents`** — démontre la traction et la rétention.

## Multi-tenant & sécurité

- Tous les helpers (`_count_documents`, `_count_processed_and_validated`,
  `_avg_durations_seconds`, `_draft_aggregates`,
  `_count_validated_documents_with_drafts`) imposent
  `WHERE … org_id = :current_user.org_id`. Le test
  `tests/unit/test_quality_metrics_helpers.py` capture les statements
  compilés et vérifie que le filtre est présent.
- Aucun helper ne fait de `JOIN` sans repasser une contrainte sur `org_id` des
  deux côtés (cf. `_count_validated_documents_with_drafts`).
- Aucun document complet n'est exposé : ce sont uniquement des compteurs et
  des moyennes.
- Pas de secret/PII renvoyée — uniquement des `field_name` et des
  `error_type`, qui sont des chaînes structurées non sensibles.

## Roadmap (futures métriques à brancher)

Les métriques suivantes ne sont pas encore exposées car elles dépendent de
sources qui n'existent pas encore (ou pas de manière propre). Elles seront
ajoutées par incréments :

| Métrique future | Source manquante / dépendance |
| --- | --- |
| **Temps humain économisé** | Estimation du baseline (durée d'anonymisation manuelle) — à modéliser par doc_type. |
| **Coût IA par document** | Persister tokens / coûts unitaires depuis `LlmRequest` (déjà partiellement présent), agréger par doc. |
| **Taux d'export bloqué** | Étendre l'audit log avec un événement `export_blocked` distinct (aujourd'hui mélangé à `approve-export`). |
| **Taux de ré-identification résiduelle** | Brancher `reidentification_risk_service` pour stocker un score par document validé. |
| **Documents full-ready sans correction** | Variante de `one_shot_full_ready_rate` filtrée par `doc_type`. |
| **Cohorting** | Agrégats hebdo / mensuels pour suivre la tendance temporelle (à exposer via `?since=` / `?bucket=`). |

Tant que ces sources ne sont pas fiables, l'endpoint **ne fabrique pas de
métrique** — c'est un parti pris : mieux vaut un `null` honnête qu'un chiffre
trompeur dans un deck.

## Tests associés

- `tests/api/test_quality_dashboard.py` — registration, auth, cas vide,
  calculs assemblés, ratios null sans validation, isolation `org_id`,
  groupements `corrections_by_field` / `corrections_by_error_type` /
  `documents_by_status`.
- `tests/unit/test_quality_metrics_helpers.py` — chaque helper SQL filtre
  bien sur `org_id`, average en Python pour `_avg_durations_seconds`.
