# PCG Engine — Plan Comptable Général Suggestion Engine

> Suggéreur de comptes comptables français, **explicable, déterministe et
> extensible**. Pas d'IA cachée derrière, pas de boîte noire.

## 1. Ce que fait le PCG Engine aujourd'hui (v1)

Le moteur prend en entrée :

- un **libellé** brut extrait d'un document (ex. *« Loyer local commercial mars 2026 »*)
- une **nature** (`charge`, `produit`, `autre`)

Il renvoie :

- une **suggestion principale** : code PCG à 6 chiffres + libellé
- **0..N alternatives** classées par confiance
- une **confidence** ∈ [0, 1]
- une **raison** courte et lisible
- une **source** identifiant pourquoi la suggestion a été produite :
  - `rule` — règle métier déclenchée (cas standard aujourd'hui)
  - `fallback_nature` — aucune règle, on retombe sur la nature (faible confidence)
  - `fallback_unknown` — aucun signal, compte d'attente 471000 (revue humaine)
  - `historical_similarity` — réservé : cf. roadmap §5
  - `llm_assisted` — réservé : cf. roadmap §5

### Catalogue v1 (19 règles)

Les règles vivent dans [`app/services/pcg_rules.py`](../app/services/pcg_rules.py)
et couvrent les 18 catégories prioritaires :

| Catégorie                          | Compte v1 | Notes                                          |
|------------------------------------|-----------|------------------------------------------------|
| Loyers                             | 613100    | Locations immobilières                         |
| Charges locatives / copropriété    | 614000    |                                                |
| Assurances                         | 616000    | Compagnies AXA / Allianz / etc. matchées       |
| Honoraires comptables              | 622600    | Expert-comptable, cabinet comptable            |
| Honoraires juridiques              | 622600    | Avocat, notaire, huissier                      |
| Honoraires divers                  | 622600    | Consulting / consultant / honoraires génériques|
| Frais bancaires                    | 627000    | Agios, tenue de compte, commissions            |
| Fournitures administratives        | 606400    | Papeterie, cartouches, ramettes                |
| Télécom / Internet                 | 626100    | Orange, SFR, Free Pro, fibre, ligne mobile     |
| Frais postaux                      | 626100    | La Poste, Chronopost, affranchissement         |
| Déplacements                       | 625100    | SNCF (billet), taxi, Uber, vol, hôtel, mission |
| Péages / parking                   | 625100    | Péage, parking, stationnement                  |
| Carburant                          | 606140    | Essence, gasoil, Total Energies, Shell, BP     |
| Restauration / Réception           | 625700    | Restaurant, brasserie, traiteur, réception     |
| Entretien / Réparation             | 615000    | Maintenance, dépannage, réparation             |
| Sous-traitance                     | 611000    | Sous-traitance, freelance, prestataire externe |
| Achats marchandises                | 607000    | Marchandises destinées à la revente            |
| Logiciels / SaaS                   | 651100    | Abonnements SaaS, licences logicielles         |
| Logiciels / SaaS (alt.)            | 622800    | Variante : pratique de certains cabinets       |
| Publicité / Marketing              | 623000    | Google Ads, Facebook Ads, campagne, annonce    |
| Cotisations professionnelles       | 628100    | Ordre des avocats / experts, syndicat, CCI     |

Une catégorie peut avoir plusieurs règles si plusieurs comptes sont
défendables ; le moteur surface alors l'un en principal et les autres en
alternatives, ce qui est la principale différence visible avec la v0.

## 2. Ce qu'il ne fait pas (encore)

- **Pas de LLM** dans la boucle. Aucun appel réseau, pas de dépendance
  externe (vérifié par `tests/unit/test_pcg_mapping_service.py::test_no_dependency_on_llm_or_network`).
- **Pas de mémoire**. Chaque appel est sans état : deux libellés identiques
  produisent toujours la même suggestion.
- **Pas d'apprentissage** automatique sur les corrections passées (cf. §5).
- **Pas de désambiguïsation contextuelle** (le moteur ne lit pas le reste du
  document, juste le libellé et la nature).

## 3. Pourquoi le moteur est explicable

Trois propriétés conçues pour passer un audit :

1. **Source identifiée** — chaque suggestion sait *pourquoi* elle a été
   produite (`rule`, `fallback_nature`, etc.). Une suggestion `rule` est
   reproductible ; une suggestion `fallback_unknown` invite explicitement à
   une revue humaine.
2. **Mots-clés matchés exposés** — `matched_keywords` indique exactement
   quels termes ont déclenché la règle. Pas de magie.
3. **Catalogue lisible** — `pcg_rules.py` est un fichier de données pur :
   un comptable peut le relire, valider, ouvrir une PR pour ajouter une
   règle, sans toucher au moteur.

## 4. Comment les GoldenCaseDraft alimenteront le moteur

Les `GoldenCaseDraft` (cf. [`docs/DATA_FLYWHEEL.md`](./DATA_FLYWHEEL.md))
capturent chaque correction humaine sous la forme :

```text
field_name + predicted_value + corrected_value + source_snippet + document_type
```

Quand le volume sera suffisant, on pourra construire un index de
similarité au-dessus des `corrected_value` acceptés. Le moteur PCG expose
déjà le hook nécessaire :

```python
from app.services.pcg_mapping_service import suggest, PcgSuggestion, PcgSource

def historical_lookup(libelle: str, nature: str) -> list[PcgSuggestion]:
    """À implémenter quand on aura assez de drafts acceptés."""
    ...

result = suggest("Loyer local mars", "charge", historical_lookup=historical_lookup)
```

Lorsque `historical_lookup` retourne une suggestion à confiance plus haute
qu'une règle, elle devient la suggestion principale (`source =
historical_similarity`) et la règle redescend en alternative. Si
`historical_lookup` lève une exception, le moteur retombe silencieusement
sur les règles : aucun risque pour les appels existants.

## 5. Roadmap

| Phase | Source                  | Description                                                                 | État |
|-------|-------------------------|-----------------------------------------------------------------------------|------|
| 1     | `rule`                  | Catalogue de règles métier déterministe. C'est l'état actuel.               | ✅    |
| 2     | `historical_similarity` | Reverse-lookup sur `GoldenCaseDraft` acceptés (similarité textuelle simple). | ⏳    |
| 3     | `historical_similarity` | Similarité sémantique (embeddings + index, ex. pgvector si trivial).        | ⏳    |
| 4     | `llm_assisted`          | Suggestion LLM **optionnelle**, derrière un feature flag, jamais obligatoire.| ⏳    |

Aucune phase ≥ 2 ne casse les appels existants : les nouvelles sources
viennent enrichir le pipeline, le fallback ultime reste les règles.

## 6. Compatibilité ascendante

L'entrée historique :

```python
from app.services.pcg_mapping_service import suggest_pcg_code

out = suggest_pcg_code(libelle, nature)   # {"code": "...", "label": "..."}
```

est **conservée à l'identique**. Le dict retourné contient désormais aussi
`confidence`, `reason`, `source`, `matched_keywords` et `alternatives`,
mais aucun de ces champs n'est requis : les anciens appels (`out["code"]`)
fonctionnent inchangés. Voir le test
`tests/unit/test_pcg_mapping_service.py::TestBackwardCompatibility`.

Pour les nouveaux appels, préférer :

```python
from app.services.pcg_mapping_service import suggest

result = suggest(libelle, nature)
result.suggestion       # PcgSuggestion
result.alternatives     # tuple[PcgSuggestion, ...]
result.to_dict()        # JSON-serialisable
```

## 7. Ajouter une règle

1. Ouvrir [`app/services/pcg_rules.py`](../app/services/pcg_rules.py).
2. Ajouter un `PcgRule(category=..., keywords=..., account=PcgAccount(code, label), base_confidence=..., reason=...)`.
3. Ajouter une ligne dans `coverage_samples` du test
   `TestRuleCatalog::test_all_required_categories_are_covered` si la
   catégorie est nouvelle.
4. `pytest tests/unit/test_pcg_mapping_service.py`.

Aucun changement dans le moteur lui-même n'est requis tant qu'on reste sur
le matching par mots-clés.
