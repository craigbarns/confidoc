# ConfiDoc — Policy Engine (RGPD Premium)

Cette policy formalise le principe produit:

- extraction sur document brut en interne (moteur uniquement),
- exploitation IA uniquement sur sortie anonymisee/pseudonymisee.

## Regles enforcees

- **P1 — Internal Raw Access Only**
  - Le brut est reserve au moteur interne d'extraction.
  - Aucun export standard ne retourne le brut.

- **P2 — AI Uses Anonymized Data Only**
  - Le copilote et la recherche KB utilisent uniquement des donnees anonymisees.
  - Les donnees identifiantes (noms, adresses, identifiants) ne sont pas exposees aux flux IA.

- **P3 — Audit Without Raw Content**
  - L'export audit contient des hashes, compteurs, metadonnees et statuts.
  - Aucun texte brut n'est inclus.

- **P4 — LLM Safety**
  - Les traces LLM persistent uniquement des hashes de snippets et des metadonnees.
  - Pas de snippet brut dans les exports audit.

- **P5 — Controlled Exception**
  - Le seul acces au texte original passe par un endpoint dedie avec opt-in explicite:
    - `allow_original=true`
  - Cette route est reservee a un usage de revue interne.

## Champs de preuve (audit-export)

L'endpoint audit expose maintenant:

- `security_policy.*`
- `exposure_proof.*`

Ces champs permettent d'attester techniquement:

- que le brut n'est pas expose au copilote,
- que l'audit ne contient pas de donnees brutes,
- que le mode original exige un consentement explicite.

## Positionnement

ConfiDoc extrait les informations metier sur le document source, puis genere une version structuree anonymisee permettant aux equipes comptables d'utiliser l'IA sans exposer les donnees identifiantes.
