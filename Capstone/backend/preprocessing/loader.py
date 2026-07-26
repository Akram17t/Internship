from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


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


def _load_single_document(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        documents = PyPDFLoader(str(path)).load()
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
