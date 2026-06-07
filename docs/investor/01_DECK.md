# ConfiDoc — Deck investisseur (contenu)

> 11 slides. Contenu prêt ; mettre en forme (Pitch/Figma/Slides). Les `‹…›` sont à
> compléter par le fondateur (ne rien inventer : traction, équipe, chiffres réels).
> Garder le wording RGPD prudent (cf. [05_RGPD_POSITIONING.md](05_RGPD_POSITIONING.md)).

---

## Slide 1 — Titre / positionnement
**ConfiDoc** — *Le firewall de confidentialité IA pour les cabinets réglementés.*
Sous-titre : *Utilisez l'IA sur vos dossiers clients sans jamais exposer une donnée
confidentielle.*
‹Logo · nom fondateur · contact · date · « Seed / Pre-seed »›

---

## Slide 2 — Le problème (urgent)
Les **experts-comptables, DAF externalisés, avocats fiscalistes, notaires** veulent
utiliser l'IA générative pour gagner des heures sur les bilans, liasses, contrats.
**Ils ne le font pas** — parce qu'envoyer un dossier client dans une IA publique, c'est :
- une violation du **RGPD** et du **secret professionnel**,
- un risque de **fuite** de données financières/personnelles,
- aucune **traçabilité** opposable en cas de contrôle.

Résultat : l'IA reste **bloquée à la porte** des cabinets. Le gain de productivité IA
(20–40 % sur certaines tâches) est inaccessible à ceux qui manipulent le plus de
données sensibles.

---

## Slide 3 — Pourquoi maintenant
- **Adoption IA massive** côté pros, mais **interdiction de fait** sur données clients.
- **AI Act** (entrée en application progressive) + **RGPD** + **souveraineté EU** :
  la conformité devient un prérequis d'achat, pas une option.
- **La CNIL** insiste sur la distinction pseudonymisation/anonymisation et le **risque
  de réidentification dans le temps** → besoin d'**outils de gouvernance**, pas de
  promesses magiques.
- Les agents IA arrivent en entreprise → besoin d'une **couche de contrôle** entre
  les données sensibles et les modèles.

---

## Slide 4 — La solution
**ConfiDoc = un firewall de confidentialité entre vos documents et l'IA.**
Avant, pendant et après chaque échange IA :
1. **Pseudonymisation** des données identifiantes (mapping réversible chiffré).
2. **Privacy Gate** déterministe : autorise / exige une validation humaine / bloque,
   selon le risque (fail-closed).
3. **AI Firewall** : inspection du **prompt sortant** et de la **réponse entrante** —
   redaction ou blocage de toute donnée identifiante résiduelle, sur **tous** les flux IA.
