from __future__ import annotations

import unittest

from backend.preprocessing.embedding import NscaleEmbeddings


class FakeEmbeddingItem:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class FakeEmbeddingResponse:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.data = [FakeEmbeddingItem(embedding) for embedding in embeddings]


class FakeEmbeddingsEndpoint:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(
        self,
        *,
        model: str,
        input: list[str],
        encoding_format: str,
    ) -> FakeEmbeddingResponse:
        self.calls.append(
            {
                "model": model,
                "input": input,
                "encoding_format": encoding_format,
            }
        )
        return FakeEmbeddingResponse(
            [[float(index), float(len(text))] for index, text in enumerate(input)]
        )


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = FakeEmbeddingsEndpoint()


class NscaleEmbeddingsTests(unittest.TestCase):
    def test_embed_query_uses_openai_compatible_float_format(self) -> None:
        client = FakeOpenAIClient()
        embeddings = NscaleEmbeddings(
            api_key="token",
            base_url="https://inference.api.nscale.com/v1",
            model="Qwen/Qwen3-Embedding-8B",
            client=client,
        )

        vector = embeddings.embed_query("The food was delicious")

        self.assertEqual(vector, [0.0, 22.0])
        self.assertEqual(
            client.embeddings.calls,
            [
                {
                    "model": "Qwen/Qwen3-Embedding-8B",
                    "input": ["The food was delicious"],
                    "encoding_format": "float",
                }
            ],
        )

    def test_embed_documents_batches_requests(self) -> None:
        client = FakeOpenAIClient()
        embeddings = NscaleEmbeddings(
            api_key="token",
            base_url="https://inference.api.nscale.com/v1",
            model="Qwen/Qwen3-Embedding-8B",
            batch_size=2,
            client=client,
        )

        vectors = embeddings.embed_documents(["alpha", "beta", "gamma"])

        self.assertEqual(vectors, [[0.0, 5.0], [1.0, 4.0], [0.0, 5.0]])
        self.assertEqual(len(client.embeddings.calls), 2)
        self.assertEqual(client.embeddings.calls[0]["input"], ["alpha", "beta"])
        self.assertEqual(client.embeddings.calls[1]["input"], ["gamma"])


if __name__ == "__main__":
    unittest.main()
