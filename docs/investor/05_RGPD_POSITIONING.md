# ConfiDoc — Position RGPD (à dire avec prudence)

> Source de référence : CNIL, *L'anonymisation de données personnelles* —
> https://www.cnil.fr/fr/lanonymisation-de-donnees-personnelles

## La distinction qui nous engage

- **Anonymisation** (au sens CNIL/RGPD) : traitement **irréversible** rendant impossible
  toute réidentification, y compris dans le temps et par recoupement. Une donnée
  réellement anonyme **sort** du champ du RGPD. Le seuil est **élevé** (critères :
  individualisation, corrélation, inférence).
- **Pseudonymisation** : remplacement des identifiants par des pseudonymes, **avec
  possibilité de réidentifier** (clé/mapping conservé). La donnée **reste personnelle** et
  **dans le champ** du RGPD. C'est une **mesure de sécurité**, pas une sortie du RGPD.

La CNIL insiste sur le **risque de réidentification dans le temps** (recoupements,
nouvelles données disponibles plus tard).

## Ce que fait ConfiDoc (honnête)

ConfiDoc réalise principalement de la **pseudonymisation** : le mapping
identifiant→pseudonyme est **réversible et chiffré** (réversibilité utile pour la revue
humaine et la restitution). **Donc, par défaut, les données traitées restent des données
personnelles au sens du RGPD.**

La valeur de ConfiDoc n'est pas de prétendre « anonymiser à 100 % », mais de :
1. **réduire fortement l'exposition** des identifiants avant tout usage IA ;
2. **mesurer le risque de réidentification** (scoring) et le **maîtriser dans le temps** ;
3. **empêcher toute fuite** vers une IA via le Privacy Gate + l'AI Firewall (prompt+réponse) ;
4. **prouver** le traitement (journal d'audit cryptographique opposable) ;
5. offrir un **mode souverain** (aucun appel IA externe) pour les cas les plus sensibles.

## Wording autorisé / interdit (discipline commerciale)

| ✅ À dire | ❌ À éviter |
|---|---|
| « pseudonymisation des données identifiantes » | « anonymisation garantie / irréversible » |
| « risque de réidentification mesuré et maîtrisé » | « zéro risque », « 100 % anonyme » |
| « les données restent protégées et sous votre contrôle » | « les données sortent du RGPD » |
| « firewall qui empêche la fuite vers l'IA » | « conforme RGPD » au sens d'une certification |
| « preuve d'audit opposable » | « certifié CNIL » (la CNIL ne certifie pas un produit ainsi) |

## Implications produit / data room
- Traiter les données pilotes sous **DPA**, hébergement **UE**, durées de conservation
  définies (rétention déjà implémentée).
- Documenter : finalités, base légale (sous-traitance art. 28), sous-traitants, mesures
  de sécurité, procédure en cas de violation.
- Si un jour une **anonymisation** (au sens fort) est visée, le démontrer par une étude
  de risque de réidentification dédiée — ne pas l'affirmer par défaut.

> En due diligence, **assumer cette prudence est un atout** : cela montre une maîtrise
> RGPD réelle face à des acheteurs DPO/RSSI avertis.
