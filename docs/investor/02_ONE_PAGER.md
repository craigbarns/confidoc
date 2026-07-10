# ConfiDoc — One-pager pre-seed

**Secure AI Chat for confidential documents.**  
*Anonymisez vos documents sensibles, discutez avec l'IA sur la version securisee, prouvez
ce qui a ete expose.*

## Probleme

Les entreprises veulent utiliser l'IA sur leurs bilans, contrats, liasses, dossiers
clients et documents juridiques. Mais envoyer le document brut a un modele externe cree
un risque de fuite, de non-conformite RGPD, de violation du secret professionnel et
d'absence de preuve.

Les documents les plus utiles restent donc les moins exploitables par IA.

## Solution

ConfiDoc s'intercale entre le document et l'IA :

- detection des donnees sensibles ;
- version anonymisee/pseudonymisee avec score de risque ;
- chat IA uniquement sur cette version securisee ;
- inspection des prompts et reponses ;
- blocage des fuites residuelles ;
- rapport d'audit exportable pour DPO/RSSI/client.

## Produit

**Anonymize** : detection, masquage, pseudonymisation, risk score.  
**Ask** : chat IA avec citations sur document securise.  
**Prove** : audit trail, preuve d'exposition IA, rapport de conformite.

## Pourquoi maintenant

Les entreprises passent de l'experimentation IA a l'industrialisation. Les agents IA vont
acceder aux documents et outils internes. Les DPO/RSSI exigent des controles avant
d'autoriser ces usages. OWASP, NIST et l'ecosysteme MCP confirment que la securite des
agents et workflows IA devient une categorie a part entiere.

## Wedge marche

Premier marche : cabinets comptables, DAF externalises, avocats, assurance/fintech,
equipes compliance. Expansion : gateway de securite pour agents IA sur donnees sensibles.

## Statut

Produit deja construit : upload, OCR/extraction, anonymisation, scoring, audit,
dashboard DPO/RSSI, demo publique, backend FastAPI/PostgreSQL/Redis, modes IA externe et
client sensible.

## Business model

Pilotes payants (`2-5 k€` setup + `500-2 000 €/mois`), puis SaaS par siege + volume
documentaire + tier gouvernance enterprise.

## Levee

Recommandation : `500 k€ pre-seed` pour 18 mois. Objectif : 3-5 pilotes payants,
premiere recrue GTM, un dev produit, durcissement securite/compliance, passage de demo a
produit vendable.

## Contact

`‹Gregory Baranes · email · telephone · LinkedIn · demo›`

> Discipline RGPD : dire "version anonymisee/pseudonymisee selon le risque", pas
> "anonymisation garantie".
