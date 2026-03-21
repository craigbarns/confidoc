# ConfiDoc — Documentation de présentation (Cabinet comptable)

## 1) Objectif de ConfiDoc

ConfiDoc est une solution SaaS qui permet de transformer des documents comptables contenant des données sensibles en versions anonymisées, exploitables en interne ou pour des usages IA, tout en gardant une traçabilité complète.

En pratique, ConfiDoc aide le cabinet à :

- protéger les informations personnelles et identifiantes,
- préparer des jeux de données comptables plus propres,
- garder les montants et la structure utile au travail comptable,
- tracer les actions réalisées sur chaque document.

---

## 2) À qui sert la plateforme

Cette version est conçue pour les usages comptables :

- cabinets d'expertise comptable,
- directions financières,
- équipes de contrôle interne et audit.

---

## 3) Ce que ConfiDoc fait concrètement

Pour chaque document (PDF, image), la plateforme peut :

- extraire le texte,
- détecter les données sensibles,
- proposer une version anonymisée (profil **Dataset comptable** / pseudonymisation métier selon réglages),
- permettre validation humaine,
- exporter un format dataset ou un dataset métier structuré,
- proposer une synthèse IA sur données anonymisées (option locale Ollama),
- indexer dans une base de connaissance anonyme pour la recherche.

### Exemples de données masquées

- noms et prénoms,
- emails,
- téléphones,
- adresses,
- IBAN / SIREN / SIRET (selon règles).

### Ce qui est préservé pour la comptabilité

- montants comptables (dans le profil dataset comptable),
- informations utiles aux écritures,
- structure de lignes exploitable.

---

## 4) Parcours utilisateur recommandé

Dans l'interface `/ui`, le flux simple est :

1. **Uploader** un document  
2. Cliquer **🚀 Traiter tout** (ou **🔒 Anonymiser** puis les étapes une par une)  
3. Vérifier la prévisualisation (mode **Anonymisé** ou **Avant / Après**)  
4. Consulter le panneau **Ce qui a été masqué**  
5. Optionnel : **🤖 Synthèse IA** (données anonymisées uniquement)  
6. Poser des questions dans **Question à la base anonyme**

Le bouton **🚀 Traiter tout** enchaîne automatiquement :

- anonymisation,
- prévisualisation,
- validation,
- export dataset.

---

## 5) Fonction des boutons (interface actuelle `/ui`)

Par document :

- **🚀 Traiter tout** : enchaîne anonymisation → prévisualisation → validation → export dataset  
- **🔒 Anonymiser** : lance la détection et la version anonymisée  
- **👁️ Prévisualiser** : affiche la version anonymisée actuelle  
- **✓ Valider** : confirme la version finale  
- **📊 Exporter le dataset** : exporte le format exploitable pour dataset (téléchargement JSON)  
- **🧠 Dataset métier** : exporte le JSON structuré par type de document (routeur + champs métier)  
- **🤖 Synthèse IA** : génère une synthèse lisible à partir de données anonymisées (avec mode secours si besoin)  
- **🛡️ Exporter la preuve** : certificat / intégrité (JSON téléchargé)  
- **🧾 Exporter l'audit** : journal d'audit sans données brutes (JSON téléchargé)  
- **🗑️** : supprime le document et les données associées (avec confirmation)

Zone **Question à la base anonyme** : interroge la base indexée (ingestion automatique des documents prêts avant recherche).

---

## 6) Confidentialité et conformité (vision métier)

La solution est pensée pour un cadre RGPD et métier sensible :

- anonymisation avant usage dataset / IA,
- contrôle humain possible avant validation finale,
- journalisation technique des traitements,
- hébergement EU (selon votre configuration Railway Europe),
- minimisation des données envoyées en assistance IA.

> Note : la conformité finale dépend aussi de votre gouvernance interne, contrats, DPA, politique de conservation, et procédure de contrôle.

---

## 7) Utilisation des données avec un LLM (simple)

La stratégie recommandée est :

- anonymiser les documents,
- indexer dans la base de connaissance,
- faire des recherches contextuelles,
- n'envoyer au LLM que les extraits pertinents et déjà anonymisés.

Cela permet d'améliorer la qualité des réponses tout en limitant l'exposition de données.

---

## 8) Limites connues (version actuelle)

- La qualité dépend de la qualité OCR pour certains scans.
- Certains formats de documents atypiques peuvent nécessiter des ajustements de règles.
- Le module de questions repose sur la base anonymisée : si peu de documents sont traités, les résultats seront limités.

---

## 9) Bonnes pratiques pour un cabinet

- Faire valider un échantillon de documents au départ.
- Définir des règles de revue (qui valide quoi).
- Mettre une convention de nommage documentaire.
- Superviser les cas `needs_review`.
- Documenter les durées de rétention et d'effacement.

---

## 10) Message de présentation court (prêt à lire en rendez-vous)

ConfiDoc nous permet de traiter nos documents comptables de façon sécurisée : les données sensibles sont anonymisées, les informations utiles au travail comptable sont conservées, et nous pouvons ensuite interroger une base anonyme ou produire des synthèses assistées pour alimenter des usages IA avec beaucoup moins de risque.
