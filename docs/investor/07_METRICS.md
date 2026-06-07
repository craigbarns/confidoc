# ConfiDoc — Métriques (North Star + KPIs)

> Objectif : transformer l'usage en **histoire de valeur** chiffrée. Le produit expose
> déjà des compteurs firewall (`/api/v1/firewall/stats`) — base à étendre.

## North Star
**Documents sensibles traités sous firewall / mois** (= valeur protégée délivrée).
Proxy direct de l'usage réel et du risque évité.

## KPIs valeur / produit (à instrumenter & afficher)
- **Fuites interceptées** (redactions + blocages) — argument sécurité chiffré.
- **% d'échanges IA inspectés** (doit être 100 % — preuve de la promesse).
- **Temps gagné / document** (à mesurer en pilote — ex. min économisées vs traitement manuel).
- **Risques critiques neutralisés** (IBAN/NSS bloqués).
- **Coût IA/OCR par document** (déjà visé dans la roadmap — marge unitaire).

## KPIs business (à suivre dès les pilotes)
- **Pilotes signés → LOI → contrats payants** (taux de conversion).
- **MRR / ARR**, **ARPA** (par cabinet), **nb sièges actifs**.
- **Activation** : % de cabinets ayant traité ≥ ‹N› documents en semaine 1.
- **Rétention / usage hebdo** (cabinets actifs).
- **CAC** (surtout en solo : coût/temps par pilote) et **payback**.

## Tableau de bord (gabarit à remplir au fil de l'eau)
| Métrique | Aujourd'hui | Cible 3 mois | Cible 12 mois |
|---|---|---|---|
| Documents/mois sous firewall | ‹…› | ‹…› | ‹…› |
| Pilotes / LOI / payants | ‹0/0/0› | ‹3/2/1› | ‹…› |
| MRR | ‹…› | ‹…› | ‹…› |
| % échanges IA inspectés | 100 % | 100 % | 100 % |
| Fuites interceptées (cum.) | ‹…› | ‹…› | ‹…› |

> ⚠️ Ne montrer que des chiffres **réellement mesurés**. La démo publique fournit déjà des
> compteurs live ; pour les pilotes, instrumenter « temps gagné » et « documents traités »
> dès le premier onboarding.
