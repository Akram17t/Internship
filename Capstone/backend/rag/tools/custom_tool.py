from __future__ import annotations

from backend.settings import get_int_env, load_capstone_env
from backend.preprocessing.vectorstore import hybrid_search

load_capstone_env()


def _citation_from_document(document, citation_id: int) -> dict[str, object]:
    page = document.metadata.get("page")
    return {
        "id": citation_id,
        "source": str(document.metadata.get("source", "unknown source")),
        "page": page + 1 if isinstance(page, int) else None,
        "section": document.metadata.get("section"),
        "chunk_id": document.metadata.get("chunk_id"),
    }


def retrieve_knowledge(query: str, k: int | None = None) -> tuple[str, list[dict[str, object]]]:
    documents = hybrid_search(query, k=k or get_int_env("TOP_K", 4))
    if not documents:
        return "No matching knowledge chunks were found in the local vector database.", []

    evidence_sections: list[str] = []
    citations: list[dict[str, object]] = []
    citation_ids: dict[tuple[object, ...], int] = {}

    for document in documents:
        metadata = document.metadata
        key = (
            metadata.get("source"),
            metadata.get("page"),
            metadata.get("section"),
        )
        citation_id = citation_ids.get(key)
        if citation_id is None:
            citation_id = len(citations) + 1
            citation_ids[key] = citation_id
            citations.append(_citation_from_document(document, citation_id))

        citation = citations[citation_id - 1]
        details = [f"File: {citation['source']}"]
        if citation.get("section"):
            details.append(f"Section: {citation['section']}")
        if citation.get("page"):
            details.append(f"PDF page: {citation['page']}")
        if metadata.get("chunk_id"):
            details.append(f"Chunk: {metadata['chunk_id']}")

        content = " ".join(document.page_content.split())
        evidence_sections.append(
            f"[{citation_id}] " + " | ".join(details) + f"\nExact excerpt: {content}"
        )

    return "\n\n".join(evidence_sections), citations
