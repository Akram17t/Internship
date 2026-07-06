from __future__ import annotations

import math
import uuid
from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.settings import (
    get_env,
    get_float_env,
    get_int_env,
    get_required_env,
    load_capstone_env,
)
from backend.preprocessing.embedding import get_embedding_model

load_capstone_env()


BACKEND_DIR = Path(__file__).resolve().parent.parent
ACTIVE_INDEX_FILE = ".active-chroma-index"
VERSIONED_INDEX_DIR = "indexes"


def _get_chroma_base_dir() -> Path:
    raw_dir = get_env("CHROMA_DIR", "backend/chroma_db")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = BACKEND_DIR.parent / path
    return path


def get_chroma_dir() -> Path:
    base_dir = _get_chroma_base_dir()
    active_file = base_dir / ACTIVE_INDEX_FILE
    if active_file.exists():
        active_name = active_file.read_text(encoding="utf-8").strip()
        active_dir = (base_dir / active_name).resolve()
        try:
            active_dir.relative_to(base_dir.resolve())
        except ValueError:
            return base_dir
        if active_dir.exists():
            return active_dir
    return base_dir


def get_vectorstore() -> Chroma:
    return Chroma(
        persist_directory=str(get_chroma_dir()),
        embedding_function=get_embedding_model(),
    )


def rebuild_vectorstore(chunks: list[Document]) -> Chroma:
    base_dir = _get_chroma_base_dir()
    index_name = f"{VERSIONED_INDEX_DIR}/{uuid.uuid4().hex}"
    chroma_dir = base_dir / index_name
    chroma_dir.mkdir(parents=True, exist_ok=True)

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=get_embedding_model(),
        persist_directory=str(chroma_dir),
    )
    (base_dir / ACTIVE_INDEX_FILE).write_text(index_name, encoding="utf-8")
    return vectorstore


@lru_cache(maxsize=1)
def get_reranker():
    model_name = get_required_env("RERANK_MODEL")
    if not model_name:
        return None

    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        return None

    try:
        return CrossEncoder(model_name, max_length=get_int_env("RERANK_MAX_LENGTH", 256))
    except Exception:
        return None


def _rerank_documents(
    query: str, documents: list[Document]
) -> list[tuple[Document, float | None]]:
    """Order documents by reranker relevance; score is a 0-1 value (None if no reranker)."""
    reranker = get_reranker()
    if reranker is None or not documents:
        return [(document, None) for document in documents]

    pairs = [(query, document.page_content) for document in documents]
    scores = reranker.predict(pairs)
    ranked = sorted(
        zip(documents, scores),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    # CrossEncoder outputs relevance logits; sigmoid normalizes them to 0-1
    # so RETRIEVAL_MIN_SCORE is an intuitive, model-agnostic threshold.
    return [(document, 1.0 / (1.0 + math.exp(-float(score)))) for document, score in ranked]


def hybrid_search(query: str, k: int = 4) -> list[Document]:
    """Retrieve semantically relevant chunks, rerank, and drop off-topic matches."""
    vectorstore = get_vectorstore()
    fetch_k = get_int_env("RERANK_CANDIDATES", max(k + 2, 6))
    vector_results = vectorstore.similarity_search(query, k=fetch_k)
    ranked = _rerank_documents(query, vector_results)

    # When the best rerank score is below the threshold, treat the query as
    # having no relevant source so callers can short-circuit before hitting the
    # LLM (e.g. an off-topic FAQ question -> instant "no source" response).
    min_score = get_float_env("RETRIEVAL_MIN_SCORE", 0.0)
    if min_score > 0:
        ranked = [item for item in ranked if item[1] is None or item[1] >= min_score]

    return [document for document, _ in ranked][:k]
