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
- **Deux couleurs en opposition narrative** : terracotta `#A4471E` = "données brutes / PII / sensible", émeraude `#047857` = "RGPD safe / protégé". L'app raconte visuellement le passage de l'un à l'autre. Aucune autre couleur d'accent décorative.
- **Bordures, pas d'ombres** : low chrome. Une `1px solid` claire structure l'écran.
- **Zéro gradient dans le chrome.** Les seuls dégradés tolérés sont (a) sur les tokens anonymisés (effet "carte plastique" subtil), et (b) sur la ligne du scan reveal.
- **Tabular nums partout** où des chiffres apparaissent (KPI, scores, montants).
- **Retenue radicale du motion.** Un seul moment d'animation par document : le scan reveal à la validation. Le reste est immobile pour que ce moment compte.

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
| `--accent` | `#047857` | Trust, succès, validations, RGPD safe, anneau "safe" du Trust Gauge |
| `--accent-soft` | `#ECFDF5` | Pills "anonymisé / safe" (fond), fond des tokens-cartes |
| `--accent-soft-ink` | `#065F46` | Pills "anonymisé / safe" (texte) |
| `--accent-border` | `#A7F3D0` | Bordure des tokens-cartes, des pills safe |
| `--raw` | `#A4471E` | **Couleur narrative "données brutes / PII"** : utilisée pour highlight des PII dans l'original, et pour la pluie hors zone "safe" du Trust Gauge |
| `--raw-soft` | `#FDF6F1` | Fond de la pane original, fond highlight PII |
| `--raw-soft-ink` | `#A4471E` | Texte sur fond raw-soft |
| `--warning` | `#B45309` | Trust 70-89%, "À reviewer", drafts, anneau "quasi-ID" du Trust Gauge |
| `--warning-soft` | `#FEF3C7` | Pills warning (fond) |
| `--warning-soft-ink` | `#92400E` | Pills warning (texte) |
| `--danger` | `#B91C1C` | Trust <70%, erreurs, suppression |
| `--info` | `#5B21B6` | Pills "Exporté", actions Copilot |
| `--info-soft` | `#EDE9FE` | Pills info (fond) |

**Règle d'opposition** : terracotta `--raw` et émeraude `--accent` ne sont **jamais utilisés côte à côte sur un même élément**. Leur opposition est *toujours* spatiale (pane gauche vs pane droite, anneau plein vs anneau vide, état avant vs état après). C'est ce qui rend l'histoire visuelle lisible.

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

- **Famille principale** : Inter (déjà installée) — graisses 400 / 500 / 600 / 700.
- **Famille signature (literary)** : *Iowan Old Style* (fallback `Times New Roman`, `Georgia`) en *italique* `font-weight: 500`. **Usage strict** : mots-pivots dans les titres hero des pages clés (ex : "trois bilans", "la barre des 90%"). **Une seule occurrence par page maximum.** Cette retenue est ce qui fait la différence entre charme et ridicule.
- **Famille code (tokens & nombres techniques)** : *JetBrains Mono* (fallback `ui-monospace`, `Menlo`). Utilisée uniquement dans les tokens-cartes (`[PERSONNE_1]`) et les valeurs cryptographiques (clés, checksums).
- **Tabular nums activés** (`font-variant-numeric: tabular-nums`) sur tout chiffre : KPI, montants, scores, dates.
- **Échelle (px)** : 10, 11, 12, 13, 14, 17, 22, 26, 32. Pas d'autre taille.
- **Letter-spacing** : `-0.02em` sur titres ≥ 22px, `0.06-0.08em` sur uppercase labels.
- **Line-height** : 1.5 (corps), 1.3 (titres), 1.75 (zones de lecture longues).

### 3.4 Espacement, rayons, ombres

- Base 4px. Échelle 4 / 8 / 12 / 16 / 22 / 26 / 32 / 48.
- Rayons : `5px` (badges), `7px` (boutons), `8px` (chips, inputs), `10px` (cartes intérieures), `14px` (containers principaux). Plus de `--radius-xl 20px`.
- Ombres : presque jamais. Une seule autorisée : `0 24px 60px -28px rgba(0,0,0,0.18)` pour modales et docked panels. Le reste = bordures 1px.

### 3.5 La couche signature (5 éléments exceptionnels)

Ces 5 éléments sont ce qui rend ConfiDoc reconnaissable et non interchangeable avec n'importe quel SaaS B2B propre. Aucun n'est négociable.

#### 3.5.1 Token-card (`<span class="token-card">`)

Chaque `[PERSONNE_1]`, `[ADRESSE_1]`, etc. dans la pane Anonymisé est rendu en *carte plastique miniature* :

