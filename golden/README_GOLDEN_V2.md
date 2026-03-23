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

## Commande

Intégrer ces cas dans le runner golden pour obtenir:

- PASS/FAIL par cas
- diff lisible sur champs critiques/flags/statuts
