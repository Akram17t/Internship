"""Unit tests for context_schema.py: pure parsing logic, no LLM/network calls."""
from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

from researcher_crew.context_schema import (
    ContextDecision,
    ContextResolution,
    is_retrieval_decision,
    parse_resolution,
)


class TestParseResolutionValidJson:
    def test_plain_json_no_retrieval(self):
        raw = '{"decision": "NO_RETRIEVAL", "retrieval_query": "HRIS itu apa?", "cache_query": "HRIS itu apa?"}'
        result = parse_resolution(raw)
        assert result is not None
        assert result.decision == ContextDecision.NO_RETRIEVAL
        assert result.retrieval_query == "HRIS itu apa?"
        assert result.cache_query == "HRIS itu apa?"

    def test_plain_json_retrieve(self):
        raw = (
            '{"decision": "RETRIEVE", '
            '"retrieval_query": "form resign pengunduran diri karyawan", '
            '"cache_query": "form resign"}'
        )
        result = parse_resolution(raw)
        assert result is not None
        assert result.decision == ContextDecision.RETRIEVE

    def test_json_with_reasoning_field(self):
        raw = (
            '{"decision": "RETRIEVE", "retrieval_query": "q", "cache_query": "q", '
            '"reasoning": "user referenced previous turn"}'
        )
        result = parse_resolution(raw)
        assert result is not None
        assert result.reasoning == "user referenced previous turn"

    def test_reasoning_defaults_to_empty_string(self):
        raw = '{"decision": "RETRIEVE", "retrieval_query": "q", "cache_query": "q"}'
        result = parse_resolution(raw)
        assert result is not None
        assert result.reasoning == ""


class TestParseResolutionMarkdownFence:
    def test_json_wrapped_in_code_fence_with_json_tag(self):
        raw = (
            "```json\n"
            '{"decision": "RETRIEVE", "retrieval_query": "q", "cache_query": "q"}\n'
            "```"
        )
        result = parse_resolution(raw)
        assert result is not None
        assert result.decision == ContextDecision.RETRIEVE

    def test_json_wrapped_in_code_fence_no_tag(self):
        raw = (
            "```\n"
            '{"decision": "NO_RETRIEVAL", "retrieval_query": "q", "cache_query": "q"}\n'
            "```"
        )
        result = parse_resolution(raw)
        assert result is not None
        assert result.decision == ContextDecision.NO_RETRIEVAL

    def test_json_with_surrounding_whitespace(self):
        raw = '\n\n  {"decision": "RETRIEVE", "retrieval_query": "q", "cache_query": "q"}  \n\n'
        result = parse_resolution(raw)
        assert result is not None


class TestParseResolutionDecisionAliases:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("RETRIEVE", ContextDecision.RETRIEVE),
            ("retrieve", ContextDecision.RETRIEVE),
            ("Retrieval", ContextDecision.RETRIEVE),
            ("REWRITE", ContextDecision.RETRIEVE),
            ("NO_RETRIEVAL", ContextDecision.NO_RETRIEVAL),
            ("no retrieval", ContextDecision.NO_RETRIEVAL),
            ("KEEP", ContextDecision.NO_RETRIEVAL),
            ("keep", ContextDecision.NO_RETRIEVAL),
            ("REUSE_EVIDENCE", ContextDecision.REUSE_EVIDENCE),
            ("continue_to_use_evidence", ContextDecision.REUSE_EVIDENCE),
        ],
    )
    def test_decision_alias_normalization(self, value, expected):
        raw = f'{{"decision": "{value}", "retrieval_query": "q", "cache_query": "q"}}'
        result = parse_resolution(raw)
        assert result is not None, f"expected alias {value!r} to parse"
        assert result.decision == expected

    def test_unknown_decision_value_fails(self):
        raw = '{"decision": "MAYBE_LATER", "retrieval_query": "q", "cache_query": "q"}'
        result = parse_resolution(raw)
        assert result is None


class TestParseResolutionMalformed:
    def test_empty_string(self):
        assert parse_resolution("") is None

    def test_whitespace_only(self):
        assert parse_resolution("   \n\t  ") is None

    def test_invalid_json_syntax(self):
        assert parse_resolution("{decision: RETRIEVE, not valid json}") is None

    def test_valid_json_but_not_object(self):
        assert parse_resolution('["RETRIEVE", "q", "q"]') is None

    def test_valid_json_missing_required_field(self):
        raw = '{"decision": "RETRIEVE", "retrieval_query": "q"}'  # missing cache_query
        assert parse_resolution(raw) is None

    def test_valid_json_missing_decision(self):
        raw = '{"retrieval_query": "q", "cache_query": "q"}'
        assert parse_resolution(raw) is None

    def test_empty_retrieval_query_fails_min_length(self):
        raw = '{"decision": "RETRIEVE", "retrieval_query": "", "cache_query": "q"}'
        assert parse_resolution(raw) is None

    def test_prose_response_not_json(self):
        raw = "I think the user is asking about resignation procedures."
        assert parse_resolution(raw) is None

    def test_partial_truncated_json(self):
        raw = '{"decision": "RETRIEVE", "retrieval_query": "q", "cache_qu'
        assert parse_resolution(raw) is None


class TestIsRetrievalDecision:
    def test_retrieve_is_retrieval(self):
        assert is_retrieval_decision(ContextDecision.RETRIEVE.value) is True

    def test_reuse_evidence_is_retrieval(self):
        # REUSE_EVIDENCE currently maps to "go retrieve" until 3-way is fully wired.
        assert is_retrieval_decision(ContextDecision.REUSE_EVIDENCE.value) is True

    def test_no_retrieval_is_not_retrieval(self):
        assert is_retrieval_decision(ContextDecision.NO_RETRIEVAL.value) is False

    def test_unknown_string_is_not_retrieval(self):
        assert is_retrieval_decision("GARBAGE") is False

    def test_empty_string_is_not_retrieval(self):
        assert is_retrieval_decision("") is False


class TestContextResolutionModel:
    def test_direct_model_construction(self):
        resolution = ContextResolution(
            decision=ContextDecision.RETRIEVE,
            retrieval_query="perjalanan dinas luar negeri",
            cache_query="perjalanan dinas luar negeri",
        )
        assert resolution.decision == ContextDecision.RETRIEVE

    def test_model_rejects_empty_cache_query(self):
        with pytest.raises(Exception):
            ContextResolution(
                decision=ContextDecision.RETRIEVE,
                retrieval_query="q",
                cache_query="",
            )
