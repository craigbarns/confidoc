# ConfiDoc — Roadmap sécurité (fait / reste / désactivé en prod)

> Pour la due diligence : **transparence totale**. Ce qui est réel, ce qui est prévu, ce
> qui est volontairement désactivé. (État au dernier déploiement `main`.)

## ✅ Fait (en production)

**Gouvernance IA / anti-fuite**
- **Privacy Gate** déterministe (LangGraph), **fail-closed** : autorise / exige validation
  humaine / bloque selon le risque ; aucune action IA/export si indisponible.
- **AI Firewall** sur **tous** les chemins LLM : inspection du prompt **sortant** et de la
  réponse **entrante** (synthèse, streaming bufferisé, extraction, revue, copilot) — redaction
  en mode normal, blocage en mode sensible / risque critique.
- **Mode client sensible** : **aucun appel IA externe** (souveraineté totale).
- **Pseudonymisation** (regex + NER + LLM assist) + **score de risque de réidentification**.

**Traçabilité & conformité**
- **Journal d'audit cryptographique** : horodatage + empreinte **SHA-256** par événement
  (preuve d'intégrité opposable).
- **Rétention** RGPD automatique (purge planifiée), durées configurables.

**Plateforme / hygiène**
- **RBAC** multi-tenant (rôles owner/admin/member/viewer), isolation par organisation.
- **RLS PostgreSQL** sur les tables documentaires/métier tenantées, avec test CI réel
  2-orgs (fail-closed sans contexte, org A ≠ org B, bypass système contrôlé).
- **Headers de sécurité** + **CSP** (script nonce), **rate limiting**, logs structurés.
- `ProxyHeadersMiddleware` **verrouillable** (`TRUSTED_PROXY_HOSTS`).
- **Stratégie DB explicite** : Alembic = source de vérité (entrypoint), auto-init opt-out (`DB_AUTO_INIT`).
- **CI** : tests (≈764, dont RLS sur vrai PostgreSQL) + scan image (Trivy) +
  **format Ruff enforcé** ; `/health` `/readiness` `/version`.
- Secrets via variables d'environnement ; blocage des valeurs par défaut en production.

## 🔜 Reste à faire (priorisé pour les pilotes/levée)

1. **DPA type + liste des sous-traitants + hébergement UE documenté** (rapide, requis pilote).
2. **Pen test** externe + correction (avant déploiement clients réels).
3. **SSO / SAML** (exigence cabinets/entreprises).
4. **Chemin ISO 27001** (politique sécurité, gestion des accès, journal des incidents) —
   argument d'achat enterprise ; viser une **attestation** à ‹12–18 mois›.
5. **Sauvegardes / PRA documentés** (RPO/RTO).
6. **Nettoyage dette qualité** (lint `ruff check` F401 progressif ; mypy — chantier dédié, non bloquant).
7. ‹Selon verticale : HDS si santé, SecNumCloud si secteur public — non prévu au wedge›.

## ⏸️ Désactivé / configurable en prod (par design)
- **IA externe désactivée** en `SENSITIVE_CLIENT_MODE` (souveraineté).
- **Mistral off par défaut** tant que clé non fournie (pas d'appel externe implicite).
- **`DB_AUTO_INIT=True`** par défaut (confort démo/mono-service) → à passer **False** en
  prod stricte gérée par migrations.
- **Lint `ruff check`** informatif (non bloquant) le temps du nettoyage progressif ;
  **format** déjà enforcé.

## Posture pour la due diligence
- Architecture **RGPD-by-design**, pas rajoutée après coup.
- Aucune sur-promesse : voir [05_RGPD_POSITIONING.md](05_RGPD_POSITIONING.md).
- Les éléments « reste à faire » sont **normaux à ce stade** (pre-seed) et **chiffrés**
  dans l'emploi des fonds — c'est un signe de maîtrise, pas une faiblesse.
