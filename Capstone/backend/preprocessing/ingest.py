from __future__ import annotations

from pathlib import Path

from backend.settings import get_env, load_capstone_env
from backend.preprocessing.chunker import chunk_documents
from backend.preprocessing.loader import load_documents
from backend.preprocessing.vectorstore import get_chroma_dir, rebuild_vectorstore

load_capstone_env()


ROOT_DIR = Path(__file__).resolve().parents[2]
CITATION_SCHEMA_MARKER = ".citation-metadata-v1"


def get_data_dir() -> Path:
    # Tentukan folder dokumen sumber untuk proses ingest.
    raw_dir = get_env("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def main() -> None:
    # Muat dokumen, pecah jadi chunk, lalu bangun ulang vector DB.
    documents = load_documents(get_data_dir())
    chunks = chunk_documents(documents)
    rebuild_vectorstore(chunks)
    (get_chroma_dir() / CITATION_SCHEMA_MARKER).write_text("1\n", encoding="ascii")

    print(f"Loaded {len(documents)} source documents.")
    print(f"Created {len(chunks)} chunks.")
    print("Vector database rebuilt successfully.")


if __name__ == "__main__":
    main()
