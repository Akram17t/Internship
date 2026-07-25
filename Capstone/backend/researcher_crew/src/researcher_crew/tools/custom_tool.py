from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.settings import get_int_env, load_capstone_env
from backend.preprocessing.vectorstore import hybrid_search

load_capstone_env()


def _citation_from_document(document, citation_id: int) -> dict[str, object]:
    # Ubah satu chunk hasil retrieval menjadi payload citation.
    page = document.metadata.get("page")
    page_end = document.metadata.get("page_end")
    visible_page = page + 1 if isinstance(page, int) else None
    visible_page_end = page_end + 1 if isinstance(page_end, int) else None
    return {
        "id": citation_id,
        "source": str(document.metadata.get("source", "unknown source")),
        "page": visible_page,
        "page_end": (
            visible_page_end
            if (
                isinstance(visible_page, int)
                and isinstance(visible_page_end, int)
                and visible_page_end > visible_page
            )
            else None
        ),
        "section": document.metadata.get("section"),
        "chunk_id": document.metadata.get("chunk_id"),
        "content_type": document.metadata.get("content_type"),
    }


def retrieve_knowledge(query: str, k: int | None = None) -> tuple[str, list[dict[str, object]]]:
    # Jalankan retrieval lalu bentuk evidence dan citation yang sudah deduplikasi.
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
            metadata.get("page_end"),
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
            if citation.get("page_end"):
                details.append(f"PDF pages: {citation['page']}-{citation['page_end']}")
            else:
                details.append(f"PDF page: {citation['page']}")
        if metadata.get("chunk_id"):
            details.append(f"Chunk: {metadata['chunk_id']}")

        content = " ".join(document.page_content.split())
        evidence_sections.append(
            f"[{citation_id}] " + " | ".join(details) + f"\nExact excerpt: {content}"
        )

    return "\n\n".join(evidence_sections), citations
