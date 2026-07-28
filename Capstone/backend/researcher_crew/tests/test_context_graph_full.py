"""Integration tests for the full context resolution StateGraph.

Uses resolve_query_context(..., llm_caller=fake) to exercise every routing
path without hitting the real model. Each fake caller counts its own calls
so retry-loop behavior can be asserted directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from researcher_crew.context_graph import resolve_query_context


class TestNoHistoryPath:
    def test_empty_context_skips_llm_entirely(self):
        calls = []

        def fake_caller(prompt: str) -> str:
            calls.append(prompt)
            return '{"decision": "RETRIEVE", "retrieval_query": "x", "cache_query": "x"}'

        result = resolve_query_context(
            original_question="Apa itu HRIS?",
            conversation_context="",
            llm_caller=fake_caller,
        )
        assert result["retrieval_query"] == "Apa itu HRIS?"
        assert result["cache_query"] == "Apa itu HRIS?"
        assert result["changed"] is False
        assert calls == [], "LLM should not be called when there is no history"

    def test_whitespace_only_context_treated_as_no_history(self):
        result = resolve_query_context(
            original_question="Test question",
            conversation_context="   \n  ",
            llm_caller=lambda prompt: "SHOULD NOT BE CALLED",
        )
        assert result["retrieval_query"] == "Test question"


class TestNoRetrievalPath:
    def test_no_retrieval_decision_skips_validation(self):
        raw = '{"decision": "NO_RETRIEVAL", "retrieval_query": "Makasih ya", "cache_query": "Makasih ya"}'
        result = resolve_query_context(
            original_question="Makasih ya",
            conversation_context="User: prosedur resign\nAssistant: ...",
            llm_caller=lambda prompt: raw,
        )
        assert result["decision"] == "NO_RETRIEVAL"


class TestRetrievePath:
    def test_valid_retrieve_passes_through_validation(self):
        raw = (
            '{"decision": "RETRIEVE", '
            '"retrieval_query": "form yang harus diisi untuk resign pengunduran diri karyawan", '
            '"cache_query": "form untuk resign"}'
        )
        result = resolve_query_context(
            original_question="Form apa aja yang harus diisi buat itu?",
            conversation_context="User: Bagaimana prosedur resign?\nAssistant: ...",
            llm_caller=lambda prompt: raw,
        )
        assert result["decision"] == "RETRIEVE"
        assert "resign" in result["retrieval_query"].lower()
        assert result["cache_query"] == "form untuk resign"


class TestRetryLoop:
    def test_invalid_output_retries_then_succeeds(self):
        call_count = {"n": 0}
        long_query = "x" * 700  # exceeds _MAX_RETRIEVAL_QUERY_CHARS = 600

        def fake_caller(prompt: str) -> str:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (
                    '{"decision": "RETRIEVE", "retrieval_query": "' + long_query + '", '
                    '"cache_query": "short"}'
                )
            return '{"decision": "RETRIEVE", "retrieval_query": "normal length query", "cache_query": "normal query"}'

        result = resolve_query_context(
            original_question="Kalau luar negeri gimana?",
            conversation_context="User: perjalanan dinas dalam negeri\nAssistant: ...",
            llm_caller=fake_caller,
            max_attempts=2,
        )
        assert call_count["n"] == 2, "expected exactly one retry"
        assert result["retrieval_query"] == "normal length query"

    def test_exhausted_retries_falls_back_to_original(self):
        call_count = {"n": 0}
        long_query = "y" * 700

        def always_invalid_caller(prompt: str) -> str:
            call_count["n"] += 1
            return (
                '{"decision": "RETRIEVE", "retrieval_query": "' + long_query + '", '
                '"cache_query": "short"}'
            )

        original = "Kalau luar negeri gimana?"
        result = resolve_query_context(
            original_question=original,
            conversation_context="User: perjalanan dinas dalam negeri\nAssistant: ...",
            llm_caller=always_invalid_caller,
            max_attempts=2,
        )
        assert call_count["n"] == 2, "should stop retrying at max_attempts"
        assert result["retrieval_query"] == original
        assert result["cache_query"] == original
        assert result["changed"] is False


class TestDurationTracking:
    def test_duration_seconds_is_populated(self):
        result = resolve_query_context(
            original_question="Test",
            conversation_context="",
            llm_caller=lambda prompt: "unused",
        )
        assert result["duration_seconds"] >= 0.0
