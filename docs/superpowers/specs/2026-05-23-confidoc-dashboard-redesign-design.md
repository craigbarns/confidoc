# ConfiDoc — Redesign global du dashboard

**Date :** 2026-05-23
**Statut :** Spec validé en brainstorming, prêt pour planification d'implémentation
**Portée :** Refonte cohérente de l'application web (`app/templates/index.html`, `app/static/css/style.css`, `app/static/js/app.js`)
**Périmètre exclu :** API backend, modèles de données, workflows métier, services d'anonymisation. Seul le rendu et l'organisation des écrans changent.

---

## 1. Problème

ConfiDoc cible des professions réglementées (comptables, juristes, DPO) qui achètent de la confiance. Le dashboard actuel a trois problèmes :

1. **Signal visuel inadapté.** Glassmorphisme sombre + dégradé indigo→violet → ressemble à un outil grand public IA (Midjourney, Linear consumer). Mauvais signal pour quelqu'un qui confie un bilan client.
2. **Architecture d'information bavarde.** 6 sections visibles + 4 panels cachés. La tâche principale (anonymiser un document) demande 5 clics et 3 changements d'écran.
3. **Friction sur le workflow cœur.** Anonymisation et IA Copilot sont des panels enfouis, alors qu'ils sont l'essence du produit.

## 2. Direction retenue : "Sober Professional + signature"

Base claire, sobre, lisible — avec **une signature reconnaissable** pour ne pas tomber dans le cliché Stripe/Ramp. Pas de fioriture, mais pas anonyme non plus.

### 2.1 Principes
- **Confiance avant tout** : le visuel ne doit jamais distraire d'une donnée chiffrée.
- **Densité professionnelle** : ce n'est pas Notion. Un comptable doit voir beaucoup d'infos sans scroller.
- **Une couleur d'accent unique** : vert émeraude `#047857` = "RGPD safe / vérifié". Aucune autre couleur décorative.
- **Bordures, pas d'ombres** : low chrome. Une `1px solid` claire structure l'écran.
- **Zéro gradient dans le chrome.** Les seuls dégradés tolérés sont dans le logo / l'illustration éventuelle.
- **Tabular nums partout** où des chiffres apparaissent (KPI, scores, montants).

## 3. Design tokens

### 3.1 Couleurs — thème clair (par défaut)

| Token | Hex | Usage |
|---|---|---|
| `--surface` | `#FAFAF7` | Fond d'application (ivoire chaud) |
| `--surface-2` | `#FFFFFF` | Cartes, lignes de tableau, zones de contenu |
| `--surface-muted` | `#F0EFE9` | Hover discret, icônes de doc, badges neutres |
| `--border` | `#ECEBE4` | Bordure standard |
| `--border-strong` | `#D6D3C6` | Drop zones, séparateurs marqués |
| `--ink` | `#0F0F12` | Texte principal, boutons primaires |
| `--ink-2` | `#3F3F44` | Texte secondaire |
| `--ink-muted` | `#6E6E72` | Labels, métadonnées |
| `--ink-dim` | `#9A9A9F` | Texte tertiaire, timestamps |
| `--accent` | `#047857` | Trust, succès, validations, RGPD safe |
| `--accent-soft` | `#ECFDF5` | Pills "anonymisé / safe" (fond) |
| `--accent-soft-ink` | `#065F46` | Pills "anonymisé / safe" (texte) |
| `--warning` | `#B45309` | Trust 70-89%, "À reviewer", drafts |
| `--warning-soft` | `#FEF3C7` | Pills warning (fond) |
| `--warning-soft-ink` | `#92400E` | Pills warning (texte) |
| `--danger` | `#B91C1C` | Trust <70%, erreurs, suppression |
| `--info` | `#5B21B6` | Pills "Exporté", actions Copilot |
| `--info-soft` | `#EDE9FE` | Pills info (fond) |

### 3.2 Couleurs — thème sombre (option utilisateur, gardée mais épurée)

| Token | Hex | Usage |
|---|---|---|
| `--surface` | `#0A0A14` | Fond |
| `--surface-2` | `#15151F` | Cartes |
| `--surface-muted` | `#1F1F2A` | Hover |
| `--border` | `rgba(255,255,255,0.06)` | Bordure standard |
| `--ink` | `#EDEDF5` | Texte principal |
| `--ink-muted` | `#A0A0B8` | Texte secondaire |
| `--accent` | `#10B981` | Idem clair, version vivante |

Le thème sombre ne fait **plus** de glassmorphisme et **plus** de gradient indigo→violet. C'est un sombre sobre.

### 3.3 Typographie

