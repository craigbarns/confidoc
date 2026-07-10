# ConfiDoc — Pack de levee pre-seed

> **Positionnement investisseur** : *Secure AI Chat for confidential documents.*
> ConfiDoc transforme un document sensible en version anonymisee/pseudonymisee, permet
> d'en discuter avec une IA qui ne voit jamais le brut, puis produit une preuve d'audit.

Ce dossier est la data room de travail pour lever un pre-seed. Il doit servir a trois
choses : convaincre vite, lancer des pilotes, et donner aux investisseurs une lecture
coherente du produit, du marche et du plan d'execution.

## Narratif a tenir

**Avant** : ConfiDoc = anonymisation documentaire RGPD.

**Maintenant** : ConfiDoc = couche de confiance pour utiliser l'IA sur des documents
confidentiels.

Le wedge commercial reste les documents reglementes, car c'est la ou la douleur est
immediate. La vision levee est plus large : devenir le firewall de donnees sensibles
pour les agents IA et workflows IA d'entreprise.

## Index

| Doc | Objet | Etat |
|-----|-------|------|
| [01_DECK.md](01_DECK.md) | Deck pre-seed 12 slides, contenu investisseur | Pret a pitcher |
| [02_ONE_PAGER.md](02_ONE_PAGER.md) | Teaser une page a envoyer avant rendez-vous | Pret |
| [03_DEMO_SCRIPT_7MIN.md](03_DEMO_SCRIPT_7MIN.md) | Script demo : anonymiser, discuter, prouver | Pret |
| [04_PILOT_PLAN.md](04_PILOT_PLAN.md) | Plan 3-5 pilotes/LOI et messages d'approche | Pret |
| [05_RGPD_POSITIONING.md](05_RGPD_POSITIONING.md) | Discipline RGPD : pseudonymisation vs anonymisation | Reference |
| [06_SECURITY_ROADMAP.md](06_SECURITY_ROADMAP.md) | Securite : fait / reste / verite terrain | Reference |
| [07_METRICS.md](07_METRICS.md) | North Star + KPIs a instrumenter | Cadre |
| [08_RAISE_PLAN.md](08_RAISE_PLAN.md) | Montant, emploi des fonds, jalons | Pret |
| [09_EXECUTION_30_DAYS.md](09_EXECUTION_30_DAYS.md) | Plan d'execution avant lancement de levee | Nouveau |

## Message court

> Les entreprises veulent utiliser ChatGPT, Claude, Mistral ou leurs agents internes sur
> des documents clients. Elles ne peuvent pas envoyer les donnees brutes. ConfiDoc cree
> une version IA-safe, autorise la discussion sur cette version, bloque les fuites et
> genere une preuve d'audit.

## Checklist avant d'envoyer a des investisseurs

- [ ] Deck PPTX exporte et relu.
- [ ] One-pager personnalise avec contact fondateur.
- [ ] Demo live stable : `/firewall` + `/ui`.
- [ ] 20 prospects pilotes listes.
- [ ] 5 rendez-vous utilisateurs planifies.
- [ ] Montant de levee fixe : recommandation initiale `500 k€ pre-seed`.
- [ ] Trois chiffres reels mesures pendant les pilotes : documents traites, fuites
      detectees/bloquees, temps gagne.

## Acces produit

- Demo publique : `https://confidoc-production.up.railway.app/firewall`
- Console : `https://confidoc-production.up.railway.app/ui`
- Sante/transparence : `/health`, `/readiness`, `/version`

## Regle de prudence

Ne pas promettre une anonymisation absolue. Dire :

> ConfiDoc produit une version anonymisee quand le risque de reidentification est
> suffisamment bas, ou une version pseudonymisee avec mapping chiffre et score de risque.
> L'IA ne recoit que la version securisee.
