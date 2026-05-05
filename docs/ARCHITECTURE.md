# Architecture

## Vue logique

ConfiDoc est une plateforme B2B de traitement documentaire sensible:

```
Utilisateur B2B
  -> FastAPI
  -> PostgreSQL
  -> Stockage objet ou database fallback
  -> Workers API/Celery
  -> OCR
  -> Anonymisation
  -> Scoring RGPD + AI Readiness
  -> Analyse IA optionnelle sur texte anonymise
  -> Audit trail
  -> Exports
```

## Backend

- FastAPI expose les routes `/api/v1`.
- Les dependances d'authentification placent `user`, `org_id`, `membership` et `auth_type` dans `request.state`.
- Les routes documentaires sont separees en CRUD, processing, dossier et export.
- Les endpoints Railway exposes au niveau racine sont `/health`, `/readiness` et `/version`.

## Base de donnees

PostgreSQL porte:

- `users`
- `organizations`
- `memberships`
- `roles`
- `documents`
- `document_versions`
- `entity_detections`
- `pseudonym_mappings`
- `audit_logs`
- tables d'integration, qualite et golden drafts

Le multi-tenant est centre sur `org_id`. Les documents B2B doivent etre rattaches a une organisation et les acces passent par membership actif + role.

## Roles B2B

Modele cible:

- `owner`: controle total organisation, membres, policies, documents et exports.
- `admin`: administration operationnelle, membres, policies, documents, exports, audit.
- `member`: upload, process, validation, metadata, exports et audit operationnel.
- `viewer`: lecture document anonymise et exports autorises, sans suppression ni administration.

Compatibilite:

- `operator` est normalise en `member`.
- `auditor` est normalise en `viewer`.

## Workers

`DOCUMENT_PROCESSING_BACKEND=api` convient a une demo Railway simple service. `celery` doit etre active lorsque des workers dedies OCR/NLP sont deployes avec Redis.

Railway:

- service web: `railway.json`, Dockerfile racine.
- worker: `railway.worker.json`, Dockerfile worker.
- `/health` reste la sonde liveness rapide.
- `/readiness` verifie PostgreSQL, Redis, stockage et donne un signal worker informatif.

## Stockage

Backends:

- `minio`: compatible S3, recommande pour production ou client pilote.
- `database`: acceptable pour pilote controle, facilite Railway sans volume persistant.
- `local`: uniquement dev, bloque en production.

Chaque document conserve `storage_backend`, `storage_key`, `sha256`, taille et type.

## Pipeline documentaire

1. Upload authentifie et limite.
2. Scan sandbox et hash SHA-256.
3. Audit `document:uploaded`.
4. OCR vers `ORIGINAL_TEXT`.
5. Anonymisation vers `PREVIEW_ANONYMIZED`.
6. Scoring RGPD et Trust Score / AI Readiness.
7. Validation humaine vers `FINAL_ANONYMIZED`.
8. Analyse IA optionnelle sur texte anonymise.
9. Export et audit.

## Audit trail

L'audit trail centralise utilise:

- `user_id`
- `org_id`
- `actor_type`
- `action`
- `resource_type`
- `resource_id`
- `request_id`
- `event_hash`
- `details` sanitisees

Les metadata sensibles sont hashees ou redigees. L'audit visualise une organisation, pas les donnees d'une autre organisation.

## Scoring

Le scoring combine:

- risque de reidentification
- validation humaine
- nombre d'entites
- presence de texte anonymise
- audit events
- status pipeline

Deux scores sont visibles:

- Trust Score: confiance globale dans le traitement.
- AI Readiness Score: capacite a utiliser le document dans un flux IA.

## Deploiement

Railway attend:

- `APP_ENV=production`
- secrets non defaut
- `DATABASE_URL`
- `REDIS_URL`
- `STORAGE_BACKEND=minio` ou `database`
- `ALLOWED_ORIGINS` restreint
- migrations Alembic lancees avant trafic client

Le service refuse de demarrer en production avec secrets `CHANGE-ME` ou stockage local.
