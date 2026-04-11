"""Unit tests for Copilot service helpers."""

from app.services.copilot_service import (
    build_dual_corpus,
    confidence_bucket,
    extract_keywords,
    retrieve_citations,
)


def test_extract_keywords_filters_short_and_stopwords():
    kws = extract_keywords("Quel est le ratio d'endettement pour le client retail ?")
    assert "ratio" in kws
    assert "endettement" in kws
    assert "pour" not in kws


def test_retrieve_citations_returns_ranked_snippets():
    text = (
        "Le ratio d'endettement est de 0.85 au 31/12.\n\n"
        "Le chiffre d'affaires progresse de 8%.\n\n"
        "Le ratio de liquidité est stable."
    )
    cites = retrieve_citations("Quel est le ratio d'endettement ?", text, top_k=2)
    assert len(cites) >= 1
    assert "ratio" in cites[0]["snippet"].lower()


def test_confidence_bucket_thresholds():
    assert confidence_bucket([]) == "low"
    assert confidence_bucket([{"score": 0.4}]) == "medium"
    assert confidence_bucket([{"score": 0.9}, {"score": 0.7}]) == "high"


def test_build_dual_corpus_contains_markers():
    s = build_dual_corpus("aaa", "bbb", max_each=100)
    assert "DOCUMENT COURANT" in s
    assert "AUTRE DOCUMENT" in s
    assert "aaa" in s and "bbb" in s
