"""Context resolution graph: LangGraph StateGraph replacing the old regex-based
_rewrite_query in main.py.

Design (per plan discussion):
- No regex anywhere; all decisions are made by one LLM call per attempt.
- 2-way decision active now (NO_RETRIEVAL / RETRIEVE); REUSE_EVIDENCE is
  defined in the schema but currently treated as RETRIEVE (no evidence
  cache exists in cache_db.py yet).
- Dual output: retrieval_query (context-synthesized, used for document
  retrieval) and cache_query (short standalone question, used as the
  semantic cache key).
- Scope ends here: this module does not call retrieve_knowledge, generation,
  or finalization. Callers (main.py) take retrieval_query/cache_query and
  drive the rest of the pipeline themselves.
"""
from __future__ import annotations

import functools
import time
from typing import Callable

from langgraph.graph import END, StateGraph

from researcher_crew.context_prompts import build_context_resolution_prompt
from researcher_crew.context_schema import ContextState, is_retrieval_decision, parse_resolution

try:
    from backend.observability import span, update_observation
except ImportError:  # pragma: no cover - defensive, backend is always on sys.path in this project
    from contextlib import contextmanager

    class _NoopObservation:
        def update(self, **_: object) -> None:
            return None

    @contextmanager
    def span(*_args: object, **_kwargs: object):  # type: ignore[no-redef]
        yield _NoopObservation()

    def update_observation(*_args: object, **_kwargs: object) -> None:  # type: ignore[no-redef]
        return None

# Type of the LLM call the node needs: (prompt, num_predict, temperature) -> raw text.
LLMCaller = Callable[..., str]

DEFAULT_MAX_ATTEMPTS = 2
_NUM_PREDICT = 220
_TEMPERATURE = 0.0

# Absolute ceilings used by validate_node; kept as plain constants (not regex)
# so validation stays a cheap heuristic sanity check, not content matching.
_MAX_RETRIEVAL_QUERY_CHARS = 600
_MIN_QUERY_CHARS = 3


def _default_llm_caller() -> LLMCaller:
    """Lazily import main.py's LLM caller to avoid a circular import at module load."""
    from researcher_crew.main import ModelGenerationError, _generate_with_model

    def _call(prompt: str) -> str:
        try:
            return _generate_with_model(
                prompt,
                num_predict=_NUM_PREDICT,
                temperature=_TEMPERATURE,
                generation_name="context-resolution-generation",
                trace_metadata={"node": "resolve_context"},
                trace_generation=True,
            )
        except ModelGenerationError:
            return ""

    return _call


def resolve_context_node(state: ContextState, llm_caller: LLMCaller | None = None) -> dict:
    """LLM decides NO_RETRIEVAL vs RETRIEVE and produces both query variants.

    On any parse/call failure, falls back to treating the original question
    as both retrieval_query and cache_query with decision=RETRIEVE (safe
    default: better to retrieve unnecessarily than to silently skip it).
    """
    caller = llm_caller or _default_llm_caller()
    prompt = build_context_resolution_prompt(
        question=state["original_question"],
        conversation_context=state["conversation_context"],
    )

    raw_output = caller(prompt)
    resolution = parse_resolution(raw_output)

    attempts = state.get("attempts", 0) + 1

    if resolution is None:
        original = state["original_question"]
        return {
            "decision": "RETRIEVE",
            "retrieval_query": original,
            "cache_query": original,
            "changed": False,
            "attempts": attempts,
        }

    original = state["original_question"]
    changed = (
        resolution.retrieval_query.strip() != original.strip()
        or resolution.cache_query.strip() != original.strip()
    )

    return {
        "decision": resolution.decision.value,
        "retrieval_query": resolution.retrieval_query,
        "cache_query": resolution.cache_query,
        "changed": changed,
        "attempts": attempts,
    }


def check_history_node(state: ContextState) -> dict:
    """Early exit when there is no conversation history: skip the LLM call."""
    original = state["original_question"]
    has_history = bool(state["conversation_context"].strip())
    with span(
        "check-history",
        metadata={"has_history": has_history},
    ) as node_span:
        if not has_history:
            update_observation(node_span, output={"skip_llm": True})
            return {
                "decision": "RETRIEVE",
                "retrieval_query": original,
                "cache_query": original,
                "changed": False,
            }
        update_observation(node_span, output={"skip_llm": False})
        return {}


def _route_after_check_history(state: ContextState) -> str:
    if not state["conversation_context"].strip():
        return "passthrough"
    return "resolve"


def _route_after_resolve(state: ContextState) -> str:
    if not is_retrieval_decision(state.get("decision", "")):
        return "passthrough"
    return "validate"


