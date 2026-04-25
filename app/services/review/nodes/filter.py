"""ConfiDoc Backend — Review Agent Node: Filter."""

from app.services.review.state import ReviewState
from app.services.review.constants import ALARMIST_KEYWORDS, DOWNGRADE_TRIGGERS


async def filter_node(state: ReviewState) -> ReviewState:
    """Post-processing: downgrade overly aggressive findings."""
    findings = state.get("findings", {})
    filtered = {
        "anomalies_confirmees": [],
        "points_attention": [],
        "informations_manquantes": list(findings.get("informations_manquantes", [])),
        "verifications_recommandees": list(findings.get("verifications_recommandees", [])),
    }

    for item in findings.get("anomalies_confirmees", []):
        desc = (item.get("description") or "").lower()
        detail = (item.get("detail") or "").lower()
        combined = desc + " " + detail

        if any(kw in combined for kw in ALARMIST_KEYWORDS):
            filtered["verifications_recommandees"].append(item)
            continue

        if any(kw in combined for kw in DOWNGRADE_TRIGGERS):
            filtered["points_attention"].append(item)
            continue

        filtered["anomalies_confirmees"].append(item)

    for item in findings.get("points_attention", []):
        desc = (item.get("description") or "").lower()
        detail = (item.get("detail") or "").lower()
        combined = desc + " " + detail

        if any(kw in combined for kw in ALARMIST_KEYWORDS):
            filtered["verifications_recommandees"].append(item)
            continue

        filtered["points_attention"].append(item)

    for cat in filtered:
        filtered[cat] = filtered[cat][:3]

    return {
        **state,
        "findings": filtered,
        "current_step": "filter",
        "steps_completed": state.get("steps_completed", []) + ["filter"],
    }
