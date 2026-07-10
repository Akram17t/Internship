from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document

from backend.preprocessing.flowchart_extractor import extract_flowchart_documents


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def classify_document_kind(path: Path) -> str:
    # Klasifikasikan file sumber sebagai form, SOP, atau dokumen umum.
    # Semua dokumen kini PDF, jadi jenis ditentukan dari awalan nama file.
    name = path.stem.lower()
    if name.startswith("form"):
        return "form"
    if name.startswith("sop"):
        return "sop"
    return "document"


def _normalize_documents(documents: list[Document], source_path: Path) -> list[Document]:
    # Tambahkan metadata yang konsisten ke dokumen hasil load.
    for document in documents:
        metadata = document.metadata
        metadata["source"] = source_path.name
        metadata["doc_type"] = source_path.suffix.lower().lstrip(".")
        metadata["document_kind"] = classify_document_kind(source_path)
        metadata["title"] = source_path.stem
        metadata.setdefault("page", "N/A")
    return documents


def _load_single_document(path: Path) -> list[Document]:
    # Muat satu file yang didukung menjadi Document LangChain.
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        documents = PyPDFLoader(str(path)).load()
        documents.extend(extract_flowchart_documents(path))
    elif suffix == ".docx":
        documents = Docx2txtLoader(str(path)).load()
    elif suffix == ".txt":
        documents = TextLoader(str(path), encoding="utf-8").load()
    else:
        return []

    return _normalize_documents(documents, path)


def load_documents(data_dir: str | Path) -> list[Document]:
    # Muat semua dokumen sumber yang didukung dari folder data.
    base_dir = Path(data_dir)
    if not base_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {base_dir}")

    documents: list[Document] = []
    for path in sorted(base_dir.rglob("*")):
        if not (path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS):
            continue
        # Template form tidak ikut di-embed; hanya diunduh/diisi lewat forms service.
        if classify_document_kind(path) == "form":
            continue
        documents.extend(_load_single_document(path))

    if not documents:
        raise ValueError(f"No supported documents found in: {base_dir}")

    return documents
