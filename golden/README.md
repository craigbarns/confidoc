# Golden sets ConfiDoc

## Rôle

Jeux de **référence** pour :

- documentation du **contrat métier** (champs attendus par type) ;
- validation **structurelle** (JSON Schema) ;
- futurs tests **extracteur vs `expected_api_subset`** (valeurs, avec tolérance).

**Aucun impact** sur le runtime API : fichiers statiques sauf si vous branchez des tests explicites.

## Fichiers

| Fichier | Description |
|---------|-------------|
| `golden_schema.json` | Schéma JSON Schema (draft-07) |
| `golden_sets.minimal.json` | Exemple **synthétique** sans PII (CI + doc) |
| `golden_sets.json` | *(optionnel)* Jeu complet — ne pas committer de données réelles non anonymisées |

## Structure d’une entrée

- **`doc_type`** : `bilan` \| `compte_resultat` \| `fiscal_2072` \| `etat_immobilisations`
- **`source_filename`** : nom du PDF de référence (traçabilité)
- **`golden_reference`** : vérité enrichie (`fields` avec `value` + `notes` optionnelles ; `tables` ; `metadata`)
- **`expected_api_subset`** : ce qu’on veut pouvoir comparer à l’API (`value`, `confidence`, `source`)

### Comparaison avec l’API réelle

L’export ConfiDoc utilise `source` du type `label:...`, pas `llm_golden_set`. Pour les tests automatiques futurs :

- comparer d’abord les **`value`** (avec tolérance sur floats) ;
- traiter `confidence` / `source` comme **non stricts** ou optionnels.

Le préfixe `golden:compare_value_only` dans l’exemple minimal indique cette intention.

### Types

Normaliser en tests : `exercice` peut être `2024` ou `"2024"` selon l’extracteur.

### `etat_immobilisations`

Non couvert par le **registry V1** : marquer `"target": "future_v2"` dans `metadata` et exclure des tests stricts jusqu’à extracteur dédié.

## Validation

**macOS (Homebrew) / PEP 668** : ne pas installer dans le Python système. Toujours activer un venv d’abord :

```bash
cd /chemin/vers/ConfiDoc
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Puis :

```bash
python scripts/validate_golden_sets.py golden/golden_sets.minimal.json
```

Sans venv, `pip install` peut échouer avec *externally-managed-environment*, et `ModuleNotFoundError: app` / `No module named pytest` apparaissent car les paquets ne sont pas installés pour cet interpréteur.

## Régression extraction (valeurs)

Le fichier **`regression_fixtures.json`** contient des textes synthétiques et un sous-ensemble de montants attendus. Les tests `tests/golden/test_golden_regression.py` appellent `build_structured_dataset` et comparent les **valeurs** (tolérance sur floats).

```bash
python scripts/run_golden_regression.py
pytest tests/golden/test_golden_regression.py -q
```

> Astuce : pour le bilan, les libellés `creances` / `disponibilites` sans accents sont plus fiables avec l’extracteur actuel (voir fixture).

## Anonymisation

Ne pas committer de noms / adresses réels. Utiliser des sociétés fictives et des identifiants stables (`ASSOCIE_1`, …).
