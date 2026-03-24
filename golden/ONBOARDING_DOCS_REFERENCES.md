# Onboarding documents de reference (cabinet)

Objectif: transformer tes vrais documents comptables en cas Golden pour augmenter rapidement le taux `Core Ready` sur la realite terrain.

## 1) Ce que tu me donnes

Commence simple, 5 a 10 docs par type:

- `fiscal_2072`
- `bilan`
- `compte_resultat`
- `releve_bancaire`

Idealement, par type:

- 2-3 docs "propres"
- 2-3 docs "bruites" (scan, OCR imparfait, colonnes cassees)

## 2) Arborescence recommandee

Depose les nouveaux cas sous `golden/cases`:

```text
golden/cases/
  fiscal_2072/
    2072_real_01/
      input.txt
      expected.min.json
      meta.json
  bilan/
    bilan_real_01/
      input.txt
      expected.min.json
      meta.json
  compte_resultat/
    cr_real_01/
      input.txt
      expected.min.json
      meta.json
  releve_bancaire/
    releve_real_01/
      input.txt
      expected.min.json
      meta.json
```

## 3) Contenu de chaque fichier

### `input.txt`

Texte OCR/extrait du document (anonymise de preference).

### `meta.json` (template)

```json
{
  "id": "bilan_real_01",
  "requested_doc_type": "bilan",
  "source_filename": "BILAN_CLIENT_X_2024.pdf",
  "tags": ["real", "cabinet", "clean"],
  "notes": "Cas reel cabinet - bilan annuel",
  "active": true
}
```

### `expected.min.json` (template minimal)

```json
{
  "doc_type": "bilan",
  "extractor_name": "extractor_bilan",
  "critical_fields": {
    "total_actif": 1250000.0,
    "total_passif": 1250000.0,
    "capitaux_propres": 300000.0
  },
  "quality": {
    "critical_missing_fields": [],
    "quality_flags_must_include": [],
    "quality_flags_must_exclude": ["critical_fields_missing"],
    "needs_review": false,
    "ready_for_ai": true
  }
}
```

Tu peux commencer avec 3-5 champs critiques seulement. On enrichit ensuite.

## 4) Regles pratiques pour aller vite

- Si une valeur n'est pas fiable dans l'attendu: mets-la a `null`.
- Si tu veux juste valider un statut: renseigne surtout le bloc `quality`.
- Si un cas est en brouillon: `active=false` dans `meta.json`.

## 5) Commandes de validation

```bash
# Tous les cas actifs
python scripts/run_golden_v2.py

# Un cas specifique
python scripts/run_golden_v2.py --case-id bilan_real_01

# Inclure les brouillons
python scripts/run_golden_v2.py --include-inactive
```

## 6) Confidentialite / RGPD

- Priorite: documents deja anonymises.
- Sinon: pseudonymiser avant d'ajouter aux Golden.
- Ne jamais commiter de donnees brutes sensibles (emails, IBAN, noms complets non masques).

## 7) Plan de calibration recommande

1. Ajouter 3 cas reels par type (12 cas total)
2. Lancer Golden V2
3. Corriger les top 3 causes de FAIL
4. Re-lancer jusqu'a stabilisation
5. Cible initiale:
   - >= 80% `Core Ready` sur docs reels
   - 0 regression sur cas deja verts

