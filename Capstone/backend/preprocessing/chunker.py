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
DECIMAL_HEADING_PATTERN = re.compile(
    r"^\d+\.\d+(?:\.\d+)?\.?\s+[A-Z][A-Za-z0-9/&(),'\- ]+$"
)
TOP_LEVEL_HEADING_PATTERN = re.compile(r"^\d+\.\s+(?P<title>.+)$")
OFFICIAL_UPPERCASE_TITLES = {
    "TUJUAN",
    "RUANG LINGKUP",
    "DEFINISI",
    "KEBIJAKAN",
    "KETENTUAN",
    "AKTIVITAS",
    "TUGAS DAN TANGGUNG JAWAB",
    "UKURAN KEBERHASILAN",
    "DOKUMEN TERKAIT",
    "ALUR PROSES",
}
TEMPLATE_TITLE_PATTERN = re.compile(r"(?i)^\[nama perusahaan\](?:\s+.+)?$")
TABLE_HEADER_PATTERNS = (
    re.compile(r"(?i)\bperan\s+tanggung\s+jawab\b"),
    re.compile(r"(?i)\bnomor\s+form\s+nama\s+form\b"),
    re.compile(r"(?i)\bno\s+proses\s+pic\s+sasaran\b"),
    re.compile(r"(?i)\bdestinasi\s+jabatan\b"),
    re.compile(r"(?i)\bjabatan\s+requestor\b"),
    re.compile(r"(?i)\baspek\s+peristiwa\b"),
)
TABLE_ROW_PATTERN = re.compile(
    r"(?i)^(?:\d+\s+\S+|(?:dalam|luar)\s+negeri\b|(?:staff|manager|director|"
    r"supervisor|karyawan|administrator|pemohon|pemilik|incident|general|hr)\b|"
    r"\[nomor\s+form\]|[A-Z0-9]+/FM/|FM/[A-Z]+/)"
)
CURRENCY_PATTERN = re.compile(r"(?i)\b(?:rp|usd)\s*\d")
ORPHAN_POLICY_LINE_PATTERN = re.compile(
    r"(?i)^perjalanan\s+dinas\s+lebih\s+dari\s+\d+.*\bpenugasan\b"
)
# cek heading huruf besar pendek
UPPERCASE_HEADING_PATTERN = re.compile(r"^[A-Z][A-Z0-9/&(),'\- ]+$")


def build_text_splitter(chunk_size: int = 1200, chunk_overlap: int = 150) -> RecursiveCharacterTextSplitter:
    # Buat text splitter utama sebelum embedding.
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _normalize_whitespace(value: str) -> str:
    # Rapikan whitespace berulang menjadi satu spasi.
    return " ".join(value.split())


def _normalize_heading_title(value: str) -> str:
    normalized = _normalize_whitespace(value).strip(".:").upper()
    return normalized


def _is_official_uppercase_title(value: str) -> bool:
    original = _normalize_whitespace(value).strip(".:")
    normalized = _normalize_heading_title(value)
    if normalized in OFFICIAL_UPPERCASE_TITLES and original == original.upper():
        return True
    return bool(
        original == original.upper()
        and UPPERCASE_HEADING_PATTERN.match(original)
        and len(original.split()) >= 2
    )


def _is_template_title_line(line: str) -> bool:
    return bool(TEMPLATE_TITLE_PATTERN.match(_normalize_whitespace(line)))


def _is_noise_line(line: str) -> bool:
    # Deteksi baris boilerplate berulang yang tidak perlu di-embed.
    normalized = line.strip()
    if not normalized:
        return True
    if _is_template_title_line(normalized):
        return True
    return any(pattern.match(normalized) for pattern in NOISE_LINE_PATTERNS)


