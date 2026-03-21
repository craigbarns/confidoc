#!/usr/bin/env bash
set -euo pipefail

# ConfiDoc E2E smoke test
# Flux:
# 1) login
# 2) upload
# 3) polling processing -> ready (via /preview disponible)
# 4) preview
# 5) validate (feedback humain)
# 6) audit export
# 7) structured dataset export
# 8) feedback stats (dataset-summary)

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Erreur: commande manquante: $1" >&2
    exit 1
  }
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Erreur: variable d'environnement manquante: $name" >&2
    exit 1
  fi
}

json_get() {
  local json_file="$1"
  local expr="$2"
  python3 - "$json_file" "$expr" <<'PY'
import json
import sys

path = sys.argv[1]
expr = sys.argv[2]

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

cur = data
for part in expr.split("."):
    if part == "":
        continue
    if isinstance(cur, dict):
        cur = cur.get(part)
    else:
        cur = None
        break

if cur is None:
    print("")
elif isinstance(cur, (dict, list)):
    print(json.dumps(cur, ensure_ascii=False))
else:
    print(cur)
PY
}

http_json() {
  local method="$1"
  local url="$2"
  local out="$3"
  local auth="${4:-}"
  local data_file="${5:-}"
  local form_file="${6:-}"

  local headers=(-H "Accept: application/json")
  if [[ -n "$auth" ]]; then
    headers+=(-H "Authorization: Bearer $auth")
  fi

  local code
  if [[ -n "$form_file" ]]; then
    code="$(curl -sS -X "$method" "$url" \
      "${headers[@]}" \
      -F "file=@${form_file}" \
      -o "$out" -w "%{http_code}")"
  elif [[ -n "$data_file" ]]; then
    code="$(curl -sS -X "$method" "$url" \
      "${headers[@]}" \
      -H "Content-Type: application/json" \
      --data "@${data_file}" \
      -o "$out" -w "%{http_code}")"
  else
    code="$(curl -sS -X "$method" "$url" \
      "${headers[@]}" \
      -o "$out" -w "%{http_code}")"
  fi
  echo "$code"
}

