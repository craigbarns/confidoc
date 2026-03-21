#!/usr/bin/env bash
set -euo pipefail

# Run compact smoke checks for V1 extractors only.
# Required env:
#   CONFIDOC_BASE_URL
#   CONFIDOC_EMAIL
#   CONFIDOC_PASSWORD
#   CONFIDOC_TEST_FILE_BILAN
#   CONFIDOC_TEST_FILE_COMPTE_RESULTAT
#   CONFIDOC_TEST_FILE_FISCAL_2072

for required in CONFIDOC_BASE_URL CONFIDOC_EMAIL CONFIDOC_PASSWORD \
  CONFIDOC_TEST_FILE_BILAN CONFIDOC_TEST_FILE_COMPTE_RESULTAT CONFIDOC_TEST_FILE_FISCAL_2072; do
  if [[ -z "${!required:-}" ]]; then
    echo "Erreur: variable d'environnement manquante: $required" >&2
    exit 1
  fi
done

DOC_TYPES=("bilan" "compte_resultat" "fiscal_2072")

for dt in "${DOC_TYPES[@]}"; do
  file=""
  case "$dt" in
    bilan) file="$CONFIDOC_TEST_FILE_BILAN" ;;
    compte_resultat) file="$CONFIDOC_TEST_FILE_COMPTE_RESULTAT" ;;
    fiscal_2072) file="$CONFIDOC_TEST_FILE_FISCAL_2072" ;;
    *)
      echo "Erreur: doc_type non supporte: $dt" >&2
      exit 1
      ;;
  esac
  if [[ ! -f "$file" ]]; then
    echo "Erreur: fichier introuvable pour $dt: $file" >&2
    exit 1
  fi
  echo ""
  echo "===== EXTRACTOR: $dt ====="
  echo "file: $file"
  CONFIDOC_TEST_FILE="$file" CONFIDOC_DOC_TYPE="$dt" ./scripts/e2e_smoke.sh --compact
done
