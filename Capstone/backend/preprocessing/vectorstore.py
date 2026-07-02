from __future__ import annotations

import os
import uuid
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.preprocessing.embedding import get_embedding_model

load_dotenv()


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
ACTIVE_INDEX_FILE = ".active-chroma-index"
VERSIONED_INDEX_DIR = "indexes"


def _get_chroma_base_dir() -> Path:
    raw_dir = os.getenv("CHROMA_DIR", "backend/chroma_db")
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
    model_name = os.getenv("RERANK_MODEL", DEFAULT_RERANK_MODEL).strip()
    if not model_name:
        return None

    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        return None

    try:
        return CrossEncoder(model_name, max_length=int(os.getenv("RERANK_MAX_LENGTH", "256")))
    except Exception:
        return None


def _rerank_documents(query: str, documents: list[Document]) -> list[Document]:
    reranker = get_reranker()
    if reranker is None or not documents:
        return documents

    pairs = [(query, document.page_content) for document in documents]
    scores = reranker.predict(pairs)
    ranked = sorted(
        zip(documents, scores),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    return [document for document, _ in ranked]


def hybrid_search(query: str, k: int = 4) -> list[Document]:
    """Retrieve semantically relevant chunks, then rerank them when available."""
    vectorstore = get_vectorstore()
    fetch_k = int(os.getenv("RERANK_CANDIDATES", str(max(k + 2, 6))))
    vector_results = vectorstore.similarity_search(query, k=fetch_k)
    return _rerank_documents(query, vector_results)[:k]
