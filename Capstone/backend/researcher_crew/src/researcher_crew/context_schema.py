"""Schema and state definitions for the context resolution graph.

Replaces the old regex-based rewrite subsystem. All context-reference
decisions are made by the LLM; this module only defines data contracts
and lenient parsing of the LLM's JSON output (the endpoint wraps JSON in
markdown code fences and does not reliably follow enum casing, so parsing
here is deliberately tolerant).
"""
from __future__ import annotations

import json
import re
from enum import Enum
from typing import TypedDict

from pydantic import BaseModel, Field, ValidationError


class ContextDecision(str, Enum):
    """Decision made by the LLM about whether retrieval is needed.

    REUSE_EVIDENCE is defined now so the graph structure does not need to
    change when 3-way routing is implemented later, but current node logic
    treats REUSE_EVIDENCE the same as RETRIEVE (no evidence cache exists
    yet in cache_db.py).
    """

    NO_RETRIEVAL = "NO_RETRIEVAL"
    RETRIEVE = "RETRIEVE"
    REUSE_EVIDENCE = "REUSE_EVIDENCE"


# Decisions that should be treated as "go retrieve" until REUSE_EVIDENCE
# gets its own dedicated handling (see plan Task 1, item "1=c").
RETRIEVAL_DECISIONS = {ContextDecision.RETRIEVE, ContextDecision.REUSE_EVIDENCE}


class ContextResolution(BaseModel):
    """Structured output the LLM must produce for one context resolution call."""

    decision: ContextDecision
    retrieval_query: str = Field(min_length=1)
    cache_query: str = Field(min_length=1)
    reasoning: str = Field(default="")


class ContextState(TypedDict):
    """Full state carried through the context resolution graph."""

    # --- Inputs ---
    original_question: str
    conversation_context: str
    conversation_id: str

    # --- Processing ---
    decision: str  # ContextDecision value, stored as str for TypedDict simplicity
    attempts: int
    max_attempts: int

    # --- Outputs ---
    retrieval_query: str
    cache_query: str
    changed: bool
    duration_seconds: float


_CODE_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)

# Endpoint observed to emit lowercase/alternate decision spellings
# (e.g. "retrieval" instead of "RETRIEVE"); tolerate common variants.
_DECISION_ALIASES = {
    "NO_RETRIEVAL": ContextDecision.NO_RETRIEVAL,
    "NO RETRIEVAL": ContextDecision.NO_RETRIEVAL,
    "NORETRIEVAL": ContextDecision.NO_RETRIEVAL,
    "KEEP": ContextDecision.NO_RETRIEVAL,
    "RETRIEVE": ContextDecision.RETRIEVE,
    "RETRIEVAL": ContextDecision.RETRIEVE,
    "REWRITE": ContextDecision.RETRIEVE,
    "REUSE_EVIDENCE": ContextDecision.REUSE_EVIDENCE,
    "REUSE EVIDENCE": ContextDecision.REUSE_EVIDENCE,
    "CONTINUE_TO_USE_EVIDENCE": ContextDecision.REUSE_EVIDENCE,
}


def _strip_code_fence(raw: str) -> str:
    """Strip a single markdown code fence wrapper if present."""
    match = _CODE_FENCE_PATTERN.match(raw.strip())
    if match:
        return match.group("body").strip()
    return raw.strip()


def _normalize_decision(value: object) -> str:
    if not isinstance(value, str):
        return ""
    key = value.strip().upper()
    alias = _DECISION_ALIASES.get(key)
    return alias.value if alias else key


def parse_resolution(raw: str) -> ContextResolution | None:
    """Parse and validate the LLM's JSON output into a ContextResolution.

    Tolerant of markdown code fences and decision value casing/spelling
    variance. Returns None on any failure so callers can fall back safely.
    """
    if not raw or not raw.strip():
        return None

    text = _strip_code_fence(raw)

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    normalized_decision = _normalize_decision(payload.get("decision"))
    payload = {**payload, "decision": normalized_decision}

    try:
        return ContextResolution.model_validate(payload)
    except ValidationError:
        return None


def is_retrieval_decision(decision: str) -> bool:
    """True if the decision means retrieval should happen (2-way + REUSE_EVIDENCE)."""
    try:
        parsed = ContextDecision(decision)
    except ValueError:
        return False
    return parsed in RETRIEVAL_DECISIONS
