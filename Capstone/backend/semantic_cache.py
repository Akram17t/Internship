from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma

from backend.cache_db import (
    get_semantic_cache_entry,
    get_semantic_cache_entry_by_question,
    insert_semantic_cache_entry,
    mark_semantic_cache_hit,
    normalize_semantic_question,
)
from backend.preprocessing.embedding import get_embedding_model
from backend.preprocessing.vectorstore import get_active_index_name
from backend.settings import get_env, get_float_env, get_int_env, get_required_env, load_capstone_env

load_capstone_env()

logger = logging.getLogger("uvicorn.error")
_CACHE_LOCK = threading.Lock()
_CACHE_COLLECTION = "semantic_answer_cache"

UNSUPPORTED_MARKERS = (
    "tidak tersedia dalam dokumen",
    "tidak tersedia di dokumen",
    "tidak disebutkan",
    "tidak dinyatakan",
    "tidak ada ketentuan",
    "tidak dapat menemukan informasi terkait hal tersebut",
    "tidak ada informasi",
    "tidak memuat",
    "tidak mencakup",
    "tidak menjelaskan",
    "tanpa menyebutkan",
    "tidak ditemukan",
    "belum tersedia",
    "belum dapat dikonfirmasi",
    "tidak dapat dikonfirmasi",
    "dokumen yang terindeks tidak",
    "dokumen terindeks tidak",
)


@dataclass(frozen=True)
class SemanticCacheHit:
    entry_id: str
    answer: str
    citations: list[dict[str, object]]
    selected_forms: list[str]
    similarity: float


def _is_enabled() -> bool:
    raw_value = get_env("SEMANTIC_CACHE_ENABLED", "true").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _cache_dir() -> Path:
    raw_dir = get_env("SEMANTIC_CACHE_DIR", "backend/cache/semantic_chroma")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def _threshold() -> float:
    return get_float_env("SEMANTIC_CACHE_THRESHOLD", 0.92)


def _top_k() -> int:
    return max(get_int_env("SEMANTIC_CACHE_TOP_K", 1), 1)


def _model_name() -> str:
    return get_required_env("MODEL")


def _embed_model_name() -> str:
    return get_required_env("EMBED_MODEL")


def _is_unsupported_answer(answer: str) -> bool:
    normalized = " ".join(answer.lower().split())
    return any(marker in normalized for marker in UNSUPPORTED_MARKERS)


def _is_cacheable(answer: str, citations: list[dict[str, object]]) -> bool:
    return bool(answer.strip()) and bool(citations) and not _is_unsupported_answer(answer)


def _normalize_cache_question(question: str) -> str:
    return normalize_semantic_question(question)


def _get_cache_store() -> Chroma:
    directory = _cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=_CACHE_COLLECTION,
        persist_directory=str(directory),
        embedding_function=get_embedding_model(),
    )


def _normalize_citations(raw_citations: Any) -> list[dict[str, object]]:
    if not isinstance(raw_citations, list):
        return []
    citations: list[dict[str, object]] = []
    for item in raw_citations:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        if not source:
            continue
        citations.append(dict(item))
    return citations


def _normalize_selected_forms(raw_forms: Any) -> list[str]:
    if not isinstance(raw_forms, list):
        return []
    return [str(item).strip() for item in raw_forms if str(item).strip()]


