from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


SECTION_HEADING_PATTERN = re.compile(
    r"(?im)^[ \t]*(Pasal\s+\d+[A-Za-z]?\s*(?:[\-–—]\s*[^\r\n]+)?)\s*$"
)


def build_text_splitter(chunk_size: int = 1200, chunk_overlap: int = 150) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def split_documents_by_section(documents: list[Document]) -> list[Document]:
    """Split policy documents at article headings while carrying sections across PDF pages."""
    sectioned_documents: list[Document] = []
    active_sections: dict[str, str] = {}

    def append_segment(document: Document, content: str, section: str | None) -> None:
        normalized_content = content.strip()
        if not normalized_content:
            return

        metadata = dict(document.metadata)
        if section:
            metadata["section"] = section
        sectioned_documents.append(Document(page_content=normalized_content, metadata=metadata))

    for document in documents:
        source = str(document.metadata.get("source", "unknown source"))
        current_section = active_sections.get(source)
        matches = list(SECTION_HEADING_PATTERN.finditer(document.page_content))

        if not matches:
            append_segment(document, document.page_content, current_section)
            continue

        append_segment(document, document.page_content[: matches[0].start()], current_section)

        for index, match in enumerate(matches):
            current_section = " ".join(match.group(1).split())
            segment_end = matches[index + 1].start() if index + 1 < len(matches) else len(document.page_content)
            append_segment(document, document.page_content[match.start() : segment_end], current_section)

        if current_section:
            active_sections[source] = current_section

    return sectioned_documents


def chunk_documents(documents: list[Document]) -> list[Document]:
    splitter = build_text_splitter()
    chunks = splitter.split_documents(split_documents_by_section(documents))

    for index, chunk in enumerate(chunks, start=1):
        chunk.metadata["chunk_id"] = index

    return chunks
