# Security

## Authentification

ConfiDoc supporte:

- JWT Bearer pour l'interface.
- API keys ConfiDoc pour integrations B2B.
- Bootstrap admin controle par `BOOTSTRAP_SECRET`.

En production:

- secrets fournis par Railway Variables.
- expiration access token courte.
- refresh token separe.
- `JWT_ALGORITHM` explicite.
- aucun secret dans le repository.

## Autorisations

Le controle d'acces combine:

- utilisateur actif;
- organisation active;
- membership actif;
- role;
- permission fine par action documentaire.

Permissions critiques:

- `documents.read`
- `documents.raw`
- `documents.upload`
- `documents.process`
- `documents.validate`
- `documents.metadata`
- `documents.delete`
- `exports.download`
- `exports.create`
- `audit.read`
- `members.manage`
- `org.manage`

Les documents avec `org_id` exigent une membership active. Les documents legacy sans `org_id` restent owner-only.

## Stockage fichiers

Production:

- `STORAGE_BACKEND=local` interdit.
- utiliser S3/R2/MinIO ou `database` pour pilote controle.
- hash SHA-256 calcule a l'upload.
- suppression physique a verifier par backend.

## Encryption

Variables obligatoires:

- `ENCRYPTION_MASTER_KEY`
- `PSEUDO_MAPPING_KEY`
- `SECRET_KEY`
- `JWT_SECRET_KEY`

Les mappings reversibles de pseudonymisation doivent rester separes des exports.

## Audit trail

L'audit trail est RGPD-minimise:

- pas de texte document;
- pas de snippet;
- pas de mapping;
- pas de token;
- pas de secret;
- hash stable `event_hash`;
- `request_id` present via middleware pour les requetes HTTP.

L'endpoint visuel `/api/v1/compliance/audit-logs` est scope a l'organisation courante et exige `audit.read`.

## Logging

Les logs doivent rester operationnels:

- ids techniques;
- taille;
- status;
- duree;
- erreurs techniques.

Ils ne doivent pas contenir:

- document original;
- texte OCR;
- extrait anonymise long;
- reponse brute LLM;
- valeurs originales detectees;
- secrets.

Les erreurs LLM exposent uniquement hash et longueur de reponse.

## Gestion des secrets Railway

Utiliser Railway Variables pour:

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `ENCRYPTION_MASTER_KEY`
- `PSEUDO_MAPPING_KEY`
- `MISTRAL_API_KEY`
- `BOOTSTRAP_SECRET`
- `CONFIDOC_SEED_ADMIN_PASSWORD`

Ne pas committer `.env`.

## Rate limiting

Rate limiting configure:

- login;
- upload;
- default API.

A renforcer avant scale:

- quotas par organisation;
- quotas par API key;
- limites par taille et type document;
- circuit breaker OCR/LLM.

## Erreurs frontend

Les endpoints d'export renvoient des messages generiques en cas d'erreur serveur. Les logs conservent le diagnostic technique sans contenu documentaire.

## Limites actuelles

- RLS PostgreSQL est active sur les donnees metier et documentaires tenantées
  (`documents`, versions, detections, mappings, clients/dossiers, integrations,
  audit logs, golden drafts). Les tables de decouverte auth (`users`,
  `memberships`, `roles`, `organizations`) restent hors de cette premiere couche
  pour permettre la resolution de l'organisation courante avant pose du contexte
  DB transactionnel.
- Les permissions sont centralisees en code; une UI de gestion fine reste a construire.
- Les integrations IA externes doivent etre contractualisees client par client.
- La rotation de cles et les backups chiffrés doivent etre formalises pour clients pilotes.
