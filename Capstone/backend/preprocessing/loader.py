from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _normalize_documents(documents: list[Document], source_path: Path) -> list[Document]:
    for document in documents:
        metadata = document.metadata
        metadata["source"] = source_path.name
        metadata["doc_type"] = source_path.suffix.lower().lstrip(".")
        metadata.setdefault("page", "N/A")
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
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            documents.extend(_load_single_document(path))

    if not documents:
        raise ValueError(f"No supported documents found in: {base_dir}")

    return documents
