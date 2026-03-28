# Checklist de déploiement Railway - ConfiDoc

**Walkthrough technique (routes API, EntityRegistry, endpoint `/structured`) :** voir [`WALKTHROUGH.md`](./WALKTHROUGH.md).

## 🚀 Configuration du déploiement

### Variables d'environnement requises

```bash
# Base de données
DATABASE_URL=postgresql://...

# Sécurité (à vérifier avant déploiement)
SECRET_KEY=<prod_key>
JWT_SECRET_KEY=<prod_key>
ENCRYPTION_MASTER_KEY=<prod_key>

# LLM (optionnel mais recommandé)
MISTRAL_API_KEY=<key>
MISTRAL_ENABLED=true
OLLAMA_ENABLED=false

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=production
```

### Configuration Railway

```yaml
# railway.yml (déjà présent)
services:
  web:
    build:
      dockerfile: Dockerfile
    healthcheck:
      path: /health
      port: 8000
```

---

## 🔬 Smoke Tests de pré-production

### 1. Bilan réel

**Endpoint:** `POST /api/v1/documents/{id}/export-structured-dataset?doc_type=bilan`

**Vérifications:**
```json
{
  "quality": {
    "ready_for_ai_core": "true si champs critiques présents",
    "ready_for_ai": "true si coverage >= 75%",
    "bilan_balance_gap": "< 500 ou < 3% du total",
    "critical_missing_fields": "[]"
  },
  "fields": {
    "total_actif.value": "présent et cohérent",
    "total_passif.value": "présent et cohérent",
    "immobilisations.source_hint": "ne commence pas par 'fallback:' si possible"
  }
}
```

**Script de test:**
```bash
curl -X POST \
  "https://$RAILWAY_URL/api/v1/documents/$DOC_ID/export-structured-dataset?doc_type=bilan" \
  -H "Authorization: Bearer $TOKEN" | jq '.quality'
```

### 2. Compte de Résultat (CR)

**Vérifications:**
```json
{
  "quality": {
    "result_chain_consistent": "true",
    "cr_chain_delta_rex_rc": "< tolérance calculée",
    "total_produits.value": "extrait ou calculé",
    "total_charges.value": "extrait ou calculé"
  }
}
```

**Tolérances attendues selon CA:**
- CA < 1M€: delta < 100k
- CA 1-10M€: delta < 250k
- CA > 10M€: delta < 500k

### 3. Formulaire 2072

**Vérifications RGPD:**
```json
{
  "fields": {
    "denomination_sci.value": "SOCIETE_1 ou pseudonymisé",
    "adresse_sci.value": "null ou ADRESSE_SOCIETE_1"
  },
  "quality": {
    "arithmetic_consistency_ok": "RB - FC - IE ≈ RN"
  }
}
```

**Vérification pas de PII:**
```bash
curl -s ... | grep -iE "(baranes|dupont|gregory|@|06[0-9])" && echo "FAIL" || echo "OK"
```

### 4. Relevé Bancaire

**Vérifications:**
```json
{
  "quality": {
    "dates_ok": "true si période présente",
    "balance_ok": "solde_final ≈ solde_initial + crédits - débits",
    "parsed_lines_ratio": ">= 0.7"
  }
}
```

**⚠️ Attention:** Si `dates_ok = false`, vérifier que c'est bien dû à des dates de période manquantes (pas un bug)

### 5. Export structuré anonymisé

**Vérifications RGPD strictes:**
```bash
# Test complet
curl -s "$API/export-structured-dataset?doc_type=bilan" | python3 << 'PYEOF'
import json, sys, re

data = json.load(sys.stdin)
result = json.dumps(data)

# Patterns PII à bannir
patterns = [
    (r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', 'email'),
    (r'\b0\d{9}\b', 'phone'),
    (r'\bFR\d{2}[\s]?[0-9]{4}', 'iban'),
    (r'BARANES|DUPONT|MARTIN', 'nom'),
]

errors = []
for pattern, pii_type in patterns:
    if re.search(pattern, result, re.IGNORECASE):
        errors.append(f"PII detected: {pii_type}")

if errors:
    print("FAIL:", errors)
    sys.exit(1)
else:
    print("OK - No PII detected")
PYEOF
```

