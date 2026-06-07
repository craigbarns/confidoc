# ConfiDoc — Pack investisseur & data room

> **Positionnement** : *Le firewall de confidentialité IA pour les cabinets réglementés
> qui veulent utiliser l'IA sans exposer les dossiers de leurs clients.*

Ce dossier est la **data room** versionnée de ConfiDoc. Il consolide et remplace les
documents épars (`DEMO_PITCH.md`, `docs/DEMO_SCRIPT.md`, `docs/ROADMAP_INVESTOR.md`,
`docs/DUE_DILIGENCE.md`). Tout est tenu à jour avec l'état réel du produit.

## Index

| Doc | Objet | État |
|-----|-------|------|
| [01_DECK.md](01_DECK.md) | Deck 11 slides (contenu prêt à mettre en forme) | ✅ produit · ‹chiffres/équipe à compléter› |
| [02_ONE_PAGER.md](02_ONE_PAGER.md) | One-pager (teaser 1 page) | ✅ |
| [03_DEMO_SCRIPT_7MIN.md](03_DEMO_SCRIPT_7MIN.md) | Script de démo 7 min (parcours réel) | ✅ |
| [04_PILOT_PLAN.md](04_PILOT_PLAN.md) | ICP, plan d'acquisition pilotes, modèle de LOI | ✅ |
| [05_RGPD_POSITIONING.md](05_RGPD_POSITIONING.md) | Pseudonymisation vs anonymisation (prudence CNIL) | ✅ |
| [06_SECURITY_ROADMAP.md](06_SECURITY_ROADMAP.md) | Sécurité : fait / reste / désactivé en prod | ✅ (vérité terrain) |
| [07_METRICS.md](07_METRICS.md) | North Star + KPIs à instrumenter | ✅ cadre · ‹valeurs à mesurer› |
| [08_RAISE_PLAN.md](08_RAISE_PLAN.md) | Trajectoire 5 ans, emploi des fonds, jalons | ✅ cadre · ‹montants à fixer› |

## Checklist data room (à compléter par le fondateur)

- [ ] **Société** : Kbis, statuts, cap table, pacte d'associés.
- [ ] **Équipe** : CV fondateur(s), rôles, advisors.
- [ ] **Produit** : ce pack + accès démo live + accès code (lecture).
- [ ] **Sécurité/RGPD** : [06_SECURITY_ROADMAP.md](06_SECURITY_ROADMAP.md), [05_RGPD_POSITIONING.md](05_RGPD_POSITIONING.md), registre des traitements, DPA type, liste sous-traitants, hébergement (UE/souverain).
- [ ] **Traction** : pilotes/LOI signées, pipeline, verbatims clients.
- [ ] **Finances** : P&L prévisionnel, plan de trésorerie, hypothèses, emploi des fonds.
- [ ] **Légal/IP** : marque ConfiDoc, CGU/CGV, mentions, propriété du code.

## Accès produit (démo)

- **Démo publique sans login** : `https://confidoc-production.up.railway.app/firewall`
  (bouton « Lancer la démonstration » → interception en direct).
- **Console** : `https://confidoc-production.up.railway.app/ui`.
- **Santé/transparence** : `/health`, `/readiness`, `/version`.

> ⚠️ **Règle de prudence (transversale)** : on parle de **pseudonymisation + maîtrise du
> risque de réidentification**, jamais d'« anonymisation garantie ». Voir
> [05_RGPD_POSITIONING.md](05_RGPD_POSITIONING.md).
