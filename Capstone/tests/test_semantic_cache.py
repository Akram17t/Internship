from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from langchain_core.documents import Document

from backend.semantic_cache import (
    _normalize_cache_question,
    lookup_semantic_cache,
    store_semantic_cache,
)


class FakeCacheStore:
    def __init__(self, results: list[tuple[Document, float]] | None = None) -> None:
        self.results = results or []
        self.added_texts: list[str] = []
        self.searched_questions: list[str] = []

    def similarity_search_with_relevance_scores(self, question: str, k: int) -> list[tuple[Document, float]]:
        self.searched_questions.append(question)
        return self.results[:k]

    def add_texts(self, texts: list[str], metadatas: list[dict[str, str]], ids: list[str]) -> None:
        self.added_texts.extend(texts)


class SemanticCacheTests(unittest.TestCase):
    def test_question_normalization_ignores_case_and_punctuation(self) -> None:
        self.assertEqual(
            _normalize_cache_question("HRIS tuh apa sih?"),
            _normalize_cache_question("hris TUH apa sih!!!"),
        )

    def _valid_entry(self) -> dict[str, object]:
        return {
            "id": "entry-1",
            "question": "Seberapa besar uang saku dan uang makan?",
            "answer": "Nominalnya tercantum dalam SOP. [1]",
            "citations": [
                {
                    "id": 1,
                    "source": "SOP - Perjalanan Dinas.pdf",
                    "page": 6,
                    "section": "4.7 Uang Saku dan Uang Makan Harian",
                    "chunk_id": 67,
                }
            ],
            "selected_forms": [],
            "active_index": "indexes/current",
            "model_name": "ollama/qwen3:8b",
            "embed_model_name": "qwen3-embedding:4b",
            "hit_count": 0,
            "last_hit_at": None,
        }

    def test_disabled_lookup_always_misses(self) -> None:
        with patch("backend.semantic_cache._is_enabled", return_value=False):
            self.assertIsNone(lookup_semantic_cache("pertanyaan"))

    def test_lookup_misses_when_metadata_is_stale(self) -> None:
        store = FakeCacheStore(
            [(Document(page_content="cached", metadata={"entry_id": "entry-1"}), 0.98)]
        )
        stale_entry = self._valid_entry()
        stale_entry["active_index"] = "indexes/old"

        with (
            patch("backend.semantic_cache.get_semantic_cache_entry_by_question", return_value=None),
            patch("backend.semantic_cache._get_cache_store", return_value=store),
            patch("backend.semantic_cache.get_semantic_cache_entry", return_value=stale_entry),
            patch("backend.semantic_cache.get_active_index_name", return_value="indexes/current"),
            patch("backend.semantic_cache._model_name", return_value="ollama/qwen3:8b"),
            patch("backend.semantic_cache._embed_model_name", return_value="qwen3-embedding:4b"),
            patch("backend.semantic_cache._threshold", return_value=0.92),
        ):
            self.assertIsNone(lookup_semantic_cache("pertanyaan"))

    def test_lookup_misses_when_model_differs(self) -> None:
        store = FakeCacheStore(
            [(Document(page_content="cached", metadata={"entry_id": "entry-1"}), 0.98)]
        )
        stale_entry = self._valid_entry()
        stale_entry["model_name"] = "ollama/old-model"

        with (
            patch("backend.semantic_cache.get_semantic_cache_entry_by_question", return_value=None),
            patch("backend.semantic_cache._get_cache_store", return_value=store),
            patch("backend.semantic_cache.get_semantic_cache_entry", return_value=stale_entry),
            patch("backend.semantic_cache.get_active_index_name", return_value="indexes/current"),
            patch("backend.semantic_cache._model_name", return_value="ollama/qwen3:8b"),
            patch("backend.semantic_cache._embed_model_name", return_value="qwen3-embedding:4b"),
            patch("backend.semantic_cache._threshold", return_value=0.92),
        ):
            self.assertIsNone(lookup_semantic_cache("pertanyaan"))

    def test_lookup_misses_when_citations_are_empty(self) -> None:
        store = FakeCacheStore(
            [(Document(page_content="cached", metadata={"entry_id": "entry-1"}), 0.98)]
        )
        entry = self._valid_entry()
        entry["citations"] = []

        with (
            patch("backend.semantic_cache.get_semantic_cache_entry_by_question", return_value=None),
            patch("backend.semantic_cache._get_cache_store", return_value=store),
            patch("backend.semantic_cache.get_semantic_cache_entry", return_value=entry),
            patch("backend.semantic_cache.get_active_index_name", return_value="indexes/current"),
            patch("backend.semantic_cache._model_name", return_value="ollama/qwen3:8b"),
            patch("backend.semantic_cache._embed_model_name", return_value="qwen3-embedding:4b"),
            patch("backend.semantic_cache._threshold", return_value=0.92),
        ):
            self.assertIsNone(lookup_semantic_cache("pertanyaan"))

    def test_lookup_hits_and_updates_hit_count(self) -> None:
        store = FakeCacheStore(
            [(Document(page_content="cached", metadata={"entry_id": "entry-1"}), 0.96)]
        )
        mark_hit = Mock()

        with (
            patch("backend.semantic_cache.get_semantic_cache_entry_by_question", return_value=None),
            patch("backend.semantic_cache._get_cache_store", return_value=store),
            patch("backend.semantic_cache.get_semantic_cache_entry", return_value=self._valid_entry()),
            patch("backend.semantic_cache.get_active_index_name", return_value="indexes/current"),
            patch("backend.semantic_cache._model_name", return_value="ollama/qwen3:8b"),
            patch("backend.semantic_cache._embed_model_name", return_value="qwen3-embedding:4b"),
            patch("backend.semantic_cache._threshold", return_value=0.92),
            patch("backend.semantic_cache.mark_semantic_cache_hit", mark_hit),
        ):
            hit = lookup_semantic_cache("Nominal uang makan dan uang saku berapa?")

        self.assertIsNotNone(hit)
        self.assertEqual(hit.entry_id, "entry-1")
        self.assertEqual(hit.citations[0]["source"], "SOP - Perjalanan Dinas.pdf")
        mark_hit.assert_called_once_with("entry-1")
        self.assertEqual(
            store.searched_questions,
            ["nominal uang makan dan uang saku berapa"],
        )

    def test_exact_normalized_hit_skips_vector_lookup(self) -> None:
        exact_entry = self._valid_entry()
        cache_store = Mock()
        mark_hit = Mock()

        with (
            patch(
                "backend.semantic_cache.get_semantic_cache_entry_by_question",
                return_value=exact_entry,
            ),
            patch("backend.semantic_cache._get_cache_store", cache_store),
            patch("backend.semantic_cache.get_active_index_name", return_value="indexes/current"),
            patch("backend.semantic_cache._model_name", return_value="ollama/qwen3:8b"),
            patch("backend.semantic_cache._embed_model_name", return_value="qwen3-embedding:4b"),
            patch("backend.semantic_cache.mark_semantic_cache_hit", mark_hit),
        ):
            hit = lookup_semantic_cache("HRIS tuh apa sih?")

        self.assertIsNotNone(hit)
        self.assertEqual(hit.similarity, 1.0)
        cache_store.assert_not_called()
        mark_hit.assert_called_once_with("entry-1")

    def test_store_skips_uncacheable_answers(self) -> None:
        with patch("backend.semantic_cache._get_cache_store") as cache_store:
            result = store_semantic_cache(
                "pertanyaan",
                "Sistem tidak dapat menemukan informasi terkait hal tersebut di dalam dokumen SOP.",
                [],
                [],
            )

        self.assertIsNone(result)
        cache_store.assert_not_called()

    def test_store_persists_cacheable_answer(self) -> None:
        store = FakeCacheStore()
        insert_entry = Mock()

        with (
            patch("backend.semantic_cache._get_cache_store", return_value=store),
            patch("backend.semantic_cache.insert_semantic_cache_entry", insert_entry),
            patch("backend.semantic_cache.get_active_index_name", return_value="indexes/current"),
            patch("backend.semantic_cache._model_name", return_value="ollama/qwen3:8b"),
            patch("backend.semantic_cache._embed_model_name", return_value="qwen3-embedding:4b"),
        ):
            entry_id = store_semantic_cache(
                "Seberapa besar uang saku dan uang makan?",
                "Nominalnya tercantum dalam SOP. [1]",
                self._valid_entry()["citations"],
                [],
            )

        self.assertIsNotNone(entry_id)
        self.assertEqual(
            store.added_texts,
            ["seberapa besar uang saku dan uang makan"],
        )
        insert_entry.assert_called_once()


if __name__ == "__main__":
    unittest.main()
