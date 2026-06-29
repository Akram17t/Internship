from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.preprocessing.embedding import get_embedding_model

load_dotenv()


BACKEND_DIR = Path(__file__).resolve().parent.parent
MIN_TERM_COVERAGE = 0.5
QUERY_STOPWORDS = {
    "ada",
    "apa",
    "apakah",
    "atau",
    "bagaimana",
    "berapa",
    "dalam",
    "dan",
    "dari",
    "dengan",
    "ini",
    "itu",
    "pada",
    "untuk",
    "yang",
}
TERM_EXPANSIONS = {
    "kapan": {"jadwal", "tanggal", "waktu"},
    "dibayarkan": {"dibayar", "pembayaran"},
    "dibayar": {"dibayarkan", "pembayaran"},
    "gajian": {"gaji", "penggajian", "pembayaran"},
    "jatah": {"hak", "entitlement"},
}


def get_chroma_dir() -> Path:
    raw_dir = os.getenv("CHROMA_DIR", "backend/chroma_db")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = BACKEND_DIR.parent / path
    return path


def get_vectorstore() -> Chroma:
    return Chroma(
        persist_directory=str(get_chroma_dir()),
        embedding_function=get_embedding_model(),
    )


def rebuild_vectorstore(chunks: list[Document]) -> Chroma:
    chroma_dir = get_chroma_dir()
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    return Chroma.from_documents(
        documents=chunks,
        embedding=get_embedding_model(),
        persist_directory=str(chroma_dir),
    )


def hybrid_search(query: str, k: int = 4) -> list[Document]:
    """Combine semantic retrieval with lexical and section-heading relevance."""
    vectorstore = get_vectorstore()
    vector_results = vectorstore.similarity_search_with_score(query, k=max(k * 5, 20))
    vector_scores = {
        document.metadata.get("chunk_id"): 1 / (1 + max(float(distance), 0))
        for document, distance in vector_results
    }

    collection = vectorstore.get(include=["documents", "metadatas"])
    query_terms = {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) >= 3
        and token not in QUERY_STOPWORDS
    }
    if not query_terms:
        return []

    ranked: list[tuple[float, float, Document]] = []
    for content, metadata in zip(collection.get("documents", []), collection.get("metadatas", [])):
        content = content or ""
        metadata = metadata or {}
        section = str(metadata.get("section", ""))
        source = str(metadata.get("source", ""))
        searchable_content = content.lower()
        searchable_section = section.lower()
        searchable_source = source.lower().replace("_", " ")

        lexical_score = 0.0
        matched_terms = 0
        for term in query_terms:
            variants = {term, *TERM_EXPANSIONS.get(term, set())}
            content_hits = min(max(searchable_content.count(variant) for variant in variants), 3)
            section_hit = 3 if any(variant in searchable_section for variant in variants) else 0
            source_hit = 1 if any(variant in searchable_source for variant in variants) else 0
            term_score = content_hits + section_hit + source_hit
            if term_score:
                matched_terms += 1
                lexical_score += term_score

        term_coverage = matched_terms / len(query_terms)
        coverage_bonus = term_coverage * 2
        semantic_score = vector_scores.get(metadata.get("chunk_id"), 0)
        total_score = lexical_score + coverage_bonus + semantic_score
        ranked.append((total_score, term_coverage, Document(page_content=content, metadata=metadata)))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        document
        for _, term_coverage, document in ranked
        if term_coverage >= MIN_TERM_COVERAGE
    ][:k]
