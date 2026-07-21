from __future__ import annotations

import sys
import unittest
from pathlib import Path

from langchain_core.documents import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.preprocessing.chunker import chunk_documents  # noqa: E402
from backend.preprocessing.flowchart_extractor import (  # noqa: E402
    _clean_flowchart_text,
    _groq_reasoning_effort,
    detect_flowchart_candidates,
)


class FlowchartExtractorTests(unittest.TestCase):
    def test_clean_flowchart_text_removes_thinking_and_code_fence(self) -> None:
        content = _clean_flowchart_text(
            """
<think>checking the image</think>
```text
Tahapan yang terbaca:
1. [Start] Mulai

Hubungan dan arah alur:
- Mulai -> Selesai
```
"""
        )

        self.assertNotIn("<think>", content)
        self.assertNotIn("```", content)
        self.assertTrue(content.startswith("Tahapan yang terbaca:"))

    def test_groq_vision_reasoning_effort_defaults_to_supported_value(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_groq_reasoning_effort(), "default")

    def test_groq_vision_reasoning_effort_rejects_text_model_values(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ",
            {"FLOWCHART_GROQ_REASONING_EFFORT": "low"},
        ):
            with self.assertRaisesRegex(RuntimeError, "none or default"):
                _groq_reasoning_effort()

    def test_detector_supports_diagram_on_following_page(self) -> None:
        candidates = detect_flowchart_candidates(
            [
                "8. DOKUMEN TERKAIT\n9. ALUR PROSES\nDiagram berikut menggambarkan alur.",
                "STANDARD OPERATING PROCEDURE\n9 dari 9",
            ],
            [0.0, 0.25],
            min_image_area_ratio=0.08,
            max_continuation_pages=1,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].heading_page, 0)
        self.assertEqual(candidates[0].image_page, 1)
        self.assertEqual(candidates[0].section, "9. ALUR PROSES")

    def test_detector_ignores_large_images_without_flowchart_heading(self) -> None:
        candidates = detect_flowchart_candidates(
            ["1. TUJUAN", "2. RUANG LINGKUP"],
            [0.4, 0.5],
            min_image_area_ratio=0.08,
        )

        self.assertEqual(candidates, [])

    def test_flowchart_is_one_chunk_and_replaces_native_placeholder(self) -> None:
        native_document = Document(
            page_content=(
                "8. ALUR PROSES\n"
                "Diagram berikut menggambarkan alur proses kontrol akses."
            ),
            metadata={
                "source": "SOP Test.pdf",
                "page": 7,
                "document_kind": "sop",
            },
        )
        flowchart_document = Document(
            page_content=(
                "8. ALUR PROSES\nTahapan yang terbaca:\n"
                + "\n".join(f"{index}. [Process] Langkah {index}" for index in range(1, 150))
            ),
            metadata={
                "source": "SOP Test.pdf",
                "page": 8,
                "document_kind": "sop",
                "section": "8. ALUR PROSES",
                "content_type": "flowchart",
                "extraction_method": "groq_vision",
            },
        )

        chunks = chunk_documents([native_document, flowchart_document])

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["content_type"], "flowchart")
        self.assertIn("Langkah 149", chunks[0].page_content)


if __name__ == "__main__":
    unittest.main()
