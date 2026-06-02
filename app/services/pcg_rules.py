"""ConfiDoc — PCG rule catalog.

A pure-data module: each entry maps a category of business expense / income to
a French PCG account, with a base confidence and a short reason. The engine
in :mod:`app.services.pcg_mapping_service` consumes this catalog and decides
which suggestion(s) to surface.

Adding a new category: append a ``PcgRule`` here. No engine code change is
required.

Sources / tradeoffs
-------------------
The codes below follow the *Plan Comptable Général* widely used in French
accounting practice. Some choices are debated by accountants (e.g. SaaS
subscriptions: 651100 vs 622800 vs 606800). When a category has multiple
defensible accounts, we add several rules with the same category name and let
the engine surface alternatives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class PcgAccount:
    """A single PCG account: 6-digit code + human label."""

    code: str
    label: str


@dataclass(frozen=True)
class PcgRule:
    """One mapping rule.

    A rule matches when *any* of its keywords is found in the normalised
    libellé. The score grows with the number of distinct keywords matched.
    """

    category: str
    keywords: tuple[str, ...]
    account: PcgAccount
    base_confidence: float
    reason: str
    # Optional restriction: only fire when the extracted ``nature`` is one of
    # these. Leave empty to match any nature.
    natures: tuple[str, ...] = field(default=())


# Ordered roughly from most specific to most generic. The engine handles
# ambiguity (multiple matches) by surfacing alternatives, so order is for
# readability only.
RULES: Final[tuple[PcgRule, ...]] = (
    # --- Loyers & charges locatives -----------------------------------------
    PcgRule(
        category="loyers",
        keywords=("loyer", "loyers", "location immobiliere", "bail commercial"),
        account=PcgAccount("613100", "Locations immobilières"),
        base_confidence=0.92,
        reason="Mots-clés 'loyer/location immobilière/bail' → location immobilière (613100).",
    ),
    PcgRule(
        category="charges_locatives",
        keywords=(
            "charges locatives",
            "charges copropriete",
            "copropriete",
            "regularisation charges",
        ),
        account=PcgAccount("614000", "Charges locatives et de copropriété"),
        base_confidence=0.9,
        reason="Charges locatives ou de copropriété → 614000.",
    ),
    # --- Assurances ----------------------------------------------------------
    PcgRule(
        category="assurances",
        keywords=("assurance", "assurances", "prime assurance", "axa", "allianz", "maif", "macif"),
        account=PcgAccount("616000", "Primes d'assurances"),
        base_confidence=0.9,
        reason="Compagnie d'assurance ou prime → 616000.",
    ),
    # --- Honoraires ----------------------------------------------------------
    PcgRule(
        category="honoraires_comptables",
        keywords=(
            "honoraires comptable",
            "expert-comptable",
            "expert comptable",
            "cabinet comptable",
            "honoraires expert",
        ),
        account=PcgAccount("622600", "Honoraires"),
        base_confidence=0.93,
        reason="Honoraires d'expert-comptable → 622600.",
    ),
    PcgRule(
        category="honoraires_juridiques",
        keywords=(
            "avocat",
            "avocats",
            "notaire",
            "huissier",
            "honoraires juridique",
            "honoraires juridiques",
            "cabinet d'avocats",
            "cabinet avocat",
        ),
        account=PcgAccount("622600", "Honoraires"),
        base_confidence=0.92,
        reason="Honoraires juridiques (avocat/notaire/huissier) → 622600.",
    ),
    PcgRule(
        category="honoraires_generaux",
        keywords=("honoraires", "consulting", "consultant"),
        account=PcgAccount("622600", "Honoraires"),
        base_confidence=0.7,
        reason="Honoraires divers → 622600.",
    ),
    # --- Frais bancaires -----------------------------------------------------
    PcgRule(
        category="frais_bancaires",
        keywords=(
            "frais bancaire",
            "frais bancaires",
            "agios",
            "commission bancaire",
            "tenue de compte",
            "frais carte",
        ),
        account=PcgAccount("627000", "Services bancaires et assimilés"),
        base_confidence=0.93,
        reason="Frais bancaires / agios / commissions → 627000.",
    ),
    # --- Fournitures administratives ----------------------------------------
    PcgRule(
        category="fournitures_administratives",
        keywords=(
            "fournitures bureau",
            "fournitures de bureau",
            "fournitures administratives",
            "papeterie",
            "cartouches",
            "ramettes papier",
        ),
        account=PcgAccount("606400", "Fournitures administratives"),
        base_confidence=0.9,
        reason="Fournitures de bureau / administratives → 606400.",
    ),
    # --- Télécom / Internet --------------------------------------------------
    PcgRule(
        category="telecom_internet",
        keywords=(
            "telephone",
            "telephonie",
            "internet",
            "abonnement internet",
            "fibre",
            "ligne mobile",
            "orange",
            "sfr",
            "bouygues",
            "free telecom",
            "free pro",
        ),
        account=PcgAccount("626100", "Frais postaux et de télécommunications"),
        base_confidence=0.88,
        reason="Téléphonie / internet / opérateur télécom → 626100.",
    ),
    # --- Frais postaux -------------------------------------------------------
    PcgRule(
        category="frais_postaux",
        keywords=("la poste", "affranchissement", "timbre", "colissimo", "chronopost"),
        account=PcgAccount("626100", "Frais postaux et de télécommunications"),
        base_confidence=0.9,
        reason="Frais postaux / affranchissement → 626100.",
    ),
    # --- Déplacements --------------------------------------------------------
    PcgRule(
        category="deplacements",
        keywords=(
            "sncf",
            "billet train",
            "train sncf",
            "uber",
            "taxi",
            "vtc",
            "billet avion",
            "air france",
            "easyjet",
            "ryanair",
            "hotel",
            "nuitee",
            "voyage",
            "deplacement",
            "frais de mission",
        ),
        account=PcgAccount("625100", "Voyages et déplacements"),
        base_confidence=0.9,
        reason="Voyage / transport / hôtel → 625100.",
    ),
    PcgRule(
        category="peages_parking",
        keywords=("peage", "parking", "stationnement", "horodateur"),
        account=PcgAccount("625100", "Voyages et déplacements"),
        base_confidence=0.85,
        reason="Péages / parking → 625100 (frais de déplacement).",
    ),
    # --- Carburant -----------------------------------------------------------
    PcgRule(
        category="carburant",
        keywords=("carburant", "essence", "gasoil", "diesel", "total energies", "shell", "bp"),
        account=PcgAccount("606140", "Carburants"),
        base_confidence=0.9,
        reason="Carburant véhicule → 606140.",
    ),
    # --- Restauration / Réception -------------------------------------------
    PcgRule(
        category="restauration_reception",
        keywords=(
            "restaurant",
            "restauration",
            "brasserie",
            "traiteur",
            "reception",
            "cocktail",
        ),
        account=PcgAccount("625700", "Réceptions"),
        base_confidence=0.85,
        reason="Restauration / traiteur / réception → 625700.",
    ),
    # --- Entretien / Réparation ---------------------------------------------
    PcgRule(
        category="entretien_reparation",
        keywords=(
            "entretien",
            "reparation",
            "maintenance",
            "depannage",
            "revision vehicule",
        ),
        account=PcgAccount("615000", "Entretien et réparations"),
        base_confidence=0.88,
        reason="Entretien / réparation / maintenance → 615000.",
    ),
    # --- Sous-traitance ------------------------------------------------------
    PcgRule(
        category="sous_traitance",
        keywords=(
            "sous-traitance",
            "sous traitance",
            "sous-traitant",
            "freelance",
            "prestataire externe",
        ),
        account=PcgAccount("611000", "Sous-traitance générale"),
        base_confidence=0.88,
        reason="Sous-traitance / freelance externe → 611000.",
    ),
    # --- Achats marchandises -------------------------------------------------
    PcgRule(
        category="achats_marchandises",
        keywords=("achat marchandise", "achats marchandises", "marchandises", "stock revente"),
        account=PcgAccount("607000", "Achats de marchandises"),
        base_confidence=0.9,
        reason="Achats de marchandises destinées à la revente → 607000.",
    ),
    # --- Logiciels / SaaS ----------------------------------------------------
    PcgRule(
        category="logiciels_saas",
        keywords=(
            "saas",
            "abonnement logiciel",
            "abonnement saas",
            "licence logiciel",
            "licence saas",
            "google workspace",
            "microsoft 365",
            "office 365",
            "slack",
            "notion",
            "github",
            "aws",
            "ovh",
        ),
        account=PcgAccount("651100", "Redevances pour concessions, licences"),
        base_confidence=0.8,
        reason="Abonnement SaaS / licence logiciel → 651100 (redevance pour licence).",
    ),
    PcgRule(
        category="logiciels_saas_alt",
        keywords=("saas", "abonnement logiciel", "licence logiciel"),
        account=PcgAccount("622800", "Divers (rémunérations d'intermédiaires)"),
        base_confidence=0.55,
        reason="Variante : certains cabinets classent les SaaS récurrents en 622800.",
    ),
    # --- Publicité / Marketing ----------------------------------------------
    PcgRule(
        category="publicite_marketing",
        keywords=(
            "publicite",
            "publicité",
            "marketing",
            "campagne",
            "google ads",
            "facebook ads",
            "linkedin ads",
            "annonce",
            "insertion",
        ),
        account=PcgAccount("623000", "Publicité, publications, relations publiques"),
        base_confidence=0.9,
        reason="Publicité / annonces / campagne marketing → 623000.",
    ),
    # --- Cotisations professionnelles ---------------------------------------
    PcgRule(
        category="cotisations_professionnelles",
        keywords=(
            "cotisation professionnelle",
            "cotisation ordre",
            "ordre des avocats",
            "ordre des experts",
            "syndicat professionnel",
            "chambre de commerce",
        ),
        # Confidence higher than honoraires_juridiques so that a libellé
        # containing both "ordre des avocats" and "avocat" still resolves to
        # the cotisation account rather than to honoraires.
        account=PcgAccount("628100", "Concours divers (cotisations)"),
        base_confidence=0.95,
        reason="Cotisation professionnelle / ordre / syndicat → 628100.",
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Fallbacks by ``nature`` — used when no rule matches at all.
# ─────────────────────────────────────────────────────────────────────────────


FALLBACK_BY_NATURE: Final[dict[str, PcgAccount]] = {
    "charge": PcgAccount("606300", "Fournitures d'entretien et de petit équipement"),
    "produit": PcgAccount("706000", "Prestations de services"),
}

UNKNOWN_ACCOUNT: Final[PcgAccount] = PcgAccount("471000", "Compte d'attente (à classer)")