4. **Score RGPD / risque de réidentification** + **journal d'audit cryptographique**
   (preuve d'intégrité SHA-256) opposable.

*« Tous les échanges IA sont inspectés en temps réel. »*

---

## Slide 5 — Comment ça marche (le parcours = la démo)
`Upload → Pseudonymisation → Privacy Gate → AI Firewall (prompt) → Modèle IA →
AI Firewall (réponse) → Score DPO → Export + preuve d'audit`

- En **mode client sensible**, aucun appel IA externe (souveraineté totale).
- En mode normal, l'IA externe ne reçoit **que** du texte pseudonymisé et firewallé.
- Tableau de bord temps réel (**AI Security Control Tower**) : prompts/réponses
  inspectés, redactions, blocages, risques critiques.

→ Voir [03_DEMO_SCRIPT_7MIN.md](03_DEMO_SCRIPT_7MIN.md) (démo live, sans login).

---

## Slide 6 — Produit (déjà en ligne)
- Backend **FastAPI / PostgreSQL / Redis / Celery / MinIO**, déployé (Railway), prod saine.
- **AI Firewall** appliqué sur tous les chemins IA (synthèse, streaming, extraction,
  revue, copilot).
- **Pipeline de pseudonymisation** (regex + NER + LLM assist) + **golden sets** et
  **benchmarks OCR** internes (qualité mesurée).
- **Dashboard DPO/RSSI** + **démo publique** + **journal d'audit cryptographique**.
- **Multi-tenant / RBAC + RLS PostgreSQL**, logs structurés, `/health` `/readiness` `/version`.

*Ce n'est pas un slideware : la démo tourne en production aujourd'hui.*

---

## Slide 7 — Marché & cible (wedge → expansion)
**Wedge (France)** : cabinets d'expertise comptable, DAF externalisés, avocats
fiscalistes, notaires — professions à **secret professionnel** + fort volume documentaire.
- ‹France : ~XX 000 cabinets comptables, ~XX 000 avocats — sourcer chiffres CNOEC/CNB›
- **Expansion** : toute entreprise EU manipulant des documents confidentiels qui veut
  déployer l'IA/les agents → **« AI firewall » horizontal** (TAM bien plus large).

Bottom-up : ‹nb cabinets cibles × ARPA cible = SAM›. ‹TAM/SAM/SOM à chiffrer›.

---

## Slide 8 — Business model
- **SaaS par siège** + **tier gouvernance DPO/RSSI** (audit, exports, quotas).
- Option **par volume de documents** pour les gros cabinets.
- ‹Pricing indicatif : € /siège/mois — à valider en pilote›.
- Coûts variables maîtrisés (OCR/LLM mesurés par document ; mode souverain = 0 coût IA externe).

---

## Slide 9 — Défendabilité (moat)
- **RGPD-by-design** : Privacy Gate fail-closed + firewall + preuve d'audit — difficile
  à rajouter après coup chez un concurrent « IA d'abord ».
- **Qualité mesurée** : golden sets + benchmarks OCR/pseudonymisation = barrière data.
- **Boucle d'apprentissage** : chaque correction humaine améliore le moteur (flywheel).
- **Preuve opposable** : journal d'audit cryptographique (SHA-256) — argument fort en
  contrôle CNIL / litige / due diligence client.
- **Confiance** : positionnement « gouvernance », pas « encore une IA ».

---

## Slide 10 — Traction & pilotes
‹À COMPLÉTER — ne rien inventer. Cibler 3–5 pilotes/LOI :›
- ‹Logos / nb pilotes signés / LOI›
- ‹Verbatims clients›
- ‹Métriques d'usage : documents traités, fuites interceptées, temps gagné› (cf. [07_METRICS.md](07_METRICS.md))
- ‹Pipeline : nb cabinets en discussion›

---

## Slide 11 — Équipe & demande
- **Fondateur solo** : ‹Gregory — rôle, parcours›. **Preuve d'exécution** : a conçu,
  construit et **mis en production seul** une plateforme complète (firewall IA,
  pseudonymisation, dashboard DPO, audit cryptographique, démo publique) — capacité à
  livrer démontrée, pas une promesse.
- **De-risking du solo** (à dire franchement) : produit déjà live → le risque n'est pas
  « est-ce faisable » mais « accélérer GTM ». La levée finance les **premiers
  recrutements** (cf. ci-dessous) et l'**onboarding d'advisors** (‹DPO/expert-comptable,
  sécurité/RSSI›) déjà identifiés.
- **Demande** : ‹montant› € en ‹pre-seed› pour ‹18–24 mois›.
- **Emploi des fonds** : ‹1er commercial/GTM cabinets · 1 dev · conformité (ISO 27001) ·
  pilotes›.
- **Trajectoire 5 ans** : wedge cabinets FR → plateforme firewall IA EU (cf.
  [08_RAISE_PLAN.md](08_RAISE_PLAN.md)). *Bpifrance : montrer la trajectoire, pas que le tour.*

---

### Annexes (slides de réserve)
- Schéma d'architecture & flux de données (UE/souverain).
- Position RGPD détaillée (pseudonymisation, réidentification — CNIL).
- Roadmap sécurité (fait/reste/désactivé).
- Benchmarks OCR / qualité pseudonymisation.