cleanup() {
  if [[ -n "${TMP_DIR:-}" && -d "${TMP_DIR:-}" ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

require_cmd curl
require_cmd python3

require_env CONFIDOC_BASE_URL
require_env CONFIDOC_EMAIL
require_env CONFIDOC_PASSWORD

BASE_URL="${CONFIDOC_BASE_URL%/}"
PROFILE="${CONFIDOC_PROFILE:-dataset_accounting_pseudo}"
DOC_TYPE="${CONFIDOC_DOC_TYPE:-auto}"
TIMEOUT_SECONDS="${CONFIDOC_POLL_TIMEOUT_SECONDS:-90}"
POLL_INTERVAL_SECONDS="${CONFIDOC_POLL_INTERVAL_SECONDS:-3}"
COMPACT_MODE="${CONFIDOC_COMPACT:-0}"
if [[ "${1:-}" == "--compact" ]]; then
  COMPACT_MODE="1"
fi

TMP_DIR="$(mktemp -d)"
LOGIN_JSON="$TMP_DIR/login.json"
LOGIN_PAYLOAD="$TMP_DIR/login_payload.json"
UPLOAD_JSON="$TMP_DIR/upload.json"
ANON_JSON="$TMP_DIR/anonymize.json"
PREVIEW_JSON="$TMP_DIR/preview.json"
VALIDATE_JSON="$TMP_DIR/validate.json"
AUDIT_JSON="$TMP_DIR/audit.json"
STRUCTURED_JSON="$TMP_DIR/structured.json"
SUMMARY_JSON="$TMP_DIR/dataset_summary.json"

if [[ -n "${CONFIDOC_TEST_FILE:-}" ]]; then
  TEST_FILE="$CONFIDOC_TEST_FILE"
else
  TEST_FILE="$TMP_DIR/smoke.png"
  # 1x1 PNG valide (evite les erreurs de parsing PDF en smoke test)
  python3 - "$TEST_FILE" <<'PY'
import base64
import sys

png_b64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAA"
    "AAC0lEQVR42mP8/x8AAwMCAO7Zx6sAAAAASUVORK5CYII="
)
with open(sys.argv[1], "wb") as f:
    f.write(base64.b64decode(png_b64))
PY
fi

if [[ ! -f "$TEST_FILE" ]]; then
  echo "Erreur: fichier de test introuvable: $TEST_FILE" >&2
  exit 1
fi

echo "==> 1) Login"
cat > "$LOGIN_PAYLOAD" <<EOF
{"email":"$CONFIDOC_EMAIL","password":"$CONFIDOC_PASSWORD"}
EOF
code="$(http_json "POST" "$BASE_URL/api/v1/auth/login" "$LOGIN_JSON" "" "$LOGIN_PAYLOAD")"
if [[ "$code" != "200" ]]; then
  echo "Echec login (HTTP $code)"
  cat "$LOGIN_JSON"
  exit 1
fi
TOKEN="$(json_get "$LOGIN_JSON" "access_token")"
if [[ -z "$TOKEN" ]]; then
  echo "Echec: access_token absent dans la reponse login"
  cat "$LOGIN_JSON"
  exit 1
fi

echo "==> 2) Upload"
UPLOAD_URL="$BASE_URL/api/v1/uploads?auto_anonymize=true&profile=$PROFILE&document_type=$DOC_TYPE"
code="$(http_json "POST" "$UPLOAD_URL" "$UPLOAD_JSON" "$TOKEN" "" "$TEST_FILE")"
if [[ "$code" != "201" ]]; then
  echo "Echec upload (HTTP $code)"
  [[ -f "$UPLOAD_JSON" ]] && cat "$UPLOAD_JSON"
  exit 1
fi
DOCUMENT_ID="$(json_get "$UPLOAD_JSON" "document_id")"
if [[ -z "$DOCUMENT_ID" ]]; then
  echo "Echec: document_id absent apres upload"
  cat "$UPLOAD_JSON"
  exit 1
fi
echo "Document ID: $DOCUMENT_ID"

echo "==> 3) Preview check / anonymize si necessaire"
code="$(http_json "GET" "$BASE_URL/api/v1/documents/$DOCUMENT_ID/preview" "$PREVIEW_JSON" "$TOKEN")"
if [[ "$code" == "200" ]]; then
  echo "Preview deja disponible apres upload (anonymize saute)."
else
  ANON_URL="$BASE_URL/api/v1/documents/$DOCUMENT_ID/anonymize?profile=$PROFILE&document_type=$DOC_TYPE"
  code="$(http_json "POST" "$ANON_URL" "$ANON_JSON" "$TOKEN")"
  if [[ "$code" != "200" ]]; then
    echo "Anonymize a repondu HTTP $code, tentative de recuperation via preview..."
    code="$(http_json "GET" "$BASE_URL/api/v1/documents/$DOCUMENT_ID/preview" "$PREVIEW_JSON" "$TOKEN")"
    if [[ "$code" != "200" ]]; then
      echo "Echec anonymize (HTTP ${code}) et preview indisponible."
      echo "Reponse anonymize:"
      cat "$ANON_JSON"
      echo ""
      echo "Reponse preview:"
      cat "$PREVIEW_JSON"
      exit 1
    fi
  fi
fi

echo "==> 4) Poll processing -> ready (preview disponible)"
deadline=$((SECONDS + TIMEOUT_SECONDS))
preview_ok="false"
while (( SECONDS < deadline )); do
  code="$(http_json "GET" "$BASE_URL/api/v1/documents/$DOCUMENT_ID/preview" "$PREVIEW_JSON" "$TOKEN")"
  if [[ "$code" == "200" ]]; then
    preview_ok="true"
    break
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done
if [[ "$preview_ok" != "true" ]]; then
  echo "Echec: preview indisponible avant timeout (${TIMEOUT_SECONDS}s)"
  cat "$PREVIEW_JSON"
  exit 1
fi
echo "Preview OK"

echo "==> 5) Preview"
PREVIEW_DETECTIONS="$(json_get "$PREVIEW_JSON" "detections_count")"
echo "detections_count: ${PREVIEW_DETECTIONS:-n/a}"

echo "==> 6) Validate (feedback humain)"
code="$(http_json "POST" "$BASE_URL/api/v1/documents/$DOCUMENT_ID/validate" "$VALIDATE_JSON" "$TOKEN")"
if [[ "$code" != "200" ]]; then
  echo "Echec validate (HTTP $code)"
  cat "$VALIDATE_JSON"
  exit 1
fi

echo "==> 7) Audit export"
code="$(http_json "GET" "$BASE_URL/api/v1/documents/$DOCUMENT_ID/audit-export" "$AUDIT_JSON" "$TOKEN")"
if [[ "$code" != "200" ]]; then
  echo "Echec audit-export (HTTP $code)"
  cat "$AUDIT_JSON"
  exit 1
fi

echo "==> 8) Structured dataset"
code="$(http_json "GET" "$BASE_URL/api/v1/documents/$DOCUMENT_ID/export-structured-dataset?doc_type=auto" "$STRUCTURED_JSON" "$TOKEN")"
if [[ "$code" != "200" ]]; then
  echo "Echec export-structured-dataset (HTTP $code)"
  cat "$STRUCTURED_JSON"
  exit 1
fi

echo "==> 9) Feedback stats (dataset-summary)"
code="$(http_json "GET" "$BASE_URL/api/v1/documents/$DOCUMENT_ID/dataset-summary" "$SUMMARY_JSON" "$TOKEN")"
if [[ "$code" != "200" ]]; then
  echo "Echec dataset-summary (HTTP $code)"
  cat "$SUMMARY_JSON"
  exit 1
fi

READY_FOR_AI="$(json_get "$SUMMARY_JSON" "quality.ready_for_ai")"
NEEDS_REVIEW="$(json_get "$SUMMARY_JSON" "quality.needs_review")"
DETECTIONS_COUNT="$(json_get "$SUMMARY_JSON" "quality.detections_count")"
QUALITY_FLAGS="$(json_get "$SUMMARY_JSON" "quality.quality_flags")"
DOC_TYPE_OUT="$(json_get "$STRUCTURED_JSON" "detected_doc_type")"
COVERAGE_RATIO="$(json_get "$STRUCTURED_JSON" "quality.coverage_ratio")"
CRITICAL_MISSING_FIELDS="$(json_get "$STRUCTURED_JSON" "quality.critical_missing_fields")"
ROUTING_CONFIDENCE="$(json_get "$STRUCTURED_JSON" "routing_confidence")"

if [[ "$COMPACT_MODE" == "1" ]]; then
  echo ""
  echo "PASS"
  echo "doc_type: ${DOC_TYPE_OUT:-unknown}"
  echo "needs_review: ${NEEDS_REVIEW:-unknown}"
  echo "coverage_ratio: ${COVERAGE_RATIO:-unknown}"
  echo "quality_flags: ${QUALITY_FLAGS:-unknown}"
else
  echo ""
  echo "===== E2E SMOKE SUCCESS ====="
  echo "base_url: $BASE_URL"
  echo "document_id: $DOCUMENT_ID"
  echo "detected_doc_type: ${DOC_TYPE_OUT:-unknown}"
  echo "detections_count: ${DETECTIONS_COUNT:-unknown}"
  echo "needs_review: ${NEEDS_REVIEW:-unknown}"
  echo "quality_flags: ${QUALITY_FLAGS:-unknown}"
  echo "critical_missing_fields: ${CRITICAL_MISSING_FIELDS:-unknown}"
  echo "coverage_ratio: ${COVERAGE_RATIO:-unknown}"
  echo "routing_confidence: ${ROUTING_CONFIDENCE:-unknown}"
  echo "ready_for_ai: ${READY_FOR_AI:-unknown}"
  echo "============================="
fi
