"""Copilot helper service: retrieval, confidence, and answer shaping."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.services.mistral_service import generate_summary_with_mistral

_STOPWORDS = {
    "avec",
    "dans",
    "pour",
    "sans",
    "sous",
    "entre",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "est",
    "sont",
    "sur",
    "des",
    "les",
    "une",
    "vos",
    "mon",
    "ton",
    "ses",
    "notre",
    "votre",
    "leur",
    "client",
    "document",
    "rapport",
}


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_keywords(question: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_àâäéèêëîïôöùûüç]+", question.lower())
    return [t for t in tokens if len(t) >= 4 and t not in _STOPWORDS]


def split_chunks(text: str, max_len: int = 700) -> list[str]:
    raw_parts = [p.strip() for p in re.split(r"\n{2,}", text or "") if p.strip()]
    chunks: list[str] = []
    for part in raw_parts:
        if len(part) <= max_len:
            chunks.append(part)
            continue
        for i in range(0, len(part), max_len):
            chunks.append(part[i : i + max_len])
    return chunks


def build_dual_corpus(text_primary: str, text_other: str, max_each: int = 12000) -> str:
    """Concatenate two anonymized texts with clear delimiters for retrieval / LLM context."""
    a = (text_primary or "")[:max_each]
    b = (text_other or "")[:max_each]
    return (
        "--- DOCUMENT COURANT (référence / N) ---\n"
        f"{a}\n\n"
        "--- AUTRE DOCUMENT (ex. N-1 ou autre pièce) ---\n"
        f"{b}"
    )


def retrieve_citations(question: str, anonymized_text: str, top_k: int = 3) -> list[dict[str, Any]]:
    chunks = split_chunks(anonymized_text)
    if not chunks:
        return []
    keywords = extract_keywords(question)
    if not keywords:
        return [{"snippet": _normalize_spaces(chunks[0])[:500], "score": 0.25}]

    scored: list[tuple[float, str]] = []
    for chunk in chunks:
        low = chunk.lower()
        hits = Counter(k for k in keywords if k in low)
        score = float(sum(hits.values())) / max(1.0, float(len(keywords)))
        if score > 0:
            scored.append((min(1.0, score), chunk))

    if not scored:
        return [{"snippet": _normalize_spaces(chunks[0])[:500], "score": 0.2}]

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[:top_k]
    return [{"snippet": _normalize_spaces(txt)[:650], "score": round(sc, 3)} for sc, txt in best]


def confidence_bucket(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "low"
    avg = sum(float(c.get("score", 0.0)) for c in citations) / len(citations)
    if avg >= 0.65:
        return "high"
    if avg >= 0.35:
        return "medium"
    return "low"


async def generate_copilot_answer(question: str, citations: list[dict[str, Any]]) -> str:
    context = "\n\n".join(
        [f"[Source {idx+1}] {c['snippet']}" for idx, c in enumerate(citations)]
    )
    payload = {
        "anonymized_text": context[:9000],
        "user_question": question.strip(),
        "quality": {"ready_for_ai": True, "ready_for_ai_core": True, "needs_review": False},
    }
    try:
        llm = await generate_summary_with_mistral(payload, prudent_mode=True, mode="question")
        validated = llm.get("validated") or {}
        resume = str(validated.get("resume_executif") or "").strip()
        points = validated.get("points_cles") or []
        if resume:
            return "\n".join([resume] + [f"- {p}" for p in points[:3] if str(p).strip()])
    except Exception:
        pass

    if not citations:
        return "Je ne trouve pas d'éléments suffisants dans le document anonymisé pour répondre avec fiabilité."
    return (
        "Voici ce que je peux établir à partir des extraits retrouvés.\n"
        "Je recommande une vérification humaine si une décision engageante est prise."
    )
