"""Portfolio-level scoring for client document dossiers."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

EXPECTED_DOCUMENTS = (
    {
        "key": "accounts",
        "label": "Bilan, liasse ou compte de resultat",
        "patterns": ("bilan", "liasse", "compte resultat", "compte_resultat", "balance"),
    },
    {
        "key": "tax",
        "label": "Declaration fiscale ou TVA",
        "patterns": ("tva", "fiscal", "impot", "declaration", "is"),
    },
    {
        "key": "bank_cash",
        "label": "Releve bancaire ou tresorerie",
        "patterns": ("banque", "bancaire", "releve", "tresorerie", "cash"),
    },
    {
        "key": "contracts",
        "label": "Contrat, bail, statuts ou PV",
        "patterns": ("contrat", "bail", "statuts", "proces verbal", "proces_verbal", "pv"),
    },
    {
        "key": "transactions",
        "label": "Factures, devis ou notes de frais",
        "patterns": ("facture", "devis", "note frais", "note_frais", "frais"),
    },
)

RISK_LEVELS = ("low", "medium", "high", "critical")


def _normalize(value: object) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _client_label(doc: dict[str, Any]) -> str:
    tags = doc.get("tags") or []
    if tags:
        label = str(tags[0] or "").strip()
        if label:
            return re.sub(r"\s+", " ", label)
    return "Sans client"


def _doc_blob(doc: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in (doc.get("tags") or []))
    return _normalize(
        " ".join(
            [
                str(doc.get("original_filename") or ""),
                str(doc.get("doc_type") or ""),
                tags,
            ]
        )
    )


def _matched_expected_keys(docs: list[dict[str, Any]]) -> set[str]:
    blob = " ".join(_doc_blob(doc) for doc in docs)
    matched: set[str] = set()
    for expected in EXPECTED_DOCUMENTS:
        if any(pattern in blob for pattern in expected["patterns"]):
            matched.add(str(expected["key"]))
    return matched


def _risk_level(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _readiness_label(score: int, blockers: list[str]) -> str:
    if score >= 82 and not blockers:
        return "Pret pour revue"
    if score >= 65:
        return "A completer"
    if score >= 40:
        return "Risque a traiter"
    return "Non pret"


def _next_actions(
    *,
    missing_documents: list[str],
    failed_count: int,
    pending_count: int,
    risk_level: str,
    ready_count: int,
) -> list[str]:
    actions: list[str] = []
    if failed_count:
        actions.append("Relancer ou remplacer les documents en echec.")
    if pending_count:
        actions.append("Finaliser l'anonymisation des documents en attente.")
    if missing_documents:
        actions.append(f"Ajouter: {missing_documents[0]}.")
    if risk_level in {"high", "critical"}:
        actions.append("Valider manuellement les mappings et preuves avant export.")
    if ready_count:
        actions.append("Generer une note de revue Dossier 360 avec les pieces pretes.")
    if not actions:
        actions.append("Preparer le rapport cabinet ou investisseur.")
    return actions[:4]


def build_dossier_360(
    documents: list[dict[str, Any]],
    *,
    risk_by_document: dict[str, float] | None = None,
    entity_counts_by_document: dict[str, int] | None = None,
    limit: int = 6,
) -> dict[str, Any]:
    """Build a finance-ready portfolio summary grouped by client tag."""

    risk_by_document = risk_by_document or {}
    entity_counts_by_document = entity_counts_by_document or {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels: dict[str, str] = {}

    for doc in documents:
        label = _client_label(doc)
        key = _normalize(label) or "sans client"
        groups[key].append(doc)
        labels[key] = label

    dossiers: list[dict[str, Any]] = []
    missing_counter: Counter[str] = Counter()

    for key, docs in groups.items():
        status_counts = Counter(_status_value(doc.get("status")) for doc in docs)
        doc_count = len(docs)
        ready_count = status_counts.get("ready", 0)
        failed_count = status_counts.get("failed", 0)
        pending_count = status_counts.get("uploaded", 0) + status_counts.get("processing", 0)
        matched = _matched_expected_keys(docs)
        missing_documents = [
            str(expected["label"])
            for expected in EXPECTED_DOCUMENTS
            if str(expected["key"]) not in matched
        ]
        missing_counter.update(missing_documents[:2])

        doc_ids = [str(doc.get("id") or "") for doc in docs]
        risks = [float(risk_by_document.get(doc_id) or 0.0) for doc_id in doc_ids]
        risk_score = max(risks) if risks else 0.0
        risk_level = _risk_level(risk_score)
        entity_count = sum(int(entity_counts_by_document.get(doc_id) or 0) for doc_id in doc_ids)

        ready_ratio = ready_count / max(doc_count, 1)
        coverage_ratio = len(matched) / len(EXPECTED_DOCUMENTS)
        failure_penalty = failed_count * 8 + pending_count * 3
        score = round(
            ready_ratio * 35
            + coverage_ratio * 35
            + max(0.0, 100.0 - risk_score) * 0.2
            + min(doc_count, 6) / 6 * 10
            - failure_penalty
        )
        score = max(0, min(100, score))

        blockers: list[str] = []
        if ready_count == 0:
            blockers.append("Aucun document pret pour analyse IA.")
        if failed_count:
            blockers.append(f"{failed_count} document(s) en echec.")
        if pending_count:
            blockers.append(f"{pending_count} document(s) a anonymiser ou finaliser.")
        if risk_level in {"high", "critical"}:
            blockers.append("Risque de re-identification eleve a valider.")
        if missing_documents:
            blockers.append(f"Piece cle manquante: {missing_documents[0]}.")

        doc_types = Counter(str(doc.get("doc_type") or "non_classe") for doc in docs)
        last_activity = max(
            (str(doc.get("updated_at") or doc.get("created_at") or "") for doc in docs),
            default="",
        )
        priority = round((100 - score) + risk_score * 0.45 + failed_count * 12 + pending_count * 5)

        dossiers.append(
            {
                "client_name": labels[key],
                "score": score,
                "readiness": _readiness_label(score, blockers),
                "risk_score": round(risk_score, 1),
                "risk_level": risk_level,
                "document_count": doc_count,
                "ready_count": ready_count,
                "entity_count": entity_count,
                "status_counts": dict(status_counts),
                "document_types": dict(doc_types),
                "matched_documents": [
                    str(expected["label"])
                    for expected in EXPECTED_DOCUMENTS
                    if str(expected["key"]) in matched
                ],
                "missing_documents": missing_documents[:4],
                "blockers": blockers[:5],
                "next_actions": _next_actions(
                    missing_documents=missing_documents,
                    failed_count=failed_count,
                    pending_count=pending_count,
                    risk_level=risk_level,
                    ready_count=ready_count,
                ),
                "priority": priority,
                "last_activity": last_activity,
                "documents_preview": [
                    {
                        "id": str(doc.get("id") or ""),
                        "filename": str(doc.get("original_filename") or ""),
                        "status": _status_value(doc.get("status")),
                        "doc_type": str(doc.get("doc_type") or ""),
                    }
                    for doc in docs[:3]
                ],
            }
        )

    dossiers.sort(key=lambda item: (item["priority"], item["risk_score"]), reverse=True)
    total_score = sum(int(dossier["score"]) for dossier in dossiers)
    avg_score = round(total_score / len(dossiers)) if dossiers else 0
    at_risk = sum(1 for dossier in dossiers if dossier["risk_level"] in {"high", "critical"})
    ready = sum(1 for dossier in dossiers if int(dossier["score"]) >= 82)

    return {
        "portfolio": {
            "clients_count": len(dossiers),
            "documents_count": len(documents),
            "average_score": avg_score,
            "ready_dossiers": ready,
            "at_risk_dossiers": at_risk,
            "critical_actions": sum(len(dossier["blockers"]) for dossier in dossiers),
            "top_missing_documents": [
                {"label": label, "count": count}
                for label, count in missing_counter.most_common(5)
            ],
        },
        "dossiers": dossiers[: max(1, limit)],
    }
