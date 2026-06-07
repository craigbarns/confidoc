# ConfiDoc — One-pager

**Le firewall de confidentialité IA pour les cabinets réglementés.**
*Utilisez l'IA sur vos dossiers clients sans jamais exposer une donnée confidentielle.*

---

**Problème.** Experts-comptables, DAF externalisés, avocats fiscalistes et notaires
veulent l'IA pour gagner des heures sur bilans, liasses et contrats — mais envoyer un
dossier client dans une IA publique viole le RGPD et le secret professionnel. L'IA reste
bloquée à la porte des cabinets.

**Solution.** ConfiDoc s'intercale entre les documents et l'IA : pseudonymisation des
données identifiantes, **Privacy Gate** déterministe (autorise / validation humaine /
bloque, fail-closed), **AI Firewall** qui inspecte le prompt **et** la réponse sur tous
les flux IA, score RGPD/risque de réidentification et **journal d'audit cryptographique**
opposable. En mode souverain, aucun appel IA externe.

**Pourquoi maintenant.** Adoption IA massive mais interdite de fait sur données clients ;
AI Act + RGPD + souveraineté EU font de la conformité un prérequis d'achat ; les agents
IA arrivent et exigent une couche de contrôle.

**Produit (déjà en production).** FastAPI/PostgreSQL/Redis, déployé ; firewall sur tous
les chemins IA ; isolation multi-tenant RBAC + RLS PostgreSQL ; dashboard DPO/RSSI temps
réel ; **démo publique sans login** ; golden sets + benchmarks OCR (qualité mesurée).
Démo : `confidoc-production.up.railway.app/firewall`.

**Marché.** Wedge : cabinets réglementés FR (secret pro + volume documentaire). Expansion :
firewall IA horizontal pour toute entreprise EU déployant l'IA/les agents.

**Modèle.** SaaS par siège + tier gouvernance DPO/RSSI ; option par volume de documents.

**Défendabilité.** RGPD-by-design (dur à rétro-fitter), qualité mesurée (golden sets),
preuve d'audit cryptographique opposable, boucle d'apprentissage.

**Équipe.** Fondateur solo — a livré la plateforme complète **en production, seul**
(preuve d'exécution). Levée = premiers recrutements (GTM + dev) + conformité (ISO 27001).

**Demande.** ‹montant› € en ‹pre-seed› (‹18–24 mois›) pour : ‹3–5 pilotes → premiers
revenus, GTM cabinets, certif sécurité›.

> Wording RGPD : **pseudonymisation + maîtrise du risque de réidentification** (cf. position CNIL), pas « anonymisation garantie ».

**Contact.** ‹nom · email · téléphone · LinkedIn›
