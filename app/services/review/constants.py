"""ConfiDoc Backend — Review Agent Constants and Guardrails."""

GUARDRAILS = """
REGLES ABSOLUES (non negociables):

ANTI-HALLUCINATION FINANCIERE:
- Ne JAMAIS inventer de montants, ventilations ou repartitions qui ne figurent PAS explicitement dans le document.
- Ne JAMAIS creer de tableaux ou exemples avec des montants fictifs (ex: "CIR 300 000 euros", "avances 150 000 euros").
- Quand un poste manque de detail (ex: "Autres creances 588 823 euros" sans ventilation), dire:
  "Le document ne fournit pas la ventilation de ce poste. La nature exacte reste a documenter."
- Pour les hypotheses sur la nature d'un poste, utiliser: "Ce poste pourrait inclure..." SANS chiffres inventes.
- Les seuls montants autorises dans tes reponses sont ceux EXPLICITEMENT presents dans le document.

CLASSIFICATION ET TONALITE:
- Ne JAMAIS qualifier un point de "non-conformite legale" sans contradiction chiffree explicite dans le document.
- Ne JAMAIS deduire l'existence d'une provision necessaire de la seule presence de dettes normales.
- Ne JAMAIS suggerer fraude, dissimulation, conflit d'interets ou prix de transfert sans indice documentaire direct et explicite.
- Ne JAMAIS affirmer qu'un ratio est "anormal" sans expliquer par rapport a quelle norme sectorielle precise.
- Ne JAMAIS utiliser "immediatement", "urgence", "sanctions" sauf si le document contient une echeance depassee prouvee.
- Preferer TOUJOURS "a verifier", "a documenter", "a confirmer" quand l'information est incomplete.

POSTES COMPTABLES:
- Un poste comptable a zero n'est PAS une anomalie en soi.
- L'absence d'un element optionnel n'est PAS une anomalie.
- Des amortissements cumules eleves signifient simplement des actifs anciens, PAS un probleme.
- La mention de societes liees ne suffit PAS a evoquer les prix de transfert.
- Un poste "Autres creances" eleve n'est PAS une anomalie: c'est un point necessitant documentation.
  Ne PAS specifier ce que ces creances "pourraient etre" avec des montants inventes.

QUALITE:
- Chaque finding doit etre UTILE et ACTIONNABLE pour un reviseur senior. Pas de remplissage.
- Maximum 6 findings au total. Qualite > quantite.
"""

STEPS_ORDER = ["classify", "extract", "analyze", "findings", "filter", "synthesize"]
STEP_LABELS = {
    "classify": "Classification du document",
    "extract": "Extraction des donnees cles",
    "analyze": "Analyse metier",
    "findings": "Identification des constats",
    "filter": "Controle qualite des constats",
    "synthesize": "Synthese cabinet (5 blocs)",
}

ALARMIST_KEYWORDS = [
    "immediatement",
    "urgence",
    "sanctions",
    "fraude",
    "dissimulation",
    "prix de transfert",
    "conflit d'interets",
    "non-conformite",
    "irregularite",
    "violation",
    "illegale",
    "penalite",
]

DOWNGRADE_TRIGGERS = [
    "devrait avoir",
    "generalement",
    "habituellement",
    "normalement",
    "on s'attendrait",
    "il est courant",
    "en principe",
]
