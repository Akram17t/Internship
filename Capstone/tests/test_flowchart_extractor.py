from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.preprocessing.chunker import chunk_documents  # noqa: E402
from backend.preprocessing.flowchart_extractor import (  # noqa: E402
    _clean_flowchart_text,
    _flowchart_max_tokens_field,
    _send_flowchart_vision_text,
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

    def test_flowchart_max_tokens_field_defaults_to_openai_compatible_field(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_flowchart_max_tokens_field(), "max_tokens")

    def test_flowchart_max_tokens_field_rejects_unknown_field(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ",
            {"FLOWCHART_MAX_TOKENS_FIELD": "tokens"},
        ):
            with self.assertRaisesRegex(RuntimeError, "max_tokens or max_completion_tokens"):
                _flowchart_max_tokens_field()

    def test_flowchart_vision_uses_router9_key_and_model(self) -> None:
        captured: dict[str, object] = {}
        captured_client: dict[str, object] = {}

        class FakeCompletions:
            def create(self, **payload: object) -> object:
                captured.update(payload)
                message = types.SimpleNamespace(
                    content=(
                        "Tahapan yang terbaca:\n1. [Start] Mulai\n\n"
                        "Hubungan dan arah alur:\n- Mulai -> Selesai"
                    )
                )
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=message)]
                )

        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=FakeCompletions())
        )

        def fake_openai_client(**kwargs: object) -> object:
            captured_client.update(kwargs)
            return fake_client

        with (
            patch.dict(
                "os.environ",
                {
                    "FLOWCHART_BASE_URL": "http://9router:20128/v1",
                    "FLOWCHART_API_KEY": "test-key",
                    "FLOWCHART_TIMEOUT_SECONDS": "240",
                },
                clear=True,
            ),
            patch.dict(
                sys.modules,
                {"openai": types.SimpleNamespace(OpenAI=fake_openai_client)},
            ),
        ):
            result = _send_flowchart_vision_text(
                b"\x89PNG\r\n\x1a\n",
                "kr/claude-sonnet-4.5",
                "Baca flowchart ini.",
            )

        self.assertEqual(captured_client["api_key"], "test-key")
        self.assertEqual(captured_client["base_url"], "http://9router:20128/v1")
        self.assertEqual(captured["model"], "kr/claude-sonnet-4.5")
        self.assertIn("Tahapan yang terbaca:", result)

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
                "extraction_method": "openai_compatible_vision",
            },
        )

        chunks = chunk_documents([native_document, flowchart_document])

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].metadata["content_type"], "flowchart")
        self.assertIn("Langkah 149", chunks[0].page_content)


if __name__ == "__main__":
    unittest.main()
