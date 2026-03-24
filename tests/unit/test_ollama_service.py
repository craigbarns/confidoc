"""Tests for Ollama service utilities."""

from app.services.ollama_service import extract_json_object_from_llm


class TestExtractJsonObject:
    def test_clean_json(self):
        result = extract_json_object_from_llm('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        raw = 'Here is the result: {"a": 1, "b": 2} done.'
        result = extract_json_object_from_llm(raw)
        assert result == {"a": 1, "b": 2}

    def test_empty_string(self):
        assert extract_json_object_from_llm("") is None

    def test_no_json(self):
        assert extract_json_object_from_llm("just plain text") is None

    def test_invalid_json(self):
        assert extract_json_object_from_llm("{not valid json}") is None

    def test_empty_object(self):
        assert extract_json_object_from_llm("{}") is None

    def test_nested_json(self):
        raw = '{"outer": {"inner": 42}}'
        result = extract_json_object_from_llm(raw)
        assert result["outer"]["inner"] == 42

    def test_json_with_markdown_fence(self):
        raw = "```json\n{\"k\": \"v\"}\n```"
        result = extract_json_object_from_llm(raw)
        assert result == {"k": "v"}

    def test_none_input(self):
        assert extract_json_object_from_llm(None) is None

    def test_only_opening_brace(self):
        assert extract_json_object_from_llm("{incomplete") is None