def _clean_page_text(document: Document) -> str:
    # Buang header, footer, dan halaman kosong yang mengganggu chunking.
    raw_lines = [line.strip() for line in document.page_content.splitlines()]
    if not raw_lines:
        return ""
    title = _normalize_whitespace(str(document.metadata.get("title", "")).strip())
    title_without_template = title.replace("(Template)", "").strip()
    title_aliases = {title.lower(), title_without_template.lower()}
    if title.lower().startswith("sop - "):
        title_aliases.add(re.sub(r"(?i)^sop\s*-\s*", "", title).strip().lower())
        title_aliases.add(re.sub(r"(?i)^sop\s*-\s*", "", title_without_template).strip().lower())

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

    if (
        len(cleaned_lines) <= 2
        and all(len(_normalize_whitespace(line).split()) <= 4 for line in cleaned_lines)
        and not any(_looks_like_heading(line) for line in cleaned_lines)
    ):
        return ""

    if (
        len(cleaned_lines) <= 3
        and "level dokumen" in lowered_page
        and "pemilik dokumen" in lowered_page
    ):
        return ""

    return "\n".join(cleaned_lines).strip()


def _looks_like_heading(line: str) -> bool:
    # Tebak apakah sebuah baris adalah heading yang layak jadi pemisah.
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
    if DECIMAL_HEADING_PATTERN.match(normalized):
        return True

    top_level_match = TOP_LEVEL_HEADING_PATTERN.match(normalized)
    if top_level_match and _is_official_uppercase_title(top_level_match.group("title")):
        return True

    if normalized.lower() not in SKIP_PAGE_MARKERS and _is_official_uppercase_title(normalized):
        return True

    return False


def _append_segment(
    sectioned_documents: list[Document],
    document: Document,
    content_lines: list[str],
    section: str | None,
) -> None:
    # Tambahkan satu segmen bersih sambil menjaga metadata.
    content = "\n".join(content_lines).strip()
    if not content:
        return
    if section and _normalize_whitespace(content) == _normalize_whitespace(section):
        return
    if not section and document.metadata.get("document_kind") == "sop":
        return

    metadata = dict(document.metadata)
    if section:
        metadata["section"] = section
    sectioned_documents.append(Document(page_content=content, metadata=metadata))


def _is_policy_section(section: str | None) -> bool:
    normalized = (section or "").lower()
    return "ketentuan" in normalized or "kebijakan" in normalized


def _is_activity_section(section: str | None) -> bool:
    return "aktivitas" in (section or "").lower()


def _split_orphan_policy_lines(documents: list[Document]) -> list[Document]:
    # Pindahkan baris kebijakan yang terbaca out-of-order agar tidak masuk section aktivitas.
    processed: list[Document] = []
    last_policy_section_by_source: dict[str, str] = {}

    for document in documents:
        source = str(document.metadata.get("source", "unknown source"))
        section = document.metadata.get("section")
        if _is_policy_section(str(section) if section else None):
            last_policy_section_by_source[source] = str(section)

        if not _is_activity_section(str(section) if section else None):
            processed.append(document)
            continue

        kept_lines: list[str] = []
        orphan_lines: list[str] = []
        for line in document.page_content.splitlines():
            normalized = _normalize_whitespace(line)
            if ORPHAN_POLICY_LINE_PATTERN.match(normalized):
                orphan_lines.append(normalized)
            else:
                kept_lines.append(line)

        if kept_lines:
            processed.append(
                Document(page_content="\n".join(kept_lines).strip(), metadata=dict(document.metadata))
            )
        if orphan_lines:
            metadata = dict(document.metadata)
            target_section = last_policy_section_by_source.get(source)
            if target_section:
                metadata["section"] = target_section
            metadata["anomaly"] = "orphan_policy_line_relocated"
            processed.append(Document(page_content="\n".join(orphan_lines), metadata=metadata))

    return processed


def _merge_section_segments(sectioned_documents: list[Document]) -> list[Document]:
    # Gabungkan potongan section yang sama agar lanjutan halaman/tabel tetap punya konteks.
    merged: list[Document] = []
    lookup: dict[tuple[str, str, str], int] = {}

    for document in sectioned_documents:
        section = str(document.metadata.get("section") or "")
        source = str(document.metadata.get("source", "unknown source"))
        content_type = str(document.metadata.get("content_type") or "text")
        if not section:
            merged.append(document)
            continue

        key = (source, section, content_type)
        existing_index = lookup.get(key)
        if existing_index is None:
            metadata = dict(document.metadata)
            metadata.pop("page_end", None)
            lookup[key] = len(merged)
            merged.append(Document(page_content=document.page_content, metadata=metadata))
            continue

        existing = merged[existing_index]
        combined_content = f"{existing.page_content.rstrip()}\n{document.page_content.strip()}"
        metadata = dict(existing.metadata)
        page = metadata.get("page")
        next_page = document.metadata.get("page")
        if isinstance(page, int) and isinstance(next_page, int) and next_page != page:
            metadata["page_end"] = max(int(metadata.get("page_end", page)), next_page)
        if document.metadata.get("anomaly"):
            metadata["anomaly"] = document.metadata["anomaly"]
        merged[existing_index] = Document(page_content=combined_content.strip(), metadata=metadata)

    return merged


