from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

from backend.preprocessing import ingest


class IngestDebugTests(unittest.TestCase):
    def test_write_chunk_debug_uses_data_dir_sibling_debug_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir) / "data"
            output_path = Path(temporary_dir) / "debug" / "chunks.md"
            chunks = [
                Document(
                    page_content="Isi chunk untuk embedding.",
                    metadata={
                        "chunk_id": 1,
                        "source": "SOP Test.pdf",
                        "section": "1. TUJUAN",
                    },
                )
            ]

            with patch.dict(os.environ, {"DATA_DIR": str(data_dir)}):
                written_path = ingest.write_chunk_debug(chunks)

            content = output_path.read_text(encoding="utf-8")

        self.assertEqual(written_path, output_path)
        self.assertIn("# Ingest Chunk Debug", content)
        self.assertIn('"chunk_id": 1', content)
        self.assertIn('"source": "SOP Test.pdf"', content)
        self.assertIn("Isi chunk untuk embedding.", content)

    def test_main_clears_vectorstore_when_data_dir_has_no_source_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "Form - Test.docx").write_text("form only", encoding="utf-8")

            with (
                patch.dict(
                    os.environ,
                    {
                        "DATA_DIR": str(data_dir),
                        "FLOWCHART_CACHE_DIR": str(root / "flowchart-cache"),
                    },
                ),
                patch("backend.preprocessing.ingest.clear_vectorstore", return_value=3) as clear_vectorstore,
                patch("backend.preprocessing.ingest.rebuild_vectorstore") as rebuild_vectorstore,
                patch("backend.semantic_cache.reset_semantic_cache") as reset_cache,
            ):
                ingest.main()

            clear_vectorstore.assert_called_once()
            rebuild_vectorstore.assert_not_called()
            reset_cache.assert_called_once()
            debug_content = (root / "debug" / "chunks.md").read_text(encoding="utf-8")

        self.assertIn("Chunks created: 0", debug_content)

    def test_main_treats_missing_data_dir_as_empty_and_clears_vectorstore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            data_dir = Path(temporary_dir) / "missing-data"

            with (
                patch.dict(
                    os.environ,
                    {
                        "DATA_DIR": str(data_dir),
                        "FLOWCHART_CACHE_DIR": str(Path(temporary_dir) / "flowchart-cache"),
                    },
                ),
                patch("backend.preprocessing.ingest.clear_vectorstore", return_value=0) as clear_vectorstore,
                patch("backend.preprocessing.ingest.rebuild_vectorstore") as rebuild_vectorstore,
                patch("backend.semantic_cache.reset_semantic_cache") as reset_cache,
            ):
                ingest.main()

            clear_vectorstore.assert_called_once()
            rebuild_vectorstore.assert_not_called()
            reset_cache.assert_called_once()
            self.assertTrue(data_dir.exists())


if __name__ == "__main__":
    unittest.main()
