from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from backend.preprocessing.chunker import chunk_documents
from backend.preprocessing.loader import load_documents
from backend.preprocessing.vectorstore import rebuild_vectorstore

load_dotenv()


ROOT_DIR = Path(__file__).resolve().parents[2]


def get_data_dir() -> Path:
    raw_dir = os.getenv("DATA_DIR", "backend/data")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def main() -> None:
    documents = load_documents(get_data_dir())
    chunks = chunk_documents(documents)
    rebuild_vectorstore(chunks)

    print(f"Loaded {len(documents)} source documents.")
    print(f"Created {len(chunks)} chunks.")
    print("Vector database rebuilt successfully.")


if __name__ == "__main__":
    main()
