# Sources datasets shortlist (ConfiDoc)

Objectif: accelerer la montee en qualite sur 4 familles prioritaires.

- bilan
- compte_resultat
- fiscal_2072
- releve_bancaire

## Strategie de sourcing

Repartition recommandees des nouveaux cas Golden:

- 40% donnees cabinet reelles anonymisees (source de verite metier)
- 30% datasets publics HF/Kaggle (robustesse layout/OCR)
- 30% cas synthetiques controles (edge cases reproductibles)

## Priorite A (a integrer en premier)

### Hugging Face

1. `nielsr/funsd`
- Type: forms scannes bruites
- Apport: OCR degrade + champs semantiques + relations
- Mapping ConfiDoc:
  - fiscal_2072 noisy
  - releve_bancaire noisy
  - generic mixed pages

2. `HuggingFaceM4/DocumentVQA`
- Type: documents multi-layout + QA
- Apport: robustesse lecture zones/sections et textes heterogenes
- Mapping ConfiDoc:
  - bilan/CR mixed layouts
  - section-aware stress tests

3. `wkrl/cord` (CORD)
- Type: receipts avec structure lignes/labels
- Apport: extraction tabulaire/lignes et erreurs OCR en colonnes
- Mapping ConfiDoc:
  - releve_bancaire operations table (analogie structure)
  - facture/justificatifs supports

4. `philschmid/ocr-invoice-data`
- Type: factures/recus OCR
- Apport: bruit OCR realiste + montants + dates + entites
- Mapping ConfiDoc:
  - releve_bancaire noisy
  - compte_resultat fallback patterns

### Kaggle

1. Invoice/Receipt OCR datasets (mot-cles)
- `invoice ocr`, `receipt ocr`, `document layout analysis`
- Apport: grande diversite de scans reels et compressions

2. Financial statement datasets (mot-cles)
- `financial statement pdf`, `balance sheet extraction`, `income statement ocr`
- Apport: matiere proche bilan/CR

3. Bank statement OCR datasets (mot-cles)
- `bank statement extraction`, `transaction table parsing`, `statement OCR`
- Apport: cas cibles releve bancaire

## Priorite B (complement)

### Hugging Face

- `aharley/rvl_cdip`
  - Type: classification doc type
  - Usage: ameliorer routage amont (pas extraction champs directe)

- `lightonai/fc-amf-ocr`
  - Type: tres grand volume OCR docs FR
  - Usage: stress OCR et pretraitement

## Sources peu prioritaires pour ConfiDoc extraction

- UCI Machine Learning Repository
- Data.gov
- EU Open Data
- AWS/Azure Open Datasets (hors cas document OCR cible)
- World Bank / Quandl

Raison: excellentes pour analytics macro, faibles pour extraction PDF/scans comptables.

## Mapping dataset -> cas Golden a creer

Par lot de 20 nouveaux cas:

- 8 cas cabinet reels anonymises
- 6 cas HF/Kaggle noisy
- 4 cas multi-section mixes
- 2 cas extremes (OCR tres degrade / pages incompletes)

Exemple de tags dans `meta.json`:

- `["real","cabinet","bilan","clean"]`
- `["hf","docvqa","compte_resultat","noisy"]`
- `["kaggle","bank_statement","releve_bancaire","table_complex"]`
- `["synthetic","fiscal_2072","ocr_bad","multi_section"]`

## Criteres de qualite d'entree (gating dataset)

Un cas est retenu si:

1. le texte OCR est exploitable (au moins partiellement)
2. le type documentaire est identifiable
3. on peut definir des champs critiques attendus minimaux
4. le cas ajoute une difficulte nouvelle (pas un doublon)

Un cas est exclu si:

1. document illegible total sans valeur de test
2. metadata insuffisante pour verifier le resultat
3. licence ou usage ambigu pour test interne

## Workflow d'integration recommande

1. collecter 30 candidats (HF/Kaggle/reel)
2. pre-filtrer (gating ci-dessus)
3. conserver 20 cas
4. creer `meta.json`, `input.txt`, `expected.min.json` minimal
5. lancer `python scripts/run_golden_v2.py`
6. corriger top causes de review observees
7. promouvoir en `active: true` uniquement les cas stables

## KPI a suivre apres ajout de nouveaux datasets

- taux `ready_for_ai_core` par type
- taux `ready_for_ai` par type
- top `critical_missing_fields`
- top `quality_flags`
- variation de couverture moyenne (`coverage_ratio`)

Objectif: chaque vague de cas doit produire une amelioration mesurable, pas seulement du volume.