- Padding `2px 8px`, rayon `4px`, bordure `1px solid var(--accent-border)`
- Fond : `linear-gradient(180deg, #FFFFFF 0%, #F6FDF9 100%)`
- Inner shadow haut : `inset 0 1px 0 rgba(255,255,255,0.8)`
- Drop shadow émeraude très subtile : `0 1px 0 rgba(4,120,87,0.06)`
- Font : JetBrains Mono `12px`, weight `600`, color `--accent`
- Hover : bordure `--accent`, halo `0 0 0 3px var(--accent-soft)`
- Cliquable → édite le mapping inline

#### 3.5.2 Trust Gauge — radial à 4 anneaux concentriques

Composant SVG dédié, présent en grand format sur Document détail et en mini format (40px) en colonne de table.

- 4 anneaux concentriques, rayons 17 / 26 / 35 / 44 (sur SVG 100×100)
- Anneaux : `PII directs (intérieur) · Cohérence tokens · Réversibilité · Quasi-identifiants (extérieur)`
- Stroke-width `4`, `stroke-linecap: round`
- Couleur stroke : `--accent` si valeur ≥ 90%, `--warning` si 70-89%, `--danger` si <70%
- Fond non rempli : `--border`
- Animation à l'apparition : `stroke-dashoffset` de la valeur "vide" → valeur réelle, durée `900ms cubic-bezier(0.16, 1, 0.3, 1)`, *une seule fois par chargement*
- Centre : valeur globale (moyenne pondérée) en font-size `30px` weight `800`, couleur sémantique
- Mini version (40×40) : pas d'animation, pas de label central, juste les 4 anneaux

#### 3.5.3 Hero literary line

Sur Accueil et sur les vues détail (Document, Dossier), le H1 n'est pas un nom de section mais **une phrase d'accueil** qui contient *un seul mot ou groupe nominal* dans la famille signature italique en couleur `--accent`.

Exemples :
- Accueil : *« Bonjour Grégory. Aujourd'hui, *trois bilans* attendent ta revue — dont un sous *la barre des 90 %* de confiance. »* → 2 italiques, c'est l'exception qui prouve la règle (page la plus importante)
- Document détail : *« Bilan SARL Martin, *en revue* depuis 12 minutes. »*
- Dossier : *« Dossier Martin & Associés — *14 documents*, dernier mouvement il y a 3 jours. »*

**Règle** : 1 italique signature par page maximum (2 sur Accueil seulement). Si pas d'italique naturel, on n'en force pas.

#### 3.5.4 Scan reveal

Animation unique et seule de l'app, déclenchée à la validation d'anonymisation (`✓ Valider & exporter`).

- Une ligne `height: 2px`, `linear-gradient(90deg, transparent, var(--accent) 30%, var(--accent) 70%, transparent)`, `box-shadow: 0 0 12px rgba(4,120,87,0.5)`
- Glow halo derrière : `linear-gradient(180deg, rgba(4,120,87,0.08), transparent)` `height: 60px` solidaire de la ligne
- Translation `translateY(0) → translateY(100%)` en `600ms cubic-bezier(0.4, 0, 0.2, 1)`
- À la fin : checkmark `28px` circulaire émeraude qui apparaît en `200ms` avec scale `0.8 → 1.0` (bounce subtil `cubic-bezier(0.34, 1.56, 0.64, 1)`)
- **Désactivée si `prefers-reduced-motion: reduce`** — remplacée par fade-in instantané du checkmark
- **Aucune autre animation comparable dans l'app.** C'est ce qui la rend mémorable.

#### 3.5.5 Privacy Lens (optionnel mais distinctif)

Toggle dans le topbar de Document détail qui overlaye un *heatmap d'opacité* sur la pane Original montrant les zones de risque de ré-identification résiduel (calculé à partir des quasi-identifiants).

- Off par défaut, raccourci clavier `⌘L`
- Zones à fort risque : voile terracotta `rgba(164,71,30,0.18)` avec bordure dashed `rgba(164,71,30,0.5)`
- Zones safe : pas d'overlay
- Permet au DPO de voir *pourquoi* le trust score est à 87 et pas 100 — visible spatialement, pas juste numériquement

### 3.6 Composants à standardiser

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

**Objectif** : "Que dois-je faire aujourd'hui ?" — pas "voici tes statistiques."

- **Hero literary** (§3.5.3) : phrase d'accueil avec 1-2 italiques signature. Exemple : *« Bonjour Grégory. Aujourd'hui, *trois bilans* attendent ta revue — dont un sous *la barre des 90 %* de confiance. »*
- **Bloc "À reviewer en premier"** (le plus important visuellement) : 3 lignes de docs critiques avec Trust Gauge mini (40px) à gauche, nom + dossier, action ▶ "Reviewer" inline. Si rien à reviewer : message éditorial *« Aucun document n'attend ta revue. »* sur fond `--surface-muted`.
- **Bloc "Activité du jour"** : timeline éditoriale (pas table) — *« 14:23 · Marie L. a uploadé Bilan Martin · 14:24 · 12 entités détectées · 14:30 · Paul a validé Relevé BNP »* en flow continu, pas grille.
- **4 KPI cards en second rang** (taille réduite, en bas) : Documents traités (delta semaine) · En revue (delta retard) · Trust Score moyen 30j · Anonymisations (anomalie PII).