def validate_node(state: ContextState) -> dict:
    """Heuristic (non-regex) quality gate on resolve_context's output.

    Checks: neither query is empty/too-short, retrieval_query isn't
    absurdly long, cache_query isn't longer than retrieval_query. On
    failure, retries resolve_context up to max_attempts, then falls back
    to the original question.
    """
    retrieval_query = state.get("retrieval_query", "")
    cache_query = state.get("cache_query", "")
    attempts = state.get("attempts", 0)
    max_attempts = state.get("max_attempts", DEFAULT_MAX_ATTEMPTS)

    is_valid = (
        len(retrieval_query.strip()) >= _MIN_QUERY_CHARS
        and len(cache_query.strip()) >= _MIN_QUERY_CHARS
        and len(retrieval_query) <= _MAX_RETRIEVAL_QUERY_CHARS
        and len(cache_query) <= len(retrieval_query) + 50
    )

    with span(
        "validate",
        metadata={"attempts": attempts, "max_attempts": max_attempts, "is_valid": is_valid},
    ) as node_span:
        if is_valid:
            update_observation(node_span, output={"result": "valid"})
            return {}

        if attempts < max_attempts:
            update_observation(node_span, output={"result": "invalid_retry"})
            # Signal retry: leave decision as-is, resolve_context_node will run again.
            return {}

        update_observation(node_span, output={"result": "invalid_exhausted_fallback"})
        original = state["original_question"]
        return {
            "decision": "RETRIEVE",
            "retrieval_query": original,
            "cache_query": original,
            "changed": False,
        }


def _route_after_validate(state: ContextState) -> str:
    retrieval_query = state.get("retrieval_query", "")
    cache_query = state.get("cache_query", "")
    attempts = state.get("attempts", 0)
    max_attempts = state.get("max_attempts", DEFAULT_MAX_ATTEMPTS)

    is_valid = (
        len(retrieval_query.strip()) >= _MIN_QUERY_CHARS
        and len(cache_query.strip()) >= _MIN_QUERY_CHARS
        and len(retrieval_query) <= _MAX_RETRIEVAL_QUERY_CHARS
        and len(cache_query) <= len(retrieval_query) + 50
    )

    if is_valid:
        return "passthrough"
    if attempts < max_attempts:
        return "retry"
    return "passthrough"


def passthrough_node(state: ContextState) -> dict:
    """No-op node; state is already in its final shape by this point."""
    return {}


_compiled_graph = None


def _build_graph(llm_caller: LLMCaller | None = None):
    """Build and compile the graph. If llm_caller is given, resolve_context_node
    is bound to it via functools.partial (used for integration tests); otherwise
    the node falls back to the real _default_llm_caller() lazily at call time.
    """
    resolve_node = (
        functools.partial(resolve_context_node, llm_caller=llm_caller)
        if llm_caller is not None
        else resolve_context_node
    )

    graph = StateGraph(ContextState)
    graph.add_node("check_history", check_history_node)
    graph.add_node("resolve_context", resolve_node)
    graph.add_node("validate", validate_node)
    graph.add_node("passthrough", passthrough_node)

    graph.set_entry_point("check_history")
    graph.add_conditional_edges(
        "check_history",
        _route_after_check_history,
        {"passthrough": "passthrough", "resolve": "resolve_context"},
    )
    graph.add_conditional_edges(
        "resolve_context",
        _route_after_resolve,
        {"passthrough": "passthrough", "validate": "validate"},
    )
    graph.add_conditional_edges(
        "validate",
        _route_after_validate,
        {"passthrough": "passthrough", "retry": "resolve_context"},
    )
    graph.add_edge("passthrough", END)
    return graph.compile()


def _get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


def resolve_query_context(
    original_question: str,
    conversation_context: str,
    conversation_id: str = "",
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    llm_caller: LLMCaller | None = None,
) -> ContextState:
    """Public entry point: run the context resolution graph and return final state.

    llm_caller is exposed for integration testing; production callers should
    omit it so the real model-backed caller is used.
    """
    initial_state: ContextState = {
        "original_question": original_question,
        "conversation_context": conversation_context,
        "conversation_id": conversation_id,
        "decision": "",
        "attempts": 0,
        "max_attempts": max_attempts,
        "retrieval_query": original_question,
        "cache_query": original_question,
        "changed": False,
        "duration_seconds": 0.0,
    }

    compiled = _build_graph(llm_caller) if llm_caller is not None else _get_compiled_graph()

    started_at = time.perf_counter()
    result = compiled.invoke(initial_state)
    result["duration_seconds"] = time.perf_counter() - started_at
    return result