---

## 📊 Vérifications UI

### Badges de confiance

**À vérifier dans le navigateur:**
1. Charger un document bilan
2. Vérifier que le tableau des champs s'affiche
3. Confirmer les badges:
   - ✓ vert pour >85%
   - ~ violet pour 70-85%
   - ⚠️ orange pour <70%
4. Vérifier que les champs calculés ont un fond orange
5. Survoler un badge pour voir la source traduite

### Headline amélioré

**Format attendu:**
```
✓ Bilan équilibré · 8/9 champs extraits · 2 champs à vérifier
```

Ou si problème:
```
⚠️ Bilan déséquilibré · 5/9 champs extraits · 3 critiques manquants
```

### Status-summary cohérent

**Endpoint:** `GET /api/v1/documents/status-summary`

**Vérifications:**
```json
{
  "buckets": {
    "full_ready": "documents avec ready_for_ai=true",
    "core_ready": "documents avec ready_for_ai_core=true mais pas full",
    "needs_review": "documents avec needs_review=true"
  }
}
```

**Cohérence:** `full_ready + core_ready + needs_review ≈ total_docs`

---

## ⚡ Commandes de déploiement Railway

### 1. Créer la PR

```bash
# Sur GitHub
git push origin feat/5-phases-extraction-quality-20250325

# Créer PR via GitHub CLI
gh pr create \
  --title "feat: 5 phases amélioration extraction et qualité" \
  --body-file RAPPORT_5_PHASES_20250325.md \
  --base main
```

### 2. Déploiement staging

```bash
# Railway CLI
railway login
railway link

# Déployer la branche
railway up --environment=staging

# Vérifier le healthcheck
railway status
```

### 3. Tests sur staging

```bash
# Test health
curl https://$STAGING_URL/health

# Test auth
curl -X POST https://$STAGING_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"test"}'

# Run smoke tests
./scripts/smoke_tests.sh $STAGING_URL $TOKEN
```

### 4. Déploiement production

```bash
# Merge PR sur GitHub
gh pr merge --squash --delete-branch

# Railway déploie automatiquement main
railway status --environment=production

# Vérifier les logs
railway logs --environment=production
```

---

## 🔥 Rollback

### Si problème détecté

```bash
# Rollback immédiat via Railway
railway rollback --environment=production

# Ou via Git
# Revert le commit sur main
git revert c19c6f2
git push origin main
```

### Points de contrôle avant rollback

- [ ] Erreurs 500 > 5% des requêtes
- [ ] Latence extraction > 30s (médiane)
- [ ] Fuite PII confirmée
- [ ] UI cassée (badges non affichés)

---

## 📈 Monitoring post-déploiement

### Métriques à surveiller (30 min après déploiement)

```bash
# Logs erreurs
railway logs --environment=production | grep -i error

# Métriques qualité
# Via le dashboard ou API:
curl "https://$PROD_URL/api/v1/documents/status-summary?days=1"
```

**Seuils d'alerte:**
- Erreurs 5xx: > 1%
- Temps extraction: > 10s (p95)
- Ready for AI: variation > -10%

### Alertes Slack/Discord

Configurer webhook pour:
- Déploiement réussi
- Erreurs 500
- Temps réponse > 5s

---

## ✅ Sign-off

**Avant déploiement prod, confirmer:**

- [ ] Smoke tests staging passent (5/5)
- [ ] Aucune fuite PII détectée
- [ ] UI badges OK
- [ ] Status-summary cohérent
- [ ] Pas de régression sur tests existants (215/215)
- [ ] Variables d'environnement prod vérifiées
- [ ] Rollback plan connu

**Sign-off par:**
- [ ] Développeur (Gregory)
- [ ] Review code (pair)
- [ ] QA smoke tests (automatisé)

---

*Checklist générée le 25 mars 2025*
*Version: 1.0*
