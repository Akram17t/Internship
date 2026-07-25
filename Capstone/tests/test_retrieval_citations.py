from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

RESEARCHER_SRC = Path(__file__).resolve().parents[1] / "backend" / "researcher_crew" / "src"
if str(RESEARCHER_SRC) not in sys.path:
    sys.path.insert(0, str(RESEARCHER_SRC))

from researcher_crew.tools import custom_tool  # noqa: E402


class RetrievalCitationTests(unittest.TestCase):
    def test_citation_uses_pdf_viewer_page_and_range(self) -> None:
        document = Document(
            page_content="Evidence dari halaman lanjutan.",
            metadata={
                "source": "SOP Test.pdf",
                "page": 5,
                "page_end": 6,
                "section": "4.7 Uang Saku",
                "chunk_id": 42,
            },
        )

        citation = custom_tool._citation_from_document(document, 1)

        self.assertEqual(citation["page"], 6)
        self.assertEqual(citation["page_end"], 7)
        self.assertEqual(citation["chunk_id"], 42)

    def test_retrieve_deduplicates_by_page_range_and_section(self) -> None:
        documents = [
            Document(
                page_content="Konten halaman pertama section yang sama.",
                metadata={"source": "SOP Test.pdf", "page": 4, "section": "4. Kebijakan"},
            ),
            Document(
                page_content="Konten halaman kedua section yang sama.",
                metadata={"source": "SOP Test.pdf", "page": 5, "section": "4. Kebijakan"},
            ),
        ]

        with patch("researcher_crew.tools.custom_tool.hybrid_search", return_value=documents):
            evidence, citations = custom_tool.retrieve_knowledge("kebijakan", k=2)

        self.assertEqual([citation["page"] for citation in citations], [5, 6])
        self.assertIn("[1] File: SOP Test.pdf | Section: 4. Kebijakan | PDF page: 5", evidence)
        self.assertIn("[2] File: SOP Test.pdf | Section: 4. Kebijakan | PDF page: 6", evidence)


if __name__ == "__main__":
    unittest.main()
