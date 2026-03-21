#!/usr/bin/env bash
set -euo pipefail

# Fast post-deploy regression for production/staging.
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

echo "==> health"
curl -sS "${CONFIDOC_BASE_URL%/}/health" >/dev/null

echo "==> readiness"
curl -sS "${CONFIDOC_BASE_URL%/}/readiness" >/dev/null

echo "==> extractor smoke matrix"
./scripts/extractor_smoke_matrix.sh

echo ""
echo "REGRESSION POST-DEPLOY: PASS"
