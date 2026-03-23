# ConfiDoc - Documentation commerciale et technique

Version: v1.0  
Derniere mise a jour: 2026-03-23  
Public cible: direction, sales, produit, operations, partenaires techniques

---

## 1. Resume executif

ConfiDoc est un SaaS de traitement documentaire pour les equipes comptables et finance qui veulent:

- anonymiser/pseudonymiser des documents sensibles;
- extraire des donnees metier structurees (bilan, compte de resultat, fiscal 2072);
- controler la qualite d'extraction avant usage;
- conserver la tracabilite (audit/proof) pour la conformite.

Promesse cle:

- **Core Ready**: donnees critiques fiables pour un usage interne prudent;
- **Full Ready**: extraction complete prete pour exploitation metier normale.

---

## 2. Vision, positionnement et proposition de valeur

### 2.1 Vision

Permettre un usage concret de l'IA et de l'automatisation comptable sans exposer les donnees sensibles.

### 2.2 Positionnement

ConfiDoc se positionne entre:

- les OCR generalistes (peu orientes metier comptable),
- les outils de data-entry manuelle (lents, peu scalables),
- et les plateformes IA sans garde-fous qualite/compliance.

### 2.3 Proposition de valeur

- Reduction du temps de pre-traitement documentaire.
- Qualite mesurable via score + flags + champs critiques.
- UX actionnable: statut, explication, action suivante.
- API exploitable pour integration SI, BI, workflows internes.

---

## 3. Cibles et cas d'usage

### 3.1 Personas prioritaires

- Expert-comptable / collaborateur cabinet.
- Responsable administratif et financier (PME/ETI).
- Equipe operations back-office documentaire.
- Equipe produit/data d'un editeur finance.

### 3.2 Cas d'usage

- Preparer des donnees structurees a partir de liasses/fichiers comptables.
- Anonymiser avant partage interne/externe.
- Produire un export auditable et traçable.
- Alimenter des flux analytics/RAG/controle interne.

---

## 4. Offre produit

### 4.1 Parcours standard

1. Login
2. Upload
3. Anonymisation (auto ou manuelle)
4. Preview
5. Validation humaine
6. Export (dataset, structured dataset, audit, proof)

### 4.2 Statuts qualite metier

- **Full Ready**: extraction complete validee pour usage normal.
- **Core Ready**: champs critiques valides, enrichissement recommande.
- **Review**: verification humaine requise avant usage serieux.

### 4.3 Valeur livree par statut

- Full Ready -> acceleration maximale.
- Core Ready -> valeur immediate sans attendre 100% de couverture.
- Review -> risque maitrise via garde-fous explicites.

---

## 5. Message commercial (deck / demo / argumentaire)

### 5.1 Pitch court

"ConfiDoc transforme vos documents comptables sensibles en donnees exploitables, anonymisees, et qualifiees - avec un statut metier clair (Core/Full Ready) pour savoir immediatement quoi faire."

### 5.2 Differenciateurs

- Focus metier comptable/fiscal (pas OCR generic-only).
- Quality gates explicites (pas de "boite noire" silencieuse).
- API + UI operationnelles.
- Conception privacy-by-default.

### 5.3 Objections et reponses

- "Le score est bas" -> "Core Ready valide deja les champs critiques."
- "Pourquoi review?" -> "Le moteur signale precisement le point a verifier."
- "Conformite?" -> "Flux anonymise + audit/proof + suppression controlee."

---

## 6. Packaging et modele economique (proposition)

### 6.1 Packaging recommande

- **Starter**: volume limite, support email, Core Ready.
- **Pro**: volumes plus eleves, SLA standard, exports avances.
- **Enterprise**: SLA cible, gouvernance, custom rules, support prioritaire.

### 6.2 Unites de facturation possibles

- Par document traite.
- Par pack de documents/mois.
- Par organisation + quota.

### 6.3 KPI business a suivre

- Time-to-first-value (premier export utile).
- Taux Core Ready / Full Ready.
- Reduction du temps de traitement manuel.
- Taux de retention pilot -> abonnement.

---

## 7. Architecture technique (haut niveau)

### 7.1 Stack

- Backend: FastAPI
- DB: PostgreSQL (SQLAlchemy async)
- Queue/cache: Redis/Celery
- Stockage: database, local ou MinIO
- Deploiement: Railway (Dockerfile)

### 7.2 Composants

- `app/api/v1/uploads.py`: upload + auto-anonymisation
- `app/api/v1/documents.py`: preview/validate/export/proof/quality
- `app/services/anonymization_service.py`: extraction texte + anonymisation
- `app/services/structured_dataset_service.py`: extraction metier + quality
- `app/services/quality_experience.py`: message UX actionnable
- `app/services/extraction_thresholds.py`: seuils centralises (override env)

### 7.3 Interface web

- `/ui` sert un template statique
- assets CSS/JS via `/static`
- badges qualite: Full Ready / Core Ready / Review

---

## 8. Contrat de donnees (structured dataset)

### 8.1 Structure globale

- `doc_type`, `detected_doc_type`
- `routing_confidence`, `routing_reasons`, `routing_runner_up`
- `fields`
- `tables`
- `quality`
- `provenance`
- `experience`

### 8.2 Bloc quality

