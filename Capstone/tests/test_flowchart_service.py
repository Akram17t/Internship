from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api.flowchart_service import (  # noqa: E402
    find_flowcharts_for_citations,
    get_flowchart_image,
)


class FlowchartServiceTests(unittest.TestCase):
    def _write_payload(
        self,
        directory: Path,
        *,
        graph_issues: list[str] | None = None,
    ) -> None:
        payload = {
            "status": "success",
            "source": "SOP Test.pdf",
            "image_page": 4,
            "model": "qwen3.5:9b",
            "graph_issues": graph_issues or [],
            "result": {
                "title": "Alur Test",
                "confidence": 0.95,
                "nodes": [
                    {
                        "id": "n1",
                        "type": "start",
                        "text": "Mulai",
                        "confidence": 1,
                    },
                    {
                        "id": "n2",
                        "type": "end",
                        "text": "Selesai",
                        "confidence": 1,
                    },
                ],
                "edges": [
                    {
                        "from": "n1",
                        "to": "n2",
                        "label": "",
                        "confidence": 1,
                    }
                ],
            },
        }
        (directory / "diagram-id.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_returns_diagram_for_matching_flowchart_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir)

            diagrams = find_flowcharts_for_citations(
                [
                    {
                        "source": "SOP Test.pdf",
                        "page": 5,
                        "section": "8. ALUR PROSES",
                    }
                ],
                cache_dir=cache_dir,
                model_name="qwen3.5:9b",
                display_enabled=True,
            )

        self.assertEqual(len(diagrams), 1)
        self.assertEqual(diagrams[0]["id"], "diagram-id")
        self.assertEqual(diagrams[0]["image_url"], "/api/flowcharts/diagram-id")

    def test_ignores_non_flowchart_citation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir)

            diagrams = find_flowcharts_for_citations(
                [
                    {
                        "source": "SOP Test.pdf",
                        "page": 5,
                        "section": "4. KETENTUAN",
                    }
                ],
                cache_dir=cache_dir,
                model_name="qwen3.5:9b",
                display_enabled=True,
            )

        self.assertEqual(diagrams, [])

    def test_extracts_original_flowchart_image_from_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cache_dir = root / "flowcharts"
            data_dir = root / "data"
            cache_dir.mkdir()
            data_dir.mkdir()
            flowchart_id = "a" * 64
            source_name = "SOP Test.pdf"

            image_document = fitz.open()
            image_page = image_document.new_page(width=120, height=80)
            image_page.draw_rect(
                fitz.Rect(0, 0, 120, 80),
                color=(0.8, 0.1, 0.1),
                fill=(0.8, 0.1, 0.1),
            )
            pixmap = image_page.get_pixmap()
            image_bytes = pixmap.tobytes("png")
            image_document.close()

            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_image(fitz.Rect(60, 80, 535, 700), stream=image_bytes)
            pdf.save(data_dir / source_name)
            pdf.close()

            (cache_dir / f"{flowchart_id}.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "source": source_name,
                        "image_page": 0,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "FLOWCHART_CACHE_DIR": str(cache_dir),
                    "DATA_DIR": str(data_dir),
                },
            ):
                image = get_flowchart_image(flowchart_id, allow_disabled=True)

        self.assertIsNotNone(image)
        self.assertTrue(image[0].startswith(b"\x89PNG"))
        self.assertEqual(image[1], "image/png")

    def test_ignores_payload_with_graph_anomaly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cache_dir = Path(temporary_dir)
            self._write_payload(cache_dir, graph_issues=["Node end terputus"])

            diagrams = find_flowcharts_for_citations(
                [
                    {
                        "source": "SOP Test.pdf",
                        "page": 5,
                        "section": "8. ALUR PROSES",
                    }
                ],
                cache_dir=cache_dir,
                model_name="qwen3.5:9b",
                display_enabled=True,
            )

        self.assertEqual(diagrams, [])


if __name__ == "__main__":
    unittest.main()
