# Due Diligence Technique

## Ce qu'il faut comprendre vite

ConfiDoc transforme un document sensible en actif exploitable:

1. upload securise;
2. OCR;
3. detection d'entites;
4. anonymisation ou pseudonymisation;
5. scoring RGPD;
6. Trust Score / AI Readiness;
7. analyse IA optionnelle;
8. audit trail;
9. export controle.

Le produit cible les cabinets comptables, avocats, notaires et cabinets de conseil qui veulent exploiter des documents clients sans exposer les donnees brutes.

## Solide aujourd'hui

- FastAPI/PostgreSQL/Redis, stack claire et scalable.
- Multi-tenant applicatif avec Organization, Membership, Role.
- RBAC centralise et permissions documentaires fines.
- Audit trail RGPD-minimise avec hash d'evenement.
- Scoring RGPD 0-100 et AI Readiness visible.
- Tests de non-regression anonymisation B2B.
- Docker et Railway health/readiness/version.
- Production blocked si secrets defaut ou stockage local.
- Logs LLM durcis sans reponse brute.

## Risques techniques

- L'anonymisation LLM brute est desactivee par defaut (`LLM_RAW_ANONYMIZATION_ENABLED=false`); si activee, elle doit etre cadree contractuellement.
- Pas encore de Row Level Security PostgreSQL.
- L'AI Firewall couvre la PII residuelle en prompt/reponse et bloque les injections explicites; le volet adversarial complet doit continuer a s'enrichir avec des cas terrain.
- La gestion fine des invitations et changements de role doit etre industrialisee.
- Le stockage `database` est un compromis pilote, pas la cible scale.
- Observabilite cout OCR/LLM encore basique.

## Roadmap de renforcement

- RLS PostgreSQL par org.
- Invitations B2B avec expiration, audit et role.
- S3/R2 avec chiffrement serveur et lifecycle policies.
- Quotas par org et budget OCR/LLM.
- Worker pool separe OCR/NLP en production.
- Dashboard DPO: retention, exports, incidents, demandes de suppression.

## Metriques techniques a suivre

- temps upload -> preview anonymisee;
- taux OCR success;
- taux anonymisation success;
- nombre entites detectees par type;
- risk score moyen;
- AI Readiness moyen;
- taux validation humaine;
- exports bloques par risque;
- cout OCR/LLM par document et par org;
- erreurs par provider externe.

## Dependances externes

- Railway pour hosting.
- PostgreSQL.
- Redis.
- S3/R2/MinIO ou database fallback.
- Mistral OCR/LLM si active.
- OCR local selon image et packages systeme.

## Couts infra / IA

Variables de cout:

- taille et nombre de documents;
- pages scannees vs texte natif;
- OCR local vs fournisseur externe;
- appels LLM pour anonymisation ou analyse;
- retention fichiers et versions;
- nombre de workers Celery.

Pour un pilote, `DOCUMENT_PROCESSING_BACKEND=api` reduit la complexite. Pour scale, separer web et workers.

## Strategie scale

1. Stabiliser un monolithe FastAPI propre sur Railway.
2. Ajouter workers OCR/NLP dedies.
3. Passer stockage objet chiffre.
4. Ajouter quotas, budgets et priorites par org.
5. Ajouter RLS et audit exportable SOC2/ISO.
6. Construire integrations cabinet: GED, Drive, SharePoint, logiciels comptables.