- `coverage_ratio`
- `filled_fields`, `total_fields`
- `critical_missing_fields`
- `needs_review`
- `ready_for_ai`
- `ready_for_ai_core`
- `quality_flags`

### 8.3 Bloc experience (UX-ready)

- `level`
- `headline_fr`
- `items[]` (code, label, severity, hint)
- `segmentation_note_fr`
- `metrics`

---

## 9. API metier (resume operationnel)

### 9.1 Auth

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`

### 9.2 Upload et traitement

- `POST /api/v1/uploads?auto_anonymize=...&profile=...&document_type=...`
- `POST /api/v1/documents/{id}/anonymize`
- `GET /api/v1/documents/{id}/preview`
- `POST /api/v1/documents/{id}/validate`

### 9.3 Exports et preuve

- `GET /api/v1/documents/{id}/export-dataset`
- `GET /api/v1/documents/{id}/export-structured-dataset?doc_type=...`
- `GET /api/v1/documents/{id}/audit-export`
- `GET /api/v1/documents/{id}/proof`
- `GET /api/v1/documents/{id}/dataset-summary`

### 9.4 Administration utilisateur (scope courant)

- `DELETE /api/v1/documents?confirm=true` (bulk suppression utilisateur)
- `DELETE /api/v1/documents/{id}` (suppression unitaire)

---

## 10. Qualite d'extraction et garde-fous

### 10.1 Principes

- Extraction orientee precision metier, pas remplissage agressif.
- Fallbacks progressifs (label, wide-gap OCR, multiline, agrégats).
- Cohérence numerique et agrégée avant "ready".

### 10.2 Exemples de garde-fous

- Rejet de montants aberrants (codes compte confondus avec montants).
- Rejet de libellés société trop generiques/bruites.
- Deductions algebriques controlees sur 2072 quand pertinent.

### 10.3 Seuils configurables

Les seuils extraction/qualite sont centralises et surchargeables via variables d'environnement:

- `EXTRACT_*` (min montants, tolerances, niveaux ready/core, caps)

---

## 11. Securite, confidentialite, conformite

### 11.1 Principes techniques

- Minimisation de donnees.
- Anonymisation/pseudonymisation avant usages IA.
- Separation des secrets via variables d'environnement.
- Traceabilite via audit/proof.

### 11.2 Recommandations operations

- Rotation reguliere des credentials.
- Politique de retention explicite.
- Journalisation et supervision des acces sensibles.
- Revues periodiques des scopes/API tokens.

---

## 12. Deployment et exploitation

### 12.1 Railway

- Build par Dockerfile (`railway.json`)
- Healthcheck: `/health`
- Restart policy: on failure

### 12.2 Pre-deploiement

- Tests unitaires (suite pytest)
- Smoke API en environnement cible
- Verification variables d'env critiques

### 12.3 Post-deploiement

- smoke e2e (`scripts/e2e_smoke.sh --compact`)
- verification des endpoints clefs
- verification UI et badges qualite

---

## 13. Observabilite et runbook

### 13.1 Logging structure

Evenement cle:

- `structured_dataset_built`

Attributs traces:

- type detecte/force, extracteur, confiance routeur
- couverture, flags qualite, statut ready/core/review
- compte des sources fallback

### 13.2 KPI techniques

- taux `ready_for_ai` / `ready_for_ai_core`
- top `quality_flags`
- latence p95 upload/extraction/export
- taux erreurs 4xx/5xx

### 13.3 Runbook incident (resume)

1. verifier `/health`
2. verifier login/token
3. verifier upload + `detail` erreur
4. verifier `dataset-summary` (flags/champs critiques)
5. tracer via logs structurés

---

## 14. Plan go-to-market (pilot)

### 14.1 Objectif pilot (2 a 4 semaines)

- valider la valeur sur cas reels
- mesurer gain de temps
- qualifier seuils strict/permissif

### 14.2 Livrables pilot

- script demo standardise
- template de feedback testeur
- tableau KPI hebdo

### 14.3 Criteres de succes

- adoption active utilisateurs pilotes
- pourcentage Core Ready eleve sur doc cibles
- baisse du temps de pre-traitement manuel

---

## 15. Roadmap recommandee

### Court terme (0-30 jours)

- instrumentation qualite complete
- tuning seuils par segment de clients
- stabilisation extracteurs bilan/2072

### Moyen terme (30-90 jours)

- enrichissement des champs secondaires
- workflows validation humaine avances
- dashboards ops business + technique

### Long terme (90+ jours)

- connecteurs SI (compta/ERP/BI)
- mode multi-entites avance
- gouvernance enterprise (SLA/reporting/audit renforces)

---

## 16. Annexes

### 16.1 Documents internes utiles

- `DOC_CONFIDOC_COMPLETE.md`
- `BETA_TEST_API.md`
- `DOCUMENTATION_COMPTABLE.md`

### 16.2 Presets de seuils

- preset strict comptable (production)
- preset permissif onboarding (pilot/demo)

---

## 17. Synthese finale

ConfiDoc dispose d'une base SaaS solide:

- valeur metier tangible,
- architecture exploitable en production,
- garde-fous qualite lisibles,
- voie claire vers un produit "exceptionnel" via instrumentation, tuning, et excellence UX metier.