def _is_table_row(line: str) -> bool:
    normalized = _normalize_whitespace(line)
    return bool(CURRENCY_PATTERN.search(normalized) or TABLE_ROW_PATTERN.match(normalized))


def _detect_table_context(content: str) -> str:
    lines = [_normalize_whitespace(line) for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not any(pattern.search(line) for pattern in TABLE_HEADER_PATTERNS):
            continue

        context: list[str] = []
        for candidate in lines[index : index + 8]:
            if context and _is_table_row(candidate):
                break
            context.append(candidate)
        return "\n".join(context).strip()
    return ""


def _attach_table_context(documents: list[Document]) -> list[Document]:
    with_context: list[Document] = []
    for document in documents:
        metadata = dict(document.metadata)
        table_context = _detect_table_context(document.page_content)
        if table_context:
            metadata["table_context"] = table_context
        with_context.append(Document(page_content=document.page_content, metadata=metadata))
    return with_context


def _prefix_table_context(chunks: list[Document]) -> list[Document]:
    contextualized: list[Document] = []
    for chunk in chunks:
        table_context = str(chunk.metadata.get("table_context") or "").strip()
        section = str(chunk.metadata.get("section") or "").strip()
        content = chunk.page_content.strip()
        if table_context and table_context not in content:
            prefix_parts = [part for part in (section, table_context) if part]
            content = "\n".join([*prefix_parts, content])

        metadata = dict(chunk.metadata)
        metadata.pop("table_context", None)
        contextualized.append(Document(page_content=content, metadata=metadata))
    return contextualized


def split_documents_by_section(documents: list[Document]) -> list[Document]:
    """Pecah dokumen berdasarkan heading terbaik yang terdeteksi sambil menjaga metadata halaman."""
    sectioned_documents: list[Document] = []
    active_sections: dict[str, str] = {}

    for document in documents:
        if document.metadata.get("content_type") == "flowchart":
            sectioned_documents.append(document)
            continue

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

    return _split_orphan_policy_lines(sectioned_documents)


def prepare_documents_for_chunking(documents: list[Document]) -> list[Document]:
    # Tahap final sebelum text splitter: section berulang digabung dan konteks tabel disimpan.
    return _attach_table_context(_merge_section_segments(split_documents_by_section(documents)))


def chunk_documents(documents: list[Document]) -> list[Document]:
    # Pecah dokumen bersih menjadi chunk dan beri chunk ID.
    splitter = build_text_splitter()
    prepared_documents = prepare_documents_for_chunking(documents)
    flowchart_documents = [
        document
        for document in prepared_documents
        if document.metadata.get("content_type") == "flowchart"
        and document.page_content.strip()
        and document.metadata.get("anomaly")
        not in {"flowchart_low_confidence", "flowchart_incomplete_graph"}
    ]
    flowchart_keys = {
        (
            document.metadata.get("source"),
            document.metadata.get("section"),
        )
        for document in flowchart_documents
    }
    text_documents = [
        document
        for document in prepared_documents
        if document.metadata.get("content_type") != "flowchart"
        and (
            document.metadata.get("source"),
            document.metadata.get("section"),
        )
        not in flowchart_keys
    ]
    chunks = _prefix_table_context(splitter.split_documents(text_documents))
    chunks.extend(
        Document(page_content=document.page_content, metadata=dict(document.metadata))
        for document in flowchart_documents
    )

    for index, chunk in enumerate(chunks, start=1):
        chunk.metadata["chunk_id"] = index

    return chunks
