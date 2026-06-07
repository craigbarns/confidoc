# ConfiDoc — Script de démo investisseur (7 minutes)

**Objectif** : faire comprendre en 7 min que ConfiDoc protège réellement les données
sensibles **avant, pendant et après** l'IA. Parcours réel :
`upload → pseudonymisation → AI firewall → score DPO → export audit`.

**Préparer** : un faux bilan PDF (`Bilan_Dupont_2024.pdf`) contenant noms, SIRET, IBAN,
email, montants. Avoir deux onglets : `/firewall` (Control Tower) et `/ui` (console).
**Règle de langage** : dire « pseudonymisé / risque de réidentification maîtrisé »,
jamais « anonymisé à 100 % ».

---

## 0:00 — Accroche (45 s)
> « Un expert-comptable veut résumer un bilan avec l'IA. S'il le colle dans ChatGPT, il
> viole le RGPD et le secret professionnel. Donc il ne le fait pas — et perd le gain de
> l'IA. ConfiDoc est le **firewall de confidentialité** qui débloque ça. Regardez. »

## 0:45 — La vitrine : AI Security Control Tower (1 min)
Ouvrir **`/firewall`** (sans login).
- Montrer « AI Firewall · Active », les compteurs (prompts/réponses inspectés,
  redactions, blocages, risques critiques), le pipeline 7 points de contrôle.
- Cliquer **« Lancer la démonstration »** → montrer l'interception en direct :
  prompt propre **autorisé**, email résiduel **masqué**, fuite IBAN **bloquée**.
> « Tout échange IA passe par ce firewall. Rien n'est restitué avant le feu vert. »

## 1:45 — Upload d'un vrai document (1 min)
Passer sur **`/ui`** → glisser `Bilan_Dupont_2024.pdf`, saisir le nom du client.
> « On charge un bilan réel. Le pipeline fait l'OCR, détecte les données identifiantes
> (noms, SIRET, IBAN, email) et crée un double **pseudonymisé**. »
Montrer le statut OCR → pseudonymisation.

## 2:45 — Le cœur : pseudonymisation + Privacy Gate (1 min 30)
- Ouvrir l'aperçu pseudonymisé : montrer les entités masquées (`[PERSONNE]`, `[IBAN]`,
  `[SIRET]`…) **côte à côte** avec l'original.
- Montrer la **décision du Privacy Gate** (autorise / validation humaine / bloque) et le
  **score de risque de réidentification**.
> « Le mapping est réversible et chiffré : c'est de la **pseudonymisation**, pas de la
> magie. La valeur, c'est qu'on **mesure et maîtrise le risque de réidentification** —
> exactement ce que la CNIL demande de regarder. »

## 4:15 — L'IA sous firewall (1 min 15)
- Lancer une analyse IA (synthèse / Copilot) sur le document.
- Montrer que **seul le texte pseudonymisé+firewallé** part vers le modèle ; afficher le
  bloc `payload_policy.firewall` (prompt inspecté / réponse inspectée).
- Mentionner le **mode client sensible** : zéro appel IA externe (souveraineté totale).
> « L'IA ne voit jamais la donnée brute. Et la réponse est ré-inspectée avant de
> revenir à l'utilisateur. »

## 5:30 — Score DPO + preuve d'audit (1 min)
- Montrer le **Trust Score / AI-readiness** et « pourquoi ce score ».
- Ouvrir le **journal d'audit** : chaque étape (upload, OCR, pseudonymisation, scoring,
  validation, export) horodatée + **empreinte SHA-256** (preuve d'intégrité).
> « En cas de contrôle CNIL ou de litige, le cabinet a une **preuve opposable**. »

## 6:30 — Export & clôture (30 s)
- Exporter le rapport / certificat de conformité.
> « Résultat : le cabinet utilise l'IA, gagne des heures, **et** garde une conformité
> démontrable. C'est l'IA débloquée pour ceux qui manipulent le plus de données
> sensibles. »

---

### Plan B (si réseau/IA externe indisponible)
- Rester sur `/firewall` + « Lancer la démonstration » (synthétique, sans dépendance).
- Mode client sensible : montrer que tout fonctionne **sans** IA externe.

### Ce qu'il NE faut PAS dire
- ❌ « anonymisation garantie / irréversible » → dire **pseudonymisation**.
- ❌ « zéro risque » → dire **risque de réidentification mesuré et maîtrisé**.
- ❌ promettre des certifications non obtenues (cf. [06_SECURITY_ROADMAP.md](06_SECURITY_ROADMAP.md)).
