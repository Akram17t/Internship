from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings

load_dotenv()


def get_embedding_model() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=os.getenv("EMBED_MODEL", "nomic-embed-text"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
