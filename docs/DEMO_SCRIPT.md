# Demo Script

## Demo investisseur 3 minutes

Phrase d'ouverture:

> ConfiDoc transforme un document client sensible en donnees exploitables par IA, avec anonymisation, score RGPD, audit trail et controles d'export.

Sequence:

1. Cliquer `Charger une démo` ou `Demo Investor` sur le dashboard.
2. Montrer le status OCR/anonymisation.
3. Ouvrir la preview anonymisee.
4. Montrer les entites detectees: email, telephone, IBAN, SIRET, adresse, personne.
5. Ouvrir le Risk Score puis le Trust Score / AI Readiness.
6. Montrer "Pourquoi ce score ?" via les recommandations.
7. Lancer ou afficher le rapport de conformite.
8. Montrer l'audit trail: upload, OCR, anonymisation, scoring, validation, export.
9. Exporter le rapport anonymise.

Chemin exact dans l'application:

1. Se connecter au compte demo.
2. Accueil -> `Charger une démo`.
3. Attendre le passage `Ajout -> OCR -> Détection -> Masquage -> Prêt IA`.
4. Montrer les KPI: Risk Score, Trust Score, AI Readiness, entités détectées, statut export et dernier audit.
5. Cliquer `Audit RGPD` puis télécharger le rapport PDF.

Conclusion:

> Le client garde la preuve de traitement et sait si le document est pret pour une IA interne ou un partage externe.

## Demo client 5 minutes

Angle client:

> Vous gardez votre workflow documentaire, mais chaque document passe par une couche de securite, anonymisation et tracabilite.

Sequence:

1. Connexion en organisation cabinet.
2. Upload d'une facture ou liasse synthetique.
3. Traitement OCR/anonymisation.
4. Vue avant/apres: original reserve aux utilisateurs autorises, anonymise pour usage operationnel.
5. Score:
   - risque RGPD;
   - Trust Score;
   - AI Readiness.
6. Validation humaine.
7. Analyse IA / extraction structuree sur version anonymisee.
8. Export rapport.
9. Audit trail organisation.

## Objections probables

"Est-ce que mes documents partent chez un LLM ?"

Reponse:

> Par defaut, les analyses exploitables sont rattachees au texte anonymise. Pour clients sensibles, on desactive Mistral et on garde OCR/anonymisation en mode local ou fournisseur contractualise.

"Comment evitez-vous qu'un collaborateur voie un autre client ?"

Reponse:

> Les documents sont rattaches a une organisation et les routes sensibles passent par RBAC: read, raw, process, validate, export et audit sont separes.

"Le score remplace-t-il une validation DPO ?"

Reponse:

> Non. Le score priorise le risque, bloque les exports critiques et donne une preuve. Les cas sensibles restent soumis a validation humaine.

"Railway est-il acceptable pour un pilote ?"

Reponse:

> Oui pour pilote si secrets Railway, PostgreSQL, Redis, stockage non local et checks `/health`, `/readiness`, `/version` sont configures. Pour enterprise, on peut porter la meme stack sur un cloud client ou une region dediee.

## Phrases fortes

- "ConfiDoc ne vend pas un chatbot, mais une couche de confiance documentaire pour l'IA."
- "Chaque document a un score, un statut, une version anonymisee et une preuve d'audit."
- "Le brut reste controle; l'IA travaille sur une version minimisee."
- "La valeur est double: reduction du risque RGPD et acceleration de l'exploitation documentaire."