- **Famille** : Inter (déjà installée) — graisses 400 / 500 / 600 / 700.
- **Tabular nums activés** (`font-variant-numeric: tabular-nums`) sur tout chiffre : KPI, montants, scores, dates.
- **Échelle (px)** : 10, 11, 12, 13, 14, 17, 22, 26, 32. Pas d'autre taille.
- **Letter-spacing** : `-0.02em` sur titres ≥ 22px, `0.06-0.08em` sur uppercase labels.
- **Line-height** : 1.5 (corps), 1.3 (titres), 1.75 (zones de lecture longues).

### 3.4 Espacement, rayons, ombres

- Base 4px. Échelle 4 / 8 / 12 / 16 / 22 / 26 / 32 / 48.
- Rayons : `5px` (badges), `7px` (boutons), `8px` (chips, inputs), `10px` (cartes intérieures), `14px` (containers principaux). Plus de `--radius-xl 20px`.
- Ombres : presque jamais. Une seule autorisée : `0 24px 60px -28px rgba(0,0,0,0.18)` pour modales et docked panels. Le reste = bordures 1px.

### 3.5 Composants à standardiser

Composants source unique de vérité, à reconstruire :

- `Button` : `primary` (ink), `primary-ok` (accent), `ghost` (border + transparent), `icon-only`
- `Pill` : `anon`, `review`, `draft`, `exported`, `danger` (rayon 999px, 10-11px, 3px 8-10px de padding)
- `Chip` (filtres) : rectangulaire, rayon 6px, border `--border`, active = border `--ink`
- `Segment` : container pill 4px padding, items 5px 12px, actif fond blanc + shadow `0 1px 2px rgba(0,0,0,0.04)`
- `Card` : border `--border`, rayon 10px, padding interne défini par contexte
- `KPICard` : variante de Card avec label uppercase + valeur grosse + delta
- `Input` : border `--border`, rayon 8px, focus ring `--accent`
- `Table` : header `--surface`, rows séparées par `--border` lighter, hover row = `--surface`
- `NavItem` : 7px 10px padding, rayon 7px, active = fond `--ink` + texte blanc + font-weight 600
- `Drawer` (pour Copilot, Audit étendu) : slide depuis la droite, largeur 420px, overlay 8% noir

## 4. Information Architecture

### 4.1 Navigation

