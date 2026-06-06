# AI Security

Ce document decrit le flux OCR -> anonymisation -> analyse IA de ConfiDoc et les garde-fous pour les clients sensibles.

## Principe directeur

ConfiDoc doit traiter les documents originaux comme des donnees hautement sensibles. L'analyse IA exploitable par un client ou un export doit etre rattachee a une version anonymisee ou pseudonymisee, avec audit trail, score de risque et validation humaine lorsque le risque est eleve.

## Flux OCR

1. Le fichier est uploade par un utilisateur authentifie et rattache a une organisation.
2. Le backend valide l'extension, limite la taille, calcule un SHA-256 et declenche un scan sandbox.
3. Le fichier est stocke via `storage_service`.
4. En production Railway, `STORAGE_BACKEND=local` est bloque au demarrage. Utiliser S3/R2/MinIO ou, en phase pilote, `database`.
5. L'OCR extrait une version texte `ORIGINAL_TEXT`.
6. L'etape est journalisee avec metadata minimisee, sans contenu brut.

## Flux anonymisation

1. La version `ORIGINAL_TEXT` est traitee par les detecteurs deterministes et, uniquement sur opt-in explicite, par le service LLM d'anonymisation.
2. Une version `PREVIEW_ANONYMIZED` est produite.
3. Les entites detectees sont stockees avec type, positions et remplacement.
4. Une version `FINAL_ANONYMIZED` est creee apres validation humaine ou lors de l'export si la preview est disponible.
5. Le scoring RGPD et le Trust Score / AI Readiness Score sont calcules sur les signaux disponibles.

## Flux analyse IA

Les services d'analyse structuree doivent consommer le texte anonymise:

- `export-fec` appelle l'extraction LLM sur `_get_anonymized_text`.
- `compliance-report` envoie uniquement un extrait anonymise au LLM narratif optionnel.
- `compare` compare deux textes anonymises.

Les endpoints qui exposent du contenu original (`raw`, `extracted-text`) exigent la permission `documents.raw`.

## Fournisseurs externes

Selon la configuration:

- Mistral OCR peut recevoir le fichier ou le contenu source necessaire a l'OCR.
- Mistral LLM peut recevoir du texte brut pour anonymisation uniquement si `LLM_RAW_ANONYMIZATION_ENABLED=true`, `MISTRAL_ENABLED=true` et une cle API sont configures. Par defaut, ce chemin est desactive et l'anonymisation retombe sur le moteur local deterministe.
- Les analyses post-anonymisation doivent recevoir une version anonymisee.

En mode client sensible, la recommandation est:

- `SENSITIVE_CLIENT_MODE=true` pour bloquer les appels Mistral OCR/LLM non essentiels au niveau applicatif.
- `MISTRAL_ENABLED=false` par defaut.
- `LLM_RAW_ANONYMIZATION_ENABLED=false` pour interdire l'envoi de texte source brut a un LLM externe.
- OCR local ou fournisseur avec DPA, region UE et retention desactivee contractuellement.
- Anonymisation deterministe locale pour les documents les plus sensibles.
- Activation LLM uniquement apres validation DPO/RSSI et documentation du sous-traitant.

## Prompts et donnees sensibles

Les prompts ne doivent pas inclure de secrets, tokens, mots de passe ou cles API. Les erreurs LLM ne doivent jamais logger de texte retourne par le fournisseur. Les parse failures journalisent uniquement:

- `response_sha256`
- `response_chars`

Les contenus, snippets, valeurs originales et mappings sont interdits dans les logs applicatifs et l'audit trail.

## Garde-fous actuels

- RBAC document par document et organisation par organisation.
- Permissions separees: `documents.read`, `documents.raw`, `documents.process`, `documents.validate`, `exports.download`, `audit.read`.
- Logs LLM sans extrait brut.
- AI Firewall sur PII residuelle en prompt sortant et reponse entrante.
- Audit trail avec sanitization des metadata sensibles et `event_hash`.
- Export gate sur risque de reidentification critique ou eleve non valide.
- Content-Disposition securise pour les telechargements.
- Production blocked si secrets par defaut ou stockage local.

## Risques restants

- Le mode anonymisation LLM brut est desactive par defaut. S'il est active pour un environnement controle, il doit etre couvert par DPA, region, retention et validation DPO/RSSI.
- L'AI Firewall actuel est un controle anti-fuite PII residuelle. Ce n'est pas encore une defense complete contre prompt injection/jailbreak.
- Le fallback `database` stocke les fichiers en base; acceptable en pilote controle, moins adapte au scale.
- Le cycle complet de suppression physique depend du backend de stockage.
- Il faut formaliser DPA, region de traitement, retention fournisseur et clauses de non-entrainement avant clients regulés.

## Anonymisation vs pseudonymisation

La pseudonymisation remplace des valeurs par des tokens reversibles ou correlables. Le RGPD continue de s'appliquer.

L'anonymisation vise a rendre la reidentification raisonnablement impossible. Elle exige de traiter les identifiants directs, les quasi-identifiants et les risques de recoupement. Le score ConfiDoc aide a mesurer cette readiness mais ne remplace pas une analyse DPO pour les cas critiques.