def lookup_semantic_cache(question: str, *, trace_id: str = "") -> SemanticCacheHit | None:
    if not _is_enabled():
        logger.info("[%s] semantic_cache=miss reason=disabled", trace_id or "chat")
        return None

    active_index = get_active_index_name()
    model_name = _model_name()
    embed_model_name = _embed_model_name()
    exact_entry = get_semantic_cache_entry_by_question(
        question,
        active_index=active_index,
        model_name=model_name,
        embed_model_name=embed_model_name,
    )
    if exact_entry is not None:
        exact_citations = _normalize_citations(exact_entry.get("citations"))
        exact_forms = _normalize_selected_forms(exact_entry.get("selected_forms"))
        exact_answer = str(exact_entry.get("answer") or "").strip()
        if _is_cacheable(exact_answer, exact_citations):
            entry_id = str(exact_entry["id"])
            mark_semantic_cache_hit(entry_id)
            logger.info(
                "[%s] semantic_cache=hit match=exact similarity=1.0000 entry=%s active_index=%s",
                trace_id or "chat",
                entry_id,
                active_index,
            )
            return SemanticCacheHit(
                entry_id=entry_id,
                answer=exact_answer,
                citations=exact_citations,
                selected_forms=exact_forms,
                similarity=1.0,
            )

    try:
        normalized_question = _normalize_cache_question(question)
        metadata_filter = {
            "$and": [
                {"active_index": active_index},
                {"model_name": model_name},
                {"embed_model_name": embed_model_name},
            ]
        }
        with _CACHE_LOCK:
            results = _get_cache_store().similarity_search_with_relevance_scores(
                normalized_question,
                k=_top_k(),
                filter=metadata_filter,
            )
    except Exception as error:
        logger.warning(
            "[%s] semantic_cache=miss reason=lookup_error detail=%s",
            trace_id or "chat",
            error,
        )
        return None

    if not results:
        logger.info("[%s] semantic_cache=miss reason=empty", trace_id or "chat")
        return None

    document, similarity = results[0]
    entry_id = str(document.metadata.get("entry_id") or "").strip()
    if not entry_id:
        logger.info(
            "[%s] semantic_cache=miss reason=missing_entry_id similarity=%.4f",
            trace_id or "chat",
            similarity,
        )
        return None

    if float(similarity) < _threshold():
        logger.info(
            "[%s] semantic_cache=miss reason=below_threshold similarity=%.4f entry=%s",
            trace_id or "chat",
            similarity,
            entry_id,
        )
        return None

    entry = get_semantic_cache_entry(entry_id)
    if entry is None:
        logger.info(
            "[%s] semantic_cache=miss reason=metadata_missing similarity=%.4f entry=%s",
            trace_id or "chat",
            similarity,
            entry_id,
        )
        return None

    if entry["active_index"] != active_index:
        logger.info(
            "[%s] semantic_cache=miss reason=index_mismatch similarity=%.4f entry=%s cached_index=%s active_index=%s",
            trace_id or "chat",
            similarity,
            entry_id,
            entry["active_index"],
            active_index,
        )
        return None
    if entry["model_name"] != model_name or entry["embed_model_name"] != embed_model_name:
        logger.info(
            "[%s] semantic_cache=miss reason=model_mismatch similarity=%.4f entry=%s",
            trace_id or "chat",
            similarity,
            entry_id,
        )
        return None

    citations = _normalize_citations(entry.get("citations"))
    selected_forms = _normalize_selected_forms(entry.get("selected_forms"))
    answer = str(entry.get("answer") or "").strip()
    if not _is_cacheable(answer, citations):
        logger.info(
            "[%s] semantic_cache=miss reason=uncacheable_payload similarity=%.4f entry=%s",
            trace_id or "chat",
            similarity,
            entry_id,
        )
        return None

    mark_semantic_cache_hit(entry_id)
    logger.info(
        "[%s] semantic_cache=hit similarity=%.4f entry=%s active_index=%s",
        trace_id or "chat",
        similarity,
        entry_id,
        active_index,
    )
    return SemanticCacheHit(
        entry_id=entry_id,
        answer=answer,
        citations=citations,
        selected_forms=selected_forms,
        similarity=float(similarity),
    )


def store_semantic_cache(
    question: str,
    answer: str,
    citations: list[dict[str, object]],
    selected_forms: list[str],
    *,
    trace_id: str = "",
) -> str | None:
    if not _is_enabled() or not _is_cacheable(answer, citations):
        return None

    entry_id = uuid.uuid4().hex
    active_index = get_active_index_name()
    model_name = _model_name()
    embed_model_name = _embed_model_name()

    try:
        insert_semantic_cache_entry(
            entry_id=entry_id,
            question=question,
            answer=answer,
            citations=citations,
            selected_forms=selected_forms,
            active_index=active_index,
            model_name=model_name,
            embed_model_name=embed_model_name,
        )
        with _CACHE_LOCK:
            _get_cache_store().add_texts(
                texts=[_normalize_cache_question(question)],
                metadatas=[
                    {
                        "entry_id": entry_id,
                        "active_index": active_index,
                        "model_name": model_name,
                        "embed_model_name": embed_model_name,
                    }
                ],
                ids=[entry_id],
            )
    except Exception as error:
        logger.warning(
            "[%s] semantic_cache=store_failed entry=%s detail=%s",
            trace_id or "chat",
            entry_id,
            error,
        )
        return None

    logger.debug(
        "[%s] semantic_cache=stored entry=%s active_index=%s",
        trace_id or "chat",
        entry_id,
        active_index,
    )
    return entry_id
