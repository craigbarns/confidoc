# ConfiDoc — Guide de test API (Beta)

Base URL (exemple) :

`https://confidoc-production.up.railway.app`

> **Sécurité** : ne commitez jamais d’identifiants réels. Utilisez des variables d’environnement ou des placeholders ci-dessous.

---

## 1) Login (obtenir un token)

Remplacez `VOTRE_EMAIL` et `VOTRE_MOT_DE_PASSE` par les identifiants fournis pour la beta (ou exportez `CONFIDOC_EMAIL` / `CONFIDOC_PASSWORD`).

```bash
curl -X POST "https://confidoc-production.up.railway.app/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"VOTRE_EMAIL","password":"VOTRE_MOT_DE_PASSE"}'
```

Réponse attendue :

- `access_token`
- `refresh_token`
- `token_type`

---

## 2) Vérifier l'accès API

```bash
curl "https://confidoc-production.up.railway.app/api/v1/documents" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

---

## 3) Upload d'un document

```bash
curl -X POST "https://confidoc-production.up.railway.app/api/v1/uploads?auto_anonymize=true&profile=dataset_accounting&document_type=auto" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -F "file=@/CHEMIN/vers/document.pdf"
```

Réponse attendue :

- `document_id`
- `processing.status`
- `processing.detections_count` (si auto anonymize)

---

## 4) Anonymiser manuellement (optionnel)

```bash
curl -X POST "https://confidoc-production.up.railway.app/api/v1/documents/DOCUMENT_ID/anonymize?profile=dataset_accounting&document_type=auto" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

---

## 5) Prévisualiser

```bash
curl "https://confidoc-production.up.railway.app/api/v1/documents/DOCUMENT_ID/preview" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

---

## 5b) Vider tous mes documents (bulk)

```bash
curl -X DELETE "$BASE_URL/api/v1/documents?confirm=true" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

Réponse JSON : `{"deleted": N}`. Sans `confirm=true` → erreur 400 (sécurité).

---

## 6) Valider

Corps JSON attendu : `doc_type`, `profile_used` (pour le suivi feedback). Valeurs par défaut côté API si corps vide ou `{}`.

```bash
curl -X POST "https://confidoc-production.up.railway.app/api/v1/documents/DOCUMENT_ID/validate" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"doc_type":"generic","profile_used":"dataset_accounting_pseudo","feedbacks":[]}'
```

---

## 7) Export dataset

```bash
curl "https://confidoc-production.up.railway.app/api/v1/documents/DOCUMENT_ID/export-dataset" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

---

## 8) Recherche dans la base anonyme (KB)

```bash
curl -X POST "https://confidoc-production.up.railway.app/api/v1/kb/search" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"charges marketing","limit":20,"include_needs_review":true}'
```

---

## 9) Script complet rapide (copier-coller)

Avant d’exécuter, définissez vos identifiants dans le shell (ne les mettez pas dans le dépôt Git) :

```bash
export CONFIDOC_EMAIL="votre.email@exemple.com"
export CONFIDOC_PASSWORD="votre_mot_de_passe"
```

```bash
BASE="https://confidoc-production.up.railway.app"
FILE="/CHEMIN/vers/document.pdf"

TOKEN=$(curl -s -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$CONFIDOC_EMAIL\",\"password\":\"$CONFIDOC_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

UPLOAD=$(curl -s -X POST "$BASE/api/v1/uploads?auto_anonymize=true&profile=dataset_accounting&document_type=auto" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$FILE")

DOC_ID=$(echo "$UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")

echo "DOC_ID=$DOC_ID"

curl -s "$BASE/api/v1/documents/$DOC_ID/export-dataset" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 10) Retour testeur (template)

- Testeur:
- Date/heure:
- Endpoint testé:
- Payload:
- Résultat attendu:
- Résultat obtenu:
- Status code:
- Réponse API:
- Capture écran/log:
