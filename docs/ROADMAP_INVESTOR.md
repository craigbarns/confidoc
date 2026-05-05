# Roadmap Investisseur

## 7 jours

- Verifier le deploiement Railway production avec `/health`, `/readiness`, `/version`.
- Configurer secrets Railway et interdire toute valeur `CHANGE-ME`.
- Valider une demo end-to-end avec document synthetique.
- Activer S3/R2/MinIO ou `database` pour pilote.
- Ajouter smoke tests post-deploy.
- Documenter le mode IA sensible: Mistral off par defaut.

## 30 jours

- Invitations organisation avec roles owner/admin/member/viewer.
- UI admin organisation et membres.
- Quotas upload/OCR/LLM par org.
- Dashboard DPO: audit trail, exports, retention, scores.
- Export rapport audit pack client.
- Tests API multi-tenant sur toutes routes sensibles.
- Observabilite cout OCR/LLM par document.

## 90 jours

- RLS PostgreSQL par organisation.
- Stockage objet chiffre, lifecycle policies, suppression prouvee.
- Worker pool OCR/NLP autoscale.
- Connecteurs GED/Drive/SharePoint.
- Mode client sensible avec OCR local et LLM desactive.
- DPA fournisseurs et registre sous-traitants.
- Pack securite pour RSSI: controles, evidences, runbooks.

## 12 mois

- Certification ou trajectoire ISO 27001 / SOC2 Type I.
- Marketplace connecteurs metiers.
- Modeles extraction par vertical: expert-comptable, avocat, notaire, conseil.
- Evaluation continue qualite anonymisation.
- Gouvernance donnees avancee: retention par policy, legal hold, DSAR.
- Scale multi-region si demande enterprise.

## MVP vs pilotes vs scale

MVP:

- upload;
- OCR;
- anonymisation;
- score;
- audit;
- export anonymise.

Clients pilotes:

- orgs;
- roles;
- audit lisible;
- stockage non local;
- docs securite;
- support Railway stable.

Scale:

- RLS;
- workers dedies;
- quotas;
- observabilite cout;
- lifecycle storage;
- integrations SI client.
