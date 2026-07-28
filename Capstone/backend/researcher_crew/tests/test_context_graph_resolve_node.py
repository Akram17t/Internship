"""Unit tests for resolve_context_node, isolated from the real LLM via
dependency injection (the node accepts an llm_caller callable)."""
from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from researcher_crew.context_graph import resolve_context_node
from researcher_crew.context_schema import ContextState


def _base_state(**overrides) -> ContextState:
    state: ContextState = {
        "original_question": "Form apa aja yang harus diisi buat itu?",
        "conversation_context": "User: Bagaimana prosedur resign?\nAssistant: ...",
        "conversation_id": "test-conv-1",
        "decision": "",
        "attempts": 0,
        "max_attempts": 2,
        "retrieval_query": "",
        "cache_query": "",
        "changed": False,
        "duration_seconds": 0.0,
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


class TestResolveContextNodeSuccess:
    def test_retrieve_decision_with_dual_queries(self):
        raw = (
            '{"decision": "RETRIEVE", '
            '"retrieval_query": "form yang harus diisi untuk resign pengunduran diri", '
            '"cache_query": "form untuk resign"}'
        )
        result = resolve_context_node(_base_state(), llm_caller=lambda prompt: raw)
        assert result["decision"] == "RETRIEVE"
        assert result["retrieval_query"] == "form yang harus diisi untuk resign pengunduran diri"
        assert result["cache_query"] == "form untuk resign"
        assert result["changed"] is True
        assert result["attempts"] == 1

    def test_no_retrieval_decision(self):
        raw = '{"decision": "NO_RETRIEVAL", "retrieval_query": "Makasih ya", "cache_query": "Makasih ya"}'
        state = _base_state(original_question="Makasih ya")
        result = resolve_context_node(state, llm_caller=lambda prompt: raw)
        assert result["decision"] == "NO_RETRIEVAL"

    def test_markdown_fenced_response_parses(self):
        raw = (
            "```json\n"
            '{"decision": "RETRIEVE", "retrieval_query": "q rich", "cache_query": "q short"}\n'
            "```"
        )
        result = resolve_context_node(_base_state(), llm_caller=lambda prompt: raw)
        assert result["decision"] == "RETRIEVE"
        assert result["retrieval_query"] == "q rich"

    def test_lowercase_decision_alias_parses(self):
        raw = '{"decision": "retrieval", "retrieval_query": "q", "cache_query": "q"}'
        result = resolve_context_node(_base_state(), llm_caller=lambda prompt: raw)
        assert result["decision"] == "RETRIEVE"

    def test_unchanged_when_queries_match_original(self):
        original = "HRIS tuh apa sih?"
        raw = f'{{"decision": "RETRIEVE", "retrieval_query": "{original}", "cache_query": "{original}"}}'
        result = resolve_context_node(
            _base_state(original_question=original), llm_caller=lambda prompt: raw
        )
        assert result["changed"] is False

    def test_attempts_increments_from_existing_state(self):
        raw = '{"decision": "RETRIEVE", "retrieval_query": "q", "cache_query": "q"}'
        result = resolve_context_node(_base_state(attempts=1), llm_caller=lambda prompt: raw)
        assert result["attempts"] == 2


class TestResolveContextNodeFallback:
    def test_empty_llm_output_falls_back_to_original(self):
        original = "Form apa aja yang harus diisi buat itu?"
        result = resolve_context_node(
            _base_state(original_question=original), llm_caller=lambda prompt: ""
        )
        assert result["decision"] == "RETRIEVE"
        assert result["retrieval_query"] == original
        assert result["cache_query"] == original
        assert result["changed"] is False

    def test_garbage_llm_output_falls_back_to_original(self):
        original = "Apa itu HRIS?"
        result = resolve_context_node(
            _base_state(original_question=original),
            llm_caller=lambda prompt: "I'm not sure how to answer that.",
        )
        assert result["decision"] == "RETRIEVE"
        assert result["retrieval_query"] == original

    def test_malformed_json_falls_back(self):
        result = resolve_context_node(
            _base_state(), llm_caller=lambda prompt: "{decision: RETRIEVE, invalid}"
        )
        assert result["decision"] == "RETRIEVE"
        assert result["retrieval_query"] == result["cache_query"]

    def test_llm_caller_receives_prompt_containing_question_and_context(self):
        captured: dict[str, str] = {}

        def fake_caller(prompt: str) -> str:
            captured["prompt"] = prompt
            return '{"decision": "RETRIEVE", "retrieval_query": "q", "cache_query": "q"}'

        state = _base_state(
            original_question="Kalau luar negeri gimana?",
            conversation_context="User: perjalanan dinas dalam negeri\nAssistant: ...",
        )
        resolve_context_node(state, llm_caller=fake_caller)
        assert "Kalau luar negeri gimana?" in captured["prompt"]
        assert "perjalanan dinas dalam negeri" in captured["prompt"]
