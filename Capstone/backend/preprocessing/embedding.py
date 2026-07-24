from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.embeddings import Embeddings

from backend.settings import get_env, get_int_env, get_required_env, load_capstone_env

load_capstone_env()


class NscaleEmbeddings(Embeddings):
    """LangChain-compatible embeddings client for Nscale's OpenAI API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        batch_size: int = 64,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.batch_size = max(1, batch_size)
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise RuntimeError(
                    "Dependency OpenAI belum terpasang. Jalankan pip install -r requirements.txt."
                ) from error
            client = OpenAI(api_key=api_key, base_url=base_url)
        self.client = client

    def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        batch = list(texts)
        response = self.client.embeddings.create(
            model=self.model,
            input=batch,
            encoding_format="float",
        )
        return [list(item.embedding) for item in response.data]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for index in range(0, len(texts), self.batch_size):
            embeddings.extend(self._embed_batch(texts[index : index + self.batch_size]))
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]


def get_embedding_model() -> NscaleEmbeddings:
    # Buat client embedding Nscale dari konfigurasi env.
    return NscaleEmbeddings(
        api_key=get_required_env("NSCALE_SERVICE_TOKEN"),
        base_url=get_env("NSCALE_BASE_URL", "https://inference.api.nscale.com/v1"),
        model=get_env("EMBED_MODEL", "Qwen/Qwen3-Embedding-8B"),
        batch_size=get_int_env("EMBED_BATCH_SIZE", 64),
    )
