# Plan d'execution Golden Set 60+ cas

Objectif: passer de 27 a 60+ cas sur les 4 familles prioritaires.

## Repartition cible

- bilan: 15
- compte_resultat: 15
- fiscal_2072: 15
- releve_bancaire: 15

Total: 60 cas

## Convention ID

Format:

`<doc_type>_<source>_<annee_or_split>_<index>`

Exemples:

- `bilan_hf_docvqa_train_001`
- `cr_hf_funsd_train_004`
- `fiscal_2072_cabinet_real_2024_003`
- `releve_bancaire_synth_noise_2026_006`

## Sources recommandees

- HF FUNSD: `nielsr/funsd`
- HF DocumentVQA: `HuggingFaceM4/DocumentVQA`
- HF CORD: `wkrl/cord`
- HF invoice OCR: `philschmid/ocr-invoice-data`
- Cabinet reel anonymise: donnees internes ConfiDoc
- Synth OCR degrade: generation locale (rotation, bruit, contraste, compression)

## Liste des 60 IDs proposes

### 1) Bilan (15)

1. `bilan_cabinet_real_2024_001`
2. `bilan_cabinet_real_2024_002`
3. `bilan_cabinet_real_2024_003`
4. `bilan_cabinet_real_2023_004`
5. `bilan_cabinet_real_2023_005`
6. `bilan_hf_docvqa_train_001`
7. `bilan_hf_docvqa_train_002`
8. `bilan_hf_docvqa_val_003`
9. `bilan_hf_funsd_train_004`
10. `bilan_hf_invoice_ocr_005`
11. `bilan_synth_noise_2026_006`
12. `bilan_synth_noise_2026_007`
13. `bilan_synth_multisection_2026_008`
14. `bilan_synth_ocr_bad_2026_009`
15. `bilan_cabinet_mixed_pages_2024_010`

### 2) Compte de resultat (15)

1. `cr_cabinet_real_2024_001`
2. `cr_cabinet_real_2024_002`
3. `cr_cabinet_real_2023_003`
4. `cr_cabinet_real_2023_004`
5. `cr_cabinet_real_2022_005`
6. `cr_hf_docvqa_train_001`
7. `cr_hf_docvqa_val_002`
8. `cr_hf_funsd_train_003`
9. `cr_hf_invoice_ocr_004`
10. `cr_hf_cord_train_005`
11. `cr_synth_noise_2026_006`
12. `cr_synth_noise_2026_007`
13. `cr_synth_multicolumn_2026_008`
14. `cr_synth_ocr_bad_2026_009`
15. `cr_cabinet_mixed_pages_2024_010`

### 3) Fiscal 2072 (15)

1. `fiscal_2072_cabinet_real_2024_001`
2. `fiscal_2072_cabinet_real_2024_002`
3. `fiscal_2072_cabinet_real_2023_003`
4. `fiscal_2072_cabinet_real_2023_004`
5. `fiscal_2072_cabinet_real_2022_005`
6. `fiscal_2072_hf_docvqa_train_001`
7. `fiscal_2072_hf_docvqa_val_002`
8. `fiscal_2072_hf_funsd_train_003`
9. `fiscal_2072_hf_invoice_ocr_004`
10. `fiscal_2072_hf_cord_train_005`
11. `fiscal_2072_synth_noise_2026_006`
12. `fiscal_2072_synth_noise_2026_007`
13. `fiscal_2072_synth_annex_shift_2026_008`
14. `fiscal_2072_synth_ocr_bad_2026_009`
15. `fiscal_2072_cabinet_mixed_pages_2024_010`

### 4) Releve bancaire (15)

1. `releve_bancaire_cabinet_real_2024_001`
2. `releve_bancaire_cabinet_real_2024_002`
3. `releve_bancaire_cabinet_real_2023_003`
4. `releve_bancaire_cabinet_real_2023_004`
5. `releve_bancaire_cabinet_real_2022_005`
6. `releve_bancaire_hf_docvqa_train_001`
7. `releve_bancaire_hf_docvqa_val_002`
8. `releve_bancaire_hf_funsd_train_003`
9. `releve_bancaire_hf_invoice_ocr_004`
10. `releve_bancaire_hf_cord_train_005`
11. `releve_bancaire_synth_noise_2026_006`
12. `releve_bancaire_synth_noise_2026_007`
13. `releve_bancaire_synth_balance_edge_2026_008`
14. `releve_bancaire_synth_ocr_bad_2026_009`
15. `releve_bancaire_cabinet_mixed_pages_2024_010`

## Matrice de difficulte (cible)

Par type (15 cas):

- 5 propres (clean)
- 5 bruites (ocr_noisy)
- 3 mixtes (multi_section / mixed_pages)
- 2 difficiles (ocr_bad / incomplete)

## Champs critiques minimaux par type

### Bilan

- total_actif
- total_passif
- capitaux_propres
- resultat_exercice
- dettes_financieres
- dettes_fournisseurs

### Compte de resultat

- chiffre_affaires
- charges_externes
- resultat_exploitation
- resultat_courant
- resultat_net

### Fiscal 2072

- denomination_sci
- date_cloture_exercice
- nombre_associes
- revenus_bruts
- frais_charges_hors_interets
- interets_emprunts
- revenu_net_foncier

### Releve bancaire

- periode_debut
- periode_fin
- solde_initial
- solde_final
- total_credits
- total_debits

## Regles readiness recommandees

- ready_for_ai: true si tous les champs critiques sont presents + checks coherence ok
- ready_for_ai_core: true si noyau metier present + checks majeurs ok
- needs_review: true si critical_missing_fields non vide ou quality_flags bloquants

## Execution en 3 vagues

### Vague A (Semaine 1): +12 cas

- 3 par type (mix clean + noisy)
- objectif: valider pipeline ingestion + expected.min.json

### Vague B (Semaines 2-3): +24 cas

- 6 par type
- focus: top causes de review (critical_missing, low_field_coverage, mismatch)

### Vague C (Semaines 4-5): +24 cas

- 6 par type
- focus: cas mixtes multi-sections + OCR difficile

## Definition of done (par cas)

Pour chaque ID:

1. `meta.json` present (id, requested_doc_type, tags, notes, active)
2. `input.txt` present
3. `expected.min.json` present avec champs critiques
4. passe `python scripts/run_golden_v2.py`
5. traceability: source + difficultes taggees

## Commandes utiles

Validation:

`python scripts/run_golden_v2.py`

Audit schema golden:

`pytest -q tests/golden/test_golden_json_schema.py`

## Priorite absolue

Commencer par les 12 cas Vague A, mesurer les flags dominants, corriger extracteurs, puis etendre.
