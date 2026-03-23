# Golden set v2 (templates)

Ce dossier contient 9 templates de cas golden (3 par type):

- `bilan`
- `compte_resultat`
- `fiscal_2072`

## Structure d'un cas

- `input.txt`: texte OCR / texte extrait utilisé comme entrée
- `expected.min.json`: attendu minimal (champs critiques + qualité)
- `meta.json`: metadata du cas (id, tags, source)

## Règle de comparaison recommandée

Comparer seulement:

1. `doc_type`
2. `extractor_name` (si fourni)
3. `critical_fields`
4. `quality.critical_missing_fields`
5. `quality_flags_must_include` / `quality_flags_must_exclude`
6. `needs_review`, `ready_for_ai`, `ready_for_ai_core`

## Commande (runner V2)

```bash
python scripts/run_golden_v2.py
```

Exemples utiles:

```bash
# Un seul cas
python scripts/run_golden_v2.py --case-id 2072_clean_01

# Racine personnalisée
python scripts/run_golden_v2.py --cases-root golden/cases
```

```bash
# Inclure aussi les templates/drafts (meta.active=false)
python scripts/run_golden_v2.py --include-inactive
```

Sortie:

- PASS/FAIL par cas
- diff lisible sur champs critiques, flags qualite et statuts

## OCR stress imports (Hugging Face)

Pour enrichir la robustesse OCR/parsing avec des cas non-métier:

```bash
python scripts/import_hf_ocr_to_golden.py --rows-per-source 8
```

Ce script:

- crée des cas `golden/cases/ocr_stress/*`,
- les marque en `active=false` (drafts non bloquants pour CI),
- génère `golden/OCR_HF_IMPORT_REPORT.md`.

Inspection des drafts:

```bash
python scripts/run_golden_v2.py --include-inactive
```

## Curation "top cas" OCR stress

Analyser et scorer les cas OCR stress:

```bash
python scripts/curate_ocr_stress_golden.py
```

Promouvoir automatiquement un sous-ensemble (active=true + expected minimal):

```bash
python scripts/curate_ocr_stress_golden.py --promote --max-total 12 --max-per-source 4
```
