from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


# cek header/footer SOP yang berulang dan ganggu retrieval
NOISE_LINE_PATTERNS = [
    re.compile(r"(?i)^\s*controlled copy\s*$"),
    re.compile(r"(?i)^\s*standard operating procedure\s*$"),
    re.compile(r"(?i)^\s*nomor dokumen\b.*\bhalaman\s*$"),
    re.compile(r"(?i)^\s*versi\s*:\s*.*$"),
    re.compile(r"(?i)^\s*nomor dokumen\s*:\s*.*$"),
    re.compile(r"(?i)^\s*pemilik prosedur\s*:\s*.*$"),
    re.compile(r"(?i)^\s*nama dokumen\s*:\s*.*$"),
    re.compile(r"(?i)^\s*departemen terkait\s*:\s*.*$"),
    re.compile(r"(?i)^\s*tanggal pengesahan\s*:\s*.*$"),
    re.compile(r"(?i)^\s*mulai berlaku\s*:\s*.*$"),
    re.compile(r"(?i)^\s*tanggal perubahan\s*:\s*.*$"),
    re.compile(r"(?i)^\s*referensi\s*:\s*.*$"),
    re.compile(r"(?i)^\s*\d+\s+dari\s+\d+\s*$"),
    re.compile(r"(?i)^.*\b\d+\s+dari\s+\d+\b.*$"),
]

SKIP_PAGE_MARKERS = (
    "lembar pengesahan",
    "lembar histori perubahan",
)

# cek heading model "Pasal 5"
ARTICLE_HEADING_PATTERN = re.compile(
    r"(?i)^pasal\s+\d+[a-z]?(?:\s*[-\u2013\u2014]\s*.+)?$"
)
# cek heading model "BAB II"
CHAPTER_HEADING_PATTERN = re.compile(
    r"(?i)^bab\s+[ivxlcdm0-9]+(?:\s*[-\u2013\u2014]\s*.+)?$"
)
# cek heading bernomor seperti "4.1 Prinsip Umum"
NUMBERED_HEADING_PATTERN = re.compile(
    r"^\d+(?:\.\d+){0,2}\.?\s+[A-Z][A-Za-z0-9/&(),'\- ]+$"
)
# cek heading huruf besar pendek
UPPERCASE_HEADING_PATTERN = re.compile(r"^[A-Z][A-Z0-9/&(),'\- ]+$")


def build_text_splitter(chunk_size: int = 1200, chunk_overlap: int = 150) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _is_noise_line(line: str) -> bool:
    normalized = line.strip()
    if not normalized:
        return True
    return any(pattern.match(normalized) for pattern in NOISE_LINE_PATTERNS)


def _clean_page_text(document: Document) -> str:
    raw_lines = [line.strip() for line in document.page_content.splitlines()]
    if not raw_lines:
        return ""
    title = _normalize_whitespace(str(document.metadata.get("title", "")).strip()).lower()
    title_aliases = {title}
    if title.startswith("sop - "):
        title_aliases.add(title.removeprefix("sop - ").strip())

    lowered_page = "\n".join(raw_lines).lower()
    if any(marker in lowered_page for marker in SKIP_PAGE_MARKERS):
        return ""
    if (
        "level dokumen" in lowered_page
        and "pemilik dokumen" in lowered_page
        and "nomor dokumen" in lowered_page
    ):
        return ""

    cleaned_lines = [
        line
        for line in raw_lines
        if not _is_noise_line(line)
        and _normalize_whitespace(line).lower() not in title_aliases
    ]
    if not cleaned_lines:
        return ""

    if len(cleaned_lines) <= 2 and all(len(_normalize_whitespace(line).split()) <= 4 for line in cleaned_lines):
        return ""

    if (
        len(cleaned_lines) <= 3
        and "level dokumen" in lowered_page
        and "pemilik dokumen" in lowered_page
    ):
        return ""

    return "\n".join(cleaned_lines).strip()


def _looks_like_heading(line: str) -> bool:
    normalized = _normalize_whitespace(line)
    if not normalized:
        return False

    word_count = len(normalized.split())
    if word_count > 12 or len(normalized) > 110:
        return False

    if ARTICLE_HEADING_PATTERN.match(normalized):
        return True
    if CHAPTER_HEADING_PATTERN.match(normalized):
        return True
    if NUMBERED_HEADING_PATTERN.match(normalized):
        return True

    if (
        UPPERCASE_HEADING_PATTERN.match(normalized)
        and 1 <= word_count <= 6
        and normalized.lower() not in SKIP_PAGE_MARKERS
    ):
        return True

    return False


def _append_segment(
    sectioned_documents: list[Document],
    document: Document,
    content_lines: list[str],
    section: str | None,
) -> None:
    content = "\n".join(content_lines).strip()
    if not content:
        return
    if section and _normalize_whitespace(content) == _normalize_whitespace(section):
        return

    metadata = dict(document.metadata)
    if section:
        metadata["section"] = section
    sectioned_documents.append(Document(page_content=content, metadata=metadata))


def split_documents_by_section(documents: list[Document]) -> list[Document]:
    """Split documents on best-effort headings while preserving page metadata."""
    sectioned_documents: list[Document] = []
    active_sections: dict[str, str] = {}

    for document in documents:
        source = str(document.metadata.get("source", "unknown source"))
        current_section = active_sections.get(source)
        cleaned_text = _clean_page_text(document)
        if not cleaned_text:
            continue

        lines = [_normalize_whitespace(line) for line in cleaned_text.splitlines() if line.strip()]
        if not lines:
            continue

        buffer: list[str] = []
        for line in lines:
            if _looks_like_heading(line):
                _append_segment(sectioned_documents, document, buffer, current_section)
                current_section = line
                buffer = [line]
                continue
            buffer.append(line)

        _append_segment(sectioned_documents, document, buffer, current_section)
        if current_section:
            active_sections[source] = current_section

    return sectioned_documents


def chunk_documents(documents: list[Document]) -> list[Document]:
    splitter = build_text_splitter()
    chunks = splitter.split_documents(split_documents_by_section(documents))

    for index, chunk in enumerate(chunks, start=1):
        chunk.metadata["chunk_id"] = index

    return chunks