L'ordre visuel inverse l'attendu : *d'abord ce qui demande ton attention, ensuite ce qui s'est passé, en dernier les chiffres de vanity.*

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
- **Topbar** : `← Documents` · breadcrumb · status pill · mode (Pseudonymiser ▾) · **`⌘L Privacy Lens`** (§3.5.5) · Exporter… · **`✓ Valider l'anonymisation` (⌘↵)**
- **Hero literary** sous le topbar (optionnel, sur 1 ligne) : *« Bilan SARL Martin, *en revue* depuis 12 minutes. »*
- **Pane Original** : fond `--raw-soft` (`#FDF6F1`), PII surlignés en `rgba(164,71,30,0.13)` avec texte `--raw`. Quand Privacy Lens activé : overlay heatmap terracotta.
- **Pane Anonymisé** : fond `--surface-2` blanc, tokens `[PERSONNE_1]` rendus en **token-card** (§3.5.1) cliquables. Édition inline du mapping (pas de modale).
- **Right rail** :
  - **Trust Gauge** (§3.5.2) en grand format (140×140), animé à l'apparition. Centre = valeur globale, légende à droite avec les 4 dimensions.
  - Métadonnées (Type, Période, Dossier, Uploadé par, Pages, Mode)
  - **Copilot IA contextuel** : 1-3 alertes proactives (ex : "Adresse partielle détectée page 4" / "Quasi-identifiant fort : CA + secteur + ville"), + input "Demander au Copilot…" (⌘J)
  - Audit (extraits) : 4 dernières entrées timestampées
- **Action bar sticky bas** : résumé ("12 entités remplacées · 0 PII résiduel direct") + `Re-anonymiser avec règles strictes` · `Aperçu PDF redacté` · `Valider & exporter`
- **À la validation** : déclenchement du **Scan reveal** (§3.5.4) qui balaye les deux panes en parallèle, puis checkmark central. Tout le reste de l'app est immobile pour faire vivre ce moment.

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

Doctrine : **retenue radicale**. L'app est immobile pour que le Scan reveal (§3.5.4) compte.

- **Hover / focus** : transition `120ms ease-out` sur `background`, `border-color`, `color`. *Aucune* sur `transform`, `scale`, `opacity` du conteneur.
- **Drawer (Copilot, modales)** : slide `200ms cubic-bezier(0.16, 1, 0.3, 1)`.
- **Trust Gauge** (§3.5.2) : animé à l'apparition uniquement (`stroke-dashoffset` sur `900ms`), pas au scroll, pas au hover.
- **Scan reveal** (§3.5.4) : la *seule* animation cérémonielle de l'app — 600ms pour la ligne, 200ms pour le check.
- **Aucune animation sur le chargement de page**, sur la navigation entre sections, sur l'apparition des lignes de table, sur les filtres. Le contenu apparaît instantanément.
- **Skeleton screens** plutôt que spinners pour les états de chargement de tables / KPI (placeholder rectangle `--surface-muted` qui pulse à 800ms).
- Spinners autorisés uniquement pour les actions ponctuelles (Anonymiser en cours, Export en cours).
- **`prefers-reduced-motion: reduce`** désactive le Scan reveal, l'animation du Trust Gauge, et le slide des drawers. Tout reste fonctionnel, juste instantané.

## 7ter. Responsive

- **Cible principale : desktop ≥ 1280px.** C'est un outil professionnel utilisé en bureau.
- **Tablet (768-1279px)** : sidebar collapse en icônes (56px de large), reste utilisable.
- **Mobile (<768px)** : un seul écran d'avertissement "ConfiDoc est optimisé pour ordinateur. Une version mobile arrive." Pas d'essai de faire fonctionner le workflow d'anonymisation sur smartphone — c'est inadapté au cas d'usage.

## 8. Plan de migration

Cible : modifier `app/templates/index.html`, `app/static/css/style.css`, `app/static/js/app.js` **sans** changer les endpoints, schemas, ni le JS métier (handlers d'API, workflows d'upload).

**Étape 1 — Tokens & primitives.** Refondre les CSS variables (section `:root` et `[data-theme]`) selon §3.1-3.4. Reconstruire les composants atomiques (Button, Pill, Chip, Segment, Card, Input, Table, NavItem). Charger les fonts : Inter (déjà OK), Iowan Old Style (web font ou fallback Times New Roman), JetBrains Mono.

