# Checklist Déploiement - Robustesse OCR

## Commits à déployer
```
62da1ee  fix(bilan): priorite TOTAL IMMOBILISATIONS
19371a6  fix(ocr): normalisation ciblée OCR
33602d4  test(golden): cas bilan cibles
4125dce  feat(golden): cas CR, 2072, Bilan
50598f3  feat(dashboard): tableau pilotage
```

## Smoke Tests Prod (à faire après deploy)

### 1. Test OCR dégradé
- [ ] Uploader bilan_ocr_stress_001
- [ ] Vérifier extraction: capitaux_propres = 156840
- [ ] Vérifier extraction: immobilisations = 260000

### 2. Test cas propre
- [ ] Uploader bilan_liasse_2050_001
- [ ] Vérifier Core Ready = true

### 3. Dashboard qualité
- [ ] Récupérer rapport: `/tmp/dashboard_report.json`
- [ ] Vérifier taux Core Ready Bilan > avant

## Métriques à mesurer

| Métrique | Avant | Après | Objectif |
|----------|-------|-------|----------|
| Core Ready Bilan | 55.6% | ? | > 60% |
| suspicious_fields moyen | 4-6 | ? | < 4 |
| capitaux_propres extrait | ~66% | ? | > 80% |

## Rollback
Si problème:
```bash
git revert 62da1ee 19371a6 --no-commit
git push origin main
```

## Validation finale
- [ ] 205 tests passent
- [ ] Dashboard montre amélioration
- [ ] Aucune régression critique
