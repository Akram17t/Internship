from __future__ import annotations

import logging
import statistics
from pathlib import Path

import fitz
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

from backend.preprocessing.diagram_description import NO_DIAGRAM_SENTINEL, describe_page_diagram

LOGGER = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
DIAGRAM_RENDER_DPI = 200
# A page is a diagram candidate if its extracted text is short both in absolute
# terms and relative to this document's own typical page (whichever bar is
# more permissive) -- see plan notes on why max() and not min().
DIAGRAM_ABS_FLOOR_CHARS = 250
DIAGRAM_RELATIVE_RATIO = 0.15
DIAGRAM_TRIVIAL_PAGE_CHARS = 20


def classify_document_kind(path: Path) -> str:
    if any(part.lower() == "forms" for part in path.parts) or path.stem.lower().startswith("form"):
        return "form"
    return "sop" if path.stem.lower().startswith("sop") else "document"


def _normalize_documents(documents: list[Document], source_path: Path) -> list[Document]:
    for document in documents:
        document.metadata.update(
            {
                "source": source_path.name,
                "doc_type": source_path.suffix.lower().lstrip("."),
                "document_kind": classify_document_kind(source_path),
                "title": source_path.stem,
            }
        )
        document.metadata.setdefault("page", "N/A")
        document.metadata.setdefault("content_type", "text")
    return documents


def _text_length(document: Document) -> int:
    return len(document.page_content.strip())


def _diagram_candidate_pages(pages: list[Document]) -> set[int]:
    lengths = [_text_length(page) for page in pages]
    baseline_samples = [length for length in lengths if length > DIAGRAM_TRIVIAL_PAGE_CHARS]
    if len(pages) < 2 or not baseline_samples:
        return set()

    baseline_median = statistics.median(baseline_samples)
    threshold = max(DIAGRAM_ABS_FLOOR_CHARS, DIAGRAM_RELATIVE_RATIO * baseline_median)

    return {
        page.metadata["page"]
        for page, length in zip(pages, lengths)
        if isinstance(page.metadata.get("page"), int) and length < threshold
    }


def _render_page_png(path: Path, page_index: int) -> bytes | None:
    try:
        with fitz.open(str(path)) as pdf:
            pixmap = pdf[page_index].get_pixmap(dpi=DIAGRAM_RENDER_DPI)
            return pixmap.tobytes("png")
    except Exception as error:
        LOGGER.warning("Could not render page %s of %s: %s", page_index, path, error)
        return None


def _augment_with_diagram_descriptions(documents: list[Document], path: Path) -> list[Document]:
    candidate_pages = _diagram_candidate_pages(documents)
    if not candidate_pages:
        return documents

    for document in documents:
        if document.metadata.get("page") not in candidate_pages:
            continue
        png_bytes = _render_page_png(path, document.metadata["page"])
        if png_bytes is None:
            continue
        description = describe_page_diagram(png_bytes)
        if not description or description.strip() == NO_DIAGRAM_SENTINEL:
            continue
        document.page_content = f"{document.page_content}\n\n[Deskripsi Diagram]\n{description}"
    return documents


def _load_single_document(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        documents = PyPDFLoader(str(path)).load()
        documents = _augment_with_diagram_descriptions(documents, path)
    elif suffix == ".docx":
        documents = Docx2txtLoader(str(path)).load()
    elif suffix == ".txt":
        documents = TextLoader(str(path), encoding="utf-8").load()
    else:
        return []
    return _normalize_documents(documents, path)


def load_documents(data_dir: str | Path) -> list[Document]:
    base_dir = Path(data_dir)
    if not base_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {base_dir}")

    documents: list[Document] = []
    for path in sorted(base_dir.rglob("*")):
        if not (path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS):
            continue
        if classify_document_kind(path) == "form":
            continue
        documents.extend(_load_single_document(path))

    if not documents:
        raise ValueError(f"No supported documents found in: {base_dir}")
    return documents