6 destinations top-level groupées en 3 zones (vs 6 destinations + 4 panels cachés actuellement). Net : **−4 panels cachés**, **+1 destination promue** (Journal d'audit), **−1 destination par fusion** (Qualité + Conformité → Qualité & RGPD).

**Workspace**
1. **Accueil** — vue d'ensemble, à reviewer, raccourcis
2. **Documents** — liste de tous les docs + upload + revue (absorbe `panel-upload` et `panel-anon`)
3. **Dossiers** — vue par client / mission

**Confiance**

4. **Qualité & RGPD** — fusion des anciens `panel-quality` + `panel-compliance`. Onglets : *Trust scores* / *Conformité RGPD* / *Golden sets*
5. **Journal d'audit** — promu top-level depuis `panel-compliance`

**Système**

6. **Paramètres**

### 4.2 Omniprésents (topbar)

- **⌘K Recherche globale** — docs, dossiers, clients, audit
- **⌘J Copilot IA** — drawer slide-from-right, contexte-aware (s'il y a un doc ouvert, le Copilot l'a en contexte)
- **Statut conformité** (pill verte top-right) — indicateur permanent

### 4.3 Mapping détaillé

| Avant | Après | Décision |
|---|---|---|
| Accueil | Accueil | conservé |
| Documents (panel vide) | Documents unifié | absorbe Upload + Anonymisation |
| `panel-upload` | bouton "Nouveau document" + drop zone dans Documents | inline |
| `panel-anon` | Vue détail document (full-screen takeover) | inline contextuel |
| Dossiers clients | Dossiers | nom raccourci |
| `panel-dossier 360°` | Vue détail dossier | inline contextuel |
| Qualité | **Qualité & RGPD** (onglet 1) | fusionné |
| Conformité | **Qualité & RGPD** (onglet 2) | fusionné |
| `panel-ai` (IA Copilot) | Drawer global ⌘J | raccourci global |
| (enfoui) Journal d'audit | Top-level | promu |
| Paramètres | Paramètres | conservé |

## 5. Écrans

### 5.1 Accueil

**Objectif** : "Que dois-je faire aujourd'hui ?"

- Header : "Bonjour {prénom}" + lead "X documents demandent ton attention aujourd'hui."
- 4 KPI cards : Documents traités (delta semaine) · En revue (delta retard) · Trust Score moyen (delta 30j) · Anonymisations (anomalie PII)
- Section "À reviewer" : 3-5 lignes de docs prioritaires, avec colonne Trust + statut, action ▶ inline
- Section "Activité récente" : 5 derniers événements d'audit (qui a fait quoi)
- (optionnel) Card "Conformité du mois" : pourcentage RGPD safe, lien vers Qualité & RGPD

### 5.2 Documents (liste)

**Objectif** : trouver et traiter un document en moins de 3 clics.

- Page head : H1 "Documents" + lead chiffré + actions `[Importer un dossier]` `[+ Nouveau document]`
- **Segments** (pill bar) : Tous · À reviewer · Anonymisés · Brouillons · Exportés (counts à droite)
- **Filter bar** : input search ⌕ + chips Dossier ▾ / Type ▾ / Trust ≥ X% ▾ / Date ▾
- **Tableau** : checkbox + Document (icône + nom + meta) + Statut (pill) + Dossier + Trust + Modifié + actions hover
- Hover row → 2 quick actions : ▶ Reviewer (primaire) + ⋯ Menu
- Drop zone discrète en bas : "Glisse un PDF ici…"
- Sélection multi → barre d'actions sticky en bas : "Anonymiser X docs en lot · Exporter · Affecter à un dossier"

### 5.3 Document détail (revue & anonymisation)

**Objectif** : poste de travail principal du comptable.

- **Layout 3 colonnes** : Original | Anonymisé | Right rail (320px)
- **Topbar** : `← Documents` · breadcrumb · status pill · mode (Pseudonymiser ▾) · Exporter… · **`✓ Valider l'anonymisation` (⌘↵)**
- **Pane Original** : fond `#FDFCF6`, PII surlignés en `--warning-soft`
- **Pane Anonymisé** : fond blanc, tokens `[PERSONNE_1]` cliquables (édition inline, pas de modale)
- **Right rail** :
  - Trust score décomposé en 4 dimensions (PII directs / Quasi-identifiants / Cohérence tokens / Réversibilité) avec barres
  - Métadonnées (Type, Période, Dossier, Uploadé par, Pages, Mode)
  - **Copilot IA contextuel** : 1-3 alertes proactives (ex : "Adresse partielle détectée page 4" / "Quasi-identifiant fort : CA + secteur + ville"), + input "Demander au Copilot…" (⌘J)
  - Audit (extraits) : 4 dernières entrées timestampées
- **Action bar sticky bas** : résumé ("12 entités remplacées · 0 PII résiduel direct") + `Re-anonymiser avec règles strictes` · `Aperçu PDF redacté` · `Valider & exporter`

### 5.4 Dossiers (liste + détail)

**Liste** : même grammaire que Documents — table avec Client / Nb docs / Trust moyen / Dernière activité / Owner. Clic = ouverture vue détail.

**Détail** : breadcrumb retour, header avec nom client + statut, onglets `Documents` / `Comparaison pluri-annuelle` / `Métadonnées client`, contenu pleine largeur. Reprend l'actuel `panel-dossier` mais avec les nouveaux tokens.

### 5.5 Qualité & RGPD

**Objectif** : tableau de bord trust global pour DPO/responsable cabinet.

- Onglets : *Trust scores* · *Conformité RGPD* · *Golden sets*
- **Trust scores** : graph distribution des trust scores du mois, top documents à risque, breakdown par type de document
- **Conformité RGPD** : checklist RGPD (PII éliminés, journal complet, durées de conservation, droits exercés), certificat exportable PDF (existe déjà)
- **Golden sets** : taux de réussite des 250+ cas de régression, dernière exécution, alertes

### 5.6 Journal d'audit

Liste paginée + filtres par utilisateur / action / type d'objet / période. Export CSV. Style cohérent avec Documents.

### 5.7 Paramètres

Onglets : *Profil* · *Apparence* (thème, densité) · *Anonymisation* (règles par défaut, mode pseudonymiser/anonymiser fort) · *Copilot* (modèle, contexte autorisé) · *API & intégrations* · *Équipe*.

## 6. Comportements omniprésents

- **⌘K** ouvre une command palette globale (recherche docs, dossiers, clients, actions ; navigation "Aller à Documents", etc.)
- **⌘J** ouvre/ferme le drawer Copilot. S'il y a un doc ouvert, le Copilot a son contexte.
- **⌘↵** valide l'action principale de l'écran courant.
- **Échap** ferme drawer/modale et revient à l'écran liste.
- **Tab order** respecte l'ordre visuel (sidebar → topbar → main → action bar).

## 7. Accessibilité

- Contraste AA minimum sur tout couple texte/fond. Le vert émeraude `#047857` sur blanc passe AA (ratio 4.7:1).
- Skip link `Aller au contenu principal` conservé.
- Toutes les actions interactives ont un `aria-label` ou texte visible.
- Focus ring visible (2px solid `--accent` à l'extérieur de l'élément).
- Tabular nums + alignement à droite pour les colonnes chiffrées.
- Respect de `prefers-reduced-motion` : désactive transitions/animations si l'utilisateur l'a demandé.

## 7bis. Animations & transitions

- **Hover / focus** : transition `120ms ease-out` sur `background`, `border-color`, `color`.
- **Drawer (Copilot, modales)** : slide `200ms cubic-bezier(0.16, 1, 0.3, 1)`.
- **Aucune animation sur le chargement de page**, sur la navigation entre sections, sur les listes. Le contenu apparaît instantanément.
- **Skeleton screens** plutôt que spinners pour les états de chargement de tables / KPI (placeholder rectangle de la couleur `--surface-muted` qui pulse à 800ms).
- Spinners autorisés uniquement pour les actions ponctuelles (Anonymiser en cours, Export en cours).

## 7ter. Responsive

- **Cible principale : desktop ≥ 1280px.** C'est un outil professionnel utilisé en bureau.
- **Tablet (768-1279px)** : sidebar collapse en icônes (56px de large), reste utilisable.
- **Mobile (<768px)** : un seul écran d'avertissement "ConfiDoc est optimisé pour ordinateur. Une version mobile arrive." Pas d'essai de faire fonctionner le workflow d'anonymisation sur smartphone — c'est inadapté au cas d'usage.

## 8. Plan de migration

Cible : modifier `app/templates/index.html`, `app/static/css/style.css`, `app/static/js/app.js` **sans** changer les endpoints, schemas, ni le JS métier (handlers d'API, workflows d'upload).

**Étape 1 — Tokens & primitives.** Refondre les CSS variables (section `:root` et `[data-theme]`) selon §3. Reconstruire les composants atomiques (Button, Pill, Chip, Segment, Card, Input, Table, NavItem).

**Étape 2 — Topbar + Sidebar.** Mettre à jour la nav (5 sections + groupes Workspace / Confiance / Système), ajouter ⌘K et ⌘J dans le topbar. Conserver les data-attributes existants (`data-nav="..."`).

**Étape 3 — Documents (liste).** Remplacer `panel-upload` par la nouvelle liste avec segments + filter bar + table. Brancher la drop zone sur l'API d'upload existante.

**Étape 4 — Document détail.** Refondre `panel-anon` en layout 3 colonnes. Réutiliser le viewer original et la zone éditable existants. Ajouter le right rail (Trust décomposé, Métadonnées, Copilot inline, Audit court).

**Étape 5 — Dossiers, Qualité & RGPD, Journal d'audit, Paramètres.** Appliquer la grammaire (page head + filtres + table) à chaque écran.

**Étape 6 — Copilot drawer.** Sortir `panel-ai` du flux principal, le transformer en drawer ⌘J avec contexte.

**Étape 7 — Suppression / nettoyage.** Retirer le CSS non utilisé (gradients indigo→violet, glow purple, blur 24px sur cartes, etc.). Objectif : passer de 5 695 lignes de CSS à <3 000.

Chaque étape est testable indépendamment : on doit pouvoir merger l'étape 1 sans l'étape 2 et avoir une UI fonctionnelle, juste partiellement migrée.

## 9. Hors-scope explicite

- Pas de changement d'API.
- Pas de changement de modèle de données.
- Pas de migration de framework (HTML + CSS + Vanilla JS conservés).
- Pas de nouveau composant tiers (pas de React/Vue, pas de Tailwind, pas de Radix). On reste vanilla.
- Pas de refonte du parcours marketing (`landing.html`, `architecture.html`, `security.html`) — uniquement le dashboard authentifié.
- Pas de localisation supplémentaire (FR reste la langue principale).

## 10. Critères de validation

Le redesign est livré quand :

1. Les 5 sections navigables fonctionnent et chargent les bons écrans.
2. Un utilisateur peut uploader → reviewer → anonymiser → exporter un document **sans quitter Documents** (workflow en 3 clics maximum).
3. ⌘K, ⌘J, ⌘↵ fonctionnent.
4. Le thème sombre est dispo et n'a plus de glassmorphisme ni de gradient indigo→violet.
5. Le CSS total passe sous 3 000 lignes.
6. Aucun gradient n'est utilisé dans le chrome (sauf logo / illustrations explicites).
7. Tous les KPI affichent en tabular nums.
8. Tous les écrans existants sont migrés (Accueil, Documents, Document détail, Dossiers, Qualité & RGPD, Journal d'audit, Paramètres).
9. Les tests smoke et les golden sets continuent de passer (pas de régression backend).
