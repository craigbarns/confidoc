"""Tests for copilot_service: retrieval, confidence, and answer shaping."""

import pytest

from app.services.copilot_service import (
    _normalize_spaces,
    build_dual_corpus,
    confidence_bucket,
    extract_keywords,
    generate_copilot_answer,
    retrieve_citations,
    split_chunks,
)


class TestExtractKeywords:
    def test_basic(self):
        kw = extract_keywords("Quels sont les chiffres du bilan ?")
        assert "chiffres" in kw
        assert "bilan" in kw

    def test_filters_stopwords(self):
        kw = extract_keywords("Quels sont les montants avec des détails ?")
        assert "quels" not in kw
        assert "avec" not in kw
        assert "montants" in kw

    def test_filters_short_words(self):
        kw = extract_keywords("le CA est bon")
        assert "le" not in kw

    def test_empty_input(self):
        assert extract_keywords("") == []


class TestSplitChunks:
    def test_basic_split(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = split_chunks(text)
        assert len(chunks) == 3

    def test_long_chunk_split(self):
        long_text = "A" * 1500
        chunks = split_chunks(long_text, max_len=700)
        assert len(chunks) >= 2

    def test_empty_text(self):
        assert split_chunks("") == []
        assert split_chunks(None) == []

    def test_whitespace_only(self):
        assert split_chunks("   \n\n   ") == []


class TestRetrieveCitations:
    def test_returns_citations(self):
        text = "Le chiffre d'affaires est de 500 000 euros.\n\nLe résultat net est positif.\n\nLes charges sont maîtrisées."
        cites = retrieve_citations("chiffre d'affaires", text)
        assert len(cites) >= 1
        assert cites[0]["score"] > 0

    def test_no_match_returns_fallback(self):
        text = "Document sans rapport avec la question."
        cites = retrieve_citations("comptabilité analytique", text)
        assert len(cites) >= 1
        assert cites[0]["score"] <= 0.25

    def test_empty_text(self):
        cites = retrieve_citations("test", "")
        assert cites == []

    def test_empty_question_returns_first_chunk(self):
        text = "Premier paragraphe du document."
        cites = retrieve_citations("", text)
        assert len(cites) == 1
        assert cites[0]["score"] == 0.25

    def test_top_k_respected(self):
        text = "\n\n".join([f"Section {i} avec bilan et résultat" for i in range(10)])
        cites = retrieve_citations("bilan résultat", text, top_k=2)
        assert len(cites) <= 2


class TestConfidenceBucket:
    def test_high(self):
        assert confidence_bucket([{"score": 0.9}, {"score": 0.7}]) == "high"

    def test_medium(self):
        assert confidence_bucket([{"score": 0.5}, {"score": 0.3}]) == "medium"

    def test_low(self):
        assert confidence_bucket([{"score": 0.1}, {"score": 0.1}]) == "low"

    def test_empty(self):
        assert confidence_bucket([]) == "low"


class TestBuildDualCorpus:
    def test_combines_texts(self):
        result = build_dual_corpus("Texte A", "Texte B")
        assert "DOCUMENT COURANT" in result
        assert "AUTRE DOCUMENT" in result
        assert "Texte A" in result
        assert "Texte B" in result

    def test_truncates_long_texts(self):
        long_a = "A" * 20000
        long_b = "B" * 20000
        result = build_dual_corpus(long_a, long_b, max_each=100)
        assert len(result) < 500


class TestNormalizeSpaces:
    def test_collapses_whitespace(self):
        assert _normalize_spaces("hello   world") == "hello world"

    def test_strips(self):
        assert _normalize_spaces("  hello  ") == "hello"

    def test_none(self):
        assert _normalize_spaces(None) == ""


class TestGenerateCopilotAnswer:
    @pytest.mark.asyncio
    async def test_local_summary_does_not_call_llm(self, monkeypatch):
        import app.services.copilot_service as copilot_svc

        async def _fail_summary(*args, **kwargs):
            pytest.fail("Local Copilot answer should not call Mistral")

        monkeypatch.setattr(copilot_svc, "generate_summary_with_mistral", _fail_summary)

        answer = await generate_copilot_answer(
            "Résumer le document",
            [{"snippet": "Le chiffre d'affaires est de 500 000 euros.", "score": 0.5}],
            allow_llm=False,
        )

        assert "version masquée" in answer
        assert "500 000" in answer
