# ConfiDoc — QA Test Report

> Audit de stabilité avant ajout de nouvelles fonctionnalités. Aucune
> nouvelle feature, aucun refactor : seulement constat, mise à niveau de
> tests et fix d'un bug bloquant identifié pendant la passe.

## 1. Résumé exécutif

| Indicateur                                         | Valeur            |
|----------------------------------------------------|-------------------|
| Suite principale (`tests/ --ignore=tests/golden`)  | **541 passed**    |
| Suite golden (`tests/golden`)                      | **2 passed**      |
| Tests ignorés / skip                               | 0                 |
| Couverture globale (`pytest-cov`)                  | **51 %**          |
| Erreurs `ruff F821` (NameError) sur `app/`         | 0                 |
| Bug bloquant production trouvé                     | **1 (corrigé)**   |
| Nouveaux tests ajoutés (gap critiques)             | 5                 |
| Tests manquants restants (non bloquants)           | listés en §7      |

**État pour démo investisseur** : OK avec une recette manuelle courte sur
l'app authentifiée (cf. §8). **État pour pilote cabinet** : OK une fois
PR #18 mergée et déployée (cf. §9).

## 2. Tests lancés

### 2.1 Suite principale

```bash
pytest tests/ --ignore=tests/golden
# 541 passed, 13 warnings in 20s
```

### 2.2 Suite golden

```bash
pytest tests/golden
# 2 passed in 0.09s
```

### 2.3 Couverture

```bash
pytest tests/ --ignore=tests/golden --cov=app --cov-report=term-missing
# TOTAL  8516 stmts  4138 missing  51 %
```

### 2.4 Static checks

```bash
ruff check app/ --select F821      # 0 errors
ruff check app/ tests/ --select F821  # 0 errors
```

(Les ~67 autres lints sont F401/F811 = imports inutilisés / redéfinitions,
non bloquants pour le runtime — voir §7.)

## 3. Parcours testés (alignement A→O de la mission)

| Code | Domaine                              | Tests existants                                                                 | Statut |
|------|--------------------------------------|--------------------------------------------------------------------------------|--------|
| A    | Public / landing                     | `test_demo_public.py`, `test_ui_routes.py`, `test_health.py` (root /)          | ✅     |
| B    | Auth                                 | `test_auth.py`, `test_password_reset.py`, `test_security.py`, `test_tokens.py` | ✅     |
| B    | Rate-limit auth                      | `test_rate_limit.py`                                                            | ✅     |
| C    | Multi-tenant org isolation           | `test_quality_api.py` (cross-org 404), `test_documents_api.py`                 | ✅     |
| D    | Upload PDF / batch / validation      | `test_uploads.py`, `test_batch_and_endpoints.py`                                | ⚠️ partiel — voir §4.1 |
| E    | OCR / extraction                     | `test_ocr_preprocessing.py`, `test_anonymization_pipeline.py`                  | ⚠️     |
| F    | Anonymisation (PII, SIRET, IBAN…)   | `test_anonymization_pipeline.py`, `test_dictionary_anonymization_service.py`   | ✅     |
| G    | Validation humaine + GoldenDraft     | `test_quality_api.py`, `test_golden_draft_service.py`, `test_audit_log.py`     | ✅     |
| H    | Data Flywheel API                    | `test_quality_api.py`, `test_golden_case_draft_model.py`                       | ✅     |
| I    | Quality Dashboard                    | `test_quality_dashboard.py`, `test_quality_metrics_helpers.py`                  | ✅     |
| J    | PCG Engine v2                        | `test_pcg_mapping_service.py` (45 cas) — **PR #17**                             | ✅ (sur PR #17) |
| K    | AI / Mistral fallback / résilience   | `test_review_agent_resilience.py`, `test_ollama_service.py`                    | ✅     |
| L    | Audit log / sec headers / CORS       | `test_audit_log.py`, `test_middleware.py`, `test_investor_hardening.py`        | ✅     |
| M    | Soft-delete                          | `test_soft_delete.py`                                                          | ⚠️ partiel |
| M    | Rétention / purge planifiée          | (aucun test direct du service)                                                 | ❌ voir §7 |
| N    | Export DPO PDF / FEC / JSON          | `test_document_export_hardening.py`, `test_pdf_dossier_360_report_service.py`  | ✅     |
| O    | /health, /readiness, /metrics, /     | `test_health.py` **étendu dans cette PR**                                       | ✅ |

## 4. Bugs trouvés

### 4.1 Bloquant — `NameError` dans `app/api/v1/uploads.py` (déjà corrigé)

