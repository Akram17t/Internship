from __future__ import annotations

from langchain_ollama import OllamaEmbeddings

from backend.settings import get_required_env, load_capstone_env

load_capstone_env()


def get_embedding_model() -> OllamaEmbeddings:
    # Buat client embedding dari konfigurasi env.
    return OllamaEmbeddings(
        model=get_required_env("EMBED_MODEL"),
        base_url=get_required_env("OLLAMA_BASE_URL"),
    )
