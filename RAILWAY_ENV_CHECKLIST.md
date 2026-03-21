# Checklist Railway - passer `/readiness` a `ready`

Cette checklist cible le probleme observe:
- `database = ok`
- `redis = localhost:6379` en erreur
- `storage/minio = localhost:9000` en erreur

Objectif: plus aucune variable `localhost` en production Railway.

## 1) Services Railway attendus

- Service `confidoc-backend` (API FastAPI)
- Service `postgres` (ou plugin PostgreSQL Railway)
- Service `redis` (ou plugin Redis Railway)
- Service S3-compatible:
  - soit un service MinIO dedie
  - soit un provider externe S3-compatible (R2, Scaleway Object Storage, etc.)

## 2) Variables backend obligatoires

Verifier dans le service `confidoc-backend`:

- `APP_ENV=production`
- `DEBUG=false`
- `DATABASE_URL=postgresql://...` (URL Railway Postgres, pas localhost)
- `REDIS_URL=redis://...` (URL Railway Redis, pas localhost)
- `CELERY_BROKER_URL=${REDIS_URL}`
- `CELERY_RESULT_BACKEND=redis://.../1` (meme host Redis, DB 1 recommande)

## 3) Variables storage (MinIO / S3) ou sans MinIO

Si vous retirez MinIO volontairement:
- `STORAGE_BACKEND=database` (recommande sur Railway) ou `local`
- dans ce mode, le check storage est marque `skipped` dans `/readiness`
- le statut global passe `ready` si database + redis sont `ok`

### Option A - MinIO dedie

- `STORAGE_BACKEND=minio`
- `MINIO_ENDPOINT=<host-minio>:<port>` (pas `localhost:9000`)
- `MINIO_ACCESS_KEY=<secret>`
- `MINIO_SECRET_KEY=<secret>`
- `MINIO_BUCKET=confidoc-documents`
- `MINIO_USE_SSL=true` (si endpoint TLS) sinon `false`

### Option B - S3-compatible externe

Utiliser des valeurs equivalentes S3-compatible:
- `STORAGE_BACKEND=minio`
- `MINIO_ENDPOINT=<endpoint-s3-compatible>`
- `MINIO_ACCESS_KEY=<access-key>`
- `MINIO_SECRET_KEY=<secret-key>`
- `MINIO_BUCKET=<bucket>`
- `MINIO_USE_SSL=true`

## 4) Secrets de securite a verifier

- `SECRET_KEY` non vide et fort
- `JWT_SECRET_KEY` non vide et fort
- `ENCRYPTION_MASTER_KEY` non vide et fort
- `ADMIN_RECOVERY_TOKEN` defini (si usage recovery prod)
- `OLLAMA_*` seulement si Ollama est reellement accessible depuis Railway

## 5) Points de controle anti-erreur (prioritaires)

- Aucune variable runtime ne contient `localhost` ou `127.0.0.1` pour Redis/MinIO.
- `DATABASE_URL` doit etre en format Railway et resolvable depuis `confidoc-backend`.
- `REDIS_URL` doit etre en format Railway et resolvable depuis `confidoc-backend`.
- Le bucket `MINIO_BUCKET` doit exister et etre accessible avec les credentials.
- `MINIO_USE_SSL` coherent avec le protocole reel de l'endpoint.

## 6) Validation post-correction

1) Redeployer le backend.
2) Verifier:

```bash
curl -sS "https://<votre-backend>.up.railway.app/health"
curl -sS "https://<votre-backend>.up.railway.app/readiness"
```

Resultat attendu:
- `/health` -> `{"status":"healthy", ...}`
- `/readiness` -> `{"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok"}}`

3) Test fonctionnel minimal:
- login
- upload document
- preview
- validate
- export structured dataset
- audit export

## 7) Diagnostic express si `/readiness` reste `degraded`

- `redis` en erreur:
  - verifier `REDIS_URL`
  - verifier que le service Redis est demarre
  - verifier DB index (`/0` pour app, `/1` pour result backend)
- `storage` en erreur:
  - verifier `MINIO_ENDPOINT` / SSL
  - verifier credentials
  - verifier existence du bucket
  - verifier connectivite reseau entre backend et endpoint storage