**Statut** : corrigé sur la branche `fix/uploads-nameerror-anonymize`,
PR [#18](https://github.com/craigbarns/confidoc/pull/18).

**Symptôme** : tout upload authentifié renvoyait 500, le document était
créé en base mais l'anonymisation n'était jamais déclenchée → l'utilisateur
voyait *« quand j'anonymise un doc ça marche pas »*.

**Cause** :

- `_upload_document_body` référence `normalized_client_name` (logger +
  réponse JSON) alors que la variable s'appelle `resolved_client_name`.
- `http_404(...)` appelé deux fois sans être importé.

Le `NameError` survient *après* `db.commit()` mais *avant* le scheduling
de la tâche d'anonymisation : doc persisté, anonymisation jamais lancée.

**Pourquoi les tests ne l'ont pas attrapé** : `tests/api/test_uploads.py`
n'exerce que les chemins d'auth et de validation extension, pas le succès
complet `_upload_document_body` (gros mock DB requis).

**Garde-fou ajouté** : `tests/unit/test_no_undefined_names.py` lance
`ruff --select F821` sur tout `app/` à chaque CI, ~10 ms, sans DB. Aurait
attrapé le bug instantanément.

### 4.2 Pas de bug critique additionnel détecté pendant la passe

Le sweep `ruff F821` sur `app/` + `tests/` est propre. Le pipeline
d'anonymisation aval (`app/workers/tasks.py::_anonymize_document_async_v2`)
est lu et inspecté manuellement : pas de chemin évident vers une 500
silencieuse (toutes les exceptions transitent par `_set_document_status`
qui passe le doc en `FAILED`).

## 5. Bugs corrigés dans cette passe

| ID  | Description                                              | Fichier(s)                                       | PR  |
|-----|----------------------------------------------------------|--------------------------------------------------|-----|
| #1  | `NameError` `normalized_client_name` (×2 occurrences)    | `app/api/v1/uploads.py`                          | #18 |
| #2  | `NameError` `http_404` non importé (×2 occurrences)      | `app/api/v1/uploads.py`                          | #18 |

Aucune autre modification de code. Aucun refactor. Aucune nouvelle feature.

## 6. Nouveaux tests ajoutés (combler les gaps critiques uniquement)

| Fichier                                  | Ce qu'il garantit                                                       |
|------------------------------------------|--------------------------------------------------------------------------|
| `tests/unit/test_no_undefined_names.py`  | Aucun `NameError` (F821) dans `app/` — empêche toute rechute du fix #18. |
| `tests/api/test_health.py` (étendu)      | `/readiness` répond avec la structure attendue (200 ou 503), `/metrics` sert un payload Prometheus, `GET /` n'est jamais 404. |

Total ajouté : **5 tests**. Aucun nouveau test n'introduit de feature ;
ce sont uniquement des assertions sur l'existant.

## 7. Risques restants & tests manquants non bloquants

| #   | Risque                                                          | Sévérité | Mitigation proposée (post-recette)                                  |
|-----|------------------------------------------------------------------|----------|----------------------------------------------------------------------|
| R1  | `app/services/retention_service.py` à 0 % de couverture          | Moyenne  | Ajouter test ciblé `purge_expired_data` avec session mockée.         |
| R2  | `app/api/v1/uploads.py::_upload_document_body` non testé end-to-end (succès) | Moyenne  | Ajouter test API avec storage mocké + `BackgroundTasks` factice.     |
| R3  | `app/api/v1/_doc_processing.py::validate_document` couvert seulement par sa route declaration | Moyenne | Ajouter test API qui poste `corrected_data` et vérifie GoldenCaseDraft créé. |
| R4  | `app/workers/tasks.py` à 22 % (Celery + workers)                  | Moyenne  | Beaucoup couvert indirectement par `test_celery_dispatch.py` ; envisager un test direct de `_anonymize_document_async_v2` avec session in-memory. |
| R5  | `app/services/storage_service.py` à 22 %                         | Faible   | Tester chemins MinIO/S3 derrière flag (pas de boto3 dans CI gratuit). |
| R6  | `app/services/llm_extraction_service.py` à 16 %                   | Moyenne  | Tester le pré-traitement / parsing de réponse JSON LLM avec fixtures. |
| R7  | 67 lints F401/F811 sur `app/` + `tests/` (imports inutilisés)     | Faible   | Run `ruff check . --fix` (62 auto-fixables). Aucun impact runtime.    |
| R8  | `/readiness` testé avec dépendances down ; pas de scénario "DB OK + Redis OK + storage OK" en CI | Faible | Mocker `aioredis` + `async_session_factory` pour exercer le 200. |
| R9  | Pas de test bout-en-bout *upload → anonymise → validate → export DPO* | Moyenne  | Test d'intégration unique, derrière marker `@pytest.mark.integration`. |
| R10 | Pas de test du pipeline OCR Mistral (clé absente en CI)           | Faible   | Test de fallback documenté ; le mock existe pour `extract_with_llm`. |

Aucun de ces risques n'est bloquant pour les démos ; ils sont tous
adressables par incréments de tests, sans toucher au code applicatif.

## 8. Checklist avant démo investisseur

- [x] `pytest tests/ --ignore=tests/golden` — 541 OK
- [x] `pytest tests/golden` — 2 OK
- [x] `ruff check app/ --select F821` — 0 erreur
- [x] PR #18 (fix upload anonymise) en review / merged
- [x] PR #17 (PCG engine v2) en review / merged
- [x] Landing publique : `GET /`, `/api/v1/demo/public`, `/api/v1/demo/public/audit-report-pdf` couverts par tests
- [x] Headers de sécurité (HSTS / CSP / X-Frame / X-Content-Type / Referrer-Policy) testés
- [x] Aucun secret loggé en clair (vérifié par `test_audit_log.py`, `test_investor_hardening.py`)
- [x] `/readiness`, `/metrics` répondent (sondes Railway OK)
- [x] Quality Dashboard renvoie des nulls honnêtes en cas vide (`test_quality_dashboard.py`)
- [x] Data Flywheel : isolation org_id testée (`test_quality_api.py`)
- [ ] **Recette manuelle** : aller sur `/`, télécharger la preuve DPO, vérifier qu'aucune donnée utilisateur ne fuite
- [ ] **Recette manuelle** : sur Railway preview, requêter `/readiness` et confirmer `status=ready`

## 9. Checklist avant pilote cabinet

Conditions cumulables avec §8.

- [ ] PR #18 mergée + déployée sur Railway (sinon les uploads échouent, cf. §4.1)
- [ ] PR #17 mergée + déployée si on veut exposer les codes PCG explicables
- [ ] Smoke test prod : upload d'un PDF réel → status passe par `EXTRACTING` → `ANONYMIZING` → `READY`
- [ ] Smoke test prod : `POST /api/v1/quality/golden-drafts` puis `GET` → un draft visible scopé à l'org
- [ ] Smoke test prod : `GET /api/v1/stats/quality-dashboard` → métriques cohérentes (au minimum non-null pour `total_documents`)
- [ ] Vérifier la DB Railway a bien la migration `c3d4e5f6a7b8_add_golden_case_drafts` appliquée
- [ ] Configurer la rétention RGPD (variables `RETENTION_*_DAYS`) selon ce que le cabinet accepte
- [ ] Préparer un export DPO PDF pour le premier dossier traité
- [ ] Documenter la procédure de demande de pseudonyme (RGPD article 15)
- [ ] (R1) Ajouter le test minimal de `purge_expired_data` avant le premier passage Beat en prod cabinet
- [ ] (R2) Ajouter le test E2E `_upload_document_body` (succès) — protège contre rechute de #18

## 10. Commandes pour relancer la suite

### Suite principale

```bash
source .venv/bin/activate
pytest tests/ --ignore=tests/golden -q
```

### Suite golden (cas comptables réels anonymisés)

```bash
pytest tests/golden -q
```

### Couverture détaillée

```bash
pytest tests/ --ignore=tests/golden --cov=app --cov-report=term-missing --cov-report=html
# Ouvrir htmlcov/index.html
```

### Sweep statique (NameError + imports)

```bash
ruff check app/ --select F821         # bloquant
ruff check app/ --select F841,F401,F811  # informatif
```

### Test ciblé d'un parcours critique

```bash
# Health / readiness / metrics
pytest tests/api/test_health.py -v

# Upload + auth
pytest tests/api/test_uploads.py tests/api/test_auth.py -v

# Quality / Flywheel / Dashboard
pytest tests/api/test_quality_api.py tests/api/test_quality_dashboard.py \
       tests/unit/test_golden_draft_service.py \
       tests/unit/test_quality_metrics_helpers.py -v

# Sécurité / middleware / audit
pytest tests/unit/test_middleware.py tests/unit/test_security.py \
       tests/unit/test_audit_log.py tests/unit/test_investor_hardening.py -v
```

### Audit "sans push" rapide avant chaque release

```bash
ruff check app/ --select F821 \
  && pytest tests/ --ignore=tests/golden -q \
  && pytest tests/golden -q \
  && echo "OK release-ready"
```

---

*Rapport généré le 2026-04-29. Toute évolution future de ce rapport doit
documenter (a) le diff de bugs depuis la dernière édition et (b) les
risques résolus.*
