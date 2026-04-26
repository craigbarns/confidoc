# ConfiDoc Cabinet API

Guide rapide pour envoyer des documents sans passer par l'interface.

## 1. Creer une cle API

Connectez-vous une fois avec un compte cabinet, puis creez une cle.

```bash
BASE="https://confidoc-production.up.railway.app/api/v1"

TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"cabinet@example.com","password":"***"}' \
  | jq -r .access_token)

curl -s -X POST "$BASE/integrations/api-keys" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"ERP cabinet","scopes":["documents:read","documents:write","ai:read"]}'
```

La reponse contient `api_key`. Elle est affichee une seule fois.

## 2. Envoyer un document comptable

```bash
API_KEY="confidoc_live_..."

curl -s -X POST "$BASE/uploads?auto_anonymize=true&profile=dataset_accounting_pseudo&document_type=accounting&client_name=WEMADE" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Idempotency-Key: wemade-2024-liasse-v1" \
  -F "file=@plaquette_wemade.pdf"
```

Parametres recommandes pour cabinets :

- `client_name` : obligatoire, nom dossier/client.
- `document_type=accounting` : active les protections comptables.
- `profile=dataset_accounting_pseudo` : pseudonymisation stable pour travailler dans le dossier.
- `profile=dataset_accounting` : anonymisation plus stricte si vous ne voulez pas de pseudonymes metier.
- `Idempotency-Key` : evite les doublons si votre ERP retente le meme upload.

## 3. Suivre le traitement

```bash
DOC_ID="..."

curl -s -H "Authorization: Bearer $API_KEY" \
  "$BASE/documents/$DOC_ID/status"
```

Quand `anonymization.done=true`, vous pouvez recuperer les sorties.

```bash
curl -s -H "Authorization: Bearer $API_KEY" \
  "$BASE/documents/$DOC_ID/structured?include_text=true"

curl -s -X POST -H "Authorization: Bearer $API_KEY" \
  "$BASE/ai/summary/$DOC_ID?mode=review"

curl -s -H "Authorization: Bearer $API_KEY" \
  "$BASE/documents/$DOC_ID/audit-report-pdf" \
  -o audit.pdf
```

## 4. Recevoir un webhook `document.ready`

```bash
curl -s -X POST "$BASE/integrations/webhooks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"ERP cabinet",
    "url":"https://erp.example.com/webhooks/confidoc",
    "events":["document.ready","document.failed","document.validated"]
  }'
```

ConfiDoc signe chaque payload avec :

- `X-ConfiDoc-Event`
- `X-ConfiDoc-Signature: sha256=<hmac_sha256>`

Le HMAC est calcule sur le corps JSON brut avec le `signing_secret` retourne a la creation du webhook.

Payload type :

```json
{
  "event": "document.ready",
  "event_id": "unique",
  "created_at": "2026-04-26T12:00:00+00:00",
  "document": {
    "id": "uuid",
    "status": "ready",
    "client_name": "WEMADE",
    "original_filename": "plaquette_wemade.pdf",
    "sha256": "...",
    "size_bytes": 123456
  },
  "links": {
    "status": "https://.../api/v1/documents/{id}/status",
    "preview": "https://.../api/v1/documents/{id}/preview",
    "structured": "https://.../api/v1/documents/{id}/structured?include_text=true",
    "audit_report_pdf": "https://.../api/v1/documents/{id}/audit-report-pdf"
  }
}
```

## 5. Endpoints utiles

- `POST /api/v1/integrations/api-keys` : creer une cle API.
- `GET /api/v1/integrations/api-keys` : lister les cles.
- `DELETE /api/v1/integrations/api-keys/{id}` : revoquer une cle.
- `POST /api/v1/integrations/webhooks` : creer un webhook.
- `POST /api/v1/integrations/webhooks/{id}/test` : envoyer un test.
- `POST /api/v1/uploads` : upload document.
- `POST /api/v1/uploads/batch` : upload batch, max 20 fichiers.
- `GET /api/v1/documents/{id}/status` : etat OCR/anonymisation.
- `GET /api/v1/documents/{id}/structured?include_text=true` : document anonymise structure.
