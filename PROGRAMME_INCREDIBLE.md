# Programme « Incroyable » — ConfiDoc

Vision : **confiance mesurable**, **clarté pour le métier**, **opérations sereines**.

---

## Piliers

### 1. Confiance (qualité)
- [x] Garde-fous P1/P2 (bilan, compte de résultat) avec tolérances et `minor_gap`
- [x] Smart split + **repli texte intégral** si meilleure qualité
- [x] Couche **`experience`** : niveau, phrase clé FR, items détaillés, note découpe
- [ ] Seuils d’alerte produit (dashboard interne / métriques)
- [ ] Jeux de référence PDF anonymisés (golden) par type

### 2. Clarté (UX & API)
- [x] `export-structured-dataset` inclut `experience`
- [x] `dataset-summary` expose `experience` pour l’UI
- [x] UI : synthèse « expérience » dans la carte qualité
- [ ] Export PDF rapport d’audit (hash + résumé qualité)
- [ ] Comparaison deux versions / deux exercices

### 3. Fiabilité pipeline
- [x] CI GitHub Actions (pytest + deps dev complètes)
- [x] Scripts smoke / post-déploiement
- [ ] Seuils optionnels dans smoke (coverage min par type)
- [ ] Webhooks « document prêt / à revoir »

### 4. PDF & contenu long
- [x] Fenêtre sémantique V1 (mots-clés)
- [ ] Marqueurs de page dans l’extraction (quand PyMuPDF disponible) pour ciblage fin
- [ ] Routeur multi-sections (bilan + CR dans un même upload)

### 5. Différenciation
- [ ] Traçabilité décisionnelle (pourquoi ce flag, quelle tolérance)
- [ ] SLA / preuve pour cabinets (exports signés, journaux)

---

## Indicateurs à suivre (hebdo)

| Indicateur | Cible directionnelle |
|------------|------------------------|
| `ready_for_ai` sur jeu ref. | ↑ |
| `critical_missing_fields` non vides | ↓ |
| `bilan_balance_mismatch` sur plaquettes connues | ↓ ou documenté |
| Temps moyen jusqu’à validation humaine | ↓ |

---

## Prochaine vague (priorisée)

1. **Golden set** : 3–5 PDF anonymisés + assertions sur `experience.level` / flags
2. **Marqueurs de page** dans `extract_text_from_file` (optionnel, feature flag)
3. **Rapport PDF** one-click pour dossiers clients

*Document vivant — à ajuster avec les retours terrain.*
