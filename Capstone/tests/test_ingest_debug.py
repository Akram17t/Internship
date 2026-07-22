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


if __name__ == "__main__":
    unittest.main()
