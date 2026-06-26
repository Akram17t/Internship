from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document

from backend.preprocessing.embedding import get_embedding_model

load_dotenv()


BACKEND_DIR = Path(__file__).resolve().parent.parent


def get_chroma_dir() -> Path:
    raw_dir = os.getenv("CHROMA_DIR", "backend/chroma_db")
    path = Path(raw_dir)
    if not path.is_absolute():
        path = BACKEND_DIR.parent / path
    return path


def get_vectorstore() -> Chroma:
    return Chroma(
        persist_directory=str(get_chroma_dir()),
        embedding_function=get_embedding_model(),
    )


def rebuild_vectorstore(chunks: list[Document]) -> Chroma:
    chroma_dir = get_chroma_dir()
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    return Chroma.from_documents(
        documents=chunks,
        embedding=get_embedding_model(),
        persist_directory=str(chroma_dir),
    )


def similarity_search(query: str, k: int = 4) -> list[Document]:
    return get_vectorstore().similarity_search(query, k=k)