**Étape 2 — Couche signature.** Implémenter les 5 composants distinctifs (§3.5) en isolation, chacun avec sa démo statique : (1) `.token-card`, (2) `<TrustGauge>` SVG animé, (3) helper `<HeroLiterary>` pour les titres, (4) `<ScanReveal>` overlay, (5) `<PrivacyLens>` toggle + overlay. Tester chaque composant standalone avant intégration.

**Étape 3 — Topbar + Sidebar.** Mettre à jour la nav (6 destinations en 3 groupes Workspace / Confiance / Système), ajouter ⌘K (palette globale) et ⌘J (drawer Copilot) dans le topbar. Conserver les data-attributes existants (`data-nav="..."`).

**Étape 4 — Documents (liste).** Remplacer `panel-upload` par la nouvelle liste avec segments + filter bar + table. Mini Trust Gauge en colonne. Brancher la drop zone sur l'API d'upload existante.

**Étape 5 — Document détail.** Refondre `panel-anon` en layout 3 colonnes. Intégrer Trust Gauge (grand format), tokens-cards dans la pane Anonymisé, Privacy Lens toggle dans le topbar, Scan reveal déclenché par "Valider & exporter".

**Étape 6 — Accueil.** Implémenter Hero literary (avec italique signature), bloc "À reviewer" avec mini Trust Gauges, timeline éditoriale, KPI cards reléguées en second rang.

**Étape 7 — Dossiers, Qualité & RGPD, Journal d'audit, Paramètres.** Appliquer la grammaire (page head + Hero literary + filtres + table) à chaque écran.

**Étape 8 — Copilot drawer.** Sortir `panel-ai` du flux principal, le transformer en drawer ⌘J avec contexte (s'il y a un doc ouvert, le Copilot l'a en contexte).

**Étape 9 — Suppression / nettoyage.** Retirer le CSS non utilisé (gradients indigo→violet, glow purple, blur 24px sur cartes, `--accent-glow`, etc.). Objectif : passer de 5 695 lignes de CSS à <3 000.

Chaque étape est testable indépendamment : on doit pouvoir merger l'étape 1 sans l'étape 2 et avoir une UI fonctionnelle, juste partiellement migrée. L'étape 2 (couche signature) est *standalone* — elle peut être merged même si aucun écran ne l'utilise encore.

## 9. Hors-scope explicite

- Pas de changement d'API.
- Pas de changement de modèle de données.
- Pas de migration de framework (HTML + CSS + Vanilla JS conservés).
- Pas de nouveau composant tiers (pas de React/Vue, pas de Tailwind, pas de Radix). On reste vanilla.
- Pas de refonte du parcours marketing (`landing.html`, `architecture.html`, `security.html`) — uniquement le dashboard authentifié.
- Pas de localisation supplémentaire (FR reste la langue principale).

## 10. Critères de validation

Le redesign est livré quand :

**Fonctionnel**

1. Les 6 destinations navigables (en 3 groupes) fonctionnent et chargent les bons écrans.
2. Un utilisateur peut uploader → reviewer → anonymiser → exporter un document **sans quitter Documents** (workflow en 3 clics maximum).
3. ⌘K (palette globale), ⌘J (Copilot drawer), ⌘↵ (action principale), ⌘L (Privacy Lens) fonctionnent.
4. Tous les écrans existants sont migrés (Accueil, Documents, Document détail, Dossiers, Qualité & RGPD, Journal d'audit, Paramètres).
5. Les tests smoke et les golden sets continuent de passer (pas de régression backend).

**Couche signature (§3.5) en place**

6. `.token-card` rendue sur tous les tokens `[PERSONNE_*]`, `[ADRESSE_*]`, etc. dans la pane Anonymisé.
7. `<TrustGauge>` (4 anneaux) visible : grand format sur Document détail, mini format en colonne de table Documents.
8. Hero literary présent sur Accueil (1-2 italiques signature) et sur les vues détail.
9. Scan reveal déclenché à la validation, désactivé proprement si `prefers-reduced-motion: reduce`.
10. Privacy Lens (⌘L) opérationnel sur Document détail — overlay heatmap terracotta sur la pane Original.

**Discipline visuelle**

11. Le thème sombre est dispo et n'a plus de glassmorphisme ni de gradient indigo→violet.
12. Le CSS total passe sous 3 000 lignes.
13. Aucun gradient dans le chrome (sauf token-card et scan reveal qui sont les deux exceptions documentées).
14. Aucune autre couleur d'accent que `--accent` (émeraude) et `--raw` (terracotta) — pas de purple, pas d'indigo, pas de bleu décoratif.
15. Tous les chiffres affichent en tabular nums.
16. Italique signature : une occurrence maximum par page (deux sur Accueil seulement, page-pivot).
