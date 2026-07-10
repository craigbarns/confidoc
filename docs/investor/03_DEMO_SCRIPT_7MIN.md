# ConfiDoc — Script demo investisseur 7 minutes

**Objectif** : montrer une histoire simple et fundable :

`document confidentiel -> version IA-safe -> chat IA -> preuve d'audit`

Preparer un faux document PDF : `Bilan_Dupont_2024.pdf` ou `Contrat_Martin_SAS.pdf`,
avec nom, email, adresse, SIRET, IBAN, montants, clauses sensibles.

Regle de langage : "version anonymisee/pseudonymisee selon le niveau de risque", jamais
"zero risque".

---

## 0:00 — Accroche

> "Tout le monde veut utiliser l'IA sur ses documents clients. Le probleme, c'est que
> les documents vraiment utiles contiennent des donnees confidentielles. ConfiDoc permet
> d'en discuter avec une IA sans que l'IA voie le document brut."

Message :

> "Nous ne vendons pas un chatbot. Nous vendons une zone de securite pour utiliser l'IA
> sur des documents confidentiels."

---

## 0:45 — Montrer le risque

Ouvrir le document brut.

Montrer rapidement :

- nom client ;
- email ;
- IBAN ;
- SIRET ;
- montants ;
- donnees contractuelles ou financieres.

> "C'est exactement le type de document que personne ne devrait coller tel quel dans une
> IA externe."

---

## 1:30 — Upload et anonymisation

Dans `/ui`, uploader le document.

Montrer :

- detection ;
- anonymisation/pseudonymisation ;
- score de risque ;
- entites masquees.

Phrase cle :

> "ConfiDoc cree une version exploitable par IA, mais retire les identifiants qui n'ont
> pas besoin d'etre vus par le modele."

---

## 2:45 — Chat IA sur version securisee

Lancer une question :

> "Resume ce document en 10 lignes et liste les 3 risques principaux."

Puis :

> "Prepare une note client avec les points d'attention."

Montrer que la reponse est utile, mais que les identifiants restent masques.

Phrase cle :

> "Le modele travaille sur le contenu utile, pas sur l'identite du client."

---

## 4:15 — Firewall sur prompts et reponses

Ouvrir `/firewall`.

Cliquer "Lancer la demonstration".

Montrer :

- prompt propre autorise ;
- email residuel masque ;
- IBAN bloque ;
- compteurs d'evenements ;
- journal sans donnee brute.

Phrase cle :

> "La securite n'est pas seulement avant l'IA. On controle aussi ce qui sort de l'IA."

---

## 5:30 — Preuve d'audit

Ouvrir le rapport / journal d'audit.

Montrer :

- horodatage ;
- hash document ;
- donnees masquees par type ;
- prompts/reponses inspectes ;
- decisions autoriser/masquer/bloquer.

Phrase cle :

> "Un DPO ou un client peut verifier ce qui a ete expose a l'IA. C'est la difference
> entre usage sauvage et usage gouverne."

---

## 6:30 — Cloture levee

> "Nous commencons par les documents reglementes, car la douleur est immediate. Ensuite,
> la meme couche devient un Agent Firewall : chaque agent IA devra prouver qui il est,
> ce qu'il peut lire, ce qu'il peut envoyer et ce qui a ete audite."

Finir sur la demande :

> "Nous levons 500 k€ pour transformer cette demo en produit commercial, signer 3 a 5
> pilotes payants et recruter le premier binome GTM/produit."

---

## Plan B

Si l'IA externe ou le reseau est instable :

- rester sur `/firewall` ;
- utiliser un document deja traite ;
- montrer le rapport d'audit ;
- presenter le mode client sensible : aucun appel IA externe.

## Ne pas dire

- "anonymisation garantie" ;
- "zero risque" ;
- "certifie ISO" si non obtenu ;
- "on fait toute la securite des agents IA" avant les pilotes.
