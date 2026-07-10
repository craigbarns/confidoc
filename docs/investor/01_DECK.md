# ConfiDoc — Deck investisseur pre-seed

> 12 slides. Les champs `‹...›` doivent etre completes par le fondateur avec des donnees
> reelles. Ne pas inventer de traction. Garder la discipline RGPD de
> [05_RGPD_POSITIONING.md](05_RGPD_POSITIONING.md).

---

## Slide 1 — Titre

**ConfiDoc**  
*Secure AI Chat for confidential documents.*

Sous-titre : *Anonymisez un document sensible, discutez avec l'IA sur la version
securisee, prouvez ce qui a ete expose.*

`‹Gregory Baranes · contact · Pre-seed · date›`

---

## Slide 2 — Probleme

Les entreprises veulent utiliser l'IA sur leurs documents les plus utiles : bilans,
liasses, contrats, dossiers clients, pieces juridiques, paie.

Elles ne le font pas correctement, car envoyer le brut a une IA cree trois risques :

- fuite de donnees personnelles ou financieres ;
- violation RGPD / secret professionnel / clauses de confidentialite ;
- aucune preuve de ce que l'IA a vu ou produit.

Resultat : les documents a plus forte valeur restent hors IA.

---

## Slide 3 — Pourquoi maintenant

- Les equipes adoptent deja ChatGPT, Claude, Mistral, Copilot et des agents IA.
- Les directions DPO/RSSI demandent de la tracabilite avant d'autoriser ces usages.
- OWASP a publie un Top 10 dedie aux applications agentiques 2026.
- MCP/A2A accelerent l'acces des agents aux outils et donnees internes.
- Les entreprises ont besoin d'une couche de controle entre donnees sensibles et IA.

Timing : le marche passe de "tester l'IA" a "industrialiser l'IA sans fuite".

---

## Slide 4 — Solution

**ConfiDoc cree une zone IA-safe pour les documents confidentiels.**

1. Upload du document sensible.
2. Detection des donnees personnelles, financieres et metier.
3. Version anonymisee/pseudonymisee avec score de risque.
4. Chat IA uniquement sur la version securisee.
5. Re-inspection des prompts et reponses.
6. Rapport d'audit : ce que l'IA a vu, ce qui a ete masque, ce qui a ete bloque.

Promesse produit :

> L'IA devient utile sur les documents confidentiels sans recevoir le document brut.

---

## Slide 5 — Produit

Trois modules simples a vendre :

**Anonymize**  
Detection, masquage, pseudonymisation, score de reidentification.

**Ask**  
Chat IA citation-based sur la version securisee du document.

**Prove**  
Audit trail, preuve d'exposition IA, rapport DPO/RSSI exportable.

La suite logique : **Agent Firewall** pour controler les agents IA qui accederont aux
documents, outils et bases internes.

---

## Slide 6 — Demo

Scenario investisseur en 7 minutes :

1. Upload d'un bilan ou contrat avec noms, email, IBAN, SIRET, montants.
2. ConfiDoc produit une version IA-safe.
3. L'utilisateur demande : "Resume ce document et liste les risques."
4. L'IA repond avec citations, sans avoir vu les identifiants.
5. ConfiDoc montre les donnees masquees et les blocages.
6. Export du rapport d'audit.

Message a faire passer :

> Ce n'est pas un chatbot documentaire. C'est un chatbot documentaire sous controle
> privacy, securite et audit.

---

## Slide 7 — Produit deja construit

ConfiDoc n'est pas une idee :

- backend FastAPI / PostgreSQL / Redis / Celery ;
- pipeline d'upload, OCR/extraction, anonymisation, scoring ;
- journal d'audit et empreintes d'integrite ;
- dashboard DPO/RSSI et demo publique ;
- modes IA externe et client sensible ;
- multi-tenant, RBAC/RLS, readiness/health/version.

Ce qui reste a faire pour lever : packaging commercial, pilotes, mesure de valeur.

---

## Slide 8 — Marche

Wedge initial : professions et equipes qui manipulent des documents confidentiels et
veulent debloquer l'IA :

- cabinets comptables et DAF externalises ;
- avocats fiscalistes / affaires ;
- assurances, fintech, compliance ;
- equipes internes DPO/RSSI qui cadrent les usages IA.

Expansion :

> De Secure AI Chat for documents vers Agent Security Gateway pour workflows IA
> d'entreprise.

`‹TAM/SAM/SOM a chiffrer avec sources : cabinets, avocats, entreprises reglementees EU›`

---

## Slide 9 — Business model

Modele pre-seed recommande :

- pilote payant : `2-5 k€` setup + `500-2 000 €/mois` selon volume ;
- SaaS equipe : par siege + volume de documents ;
- tier gouvernance : audit, DPA, logs longs, SSO, mode client sensible ;
- enterprise : gateway agents/outils, politiques avancees, deploiement dedie.

Objectif court terme :

> 3 a 5 pilotes payants avant ou pendant la levee pour transformer le risque marche en
> traction visible.

---

## Slide 10 — Defense

ConfiDoc peut etre defensible si l'execution reste focalisee :

- donnees annotees et golden sets sur documents sensibles ;
- moteur privacy-by-design difficile a rajouter apres coup ;
- audit trail comme preuve commerciale et compliance ;
- boucle de corrections humaines pour ameliorer la detection ;
- wedge reglemente avant l'expansion horizontale agentique.

Ne pas se battre frontalement contre Okta/Microsoft. Prendre le wedge :

> documents sensibles + IA + audit.

---

## Slide 11 — Traction a obtenir maintenant

Ce slide doit etre rempli par du reel.

Avant levee :

- `3-5` pilotes/LOI ;
- `20-30` entretiens DPO/RSSI/cabinets ;
- `1` demo publique stable ;
- `1` cas client documente ;
- metriques : temps gagne, taux de detection, fuites bloquees, intention de payer.

Template a remplacer :

`‹pilotes, pipeline, verbatims, usage, LOI, revenus›`

---

## Slide 12 — Levee

**Demande recommandee : `500 k€ pre-seed` pour `18 mois`.**

Objectifs du tour :

- signer les premiers pilotes payants ;
- recruter un profil GTM et un dev produit ;
- durcir securite/compliance enterprise ;
- transformer la demo en produit self-serve vendable ;
- ouvrir le chantier Agent Firewall/MCP Gateway apres preuve du wedge.

Emploi indicatif :

- 35 % GTM et ventes pilotes ;
- 30 % produit/engineering ;
- 15 % securite, legal, DPA, pentest ;
- 20 % runway fondateur et operations.

Fin de tour = produit en production + pilotes payants + pipeline seed.

---

## Annexes recommandees

- Architecture et flux de donnees.
- Discipline RGPD : anonymisation/pseudonymisation.
- Security roadmap.
- Demo script.
- Plan pilotes et LOI.
