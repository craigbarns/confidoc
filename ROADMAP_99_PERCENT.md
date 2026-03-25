# Roadmap 99% - Extraction ConfiDoc

## Vision
Atteindre 99% de précision sur les champs critiques par type de document, via une extraction multi-couches avec validation métier stricte.

## Phase 1 - Scope Étroit (Niveau 1 : 99%)

### Documents prioritaires (fiabilité déjà élevée)
| Type | Statut actuel | Objectif | Champs critiques |
|------|--------------|----------|------------------|
| Relevé bancaire | ✅ Très stable | 99% | solde_initial, solde_final, operations[] |
| Immobilisations | ✅ Très stable | 99% | brut, amortissements, net, details[] |
| Liasse IS (2065) | ✅ Stable | 99% | totaux, imposition, report |
| Facture fournisseur | ✅ Stable | 99% | montant_ht, tva, ttc, numero, date |

**Action** : Renforcer les règles métier et le golden set pour ces 4 types.

## Phase 2 - Documents complexes (Niveau 2 : 95-98%)

| Type | Statut actuel | Objectif | Difficulté |
|------|--------------|----------|------------|
| Bilan | ⚠️ OK mais fallbacks | 95-98% | Collisions actif/passif, OCR bruité |
| Compte de résultat | ⚠️ OK mais fallbacks | 95-98% | Chaîne calculs, séquences |
| 2072 Foncier | ✅ Bon | 95-98% | Quote-parts, immeubles multiples |

## Pipeline Multi-Couches (à implémenter)

```
Étape A - Classification
  └── Détecte type doc (déjà OK)

Étape B - Segmentation  
  └── Trouve sections (bilan/passif, CR, annexes)
  └── NEW: Découpe par section avant extraction

Étape C - Extraction Primaire
  ├── Méthode 1: Label direct (regex label:)
  ├── Méthode 2: Ligne tokenisée (tableaux)
  ├── Méthode 3: Section/table (lignes PCG)
  └── Sélectionne meilleure source

Étape D - Extraction Secondaire (Fallbacks)
  ├── Méthode 4: Calcul métier (actif=passif)
  ├── Méthode 5: Annexe/sous-lignes
  └── Méthode 6: Contexte élargi

Étape E - Validation Métier (RÈGLES DURES)
  ├── Bilan: actif == passif (tolérance 0.1%)
  ├── CR: REX → RC → RN cohérent
  ├── 2072: RB - FC - IE = RN
  ├── RB: solde_initial + crédits - débits = solde_final
  └── Immob: brut - amort = net

Étape F - Scoring Qualité
  ├── source_hint (label:, fallback:, derived:)
  ├── confidence (0.0 - 1.0)
  ├── is_suspicious (bool)
  └── is_derived (bool)

Étape G - Décision
  ├── ready_for_ai_core (champs critiques OK)
  ├── ready_for_ai (tout OK)
  └── needs_review (bloque si doute)
```

## Golden Set (à construire)

Pour chaque type :
- 50 docs propres (PDF natifs)
- 50 docs bruités (scans, OCR sale)
- 50 docs mixtes (formats variés)
- Annotation humaine des valeurs attendues
- Niveau de difficulté tagué

Structure par cas :
```
golden/cases/{type}/{case_name}/
  ├── input.txt          # Texte OCR
  ├── input.pdf          # PDF source (optionnel)
  ├── expected.min.json  # Valeurs attendues
  ├── meta.json          # Difficulté, source, tags
  └── annotations/       # Vérification humaine
```

## Tableau de Pilotage (à implémenter)

Mesures par type et par champ :

```python
{
  "bilan": {
    "precision_doc_type": 0.99,
    "champs": {
      "total_actif": {"precision": 0.98, "fallback_rate": 0.15},
      "total_passif": {"precision": 0.98, "fallback_rate": 0.15},
      "capitaux_propres": {"precision": 0.95, "fallback_rate": 0.05},
      "resultat_exercice": {"precision": 0.92, "fallback_rate": 0.25}
    },
    "taux_core_ready": 0.88,
    "taux_full_ready": 0.72,
    "top_erreurs": ["resultat_exercice", "creances", "disponibilites"]
  }
}
```

## Règles Métier à Durcir

### Bilan
- [ ] Équilibre actif/passif obligatoire (gap < 0.1%)
- [ ] Si déséquilibre > 1%, bloquer needs_review
- [ ] Vérifier cohérence capitaux_propres vs résultat

### Compte de Résultat
- [ ] Chaîne REX → RC → RN cohérente
- [ ] Tolerances: strict (250k) vs relaxed (500k)
- [ ] Détection auto des inversions N/N-1

### 2072 Foncier
- [ ] RB - FC - IE = RN (vérification stricte)
- [ ] Somme quote-parts = 100%
- [ ] Cohérence immeubles vs total

### Relevé Bancaire
- [ ] Équation solde: initial + crédits - débits = final
- [ ] Tolérance: max 0.01€
- [ ] Détection doublons

## Multi-Méthodes par Champ (à implémenter)

Pour chaque champ critique, avoir 3-5 méthodes :

Exemple: `resultat_exercice`
1. label: "résultat de l'exercice" (direct)
2. label: "résultat exercice" (plaquette)
3. label: "bénéfice/perte" (synonyme)
4. derived: calcul capitaux_propres - capital
5. derived: reprise annexes

Sélection: méthode avec plus haute confiance, marquer si fallback.

## Logique "Annex-First"

Quand disponible :
1. Vérifier annexe détaillée (plus fiable)
2. Si annexe OK, utiliser
3. Si annexe KO, fallback sur page principale
4. Marquer source: "annexe:" vs "principal:"

## Bloquer les Cas Douteux

Ne pas forcer l'extraction si :
- [ ] Coverage < 60%
- [ ] Balance gap > 1% (bilan)
- [ ] Chaîne CR incohérente
- [ ] Trop de suspicious_fields (>30%)
- [ ] OCR quality < threshold

## Boucle de Correction

Processus par itération :
1. Analyser top 10 erreurs du golden set
2. Identifier pattern commun
3. Patch minimal ciblé
4. Test sur cas golden concernés
5. Régression complète
6. Commit

## Métriques à Suivre

| Métrique | Cible | Actuel |
|----------|-------|--------|
| Précision champs critiques (Niveau 1) | 99% | ? |
| Précision champs critiques (Niveau 2) | 95-98% | ? |
| Taux Core Ready | 90% | ? |
| Taux Full Ready | 75% | ? |
| Fallback rate moyen | <10% | ? |
| Top erreur résolue par itération | - | - |

## Prochaines Actions Immédiates

1. [ ] Auditer golden set actuel (complétude)
2. [ ] Implémenter tableau de pilotage par champ
3. [ ] Durcir règles métier (équations)
4. [ ] Ajouter multi-méthodes pour champs critiques
5. [ ] Construire golden set manquant (50 docs/type)

## Principe Guidant

> "Mieux vaut 85% des documents très bien extraits que 100% des documents mal extraits."

Le 99% vient du refus de répondre sur les cas douteux + qualité sur les cas sûrs.
